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
    sources: Array<{ title: string; url: string }>;
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
