import { ToolId } from "./types";

export interface Session {
  id: string;
  toolId: ToolId;
  title: string;
  preview: string;
  timestamp: Date;
  verdict?: "high" | "medium" | "low" | "unverified";
}

const now = new Date();
const d = (offsetMinutes: number) =>
  new Date(now.getTime() - offsetMinutes * 60 * 1000);

export const MOCK_SESSIONS: Session[] = [
  // Today
  {
    id: "s1",
    toolId: "image-detection",
    title: "Profile photo — @elonmusk_real",
    preview: "94% probability of being AI-generated. GAN artifacts detected.",
    timestamp: d(18),
    verdict: "high",
  },
  {
    id: "s2",
    toolId: "fact-check",
    title: "\"Ukraine bans Orthodox Church nationwide\"",
    preview: "Likely False — contradicted by 6 credible sources.",
    timestamp: d(55),
    verdict: "high",
  },
  {
    id: "s3",
    toolId: "bot-detection",
    title: "@breaking_news_24h",
    preview: "89% bot probability. 112 posts/day, new account.",
    timestamp: d(142),
    verdict: "high",
  },
  // Yesterday
  {
    id: "s4",
    toolId: "text-detection",
    title: "Reuters article — AI semiconductor exports",
    preview: "Text appears human-written with 81% confidence.",
    timestamp: d(60 * 26),
    verdict: "low",
  },
  {
    id: "s5",
    toolId: "video-detection",
    title: "Speech clip — uploaded video.mp4",
    preview: "Deepfake detected in 34% of frames. Face-swap artifacts found.",
    timestamp: d(60 * 31),
    verdict: "high",
  },
  {
    id: "s6",
    toolId: "fact-check",
    title: "\"Coffee causes cancer, WHO confirms\"",
    preview: "Unverified — no direct matches in fact-check databases.",
    timestamp: d(60 * 35),
    verdict: "unverified",
  },
  // This week
  {
    id: "s7",
    toolId: "image-detection",
    title: "Protest photo — Twitter post",
    preview: "Image appears authentic with 88% confidence.",
    timestamp: d(60 * 24 * 3 + 40),
    verdict: "low",
  },
  {
    id: "s8",
    toolId: "bot-detection",
    title: "@TruthSeeker_Official",
    preview: "Account likely human-operated (72% confidence).",
    timestamp: d(60 * 24 * 4 + 10),
    verdict: "low",
  },
  {
    id: "s9",
    toolId: "text-detection",
    title: "Substack post — crypto regulation",
    preview: "78% AI-generated probability. Low perplexity score detected.",
    timestamp: d(60 * 24 * 5 + 200),
    verdict: "high",
  },
  {
    id: "s10",
    toolId: "video-detection",
    title: "Political ad — YouTube link",
    preview: "No deepfake artifacts found. Authentic with 91% confidence.",
    timestamp: d(60 * 24 * 6 + 90),
    verdict: "low",
  },
];

export function groupSessionsByDate(sessions: Session[]): { label: string; items: Session[] }[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const groups: Record<string, Session[]> = {
    Today: [],
    Yesterday: [],
    "This week": [],
  };

  for (const s of sessions) {
    const d = new Date(s.timestamp.getFullYear(), s.timestamp.getMonth(), s.timestamp.getDate());
    if (d >= today) groups["Today"].push(s);
    else if (d >= yesterday) groups["Yesterday"].push(s);
    else if (d >= weekAgo) groups["This week"].push(s);
  }

  return Object.entries(groups)
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, items }));
}
