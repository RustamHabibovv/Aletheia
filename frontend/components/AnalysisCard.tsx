"use client";

import { AnalysisResult } from "@/lib/types";
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  HelpCircleIcon,
  ExternalLinkIcon,
} from "lucide-react";

const VERDICT_CONFIG: Record<
  AnalysisResult["verdict"],
  { label: string; color: string; bg: string; Icon: React.ComponentType<{ size?: number; style?: React.CSSProperties }> }
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
}

export default function AnalysisCard({ result }: Props) {
  const cfg = VERDICT_CONFIG[result.verdict];
  const VerdictIcon = cfg.Icon;

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
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "12px 14px",
          borderBottom: "1px solid var(--border)",
          background: cfg.bg,
        }}
      >
        <VerdictIcon size={18} style={{ color: cfg.color, flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, color: cfg.color, fontSize: 14 }}>{cfg.label}</div>
          <div style={{ color: "var(--text-secondary)", fontSize: 12, marginTop: 1 }}>{result.summary}</div>
        </div>
        <ConfidenceBadge value={result.confidence} color={cfg.color} />
      </div>

      {/* Details */}
      <div style={{ padding: "10px 14px 12px" }}>
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
        {result.sources && result.sources.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Sources
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {result.sources.map((s, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "4px 8px",
                    borderRadius: 6,
                    background: "rgba(255,255,255,0.02)",
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
                  />
                  <span style={{ flex: 1, color: "var(--text-primary)" }}>{s.title}</span>
                  <ExternalLinkIcon size={12} style={{ color: "var(--text-secondary)" }} />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
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
