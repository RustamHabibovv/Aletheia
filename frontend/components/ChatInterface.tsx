"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  SendIcon,
  PaperclipIcon,
  XIcon,
  ImageIcon,
  FileTextIcon,
  VideoIcon,
  SearchCheckIcon,
  BotIcon,
  ShieldAlertIcon,
} from "lucide-react";
import { Message, ToolId, AnalysisResult, DetailItem, SourceItem } from "@/lib/types";
import { TOOLS } from "@/lib/tools";
import { Session } from "@/lib/sessions";
import { getConversation, createConversation, sendChat, ApiMessage, ApiUsage } from "@/lib/api";
import AnalysisCard from "./AnalysisCard";
import TextDetectionCard from "./TextDetectionCard";

const TOOL_ICON_MAP: Record<
  string,
  React.ComponentType<{ size?: number | string; style?: React.CSSProperties }>
> = {
  "shield-alert": ShieldAlertIcon,
  image: ImageIcon,
  "file-text": FileTextIcon,
  video: VideoIcon,
  "search-check": SearchCheckIcon,
  bot: BotIcon,
};

function mapVerdictToLocal(v: string, analysisType?: string): AnalysisResult["verdict"] {
  if (analysisType === "TEXT_DETECTION") {
    switch (v) {
      case "TRUE": return "authentic";       // Human-Written
      case "FALSE": return "ai-generated";   // AI-Generated
      case "PARTIALLY_TRUE": return "ai-generated"; // Mixed
      case "UNVERIFIABLE": return "unverified";
      default: return "unverified";
    }
  }
  switch (v) {
    case "TRUE": return "likely-true";
    case "FALSE": return "likely-false";
    case "PARTIALLY_TRUE": return "likely-false";
    case "MISLEADING": return "likely-false";
    case "UNVERIFIABLE": return "unverified";
    default: return "unverified";
  }
}

function mapApiAnalysis(api: NonNullable<ApiMessage["analysis"]>): AnalysisResult {
  const analysisType = api.analysis_type ?? "";
  const verdict = mapVerdictToLocal(api.verdict, analysisType);
  const confidence = Math.round((api.confidence_score ?? 0) * 100);

  // Text detection path
  if (analysisType === "TEXT_DETECTION") {
    const riskLevel: AnalysisResult["riskLevel"] =
      verdict === "ai-generated" ? "high" : verdict === "unverified" ? "medium" : "low";

    const details: DetailItem[] = (api.signals ?? []).map((s) => ({
      label: s.label,
      value: s.value,
      flag: s.flag as DetailItem["flag"],
    }));

    return {
      verdict,
      confidence,
      summary: api.summary,
      details,
      sources: [],
      riskLevel,
      analysisType,
      aiScore: api.ai_score ?? null,
      classification: api.classification,
      sentenceAnalysis: api.sentence_analysis,
      explanation: api.explanation,
    };
  }

  // Default fact-check path
  const riskLevel: AnalysisResult["riskLevel"] =
    verdict === "likely-false" ? "high" : verdict === "unverified" ? "medium" : "low";

  const details: DetailItem[] = (api.claims ?? []).map((c) => ({
    label: c.claim,
    value: `${c.verdict} (${Math.round(c.confidence * 100)}%) — ${c.explanation}`,
    flag: (c.verdict === "TRUE" ? "ok" : c.verdict === "UNVERIFIABLE" ? "info" : "warn") as DetailItem["flag"],
  }));

  const sources: SourceItem[] = api.sources.map((s) => {
    const tier = s.credibility_tier ?? 3;
    const reliability: SourceItem["reliability"] =
      tier <= 2 ? "high" : tier === 3 ? "medium" : "low";
    return {
      title: s.title,
      url: s.url,
      reliability,
    };
  });

  return { verdict, confidence, summary: api.summary, details, sources, riskLevel, sourceUrl: api.source_url ?? undefined };
}

function apiMessageToLocal(m: ApiMessage): Message {
  return {
    id: m.id,
    role: m.role === "USER" ? "user" : "assistant",
    content: m.content,
    timestamp: new Date(m.created_at),
    ...(m.analysis ? { analysis: mapApiAnalysis(m.analysis) } : {}),
  };
}

