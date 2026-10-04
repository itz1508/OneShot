"use client";

import { useCallback } from "react";
import type { ChatMessage } from "./useChatIntake";
import { RsmClient } from "@/lib/rsm-client";
import { getInteractionId } from "@/features/rsm-rail/rsmInteractionId";

type Props = {
  messages: ChatMessage[];
  rsm: RsmClient;
};

export function ChatLog({ messages, rsm }: Props) {
  const openInReplay = useCallback(
    async (bid: string) => {
      try {
        await rsm.putInteraction(getInteractionId(), { selectedBucketId: bid });
        window.dispatchEvent(new CustomEvent("rsm:source-updated"));
      } catch (e) {
        // The chat log must remain usable even if replay wiring fails.
        console.error(e);
      }
    },
    [rsm],
  );
  return (
    <div className="flex-1 overflow-y-auto p-4">
      {messages.length === 0 ? (
        <p className="mt-16 text-center text-xs opacity-40">
          Type or paste a message, drag/drop files, or attach a .pdf / .md /
          .zip to load into RSM.
        </p>
      ) : (
        <ul className="mx-auto flex max-w-2xl flex-col gap-3">
          {messages.map((m) => (
            <li
              key={m.id}
              className={`rounded-lg px-3 py-2 text-sm ${
                m.kind === "user" ? "bg-black/5 dark:bg-white/5 self-end max-w-[85%]"
                                   : "self-start max-w-[85%]"
              }`}
            >
              <div className={m.kind === "user" ? "whitespace-pre-wrap" : ""}>{m.text}</div>
              {m.kind === "system" && m.bucketId ? (
                <button
                  type="button"
                  onClick={() => openInReplay(m.bucketId!)}
                  className="mt-1 inline-flex items-center gap-1 text-[11px] underline opacity-70 hover:opacity-100"
                >
                  open in replay
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
