"use client";

import { useState } from "react";
import { AnalysisResult, SourceItem } from "@/lib/types";
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  HelpCircleIcon,
  ExternalLinkIcon,
  LinkIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  LockIcon,
  ZapIcon,
} from "lucide-react";

const FREE_VISIBLE_SOURCES = 5;

const VERDICT_CONFIG: Record<
  AnalysisResult["verdict"],
  { label: string; color: string; bg: string; Icon: React.ComponentType<{ size?: number | string; style?: React.CSSProperties }> }
> = {
  "ai-generated":  { label: "AI-Generated",   color: "#ef4444", bg: "rgba(239,68,68,0.1)",   Icon: AlertTriangleIcon },
  manipulated:     { label: "Manipulated",     color: "#ef4444", bg: "rgba(239,68,68,0.1)",   Icon: AlertTriangleIcon },
  "likely-false":  { label: "Likely False",    color: "#f59e0b", bg: "rgba(245,158,11,0.1)",  Icon: AlertTriangleIcon },
  authentic:       { label: "Authentic",       color: "#10b981", bg: "rgba(16,185,129,0.1)",  Icon: CheckCircle2Icon  },
  "likely-true":   { label: "Likely True",     color: "#10b981", bg: "rgba(16,185,129,0.1)",  Icon: CheckCircle2Icon  },
  human:           { label: "Human Account",   color: "#10b981", bg: "rgba(16,185,129,0.1)",  Icon: CheckCircle2Icon  },
  unverified:      { label: "Unverified",      color: "#8b8fa8", bg: "rgba(139,143,168,0.1)", Icon: HelpCircleIcon    },
  bot:             { label: "Bot Account",     color: "#ef4444", bg: "rgba(239,68,68,0.1)",   Icon: AlertTriangleIcon },
};

const RELIABILITY_COLOR = { high: "#10b981", medium: "#f59e0b", low: "#ef4444" };

interface Props {
  result: AnalysisResult;
  isFree?: boolean;
  onUpgrade?: () => void;
}

