"use client";

import { AnalysisResult } from "@/lib/types";
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  HelpCircleIcon,
  FileTextIcon,
} from "lucide-react";

const CLASSIFICATION_CONFIG: Record<
  string,
  {
    label: string;
    color: string;
    bg: string;
    Icon: React.ComponentType<{ size?: number | string; style?: React.CSSProperties }>;
  }
> = {
  "ai-generated": {
    label: "AI-Generated",
    color: "#ef4444",
    bg: "rgba(239,68,68,0.1)",
    Icon: AlertTriangleIcon,
  },
  mixed: {
    label: "Mixed Content",
    color: "#f59e0b",
    bg: "rgba(245,158,11,0.1)",
    Icon: HelpCircleIcon,
  },
  "human-written": {
    label: "Human-Written",
    color: "#10b981",
    bg: "rgba(16,185,129,0.1)",
    Icon: CheckCircle2Icon,
  },
  insufficient: {
    label: "Insufficient Text",
    color: "#8b8fa8",
    bg: "rgba(139,143,168,0.1)",
    Icon: HelpCircleIcon,
  },
};

interface Props {
  result: AnalysisResult;
}

export default function TextDetectionCard({ result }: Props) {
  const classification = result.classification ?? "mixed";
  const cfg = CLASSIFICATION_CONFIG[classification] ?? CLASSIFICATION_CONFIG["mixed"];
  const VerdictIcon = cfg.Icon;
  const aiScore = result.aiScore;
  const scorePct = aiScore != null ? Math.round(aiScore * 100) : null;
  const sentences = result.sentenceAnalysis ?? [];
  const explanation = result.explanation ?? "";
  const signals = result.details ?? [];

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
          <div style={{ fontWeight: 700, color: cfg.color, fontSize: 14 }}>
            {cfg.label}
          </div>
          <div
            style={{
              color: "var(--text-secondary)",
              fontSize: 12,
              marginTop: 1,
            }}
          >
            {result.summary}
          </div>
        </div>
        {scorePct != null && (
          <AiScoreBadge value={scorePct} color={cfg.color} />
        )}
      </div>

      <div style={{ padding: "10px 14px 12px" }}>
        {/* AI Probability Bar */}
        {scorePct != null && <ProbabilityBar value={scorePct} />}

        {/* Explanation */}
        {explanation && (
          <div
            style={{
              margin: "10px 0",
              padding: "8px 10px",
              background: "rgba(255,255,255,0.03)",
              borderRadius: 8,
              color: "var(--text-primary)",
              lineHeight: 1.6,
              fontSize: 13,
            }}
          >
            {explanation}
          </div>
        )}

        {/* Signals */}
        {signals.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
            {signals.map((s, i) => (
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
                <FlagDot flag={s.flag} />
                <span
                  style={{
                    color: "var(--text-secondary)",
                    minWidth: 0,
                    flexShrink: 0,
                    maxWidth: "55%",
                  }}
                >
                  {s.label}
                </span>
                <span
                  style={{
                    color: "var(--text-primary)",
                    flex: 1,
                    textAlign: "right",
                  }}
                >
                  {s.value}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Sentence Analysis */}
        {sentences.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: "var(--text-secondary)",
                marginBottom: 6,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              Sentence Analysis
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 4,
              }}
            >
              {sentences.map((s, i) => {
                const prob = Math.round(s.ai_probability * 100);
                const barColor =
                  s.flag === "ai"
                    ? "#ef4444"
                    : s.flag === "human"
                      ? "#10b981"
                      : "#f59e0b";
                return (
                  <div
                    key={i}
                    style={{
                      padding: "6px 8px",
                      borderRadius: 6,
                      background: "rgba(255,255,255,0.02)",
                      borderLeft: `3px solid ${barColor}`,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        marginBottom: 2,
                      }}
                    >
                      <span
                        style={{
                          fontSize: 11,
                          color: barColor,
                          fontWeight: 600,
                        }}
                      >
                        {prob}% AI
                      </span>
                      <span
                        style={{
                          fontSize: 10,
                          color: "var(--text-secondary)",
                          textTransform: "uppercase",
                        }}
                      >
                        {s.flag}
                      </span>
                    </div>
                    <div
                      style={{
                        color: "var(--text-primary)",
                        fontSize: 12,
                        lineHeight: 1.5,
                      }}
                    >
                      {s.sentence}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function AiScoreBadge({ value, color }: { value: number; color: string }) {
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
      <div style={{ fontSize: 18, fontWeight: 800, color, lineHeight: 1 }}>
        {value}%
      </div>
      <div
        style={{
          fontSize: 10,
          color: "var(--text-secondary)",
          marginTop: 2,
        }}
      >
        AI prob.
      </div>
    </div>
  );
}

function ProbabilityBar({ value }: { value: number }) {
  // Gradient from green (human) to red (AI)
  const barColor =
    value >= 65 ? "#ef4444" : value >= 30 ? "#f59e0b" : "#10b981";

  return (
    <div style={{ marginTop: 8 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 10,
          color: "var(--text-secondary)",
          marginBottom: 4,
        }}
      >
        <span>Human</span>
        <span>AI-Generated</span>
      </div>
      <div
        style={{
          height: 6,
          borderRadius: 3,
          background: "rgba(255,255,255,0.08)",
          overflow: "hidden",
          position: "relative",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${value}%`,
            borderRadius: 3,
            background: barColor,
            transition: "width 0.5s ease",
          }}
        />
      </div>
    </div>
  );
}

function FlagDot({ flag }: { flag?: "warn" | "ok" | "info" }) {
  const color =
    flag === "warn"
      ? "#ef4444"
      : flag === "ok"
        ? "#10b981"
        : "var(--text-secondary)";
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
