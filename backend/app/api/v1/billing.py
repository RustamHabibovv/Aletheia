"""Stripe billing endpoints — checkout, webhook, subscription status, customer portal."""

import logging
from datetime import UTC, datetime

import stripe
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import CurrentUser, DBSession
from app.core.config import get_settings
from app.models import Subscription, SubscriptionStatus, UsageRecord, User, UserTier

FREE_DAILY_FACTCHECK_LIMIT = 5

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# ── Schemas ──────────────────────────────────────────────────────────


class CheckoutRequest(BaseModel):
    plan: str  # "monthly" | "yearly"
    plan_tier: str = "PRO"  # "PRO" | "BUSINESS"


class ChangePlanRequest(BaseModel):
    plan_tier: str  # "PRO" | "BUSINESS"
    billing: str = "monthly"  # "monthly" | "yearly"


class ChangePlanResponse(BaseModel):
    status: str  # "upgraded" | "scheduled" | "no_change"
    current_plan_tier: str
    pending_plan_tier: str | None = None
    pending_change_at: str | None = None


class SubscriptionResponse(BaseModel):
    status: str
    plan: str
    plan_tier: str = "PRO"  # "PRO" | "BUSINESS" — derived from current Stripe price
    current_period_end: str | None = None
    cancel_at_period_end: bool = False
    pending_plan_tier: str | None = None
    pending_change_at: str | None = None


class CancelResponse(BaseModel):
    cancel_at_period_end: bool
    current_period_end: str | None


# ── Plan ranking ─────────────────────────────────────────────────────

PLAN_RANK = {"FREE": 0, "PRO": 1, "BUSINESS": 2}


def _price_to_plan_tier(price_id: str, settings) -> str:
    """Map a Stripe price ID to its plan tier. Defaults to PRO."""
    business_ids = {settings.stripe_price_business_monthly, settings.stripe_price_business_yearly}
    business_ids.discard("")
    if price_id in business_ids:
        return "BUSINESS"
    return "PRO"


def _resolve_price_id(plan_tier: str, billing: str, settings) -> str:
    """Resolve a (plan_tier, billing) pair to a configured Stripe price ID.

    Business falls back to Pro's price IDs when its own aren't configured —
    Business is a UI-only entity for now (display says $49.99 but Stripe
    charges Pro's actual price). The `plan_tier` metadata on the
    subscription still distinguishes the two so the UI shows the right card.
    """
    if plan_tier == "BUSINESS":
        monthly = settings.stripe_price_business_monthly or settings.stripe_price_pro_monthly
        yearly = settings.stripe_price_business_yearly or settings.stripe_price_pro_yearly
    else:
        monthly = settings.stripe_price_pro_monthly
        yearly = settings.stripe_price_pro_yearly
    return monthly if billing == "monthly" else yearly


