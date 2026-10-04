"use client";

import { useEffect, useRef } from "react";

export type StreamStage = "idle" | "preparing" | "streaming" | "complete" | "failed" | "cancelled";

type Props = {
  stage: StreamStage;
  errorMessage?: string | null;
  onDismiss?: () => void;
  /** When set, the surface auto-dismisses on `complete` after this many ms (default 1200). */
  autoDismissAfterMs?: number;
  /** Allow styling injection without turning the surface into a workspace. */
  className?: string;
};

/**
 * V3 ephemeral ReplayStreaming surface (ADR 0013).
 *
 * - `role="status" aria-live="polite"` so a screen reader announces stage
 *   transitions without stealing focus.
 * - Stage-based (not fake-percentage) indicator; respects `prefers-reduced-motion`.
 * - `Escape` dismisses; the parent is expected to pass `onDismiss`.
 * - Returns `null` for `idle` so the surface is truly ephemeral.
 */
export function ReplayStreamingSurface({
  stage,
  errorMessage,
  onDismiss,
  autoDismissAfterMs = 1200,
  className,
}: Props) {
  const dismissRef = useRef(onDismiss);
  useEffect(() => { dismissRef.current = onDismiss; }, [onDismiss]);

  useEffect(() => {
    if (stage !== "complete" || !dismissRef.current) return;
    const t = window.setTimeout(() => { dismissRef.current?.(); }, autoDismissAfterMs);
    return () => window.clearTimeout(t);
  }, [stage, autoDismissAfterMs]);

  useEffect(() => {
    if (stage === "idle") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismissRef.current?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stage]);

  if (stage === "idle") return null;

  const headline =
    stage === "preparing" ? "Preparing external context" :
    stage === "streaming" ? "Streaming source context\u2026" :
    stage === "complete" ? "External context delivered" :
    stage === "cancelled" ? "Delivery cancelled" :
    "Delivery failed";

  const subline =
    stage === "complete" ? "The RSM Snapshot has been delivered to the runtime." :
    stage === "failed" ? (errorMessage ?? "The daemon returned an error.") :
    stage === "cancelled" ? "The stream was cancelled before delivery completed." :
    "RSM is preparing a bounded, derived representation of your source.";

  const live: "polite" | "assertive" = stage === "failed" ? "assertive" : "polite";

  return (
    <div
      role="status"
      aria-live={live}
      aria-atomic="true"
      data-stage={stage}
      className={
        "fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4 motion-safe:animate-[fadeIn_120ms_ease-out] " +
        (className ?? "")
      }
    >
      <div className="min-w-[280px] max-w-md rounded-lg border bg-white p-6 shadow-lg dark:bg-neutral-900">
        <h2 className="text-base font-medium">{headline}</h2>
        <p className="mt-1 text-sm opacity-70">{subline}</p>

        {/* Indeterminate indicator — not fake numeric progress. */}
        {(stage === "preparing" || stage === "streaming") && (
          <div
            className="mt-4 h-2 w-full overflow-hidden rounded bg-black/5 dark:bg-white/10"
            aria-hidden="true"
          >
            <div className="h-full w-1/3 rounded bg-black/60 dark:bg-white/60 motion-safe:animate-[slide_1200ms_ease-in-out_infinite] motion-reduce:w-full motion-reduce:opacity-30" />
          </div>
        )}

        <div className="mt-5 flex items-center justify-between gap-2">
          <span className="text-xs uppercase opacity-50">{stage}</span>
          <button
            type="button"
            onClick={() => dismissRef.current?.()}
            className="rounded border px-3 py-1 text-xs"
          >
            {stage === "preparing" || stage === "streaming" ? "Cancel" : "Dismiss"}
          </button>
        </div>
      </div>

      {/* Keyframes used by the indeterminate bar; honour reduced motion via `motion-safe`. */}
      <style jsx global>{`
        @keyframes slide {
          0%   { transform: translateX(-100%); }
          50%  { transform: translateX(50%); }
          100% { transform: translateX(300%); }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
      `}</style>
    </div>
  );
}