interface Props {
  activeTool: ToolId;
  onToolChange: (tool: ToolId) => void;
  session: Session | null;
  onConversationCreated: (id: string, title: string) => void;
  onFactCheckSent?: () => void;
  usage?: ApiUsage | null;
  userTier?: "FREE" | "PRO" | "ENTERPRISE";
  tierLoaded?: boolean;
  onUpgrade?: () => void;
}

export default function ChatInterface({ activeTool, onToolChange, session, onConversationCreated, onFactCheckSent, usage, userTier = "FREE", tierLoaded = false, onUpgrade }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(session?.id ?? null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const tool = TOOLS.find((t) => t.id === activeTool)!;
  const isFree = userTier === "FREE";
  // Only enforce limit once we know the real tier — prevents the send button being
  // briefly enabled before the API response arrives on users who hit their limit.
  const limitReached = tierLoaded && isFree && usage != null && usage.remaining === 0;;

  // Reset when switching sessions or starting a new one
  useEffect(() => {
    setConversationId(session?.id ?? null);
    setMessages([]);
    setInput("");
    setAttachedFile(null);
  }, [session?.id]);

  // Load messages when an existing session is selected
  useEffect(() => {
    if (!session?.id) return;
    let cancelled = false;
    getConversation(session.id)
      .then((data) => {
        if (!cancelled) setMessages(data.messages.map(apiMessageToLocal));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [session?.id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text && !attachedFile) return;
    if (isLoading) return;

    const content = text || `[Uploaded: ${attachedFile?.name}]`;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content,
      timestamp: new Date(),
      fileName: attachedFile?.name,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setAttachedFile(null);
    setIsLoading(true);

    try {
      // Create a new conversation if we don't have one yet
      let convId = conversationId;
      if (!convId) {
        const title = text.slice(0, 80) || attachedFile?.name || "New analysis";
        const conv = await createConversation(title);
        convId = conv.id;
        setConversationId(convId);
        onConversationCreated(conv.id, conv.title);
      }

      const assistantApiMsg = await sendChat(convId, content, activeTool);
      const assistantMsg = apiMessageToLocal(assistantApiMsg);
      setMessages((prev) => [...prev, assistantMsg]);
      onFactCheckSent?.();
    } catch (err) {
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `Error: ${err instanceof Error ? err.message : "Something went wrong. Please try again."}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  }, [input, attachedFile, isLoading, conversationId, activeTool, onConversationCreated, onFactCheckSent]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!limitReached) handleSend();
    }
  }

  const isEmpty = messages.length === 0;

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
        background: "var(--background)",
      }}
    >
      {/* Header */}
      <header
        style={{
          padding: "12px 20px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "var(--surface)",
          flexShrink: 0,
          minHeight: 52,
        }}
      >
        <div
          style={{
            fontSize: 14,
            fontWeight: session ? 500 : 400,
            color: session ? "var(--text-primary)" : "var(--text-secondary)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {session ? session.title : "New analysis"}
        </div>

        {/* Tool selector */}
        <div style={{ display: "flex", gap: 4, flexShrink: 0, marginLeft: 16 }}>
          {TOOLS.map((t) => {
            const Icon = TOOL_ICON_MAP[t.icon] ?? FileTextIcon;
            const isActive = t.id === activeTool;
            return (
              <button
                key={t.id}
                onClick={() => onToolChange(t.id)}
                title={t.label}
                style={{
                  padding: "6px 10px",
                  borderRadius: 6,
                  border: isActive ? `1px solid ${t.color}` : "1px solid transparent",
                  background: isActive ? `${t.color}22` : "transparent",
                  color: isActive ? t.color : "var(--text-secondary)",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  fontSize: 12,
                  transition: "all 0.15s",
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = "rgba(255,255,255,0.06)";
                    e.currentTarget.style.color = "var(--text-primary)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = "transparent";
                    e.currentTarget.style.color = "var(--text-secondary)";
                  }
                }}
              >
                <Icon size={18} />
                <span style={{ display: "none" }}>{t.shortLabel}</span>
              </button>
            );
          })}
        </div>
      </header>

      {/* Messages area */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
        {isEmpty && <EmptyState tool={tool} onSuggest={(s) => setInput(s)} />}

        {messages.map((msg, i) => (
          <MessageRow
            key={msg.id}
            message={msg}
            index={i}
            toolColor={tool.color}
            isFree={isFree}
            onUpgrade={onUpgrade}
          />
        ))}

        {isLoading && <TypingIndicator toolColor={tool.color} />}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div
        style={{
          borderTop: "1px solid var(--border)",
          padding: "14px 20px",
          background: "var(--surface)",
          flexShrink: 0,
        }}
      >
        {attachedFile && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 10px",
              background: "var(--surface-2)",
              borderRadius: 8,
              marginBottom: 8,
              fontSize: 12,
              color: "var(--text-secondary)",
            }}
          >
            <PaperclipIcon size={13} />
            <span style={{ flex: 1 }}>{attachedFile.name}</span>
            <button
              onClick={() => setAttachedFile(null)}
              aria-label="Remove attachment"
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)", padding: 0 }}
            >
              <XIcon size={13} />
            </button>
          </div>
        )}

        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: 8,
            background: limitReached ? "rgba(239,68,68,0.05)" : "var(--surface-2)",
            border: `1px solid ${limitReached ? "rgba(239,68,68,0.35)" : "var(--border)"}`,
            borderRadius: 12,
            padding: "8px 8px 8px 14px",
          }}
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={limitReached ? "Daily limit reached — upgrade to continue" : tool.placeholder}
            disabled={isLoading || limitReached}
            rows={1}
            style={{
              flex: 1,
              background: "none",
              border: "none",
              outline: "none",
              resize: "none",
              color: "var(--text-primary)",
              fontSize: 14,
              lineHeight: 1.5,
              maxHeight: 120,
              overflowY: "auto",
              padding: "4px 0",
            }}
            onInput={(e) => {
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
            }}
          />

          <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
            {!limitReached && tool.acceptsFile && (
              <>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={tool.fileTypes}
                  style={{ display: "none" }}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) setAttachedFile(file);
                    e.target.value = "";
                  }}
                />
                <IconButton onClick={() => fileInputRef.current?.click()} title="Attach file" disabled={isLoading}>
                  <PaperclipIcon size={16} />
                </IconButton>
              </>
            )}
            {limitReached ? (
              <button
                onClick={onUpgrade}
                style={{
                  padding: "0 14px",
                  height: 36,
                  borderRadius: 8,
                  border: "none",
                  cursor: "pointer",
                  background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                  color: "#fff",
                  fontSize: 12,
                  fontWeight: 700,
                  whiteSpace: "nowrap",
                  flexShrink: 0,
                }}
              >
                Upgrade
              </button>
            ) : (
              <IconButton
                onClick={handleSend}
                disabled={isLoading || (!input.trim() && !attachedFile)}
                primary
                title="Send"
              >
                <SendIcon size={16} />
              </IconButton>
            )}
          </div>
        </div>

        <div style={{ textAlign: "center", fontSize: 11, color: "var(--text-secondary)", marginTop: 6 }}>
          {limitReached ? (
            <span style={{ color: "#ef4444" }}>
              Daily limit of {usage?.limit} analyses reached ·{" "}
              <span
                onClick={onUpgrade}
                style={{ textDecoration: "underline", cursor: "pointer" }}
              >
                Upgrade to Pro
              </span>{" "}
              for unlimited access
            </span>
          ) : (
            <>
              Press{" "}
              <kbd style={{ padding: "1px 5px", background: "var(--surface-2)", borderRadius: 4, border: "1px solid var(--border)" }}>
                Enter
              </kbd>{" "}
              to send ·{" "}
              <kbd style={{ padding: "1px 5px", background: "var(--surface-2)", borderRadius: 4, border: "1px solid var(--border)" }}>
                Shift+Enter
              </kbd>{" "}
              for new line
              {isFree && usage != null && usage.limit != null && (
                <span style={{ marginLeft: 10, color: usage.remaining != null && usage.remaining <= 2 ? "#f59e0b" : "var(--text-secondary)" }}>
                  · {usage.remaining} / {usage.limit} remaining
                </span>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function MessageRow({
  message,
  index,
  toolColor,
  isFree,
  onUpgrade,
}: {
  message: Message;
  index: number;
  toolColor: string;
  isFree?: boolean;
  onUpgrade?: () => void;
}) {
  const isUser = message.role === "user";
  return (
    <div
      className="animate-fade-in-up"
      style={{
        display: "flex",
        flexDirection: isUser ? "row-reverse" : "row",
        gap: 10,
        marginBottom: 16,
        animationDelay: `${index * 0.02}s`,
      }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          background: isUser ? "linear-gradient(135deg, #6366f1, #8b5cf6)" : `${toolColor}33`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          fontSize: 13,
          fontWeight: 700,
          color: isUser ? "#fff" : toolColor,
        }}
      >
        {isUser ? "U" : <ShieldAlertIcon size={15} />}
      </div>

      <div style={{ maxWidth: "75%", minWidth: 0 }}>
        <div
          style={{
            background: isUser ? "linear-gradient(135deg, #4f52c5, #6366f1)" : "var(--surface)",
            border: isUser ? "none" : "1px solid var(--border)",
            borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
            padding: "10px 14px",
            color: isUser ? "#fff" : "var(--text-primary)",
            fontSize: 14,
            lineHeight: 1.6,
          }}
        >
          {message.fileName && (
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4, opacity: 0.7, fontSize: 12 }}>
              <PaperclipIcon size={11} />
              {message.fileName}
            </div>
          )}
          <FormattedText text={message.content} />
        </div>

        {message.analysis && (
          message.analysis.analysisType === "TEXT_DETECTION"
            ? <TextDetectionCard result={message.analysis} />
            : <AnalysisCard result={message.analysis} isFree={isFree} onUpgrade={onUpgrade} />
        )}

        <div
          style={{
            fontSize: 11,
            color: "var(--text-secondary)",
            marginTop: 4,
            textAlign: isUser ? "right" : "left",
          }}
        >
          {message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </div>
      </div>
    </div>
  );
}

function FormattedText({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <span style={{ display: "block" }}>
      {lines.map((line, li) => {
        // Blank line — paragraph gap
        if (line === "") {
          return <span key={li} style={{ display: "block", marginTop: 8 }} />;
        }

        // Horizontal rule
        if (/^---+$/.test(line.trim())) {
          return <hr key={li} style={{ border: "none", borderTop: "1px solid var(--border)", margin: "8px 0" }} />;
        }

        // Headings
        const h3 = line.match(/^###\s+(.*)/);
        const h2 = line.match(/^##\s+(.*)/);
        const h1 = line.match(/^#\s+(.*)/);
        if (h1) return <span key={li} style={{ display: "block", fontWeight: 800, fontSize: 15, marginTop: li > 0 ? 10 : 0, color: "var(--text-primary)" }}>{renderInline(h1[1])}</span>;
        if (h2) return <span key={li} style={{ display: "block", fontWeight: 700, fontSize: 14, marginTop: li > 0 ? 8 : 0, color: "var(--text-primary)" }}>{renderInline(h2[1])}</span>;
        if (h3) return <span key={li} style={{ display: "block", fontWeight: 600, fontSize: 13, marginTop: li > 0 ? 6 : 0, color: "var(--text-primary)", opacity: 0.9 }}>{renderInline(h3[1])}</span>;

        // Numbered list
        const numbered = line.match(/^(\d+)\.\s+(.*)/);
        if (numbered) {
          return (
            <span key={li} style={{ display: "flex", gap: 6, marginTop: 3, paddingLeft: 4 }}>
              <span style={{ opacity: 0.5, flexShrink: 0, minWidth: 16 }}>{numbered[1]}.</span>
              <span>{renderInline(numbered[2])}</span>
            </span>
          );
        }

        // Bullet list
        const bullet = line.match(/^[-*]\s+(.*)/);
        if (bullet) {
          return (
            <span key={li} style={{ display: "flex", gap: 6, marginTop: 3, paddingLeft: 4 }}>
              <span style={{ opacity: 0.5, flexShrink: 0 }}>•</span>
              <span>{renderInline(bullet[1])}</span>
            </span>
          );
        }

        // Plain paragraph line
        return (
          <span key={li} style={{ display: "block", marginTop: li > 0 && lines[li - 1] !== "" ? 2 : 0 }}>
            {renderInline(line)}
          </span>
        );
      })}
    </span>
  );
}

function renderInline(text: string): React.ReactNode[] {
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  const parts = text.split(pattern);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linkMatch) {
      return (
        <a key={i} href={linkMatch[2]} target="_blank" rel="noopener noreferrer"
          style={{ color: "var(--accent, #6366f1)", textDecoration: "underline" }}>
          {linkMatch[1]}
        </a>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

function TypingIndicator({ toolColor }: { toolColor: string }) {
  return (
    <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          background: `${toolColor}33`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <ShieldAlertIcon size={15} style={{ color: toolColor }} />
      </div>
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "18px 18px 18px 4px",
          padding: "12px 16px",
          display: "flex",
          gap: 5,
          alignItems: "center",
        }}
      >
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="typing-dot"
            style={{ width: 8, height: 8, borderRadius: "50%", background: toolColor }}
          />
        ))}
      </div>
    </div>
  );
}

function EmptyState({ tool, onSuggest }: { tool: ReturnType<(typeof TOOLS)["find"]>; onSuggest: (s: string) => void }) {
  if (!tool) return null;

  const SUGGESTIONS: Record<ToolId, string[]> = {
    general: [
      "Is this news article reliable?",
      "Check this social media post for misinformation",
      "Analyze this image or video for manipulation",
    ],
    "image-detection": [
      "Is this photo real or AI-generated?",
      "Analyze this image for deepfake artifacts",
      "Check if this profile picture was created by AI",
    ],
    "text-detection": [
      "Was this news article written by an AI?",
      "Analyze the writing style of this text",
      "Check if this press release is AI-generated",
    ],
    "video-detection": [
      "Is this video a deepfake?",
      "Analyze this clip for face-swap artifacts",
      "Check this political speech for manipulation",
    ],
    "fact-check": [
      "Vaccines cause autism",
      "The moon landing was faked",
      "Climate change is caused by human activity",
    ],
    "bot-detection": [
      "Analyze @username for bot activity",
      "https://twitter.com/exampleuser",
      "Check if this account is automated",
    ],
  };

  const ToolIcon = TOOL_ICON_MAP[tool.icon] ?? FileTextIcon;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        padding: "40px 20px",
        textAlign: "center",
      }}
    >
      <div
        style={{
          width: 64,
          height: 64,
          borderRadius: 16,
          background: `${tool.color}22`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: 16,
        }}
      >
        <ToolIcon size={28} style={{ color: tool.color }} />
      </div>
      <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 8px" }}>
        {tool.label}
      </h2>
      <p style={{ fontSize: 14, color: "var(--text-secondary)", margin: "0 0 28px", maxWidth: 380, lineHeight: 1.6 }}>
        {tool.description}
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, width: "100%", maxWidth: 420 }}>
        {SUGGESTIONS[tool.id].map((s, i) => (
          <button
            key={i}
            onClick={() => onSuggest(s)}
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: "10px 14px",
              cursor: "pointer",
              color: "var(--text-secondary)",
              fontSize: 13,
              textAlign: "left",
              transition: "all 0.15s",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = tool.color;
              e.currentTarget.style.color = "var(--text-primary)";
              e.currentTarget.style.background = `${tool.color}11`;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = "var(--border)";
              e.currentTarget.style.color = "var(--text-secondary)";
              e.currentTarget.style.background = "var(--surface)";
            }}
          >
            &ldquo;{s}&rdquo;
          </button>
        ))}
      </div>
    </div>
  );
}

function IconButton({
  onClick,
  disabled,
  primary,
  title,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={title}
      style={{
        width: 36,
        height: 36,
        borderRadius: 8,
        border: "none",
        cursor: disabled ? "not-allowed" : "pointer",
        background: primary
          ? disabled
            ? "rgba(99,102,241,0.3)"
            : "linear-gradient(135deg, #6366f1, #8b5cf6)"
          : "transparent",
        color: primary ? "#fff" : "var(--text-secondary)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        opacity: disabled && !primary ? 0.4 : 1,
        transition: "all 0.15s",
        flexShrink: 0,
      }}
    >
      {children}
    </button>
  );
}