class UsageResponse(BaseModel):
    used: int
    limit: int | None  # None = unlimited (PRO)
    remaining: int | None


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/checkout")
async def create_checkout_session(
    body: CheckoutRequest,
    user: CurrentUser,
    session: DBSession,
) -> dict:
    """Create a Stripe Checkout Session and return the redirect URL."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe not configured")

    stripe.api_key = settings.stripe_secret_key

    # Block double-subscription: only one active sub per user
    existing_active = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
    )
    if existing_active.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an active subscription. Cancel it first to start a new one.",
        )

    plan_tier = body.plan_tier.upper() if body.plan_tier else "PRO"
    if plan_tier not in ("PRO", "BUSINESS"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown plan_tier '{body.plan_tier}'")

    price_id = _resolve_price_id(plan_tier, body.plan, settings)
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Stripe price for {plan_tier} {body.plan} is not configured. "
                f"Set STRIPE_PRICE_{plan_tier}_{body.plan.upper()} in .env."
            ),
        )

    # Retrieve or create a Stripe customer
    customer_id = user.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(email=user.email, name=user.name or user.email)
        customer_id = customer.id
        user.stripe_customer_id = customer_id
        session.add(user)
        await session.commit()

    checkout = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        # Tag the subscription so we can identify the plan tier later without
        # cross-referencing price IDs (useful if prices are rotated).
        subscription_data={"metadata": {"plan_tier": plan_tier}},
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
    )
    return {"url": checkout.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: DBSession) -> dict:
    """Handle Stripe webhook events."""
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    import json as _json

    if not settings.debug:
        try:
            stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
        except stripe.SignatureVerificationError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature",
            ) from err

    # Always parse payload as plain Python dict — StripeObject.get() is broken
    event_dict = _json.loads(payload)
    event_type: str = event_dict["type"]
    data: dict = event_dict["data"]["object"]

    logger.info("Stripe webhook received: %s", event_type)

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data, db)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data, db)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data, db)

    return {"received": True}


@router.get("/subscription", response_model=SubscriptionResponse | None)
async def get_subscription(user: CurrentUser, db: DBSession) -> SubscriptionResponse | None:
    """Return the active subscription for the current user, or null."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id, Subscription.status == SubscriptionStatus.ACTIVE)
        .order_by(Subscription.created_at.desc())
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return None

    # Pull live state from Stripe — we don't persist plan_tier / cancel /
    # pending change locally, so this keeps the UI accurate after reload.
    cancel_pending = False
    plan_tier = "PRO"
    pending_plan_tier: str | None = None
    pending_change_at: str | None = None

    settings = get_settings()
    if settings.stripe_secret_key and sub.stripe_subscription_id:
        try:
            import json as _json

            stripe.api_key = settings.stripe_secret_key
            stripe_sub = _json.loads(str(stripe.Subscription.retrieve(sub.stripe_subscription_id)))
            cancel_pending = bool(stripe_sub.get("cancel_at_period_end"))

            # Current plan_tier: prefer subscription metadata; fall back to price ID match.
            md = stripe_sub.get("metadata", {}) or {}
            md_tier = (md.get("plan_tier") or "").upper()
            if md_tier in ("PRO", "BUSINESS"):
                plan_tier = md_tier
            else:
                items = stripe_sub.get("items", {}).get("data", [])
                price_id = items[0].get("price", {}).get("id", "") if items else ""
                plan_tier = _price_to_plan_tier(price_id, settings)

            # Pending downgrade scheduled by /billing/change-plan.
            if md.get("pending_plan_tier"):
                pending_ts_raw = md.get("pending_change_at") or ""
                try:
                    pending_ts = int(pending_ts_raw)
                except ValueError:
                    pending_ts = 0
                now_ts = int(datetime.now(tz=UTC).timestamp())
                if pending_ts > now_ts:
                    pending_plan_tier = md["pending_plan_tier"].upper()
                    pending_change_at = datetime.fromtimestamp(pending_ts, tz=UTC).isoformat()
        except Exception:
            logger.exception("Failed to fetch live state from Stripe for sub %s", sub.stripe_subscription_id)

    return SubscriptionResponse(
        status=sub.status.value,
        plan=sub.plan.value,
        plan_tier=plan_tier,
        current_period_end=sub.current_period_end.isoformat() if sub.current_period_end else None,
        cancel_at_period_end=cancel_pending,
        pending_plan_tier=pending_plan_tier,
        pending_change_at=pending_change_at,
    )


@router.get("/usage", response_model=UsageResponse)
async def get_usage(user: CurrentUser, db: DBSession) -> UsageResponse:
    """Return today's fact-check usage for the current user."""
    if user.tier != UserTier.FREE:
        return UsageResponse(used=0, limit=None, remaining=None)

    today = datetime.now(tz=UTC).date()
    today_start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    result = await db.execute(
        select(UsageRecord).where(
            UsageRecord.user_id == user.id,
            UsageRecord.date == today_start,
        )
    )
    record = result.scalar_one_or_none()
    used = record.request_count if record else 0
    return UsageResponse(
        used=used,
        limit=FREE_DAILY_FACTCHECK_LIMIT,
        remaining=max(0, FREE_DAILY_FACTCHECK_LIMIT - used),
    )


