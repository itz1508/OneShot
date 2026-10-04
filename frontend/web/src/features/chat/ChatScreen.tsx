"use client";

import { useMemo } from "react";
import { createRsmClient } from "@/lib/rsm";
import { useChatIntake } from "./useChatIntake";
import { AttachmentChips } from "./AttachmentChips";
import { Composer } from "./Composer";
import { ChatLog } from "./ChatLog";

export function ChatScreen() {
  const rsm = useMemo(() => createRsmClient(), []);
  const intake = useChatIntake(rsm);

  return (
    <main className="flex min-h-screen flex-col pr-80">
      <header className="border-b px-4 py-3">
        <p className="text-xs uppercase tracking-wide opacity-50">RSM Chat Intake</p>
        <h1 className="mt-1 text-lg font-medium">New source</h1>
      </header>
      <ChatLog messages={intake.state.log} rsm={rsm} />
      <AttachmentChips
        items={intake.state.pending}
        onRemove={intake.removeItem}
        onSetHash={intake.setItemHash}
        busy={intake.state.submitting}
      />
      <Composer intake={intake} />
    </main>
  );
}
