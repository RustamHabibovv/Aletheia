"use client";

import { useState } from "react";
import Sidebar from "@/components/Sidebar";
import ChatInterface from "@/components/ChatInterface";
import { ToolId } from "@/lib/types";
import { Session } from "@/lib/sessions";

export default function Home() {
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [activeTool, setActiveTool] = useState<ToolId>("general");

  function handleSelectSession(session: Session) {
    setActiveSession(session);
    setActiveTool(session.toolId);
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Sidebar
        activeSessionId={activeSession?.id ?? null}
        onSelectSession={handleSelectSession}
        onNewSession={() => setActiveSession(null)}
      />
      <ChatInterface activeTool={activeTool} session={activeSession} />
    </div>
  );
}
