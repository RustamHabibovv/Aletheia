import { ApiConversation } from "./api";
import { ToolId } from "./types";

export interface Session {
  id: string;
  toolId: ToolId;
  title: string;
  timestamp: Date;
}

export function conversationToSession(c: ApiConversation): Session {
  return {
    id: c.id,
    toolId: "general",
    title: c.title,
    timestamp: new Date(c.updated_at),
  };
}

export function groupSessionsByDate(sessions: Session[]): { label: string; items: Session[] }[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const groups: Record<string, Session[]> = {
    Today: [],
    Yesterday: [],
    "This week": [],
    Older: [],
  };

  for (const s of sessions) {
    const d = new Date(s.timestamp.getFullYear(), s.timestamp.getMonth(), s.timestamp.getDate());
    if (d >= today) groups["Today"].push(s);
    else if (d >= yesterday) groups["Yesterday"].push(s);
    else if (d >= weekAgo) groups["This week"].push(s);
    else groups["Older"].push(s);
  }

  return Object.entries(groups)
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, items }));
}
