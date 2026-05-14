"use client";

import { useState } from "react";
import { CheckCircle2Icon, XIcon, ZapIcon, ShieldCheckIcon, BuildingIcon } from "lucide-react";
import { createCheckoutSession, createPortalSession, cancelSubscription, changePlan } from "@/lib/api";

type PaidPlan = "PRO" | "BUSINESS";

interface PlanChangeNotice {
  status: "upgraded" | "scheduled";
  planTier: PaidPlan;
  pendingPlanTier?: PaidPlan | null;
  pendingChangeAt?: string | null;
}

interface Props {
  onClose: () => void;
  currentPlan?: string; // "FREE" | "PRO" | "BUSINESS"
  pendingCancelAt?: string | null;
  pendingPlanTier?: PaidPlan | null;
  pendingChangeAt?: string | null;
  onPlanChanged?: (notice: PlanChangeNotice) => void;
  onCanceled?: (periodEndIso: string | null) => void;
}

type LoadingButton = "pro" | "business" | "manage" | "cancel" | "switch" | null;

// Yearly is monthly × 12 × 0.9 (10% off).
const PRO_MONTHLY_PRICE = "$14.99";
const PRO_YEARLY_PRICE = "$161.89";
const PRO_YEARLY_MONTHLY = "$13.49";

const BUSINESS_MONTHLY_PRICE = "$49.99";
const BUSINESS_YEARLY_PRICE = "$539.89";
const BUSINESS_YEARLY_MONTHLY = "$44.99";

const FREE_FEATURES = [
  "5 analyses per day",
  "Fact-checking",
  "Text detection",
  "Basic chat history",
];

const PRO_FEATURES = [
  "Unlimited analyses",
  "Priority processing",
  "Full source list per analysis",
  "API access (coming soon)",
];

const BUSINESS_FEATURES = [
  "Everything in Pro",
  "Team management (coming soon)",
  "Custom integrations (coming soon)",
  "Priority support",
  "Advanced analytics (coming soon)",
  "SLA guarantee (coming soon)",
];

