"use client";

import { useEffect, useState, useCallback } from "react";
import Sidebar from "@/components/Sidebar";
import ChatInterface from "@/components/ChatInterface";
import { ToolId } from "@/lib/types";
import { Session, conversationToSession } from "@/lib/sessions";
import { getConversations, createConversation } from "@/lib/api";

export default function Home() {
  const [conversations, setConversations] = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [activeTool, setActiveTool] = useState<ToolId>("general");

  const loadConversations = useCallback(async () => {
    try {
      const data = await getConversations();
      setConversations(data.map(conversationToSession));
    } catch {
      // silently ignore — user may not be authenticated yet
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  async function handleNewSession() {
    setActiveSession(null);
    setActiveTool("general");
  }

  function handleSelectSession(session: Session) {
    setActiveSession(session);
    setActiveTool(session.toolId);
  }

  async function handleConversationCreated(id: string, title: string) {
    // Refresh sidebar after a new conversation is created mid-chat
    await loadConversations();
    const newSession: Session = { id, toolId: activeTool, title, timestamp: new Date() };
    setActiveSession(newSession);
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Sidebar
        sessions={conversations}
        activeSessionId={activeSession?.id ?? null}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
      />
      <ChatInterface
        activeTool={activeTool}
        onToolChange={setActiveTool}
        session={activeSession}
        onConversationCreated={handleConversationCreated}
      />
    </div>
  );
}
