"use client";

import { ShieldAlertIcon, PlusIcon, LogOutIcon, ZapIcon } from "lucide-react";
import { signOut } from "next-auth/react";
import { Session, groupSessionsByDate } from "@/lib/sessions";
import { ApiUsage } from "@/lib/api";

interface SidebarProps {
  sessions: Session[];
  activeSessionId: string | null;
  onSelectSession: (session: Session) => void;
  onNewSession: () => void;
  onUpgrade?: () => void;
  usage?: ApiUsage | null;
  displayPlan?: "FREE" | "PRO" | "BUSINESS";
}

export default function Sidebar({ sessions, activeSessionId, onSelectSession, onNewSession, onUpgrade, usage, displayPlan = "FREE" }: SidebarProps) {
  const isPaid = displayPlan !== "FREE";
  const isBusiness = displayPlan === "BUSINESS";
  const planAccent = isBusiness ? "#0ea5e9" : "#6366f1";
  const planLabel = isBusiness ? "Business plan · Unlimited" : "Pro plan · Unlimited";
  const groups = groupSessionsByDate(sessions);

  return (
    <aside
      style={{
        background: "var(--surface)",
        borderRight: "1px solid var(--border)",
        width: 260,
        minWidth: 260,
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Logo */}
      <div
        style={{
          padding: "16px 16px 12px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <ShieldAlertIcon size={16} color="#fff" />
        </div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
            Aletheia
          </div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
            Misinformation Detection
          </div>
        </div>
      </div>

      {/* New analysis button */}
      <div style={{ padding: "10px 10px 6px" }}>
        <button
          onClick={onNewSession}
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "9px 12px",
            borderRadius: 8,
            border: "1px dashed var(--border)",
            cursor: "pointer",
            background: "transparent",
            color: "var(--text-secondary)",
            fontSize: 13,
            fontWeight: 500,
            transition: "all 0.15s",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--accent)";
            e.currentTarget.style.color = "var(--accent)";
            e.currentTarget.style.background = "var(--accent-glow)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--border)";
            e.currentTarget.style.color = "var(--text-secondary)";
            e.currentTarget.style.background = "transparent";
          }}
        >
          <PlusIcon size={15} />
          New analysis
        </button>
      </div>

      {/* Session list */}
      <nav style={{ flex: 1, overflowY: "auto", padding: "4px 10px 12px" }}>
        {groups.length === 0 && (
          <div style={{ padding: "20px 10px", fontSize: 13, color: "var(--text-secondary)", textAlign: "center" }}>
            No conversations yet.
          </div>
        )}
        {groups.map((group) => (
          <div key={group.label} style={{ marginBottom: 4 }}>
            <div
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: "var(--text-secondary)",
                padding: "8px 10px 4px",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
              }}
            >
              {group.label}
            </div>
            {group.items.map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                isActive={session.id === activeSessionId}
                onClick={() => onSelectSession(session)}
              />
            ))}
          </div>
        ))}
      </nav>

      {/* Daily usage bar — only shown for free users */}
      {!isPaid && usage && usage.limit !== null && (
        <div style={{ padding: "8px 14px 4px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-secondary)", marginBottom: 5 }}>
            <span>Analyses today</span>
            <span style={{ fontWeight: 600, color: usage.remaining === 0 ? "#ef4444" : "var(--text-secondary)" }}>
              {usage.used} / {usage.limit}
            </span>
          </div>
          <div style={{ height: 4, borderRadius: 2, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
            <div style={{
              height: "100%",
              width: `${Math.min(100, (usage.used / usage.limit) * 100)}%`,
              borderRadius: 2,
              background: usage.remaining === 0 ? "#ef4444" : usage.used / usage.limit > 0.7 ? "#f59e0b" : "#6366f1",
              transition: "width 0.4s ease",
            }} />
          </div>
          {usage.remaining === 0 && (
            <div style={{ fontSize: 11, color: "#ef4444", marginTop: 4 }}>
              Limit reached · Upgrade to continue
            </div>
          )}
        </div>
      )}

      {/* Upgrade button — hidden for paid users */}
      {!isPaid && onUpgrade && (
        <div style={{ padding: "8px 10px 4px" }}>
          <button
            onClick={onUpgrade}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "8px 12px",
              borderRadius: 8,
              border: "none",
              cursor: "pointer",
              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
              color: "#fff",
              fontSize: 13,
              fontWeight: 600,
              transition: "opacity 0.15s",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.opacity = "0.85"; }}
            onMouseLeave={(e) => { e.currentTarget.style.opacity = "1"; }}
          >
            <ZapIcon size={14} />
            Upgrade to Pro
          </button>
        </div>
      )}

      {/* Paid badge — shown for Pro / Business users */}
      {isPaid && onUpgrade && (
        <div style={{ padding: "8px 10px 4px" }}>
          <button
            onClick={onUpgrade}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "8px 12px",
              borderRadius: 8,
              border: `1px solid ${planAccent}4d`,
              cursor: "pointer",
              background: `${planAccent}1a`,
              transition: "all 0.15s",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = `${planAccent}33`;
              e.currentTarget.style.borderColor = `${planAccent}99`;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = `${planAccent}1a`;
              e.currentTarget.style.borderColor = `${planAccent}4d`;
            }}
          >
            <ZapIcon size={14} style={{ color: planAccent }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: planAccent }}>{planLabel}</span>
          </button>
        </div>
      )}

      {/* Logout */}
      <div style={{ padding: "8px 10px", borderTop: "1px solid var(--border)" }}>
        <button
          onClick={() => signOut({ callbackUrl: "/login" })}
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "8px 12px",
            borderRadius: 8,
            border: "none",
            cursor: "pointer",
            background: "transparent",
            color: "var(--text-secondary)",
            fontSize: 13,
            transition: "all 0.15s",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "var(--text-primary)";
            e.currentTarget.style.background = "rgba(255,255,255,0.04)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "var(--text-secondary)";
            e.currentTarget.style.background = "transparent";
          }}
        >
          <LogOutIcon size={14} />
          Sign out
        </button>
      </div>
    </aside>
  );
}

function SessionItem({
  session,
  isActive,
  onClick,
}: {
  session: Session;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        width: "100%",
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        padding: "8px 10px",
        borderRadius: 8,
        border: "none",
        cursor: "pointer",
        background: isActive ? "var(--surface-2)" : "transparent",
        marginBottom: 1,
        transition: "background 0.12s",
        textAlign: "left",
      }}
      onMouseEnter={(e) => {
        if (!isActive) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.04)";
      }}
      onMouseLeave={(e) => {
        if (!isActive) (e.currentTarget as HTMLElement).style.background = "transparent";
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 13,
            fontWeight: isActive ? 600 : 400,
            color: "var(--text-primary)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            lineHeight: 1.4,
          }}
        >
          {session.title}
        </div>
      </div>

      <span style={{ fontSize: 10, color: "var(--text-secondary)", whiteSpace: "nowrap", flexShrink: 0 }}>
        {formatTime(session.timestamp)}
      </span>
    </button>
  );
}

function formatTime(date: Date): string {
  const now = new Date();
  const diffMin = Math.floor((now.getTime() - date.getTime()) / 60000);
  const diffH = Math.floor(diffMin / 60);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const itemDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());

  if (diffMin < 60) return `${diffMin}m ago`;
  if (itemDay.getTime() === today.getTime()) return `${diffH}h ago`;
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}