function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function PricingModal({
  onClose,
  currentPlan = "FREE",
  pendingCancelAt = null,
  pendingPlanTier = null,
  pendingChangeAt = null,
  onPlanChanged,
  onCanceled,
}: Props) {
  const [billing, setBilling] = useState<"monthly" | "yearly">("yearly");
  const [loading, setLoading] = useState<LoadingButton>(null);
  const [error, setError] = useState<string | null>(null);
  const [localCancelAt, setLocalCancelAt] = useState<string | null>(pendingCancelAt);
  const [localPendingPlan, setLocalPendingPlan] = useState<PaidPlan | null>(pendingPlanTier);
  const [localPendingChangeAt, setLocalPendingChangeAt] = useState<string | null>(pendingChangeAt);
  const isLoading = loading !== null;
  const isPaid = currentPlan === "PRO" || currentPlan === "BUSINESS";
  const cancelEndsAt = localCancelAt ?? pendingCancelAt;
  const cancelEndsAtLabel = formatDate(cancelEndsAt);
  const pendingPlan = localPendingPlan ?? pendingPlanTier;
  const pendingPlanAtLabel = formatDate(localPendingChangeAt ?? pendingChangeAt);

  async function handleUpgrade(planTier: PaidPlan) {
    setLoading(planTier === "PRO" ? "pro" : "business");
    setError(null);
    try {
      const { url } = await createCheckoutSession(billing, planTier);
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      setLoading(null);
    }
  }

  async function handleManage() {
    setLoading("manage");
    setError(null);
    try {
      const { url } = await createPortalSession();
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      setLoading(null);
    }
  }

  async function handleCancel() {
    setLoading("cancel");
    setError(null);
    try {
      const res = await cancelSubscription();
      setLocalCancelAt(res.current_period_end);
      onCanceled?.(res.current_period_end);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel. Please try again.");
    } finally {
      setLoading(null);
    }
  }

  async function handleSwitch(planTier: PaidPlan) {
    setLoading("switch");
    setError(null);
    try {
      const res = await changePlan(planTier, billing);
      if (res.status === "scheduled") {
        setLocalPendingPlan(res.pending_plan_tier);
        setLocalPendingChangeAt(res.pending_change_at);
        onPlanChanged?.({
          status: "scheduled",
          planTier: res.current_plan_tier,
          pendingPlanTier: res.pending_plan_tier,
          pendingChangeAt: res.pending_change_at,
        });
      } else if (res.status === "upgraded") {
        setLocalPendingPlan(null);
        setLocalPendingChangeAt(null);
        onPlanChanged?.({ status: "upgraded", planTier: res.current_plan_tier });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't switch plan. Please try again.");
    } finally {
      setLoading(null);
    }
  }

  // Resolve button content per plan card based on currentPlan + cancel state.
  type CardAction =
    | { kind: "current" }
    | { kind: "upgrade"; plan: PaidPlan }
    | { kind: "switch"; plan: PaidPlan }
    | { kind: "cancel" }
    | { kind: "none" };

  function freeAction(): CardAction {
    if (!isPaid) return { kind: "current" };
    if (cancelEndsAt) return { kind: "none" };
    return { kind: "cancel" };
  }

  function paidAction(plan: PaidPlan): CardAction {
    if (currentPlan === plan) return { kind: "current" };
    if (isPaid) return { kind: "switch", plan };
    return { kind: "upgrade", plan };
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 16,
          width: "100%",
          maxWidth: 940,
          maxHeight: "90vh",
          overflowY: "auto",
          position: "relative",
        }}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          style={{
            position: "absolute",
            top: 14,
            right: 14,
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text-secondary)",
            padding: 4,
            borderRadius: 6,
            display: "flex",
          }}
        >
          <XIcon size={18} />
        </button>

        {/* Header */}
        <div style={{ padding: "28px 28px 0", textAlign: "center" }}>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: "var(--text-primary)" }}>
            Choose your plan
          </h2>
          <p style={{ margin: "6px 0 20px", color: "var(--text-secondary)", fontSize: 14 }}>
            Upgrade to Pro for unlimited access and advanced features.
          </p>

          {/* Cancellation banner */}
          {cancelEndsAtLabel && (
            <div
              style={{
                margin: "0 0 16px",
                padding: "10px 14px",
                borderRadius: 10,
                background: "rgba(245,158,11,0.1)",
                border: "1px solid rgba(245,158,11,0.35)",
                color: "#f59e0b",
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              Your subscription is set to end on {cancelEndsAtLabel}. You&apos;ll be moved to Free
              after that date.
            </div>
          )}

          {/* Pending plan-change banner (scheduled downgrade) */}
          {pendingPlan && pendingPlanAtLabel && !cancelEndsAtLabel && (
            <div
              style={{
                margin: "0 0 16px",
                padding: "10px 14px",
                borderRadius: 10,
                background: "rgba(14,165,233,0.1)",
                border: "1px solid rgba(14,165,233,0.35)",
                color: "#0ea5e9",
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              Switching to {pendingPlan === "PRO" ? "Pro" : "Business"} on {pendingPlanAtLabel}.
              You&apos;ll keep your current plan until then.
            </div>
          )}

          {/* Billing toggle */}
          <div style={{ display: "inline-flex", background: "var(--surface-2)", borderRadius: 8, padding: 3, border: "1px solid var(--border)" }}>
            {(["monthly", "yearly"] as const).map((b) => (
              <button
                key={b}
                onClick={() => setBilling(b)}
                style={{
                  padding: "6px 16px",
                  borderRadius: 6,
                  border: "none",
                  cursor: "pointer",
                  fontSize: 13,
                  fontWeight: 600,
                  background: billing === b ? "#6366f1" : "transparent",
                  color: billing === b ? "#fff" : "var(--text-secondary)",
                  transition: "all 0.15s",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                {b === "yearly" ? "Yearly" : "Monthly"}
                {b === "yearly" && (
                  <span style={{
                    fontSize: 10,
                    padding: "1px 6px",
                    borderRadius: 4,
                    background: billing === "yearly" ? "rgba(255,255,255,0.2)" : "rgba(99,102,241,0.15)",
                    color: billing === "yearly" ? "#fff" : "#6366f1",
                    fontWeight: 700,
                  }}>
                    SAVE 10%
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Plan cards */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, padding: 28 }}>
          {/* Free card */}
          <PlanCard
            accent="var(--text-secondary)"
            border="1px solid var(--border)"
            background="var(--surface-2)"
            iconNode={<ShieldCheckIcon size={18} style={{ color: "var(--text-secondary)" }} />}
            title="Free"
            isCurrent={currentPlan === "FREE"}
            currentBadgeBg="rgba(139,143,168,0.15)"
            currentBadgeColor="var(--text-secondary)"
            priceMain="$0"
            priceSuffix=" / month"
            featureColor="var(--text-secondary)"
            features={FREE_FEATURES}
            action={freeAction()}
            loading={loading}
            isLoading={isLoading}
            handlers={{ handleUpgrade, handleSwitch, handleCancel, handleManage }}
            ctaForUpgrade={() => "Get started"}
          />

          {/* Pro card */}
          <PlanCard
            accent="#6366f1"
            border="2px solid #6366f1"
            background="rgba(99,102,241,0.05)"
            iconNode={<ZapIcon size={18} style={{ color: "#6366f1" }} />}
            title="Pro"
            isCurrent={currentPlan === "PRO"}
            currentBadgeBg="rgba(99,102,241,0.2)"
            currentBadgeColor="#6366f1"
            priceMain={billing === "monthly" ? PRO_MONTHLY_PRICE : PRO_YEARLY_MONTHLY}
            priceSuffix=" / month"
            priceFootnote={billing === "yearly" ? `Billed ${PRO_YEARLY_PRICE}/year` : null}
            featureColor="var(--text-primary)"
            features={PRO_FEATURES}
            action={paidAction("PRO")}
            loading={loading}
            isLoading={isLoading}
            handlers={{ handleUpgrade, handleSwitch, handleCancel, handleManage }}
            ctaForUpgrade={() => `Upgrade to Pro — ${billing === "monthly" ? `${PRO_MONTHLY_PRICE}/mo` : `${PRO_YEARLY_PRICE}/yr`}`}
          />

          {/* Business card */}
          <PlanCard
            accent="#0ea5e9"
            border="2px solid #0ea5e9"
            background="rgba(14,165,233,0.05)"
            iconNode={<BuildingIcon size={18} style={{ color: "#0ea5e9" }} />}
            title="Business"
            isCurrent={currentPlan === "BUSINESS"}
            currentBadgeBg="rgba(14,165,233,0.2)"
            currentBadgeColor="#0ea5e9"
            priceMain={billing === "monthly" ? BUSINESS_MONTHLY_PRICE : BUSINESS_YEARLY_MONTHLY}
            priceSuffix=" / month"
            priceFootnote={billing === "yearly" ? `Billed ${BUSINESS_YEARLY_PRICE}/year` : null}
            featureColor="var(--text-primary)"
            features={BUSINESS_FEATURES}
            action={paidAction("BUSINESS")}
            loading={loading}
            isLoading={isLoading}
            handlers={{ handleUpgrade, handleSwitch, handleCancel, handleManage }}
            ctaForUpgrade={() => `Upgrade to Business — ${billing === "monthly" ? `${BUSINESS_MONTHLY_PRICE}/mo` : `${BUSINESS_YEARLY_PRICE}/yr`}`}
          />
        </div>

        {error && (
          <div style={{ margin: "0 28px 16px", fontSize: 13, color: "#ef4444", textAlign: "center" }}>
            {error}
          </div>
        )}

        <div style={{ textAlign: "center", paddingBottom: 20, fontSize: 12, color: "var(--text-secondary)" }}>
          Secure payment via Stripe · Cancel anytime
        </div>
      </div>
    </div>
  );
}

// ── Plan card ────────────────────────────────────────────────────────

interface PlanCardProps {
  accent: string;
  border: string;
  background: string;
  iconNode: React.ReactNode;
  title: string;
  isCurrent: boolean;
  currentBadgeBg: string;
  currentBadgeColor: string;
  priceMain: string;
  priceSuffix: string;
  priceFootnote?: string | null;
  featureColor: string;
  features: string[];
  action:
    | { kind: "current" }
    | { kind: "upgrade"; plan: "PRO" | "BUSINESS" }
    | { kind: "switch"; plan: "PRO" | "BUSINESS" }
    | { kind: "cancel" }
    | { kind: "none" };
  loading: LoadingButton;
  isLoading: boolean;
  handlers: {
    handleUpgrade: (plan: "PRO" | "BUSINESS") => void;
    handleSwitch: (plan: "PRO" | "BUSINESS") => void;
    handleCancel: () => void;
    handleManage: () => void;
  };
  ctaForUpgrade: () => string;
}

function PlanCard({
  accent,
  border,
  background,
  iconNode,
  title,
  isCurrent,
  currentBadgeBg,
  currentBadgeColor,
  priceMain,
  priceSuffix,
  priceFootnote,
  featureColor,
  features,
  action,
  loading,
  isLoading,
  handlers,
  ctaForUpgrade,
}: PlanCardProps) {
  return (
    <div
      style={{
        border,
        borderRadius: 12,
        padding: "20px 20px 24px",
        background,
        position: "relative",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        {iconNode}
        <span style={{ fontWeight: 700, fontSize: 15, color: "var(--text-primary)" }}>{title}</span>
        {isCurrent && (
          <span
            style={{
              marginLeft: "auto",
              fontSize: 11,
              padding: "2px 8px",
              borderRadius: 4,
              background: currentBadgeBg,
              color: currentBadgeColor,
              fontWeight: 600,
            }}
          >
            Current plan
          </span>
        )}
      </div>
      <div style={{ marginBottom: 16 }}>
        <span style={{ fontSize: 28, fontWeight: 800, color: "var(--text-primary)" }}>{priceMain}</span>
        <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>{priceSuffix}</span>
        {priceFootnote && (
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>{priceFootnote}</div>
        )}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: action.kind === "none" ? 0 : 20 }}>
        {features.map((f) => (
          <div key={f} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
            <CheckCircle2Icon size={14} style={{ color: accent, flexShrink: 0 }} />
            <span style={{ color: featureColor }}>{f}</span>
          </div>
        ))}
      </div>

      {renderActionButton(action, accent, loading, isLoading, handlers, ctaForUpgrade)}
    </div>
  );
}

function renderActionButton(
  action: PlanCardProps["action"],
  accent: string,
  loading: LoadingButton,
  isLoading: boolean,
  handlers: PlanCardProps["handlers"],
  ctaForUpgrade: () => string,
) {
  if (action.kind === "none") return null;

  if (action.kind === "current") {
    return (
      <button
        onClick={handlers.handleManage}
        disabled={isLoading}
        style={{
          width: "100%",
          padding: "10px 0",
          borderRadius: 8,
          border: `1px solid ${accent}`,
          background: "transparent",
          color: accent,
          fontSize: 14,
          fontWeight: 700,
          cursor: isLoading ? "not-allowed" : "pointer",
          opacity: isLoading && loading !== "manage" ? 0.6 : 1,
          transition: "all 0.15s",
        }}
      >
        {loading === "manage" ? "Redirecting…" : "Manage plan"}
      </button>
    );
  }

  if (action.kind === "cancel") {
    return (
      <button
        onClick={handlers.handleCancel}
        disabled={isLoading}
        style={{
          width: "100%",
          padding: "10px 0",
          borderRadius: 8,
          border: "1px solid var(--border)",
          background: "transparent",
          color: "var(--text-secondary)",
          fontSize: 14,
          fontWeight: 700,
          cursor: isLoading ? "not-allowed" : "pointer",
          opacity: isLoading && loading !== "cancel" ? 0.6 : 1,
          transition: "all 0.15s",
        }}
      >
        {loading === "cancel" ? "Cancelling…" : "Downgrade to Free"}
      </button>
    );
  }

  if (action.kind === "switch") {
    return (
      <button
        onClick={() => handlers.handleSwitch(action.plan)}
        disabled={isLoading}
        style={{
          width: "100%",
          padding: "10px 0",
          borderRadius: 8,
          border: "none",
          background: accent,
          color: "#fff",
          fontSize: 14,
          fontWeight: 700,
          cursor: isLoading ? "not-allowed" : "pointer",
          opacity: isLoading && loading !== "switch" ? 0.6 : 1,
          transition: "all 0.15s",
        }}
      >
        {loading === "switch" ? "Switching…" : `Switch to ${action.plan === "PRO" ? "Pro" : "Business"}`}
      </button>
    );
  }

  // upgrade
  const slot = action.plan === "PRO" ? "pro" : "business";
  return (
    <button
      onClick={() => handlers.handleUpgrade(action.plan)}
      disabled={isLoading}
      style={{
        width: "100%",
        padding: "10px 0",
        borderRadius: 8,
        border: "none",
        background: loading === slot ? `${accent}80` : accent,
        color: "#fff",
        fontSize: 14,
        fontWeight: 700,
        cursor: isLoading ? "not-allowed" : "pointer",
        opacity: isLoading && loading !== slot ? 0.6 : 1,
        transition: "all 0.15s",
      }}
    >
      {loading === slot ? "Redirecting…" : ctaForUpgrade()}
    </button>
  );
}
