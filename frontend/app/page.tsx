"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Sidebar from "@/components/Sidebar";
import ChatInterface from "@/components/ChatInterface";
import PricingModal from "@/components/PricingModal";
import { ToolId } from "@/lib/types";
import { Session, conversationToSession } from "@/lib/sessions";
import { getConversations, getUsage, getMe, syncSubscription, getSubscription, ApiUsage } from "@/lib/api";

type DisplayPlan = "FREE" | "PRO" | "BUSINESS";

export default function Home() {
  const [conversations, setConversations] = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [activeTool, setActiveTool] = useState<ToolId>("general");
  const [showPricing, setShowPricing] = useState(false);
  const [usage, setUsage] = useState<ApiUsage | null>(null);
  const [userTier, setUserTier] = useState<"FREE" | "PRO" | "ENTERPRISE">("FREE");
  const [paidPlanChoice, setPaidPlanChoice] = useState<"PRO" | "BUSINESS">("PRO");
  const [tierLoaded, setTierLoaded] = useState(false);
  const [pendingCancelAt, setPendingCancelAt] = useState<string | null>(null);
  const [pendingPlanTier, setPendingPlanTier] = useState<"PRO" | "BUSINESS" | null>(null);
  const [pendingChangeAt, setPendingChangeAt] = useState<string | null>(null);

  const loadConversations = useCallback(async () => {
    try {
      const data = await getConversations();
      setConversations(data.map(conversationToSession));
    } catch {
      // silently ignore — user may not be authenticated yet
    }
  }, []);

  const loadUsage = useCallback(async () => {
    try {
      const data = await getUsage();
      setUsage(data);
      localStorage.setItem("aletheia_usage", JSON.stringify(data));
    } catch {
      // ignore
    }
  }, []);

  const loadUserTier = useCallback(async () => {
    try {
      const me = await getMe();
      setUserTier(me.tier);
      localStorage.setItem("aletheia_tier", me.tier);
      // If the backend says FREE, the user has no paid plan — clear any
      // stale Business/Pro selection so the UI doesn't lie.
      if (me.tier === "FREE") {
        try {
          localStorage.removeItem("aletheia_paid_plan");
        } catch {}
        setPaidPlanChoice("PRO");
        setPendingCancelAt(null);
        setPendingPlanTier(null);
        setPendingChangeAt(null);
      }
    } catch {
      // ignore
    } finally {
      setTierLoaded(true);
    }
  }, []);

  const loadSubscription = useCallback(async () => {
    try {
      const sub = await getSubscription();
      if (!sub) {
        setPendingCancelAt(null);
        setPendingPlanTier(null);
        setPendingChangeAt(null);
        return;
      }
      // Backend is the source of truth for the active paid plan.
      setPaidPlanChoice(sub.plan_tier);
      try {
        localStorage.setItem("aletheia_paid_plan", sub.plan_tier);
      } catch {}
      setPendingCancelAt(sub.cancel_at_period_end ? sub.current_period_end : null);
      setPendingPlanTier(sub.pending_plan_tier);
      setPendingChangeAt(sub.pending_change_at);
    } catch {
      // ignore — banner just won't appear
    }
  }, []);

  useEffect(() => {
    // Apply localStorage cache before API calls so state is correct on first paint
    try {
      const cachedTier = localStorage.getItem("aletheia_tier") as "FREE" | "PRO" | "ENTERPRISE" | null;
      const cachedUsage = localStorage.getItem("aletheia_usage");
      const cachedPaidPlan = localStorage.getItem("aletheia_paid_plan") as "PRO" | "BUSINESS" | null;
      if (cachedTier) setUserTier(cachedTier);
      if (cachedUsage) setUsage(JSON.parse(cachedUsage));
      if (cachedPaidPlan) setPaidPlanChoice(cachedPaidPlan);
    } catch {}

    loadConversations();
    loadUsage();
    loadUserTier();
    loadSubscription();
  }, [loadConversations, loadUsage, loadUserTier, loadSubscription]);

  // After returning from Stripe Checkout (?subscribed=1), force a backend
  // sync so the user's tier reflects the new subscription even when the
  // Stripe webhook listener isn't running locally.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("subscribed") !== "1") return;

    (async () => {
      try {
        await syncSubscription();
      } catch {
        // ignore — loadUserTier will still try
      } finally {
        await loadUserTier();
        await loadUsage();
        await loadSubscription();
        // Clean the URL so a refresh doesn't re-trigger sync
        const url = new URL(window.location.href);
        url.searchParams.delete("subscribed");
        window.history.replaceState({}, "", url.pathname + url.search + url.hash);
      }
    })();
  }, [loadUserTier, loadUsage, loadSubscription]);

  const displayPlan: DisplayPlan = useMemo(() => {
    if (userTier === "FREE") return "FREE";
    return paidPlanChoice;
  }, [userTier, paidPlanChoice]);

  async function handleNewSession() {
    setActiveSession(null);
    setActiveTool("general");
  }

  function handleSelectSession(session: Session) {
    setActiveSession(session);
    setActiveTool(session.toolId);
  }

  async function handleConversationCreated(id: string, title: string) {
    await loadConversations();
    const newSession: Session = { id, toolId: activeTool, title, timestamp: new Date() };
    setActiveSession(newSession);
  }

  function handleFactCheckSent() {
    loadUsage();
    loadUserTier();
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Sidebar
        sessions={conversations}
        activeSessionId={activeSession?.id ?? null}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        onUpgrade={() => setShowPricing(true)}
        usage={usage}
        displayPlan={displayPlan}
      />
      <ChatInterface
        activeTool={activeTool}
        onToolChange={setActiveTool}
        session={activeSession}
        onConversationCreated={handleConversationCreated}
        onFactCheckSent={handleFactCheckSent}
        usage={usage}
        userTier={userTier}
        tierLoaded={tierLoaded}
        onUpgrade={() => setShowPricing(true)}
      />
      {showPricing && (
        <PricingModal
          onClose={() => setShowPricing(false)}
          currentPlan={displayPlan}
          pendingCancelAt={pendingCancelAt}
          pendingPlanTier={pendingPlanTier}
          pendingChangeAt={pendingChangeAt}
          onPlanChanged={(notice) => {
            if (notice.status === "upgraded") {
              setPaidPlanChoice(notice.planTier);
              setPendingPlanTier(null);
              setPendingChangeAt(null);
              try {
                localStorage.setItem("aletheia_paid_plan", notice.planTier);
              } catch {}
            } else if (notice.status === "scheduled") {
              setPendingPlanTier(notice.pendingPlanTier ?? null);
              setPendingChangeAt(notice.pendingChangeAt ?? null);
            }
            // Refresh from backend to stay in sync.
            loadSubscription();
            loadUserTier();
          }}
          onCanceled={(periodEnd) => setPendingCancelAt(periodEnd)}
        />
      )}
    </div>
  );
}
