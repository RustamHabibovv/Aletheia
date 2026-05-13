import { getSession } from "next-auth/react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Backend types ────────────────────────────────────────────────────

export interface ApiConversation {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ApiMessage {
  id: string;
  conversation_id: string;
  role: "USER" | "ASSISTANT" | "SYSTEM";
  content: string;
  created_at: string;
  analysis?: {
    verdict: string;
    confidence_score: number | null;
    summary: string;
    analysis_type?: string;
    claims?: Array<{
      claim: string;
      verdict: string;
      confidence: number;
      explanation: string;
      key_sources: string[];
    }>;
    sources: Array<{
      title: string;
      url: string;
      credibility_tier?: number;
      credibility_weight?: number;
      credibility_label?: string;
    }>;
    source_url?: string | null;
    // Text detection fields
    ai_score?: number | null;
    classification?: string;
    sentence_analysis?: Array<{
      sentence: string;
      ai_probability: number;
      flag: "ai" | "human" | "mixed";
    }>;
    explanation?: string;
    signals?: Array<{
      label: string;
      value: string;
      flag: "warn" | "ok" | "info";
    }>;
  } | null;
}

export interface ApiConversationWithMessages extends ApiConversation {
  messages: ApiMessage[];
}

// ── Auth header ──────────────────────────────────────────────────────

async function authHeaders(): Promise<Record<string, string>> {
  const session = await getSession();
  const token = (session as { accessToken?: string } | null)?.accessToken;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// ── API helpers ──────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { ...headers, ...(init.headers as Record<string, string> | undefined) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── User ─────────────────────────────────────────────────────────────

export interface ApiUser {
  id: string;
  email: string;
  name: string | null;
  image: string | null;
  tier: "FREE" | "PRO" | "ENTERPRISE";
}

export function getMe(): Promise<ApiUser> {
  return apiFetch("/api/v1/users/me");
}

// ── Conversations ────────────────────────────────────────────────────

export function getConversations(): Promise<ApiConversation[]> {
  return apiFetch("/api/v1/conversations");
}

export function createConversation(title: string): Promise<ApiConversation> {
  return apiFetch("/api/v1/conversations", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export function getConversation(id: string): Promise<ApiConversationWithMessages> {
  return apiFetch(`/api/v1/conversations/${id}`);
}

// ── Chat ─────────────────────────────────────────────────────────────

export function sendChat(conversationId: string, content: string, tool: string): Promise<ApiMessage> {
  return apiFetch(`/api/v1/conversations/${conversationId}/chat`, {
    method: "POST",
    body: JSON.stringify({ content, tool }),
  });
}

// ── Billing ───────────────────────────────────────────────────────────

export function createCheckoutSession(
  plan: "monthly" | "yearly",
  planTier: "PRO" | "BUSINESS" = "PRO",
): Promise<{ url: string }> {
  return apiFetch("/api/v1/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ plan, plan_tier: planTier }),
  });
}

export interface ApiSubscription {
  status: string;
  plan: string;
  plan_tier: "PRO" | "BUSINESS";
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  pending_plan_tier: "PRO" | "BUSINESS" | null;
  pending_change_at: string | null;
}

export interface ApiChangePlanResponse {
  status: "upgraded" | "scheduled" | "no_change";
  current_plan_tier: "PRO" | "BUSINESS";
  pending_plan_tier: "PRO" | "BUSINESS" | null;
  pending_change_at: string | null;
}

export function changePlan(
  planTier: "PRO" | "BUSINESS",
  billing: "monthly" | "yearly",
): Promise<ApiChangePlanResponse> {
  return apiFetch("/api/v1/billing/change-plan", {
    method: "POST",
    body: JSON.stringify({ plan_tier: planTier, billing }),
  });
}

export function getSubscription(): Promise<ApiSubscription | null> {
  return apiFetch("/api/v1/billing/subscription");
}

export interface ApiCancelResponse {
  cancel_at_period_end: boolean;
  current_period_end: string | null;
}

export function cancelSubscription(): Promise<ApiCancelResponse> {
  return apiFetch("/api/v1/billing/cancel", { method: "POST" });
}

export function createPortalSession(): Promise<{ url: string }> {
  return apiFetch("/api/v1/billing/portal", { method: "POST" });
}

// Pulls the latest subscription state from Stripe and updates the user's
// tier in the DB. Used as a fallback when the Stripe webhook listener
// isn't running locally — call after returning from Checkout.
export function syncSubscription(): Promise<{ synced: boolean; tier: string }> {
  return apiFetch("/api/v1/billing/sync", { method: "POST" });
}

export interface ApiUsage {
  used: number;
  limit: number | null;
  remaining: number | null;
}

export function getUsage(): Promise<ApiUsage> {
  return apiFetch("/api/v1/billing/usage");
}