export default function AnalysisCard({ result, isFree = false, onUpgrade }: Props) {
  const [collapsed, setCollapsed] = useState(true);
  const cfg = VERDICT_CONFIG[result.verdict];
  const VerdictIcon = cfg.Icon;
  const ChevronIcon = collapsed ? ChevronDownIcon : ChevronUpIcon;
  const hasDetails = result.details.length > 0 || (result.sources && result.sources.length > 0);

  return (
    <div
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: 12,
        overflow: "hidden",
        marginTop: 10,
        fontSize: 13,
      }}
    >
      {/* Analyzed URL banner */}
      {result.sourceUrl && (
        <a
          href={result.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "6px 14px",
            borderBottom: "1px solid var(--border)",
            background: "rgba(99,102,241,0.08)",
            textDecoration: "none",
            fontSize: 11,
            color: "var(--text-secondary)",
          }}
        >
          <LinkIcon size={11} style={{ flexShrink: 0 }} />
          <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            Analyzed: {result.sourceUrl}
          </span>
          <ExternalLinkIcon size={10} style={{ flexShrink: 0 }} />
        </a>
      )}

      {/* Header — always visible, click to expand/collapse */}
      <div
        onClick={() => hasDetails && setCollapsed((c) => !c)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "12px 14px",
          background: cfg.bg,
          cursor: hasDetails ? "pointer" : "default",
          userSelect: "none",
        }}
      >
        <VerdictIcon size={18} style={{ color: cfg.color, flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, color: cfg.color, fontSize: 14 }}>{cfg.label}</div>
          <div style={{ color: "var(--text-secondary)", fontSize: 12, marginTop: 1 }}>{result.summary}</div>
        </div>
        <ConfidenceBadge value={result.confidence} color={cfg.color} />
        {hasDetails && (
          <ChevronIcon size={16} style={{ color: "var(--text-secondary)", flexShrink: 0, marginLeft: 4 }} />
        )}
      </div>

      {/* Details — collapsible */}
      {!collapsed && hasDetails && (
        <div style={{ padding: "10px 14px 12px", borderTop: "1px solid var(--border)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {result.details.map((d, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 8,
                  padding: "5px 8px",
                  borderRadius: 6,
                  background: "rgba(255,255,255,0.02)",
                }}
              >
                <FlagDot flag={d.flag} />
                <span style={{ color: "var(--text-secondary)", minWidth: 0, flexShrink: 0, maxWidth: "45%" }}>
                  {d.label}
                </span>
                <span style={{ color: "var(--text-primary)", flex: 1, textAlign: "right" }}>{d.value}</span>
              </div>
            ))}
          </div>

          {/* Sources */}
          {result.sources && result.sources.length > 0 && (() => {
            const sources = result.sources;
            const total = sources.length;
            const gateApplies = isFree && total > FREE_VISIBLE_SOURCES;
            const visible = gateApplies ? sources.slice(0, FREE_VISIBLE_SOURCES) : sources;
            const lockedCount = gateApplies ? total - FREE_VISIBLE_SOURCES : 0;
            const lockedPreview = gateApplies ? sources.slice(FREE_VISIBLE_SOURCES, FREE_VISIBLE_SOURCES + 3) : [];

            return (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  Sources
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {visible.map((s, i) => (
                    <SourceLink key={i} source={s} />
                  ))}

                  {gateApplies && (
                    <div style={{ position: "relative", marginTop: 4 }}>
                      <div
                        aria-hidden
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: 4,
                          filter: "blur(5px)",
                          pointerEvents: "none",
                          userSelect: "none",
                          opacity: 0.7,
                        }}
                      >
                        {lockedPreview.map((s, i) => (
                          <SourceLink key={`locked-${i}`} source={s} />
                        ))}
                      </div>

                      <div
                        onClick={(e) => {
                          e.stopPropagation();
                          onUpgrade?.();
                        }}
                        style={{
                          position: "absolute",
                          inset: 0,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          flexDirection: "column",
                          gap: 6,
                          padding: 8,
                          borderRadius: 8,
                          background: "rgba(0,0,0,0.45)",
                          cursor: onUpgrade ? "pointer" : "default",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--text-primary)", fontSize: 12, fontWeight: 600 }}>
                          <LockIcon size={12} />
                          {lockedCount} more {lockedCount === 1 ? "source" : "sources"} hidden
                        </div>
                        {onUpgrade && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onUpgrade();
                            }}
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 5,
                              border: "none",
                              borderRadius: 6,
                              padding: "5px 10px",
                              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                              color: "#fff",
                              fontSize: 12,
                              fontWeight: 700,
                              cursor: "pointer",
                            }}
                          >
                            <ZapIcon size={11} />
                            Upgrade to Pro
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

function SourceLink({ source: s }: { source: SourceItem }) {
  return (
    <a
      href={s.url}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => e.stopPropagation()}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 8px",
        borderRadius: 6,
        background: "rgba(255,255,255,0.02)",
        textDecoration: "none",
      }}
    >
      <div
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: RELIABILITY_COLOR[s.reliability],
          flexShrink: 0,
        }}
        title={
          s.reliability === "high"
            ? "High credibility source"
            : s.reliability === "medium"
            ? "Moderate credibility source"
            : "Low credibility source"
        }
      />
      <span style={{ flex: 1, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {s.title}
      </span>
      <span
        style={{
          fontSize: 9,
          padding: "1px 5px",
          borderRadius: 4,
          background: `${RELIABILITY_COLOR[s.reliability]}22`,
          color: RELIABILITY_COLOR[s.reliability],
          fontWeight: 600,
          textTransform: "uppercase",
          flexShrink: 0,
        }}
      >
        {s.reliability}
      </span>
      <ExternalLinkIcon size={12} style={{ color: "var(--text-secondary)", flexShrink: 0 }} />
    </a>
  );
}

function ConfidenceBadge({ value, color }: { value: number; color: string }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        background: "rgba(0,0,0,0.25)",
        borderRadius: 8,
        padding: "6px 10px",
        minWidth: 56,
      }}
    >
      <div style={{ fontSize: 18, fontWeight: 800, color, lineHeight: 1 }}>{value}%</div>
      <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 2 }}>confidence</div>
    </div>
  );
}

function FlagDot({ flag }: { flag?: "warn" | "ok" | "info" }) {
  const color =
    flag === "warn" ? "#ef4444" : flag === "ok" ? "#10b981" : "var(--text-secondary)";
  return (
    <div
      style={{
        width: 7,
        height: 7,
        borderRadius: "50%",
        background: color,
        flexShrink: 0,
        marginTop: 4,
      }}
    />
  );
}