@router.post("/sync")
async def sync_subscription(user: CurrentUser, db: DBSession) -> dict:
    """Pull the current subscription state from Stripe and persist it.

    Used as a fallback after returning from Stripe Checkout when the local
    webhook listener (`stripe listen`) isn't running, so checkout.session
    events never arrive. Idempotent — safe to call repeatedly.
    """
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe not configured")
    if not user.stripe_customer_id:
        return {"synced": False, "tier": user.tier.value}

    stripe.api_key = settings.stripe_secret_key

    import json as _json

    subs_resp = stripe.Subscription.list(customer=user.stripe_customer_id, status="all", limit=10)
    subs: list[dict] = _json.loads(str(subs_resp)).get("data", [])

    # Prefer an active sub; otherwise the most recently created one
    active = next((s for s in subs if s.get("status") == "active"), None)
    chosen = active or (subs[0] if subs else None)

    if chosen is None:
        return {"synced": False, "tier": user.tier.value}

    stripe_sub_id = chosen.get("id", "")
    raw_status = chosen.get("status", "")
    period_start = chosen.get("current_period_start")
    period_end = chosen.get("current_period_end")

    # Map Stripe status → local
    if raw_status == "active":
        local_status = SubscriptionStatus.ACTIVE
        local_tier = UserTier.PRO
    elif raw_status in ("canceled", "cancelled"):
        local_status = SubscriptionStatus.CANCELLED
        local_tier = UserTier.FREE
    elif raw_status == "past_due":
        local_status = SubscriptionStatus.PAST_DUE
        local_tier = UserTier.PRO  # still treat as paid until cancelled
    else:
        # incomplete / trialing / etc — don't grant access
        local_status = SubscriptionStatus.PAST_DUE
        local_tier = UserTier.FREE

    existing = await db.execute(select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id))
    sub = existing.scalar_one_or_none()
    if sub is None:
        sub = Subscription(
            user_id=user.id,
            stripe_subscription_id=stripe_sub_id,
            plan=UserTier.PRO,
            status=local_status,
            current_period_start=datetime.fromtimestamp(period_start, tz=UTC) if period_start else None,
            current_period_end=datetime.fromtimestamp(period_end, tz=UTC) if period_end else None,
        )
    else:
        sub.status = local_status
        if period_start:
            sub.current_period_start = datetime.fromtimestamp(period_start, tz=UTC)
        if period_end:
            sub.current_period_end = datetime.fromtimestamp(period_end, tz=UTC)

    user.tier = local_tier
    db.add(sub)
    db.add(user)
    await db.commit()

    return {"synced": True, "tier": user.tier.value}


