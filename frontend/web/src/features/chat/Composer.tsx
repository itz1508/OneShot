"use client";

import { useCallback, useMemo, useRef } from "react";
import type { UseChatIntake } from "./useChatIntake";

type Props = {
  intake: UseChatIntake;
};

/** Feature-detect `webkitdirectory` support. */
function supportsDirectoryPicker(): boolean {
  if (typeof document === "undefined") return false;
  const input = document.createElement("input");
  input.type = "file";
  return "webkitdirectory" in input;
}

export function Composer({ intake }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const dirRef = useRef<HTMLInputElement>(null);
  const supportsDir = useMemo(() => supportsDirectoryPicker(), []);
  const canSubmit = useMemo(() => {
    if (intake.state.submitting) return false;
    if (intake.state.draftText.trim().length > 0) return true;
    return intake.state.pending.some((p) => p.state === "QUEUED");
  }, [intake.state.draftText, intake.state.pending, intake.state.submitting]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const files = Array.from(e.dataTransfer.files ?? []);
      if (files.length) intake.addFiles(files);
    },
    [intake],
  );

  return (
    <div
      className="border-t p-3"
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
    >
      <div className="mx-auto flex max-w-2xl flex-col gap-2 rounded-lg border p-2">
        <textarea
          rows={2}
          value={intake.state.draftText}
          onChange={(e) => intake.setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey) {
              e.preventDefault();
              void intake.submit();
            }
          }}
          placeholder="Type or paste a message…"
          className="w-full resize-none bg-transparent px-2 py-1 text-sm outline-none"
          disabled={intake.state.submitting}
        />
        <div className="flex items-center gap-2 border-t px-1 pt-2 text-xs">
          <button
            type="button"
            className="rounded border px-2 py-1 opacity-80 hover:opacity-100"
            onClick={() => fileRef.current?.click()}
            disabled={intake.state.submitting}
            aria-label="Attach files"
          >
            📎 Attach
          </button>
          {supportsDir && (
            <button
              type="button"
              className="rounded border px-2 py-1 opacity-80 hover:opacity-100"
              onClick={() => dirRef.current?.click()}
              disabled={intake.state.submitting}
              aria-label="Attach folder"
              title="Folder selection is supported on Chromium / Firefox; children are enumerated as individual sources."
            >
              📁 Folder
            </button>
          )}
          <span className="ml-auto opacity-50">Enter sends · Shift+Enter newline</span>
          <button
            type="button"
            className={`rounded px-3 py-1 ${
              canSubmit
                ? "bg-black text-white dark:bg-white dark:text-black"
                : "opacity-40"
            }`}
            onClick={() => void intake.submit()}
            disabled={!canSubmit}
          >
            {intake.state.submitting ? "Sending…" : "Send"}
          </button>
        </div>
      </div>
      <input
        ref={fileRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length) intake.addFiles(files);
          e.target.value = "";
        }}
      />
      {supportsDir && (
        <input
          ref={dirRef}
          type="file"
          multiple
          className="hidden"
          // @ts-expect-error — vendor attribute
          webkitdirectory=""
          directory=""
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            if (files.length) intake.addFiles(files);
            e.target.value = "";
          }}
        />
      )}
    </div>
  );
}
