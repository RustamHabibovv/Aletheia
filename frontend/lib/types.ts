export type ToolId =
  | "general"
  | "image-detection"
  | "text-detection"
  | "video-detection"
  | "fact-check"
  | "bot-detection";

export interface Tool {
  id: ToolId;
  label: string;
  shortLabel: string;
  description: string;
  icon: string;
  acceptsFile?: boolean;
  fileTypes?: string;
  placeholder: string;
  color: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  analysis?: AnalysisResult;
  fileName?: string;
}

export interface AnalysisResult {
  verdict: "ai-generated" | "authentic" | "manipulated" | "likely-false" | "likely-true" | "unverified" | "bot" | "human";
  confidence: number;
  summary: string;
  details: DetailItem[];
  sources?: SourceItem[];
  riskLevel: "high" | "medium" | "low";
  sourceUrl?: string;
}

export interface DetailItem {
  label: string;
  value: string;
  flag?: "warn" | "ok" | "info";
}

export interface SourceItem {
  title: string;
  url: string;
  reliability: "high" | "medium" | "low";
}