@router.post("/change-plan", response_model=ChangePlanResponse)
async def change_plan(
    body: ChangePlanRequest,
    user: CurrentUser,
    db: DBSession,
) -> ChangePlanResponse:
    """Switch the user's active subscription to a different plan tier.

    Rules (per product spec):
      - Same plan target → no-op (400)
      - Better plan (e.g. PRO → BUSINESS) → replace immediately, charge prorated
        difference now via `Subscription.modify(proration_behavior="always_invoice")`.
      - Worse plan (e.g. BUSINESS → PRO) → schedule the change at the current
        period_end via Stripe SubscriptionSchedule. The user keeps the current
        plan (and is billed at the current rate) until then.

    Requires the user to already have an active subscription. Use
    `/billing/checkout` for FREE → paid transitions.
    """
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe not configured")

    target_tier = body.plan_tier.upper()
    if target_tier not in ("PRO", "BUSINESS"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown plan_tier '{body.plan_tier}'")

    new_price_id = _resolve_price_id(target_tier, body.billing, settings)
    if not new_price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Stripe price for {target_tier} {body.billing} is not configured.",
        )

    sub_q = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id, Subscription.status == SubscriptionStatus.ACTIVE)
        .order_by(Subscription.created_at.desc())
    )
    sub = sub_q.scalar_one_or_none()
    if sub is None or not sub.stripe_subscription_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription to change")

    stripe.api_key = settings.stripe_secret_key

    import json as _json

    stripe_sub = _json.loads(str(stripe.Subscription.retrieve(sub.stripe_subscription_id)))
    items = stripe_sub.get("items", {}).get("data", [])
    if not items:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe subscription has no items",
        )
    item_id = items[0]["id"]
    current_price_id = items[0].get("price", {}).get("id", "")

    md = stripe_sub.get("metadata", {}) or {}
    current_tier = (md.get("plan_tier") or "").upper()
    if current_tier not in ("PRO", "BUSINESS"):
        current_tier = _price_to_plan_tier(current_price_id, settings)

    if PLAN_RANK[target_tier] == PLAN_RANK[current_tier]:
        return ChangePlanResponse(status="no_change", current_plan_tier=current_tier)

    # ── Upgrade: replace now, charge proration immediately ──
    if PLAN_RANK[target_tier] > PLAN_RANK[current_tier]:
        try:
            stripe.Subscription.modify(
                sub.stripe_subscription_id,
                items=[{"id": item_id, "price": new_price_id}],
                proration_behavior="always_invoice",
                payment_behavior="error_if_incomplete",
                metadata={"plan_tier": target_tier},
            )
        except stripe.CardError as exc:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Payment failed: {exc.user_message or 'Card was declined'}",
            ) from exc
        except stripe.StripeError as exc:
            logger.exception("Stripe upgrade failed for sub %s", sub.stripe_subscription_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not upgrade subscription: {exc.user_message or str(exc)}",
            ) from exc

        return ChangePlanResponse(status="upgraded", current_plan_tier=target_tier)

    # ── Downgrade: schedule the swap at period_end via SubscriptionSchedule ──
    period_start = stripe_sub.get("current_period_start")
    period_end = stripe_sub.get("current_period_end")
    if not period_start or not period_end:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cannot schedule downgrade — subscription is missing period boundaries",
        )

    # Reuse an existing schedule attached to this sub (Stripe only allows one).
    existing_schedule_id = stripe_sub.get("schedule")
    if existing_schedule_id:
        schedule_id = existing_schedule_id
    else:
        schedule = stripe.SubscriptionSchedule.create(from_subscription=sub.stripe_subscription_id)
        schedule_id = _json.loads(str(schedule))["id"]

    try:
        stripe.SubscriptionSchedule.modify(
            schedule_id,
            phases=[
                {
                    "items": [{"price": current_price_id, "quantity": 1}],
                    "start_date": period_start,
                    "end_date": period_end,
                    "proration_behavior": "none",
                },
                {
                    "items": [{"price": new_price_id, "quantity": 1}],
                    "iterations": 1,
                    "proration_behavior": "none",
                },
            ],
            end_behavior="release",
        )
    except stripe.StripeError as exc:
        logger.exception("Stripe schedule modify failed for sub %s", sub.stripe_subscription_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not schedule downgrade: {exc.user_message or str(exc)}",
        ) from exc

    # Tag the subscription so the UI can show "switching to X on …" without
    # re-querying the schedule.
    stripe.Subscription.modify(
        sub.stripe_subscription_id,
        metadata={
            "plan_tier": current_tier,
            "pending_plan_tier": target_tier,
            "pending_change_at": str(period_end),
        },
    )

    return ChangePlanResponse(
        status="scheduled",
        current_plan_tier=current_tier,
        pending_plan_tier=target_tier,
        pending_change_at=datetime.fromtimestamp(period_end, tz=UTC).isoformat(),
    )


@router.post("/cancel", response_model=CancelResponse)
async def cancel_subscription(user: CurrentUser, db: DBSession) -> CancelResponse:
    """Schedule the user's active subscription to end at the current period end.

    The user keeps paid features until period_end; the
    `customer.subscription.deleted` webhook (or /billing/sync) flips them to
    FREE when Stripe finalizes the cancellation. This implements the
    "downgrade to Free at period end" rule without requiring the user to
    visit Stripe's customer portal.
    """
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe not configured")

    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id, Subscription.status == SubscriptionStatus.ACTIVE)
        .order_by(Subscription.created_at.desc())
    )
    sub = result.scalar_one_or_none()
    if sub is None or not sub.stripe_subscription_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription to cancel")

    stripe.api_key = settings.stripe_secret_key

    import json as _json

    updated = stripe.Subscription.modify(sub.stripe_subscription_id, cancel_at_period_end=True)
    updated_dict: dict = _json.loads(str(updated))
    period_end = updated_dict.get("current_period_end")
    period_end_iso = datetime.fromtimestamp(period_end, tz=UTC).isoformat() if period_end else None

    return CancelResponse(
        cancel_at_period_end=bool(updated_dict.get("cancel_at_period_end")),
        current_period_end=period_end_iso,
    )


@router.post("/portal")
async def create_portal_session(user: CurrentUser) -> dict:
    """Create a Stripe Customer Portal session so the user can manage their subscription."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe not configured")
    if not user.stripe_customer_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No billing account found")

    stripe.api_key = settings.stripe_secret_key
    portal = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=settings.stripe_cancel_url,
    )
    return {"url": portal.url}


# ── Webhook helpers ──────────────────────────────────────────────────


async def _handle_checkout_completed(data: dict, db: DBSession) -> None:
    stripe_sub_id: str = data.get("subscription", "")
    customer_id: str = data.get("customer", "")
    logger.info("checkout.session.completed: customer=%s subscription=%s", customer_id, stripe_sub_id)
    if not stripe_sub_id or not customer_id:
        logger.warning("Missing subscription or customer in checkout.session.completed")
        return

    # Fetch the full subscription — convert to plain dict immediately to avoid StripeObject.get() issues
    import json as _json

    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key
    stripe_sub_obj = stripe.Subscription.retrieve(stripe_sub_id)
    stripe_sub: dict = _json.loads(str(stripe_sub_obj))

    plan = UserTier.PRO  # all paid plans map to PRO

    # Find user by stripe_customer_id
    result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
    user = result.scalar_one_or_none()
    if user is None:
        logger.warning("Webhook: no user found for Stripe customer %s", customer_id)
        return

    # Upsert subscription record
    existing_result = await db.execute(select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id))
    sub = existing_result.scalar_one_or_none()
    if sub is None:
        sub = Subscription(
            user_id=user.id,
            stripe_subscription_id=stripe_sub_id,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=datetime.fromtimestamp(stripe_sub.get("current_period_start", 0), tz=UTC),
            current_period_end=datetime.fromtimestamp(stripe_sub.get("current_period_end", 0), tz=UTC),
        )
    else:
        sub.status = SubscriptionStatus.ACTIVE

    user.tier = plan
    db.add(sub)
    db.add(user)
    await db.commit()


async def _handle_subscription_updated(data: dict, db: DBSession) -> None:
    stripe_sub_id: str = data.get("id", "")
    result = await db.execute(select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id))
    sub = result.scalar_one_or_none()
    if sub is None:
        return

    raw_status = data.get("status", "")
    if raw_status == "active":
        sub.status = SubscriptionStatus.ACTIVE
    elif raw_status in ("canceled", "cancelled"):
        sub.status = SubscriptionStatus.CANCELLED
    elif raw_status == "past_due":
        sub.status = SubscriptionStatus.PAST_DUE

    period_end = data.get("current_period_end")
    if period_end:
        sub.current_period_end = datetime.fromtimestamp(period_end, tz=UTC)

    db.add(sub)
    await db.commit()


async def _handle_subscription_deleted(data: dict, db: DBSession) -> None:
    stripe_sub_id: str = data.get("id", "")
    result = await db.execute(select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id))
    sub = result.scalar_one_or_none()
    if sub is None:
        return

    sub.status = SubscriptionStatus.CANCELLED
    db.add(sub)

    # Downgrade user tier
    user_result = await db.execute(select(User).where(User.id == sub.user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.tier = UserTier.FREE
        db.add(user)

    await db.commit()
