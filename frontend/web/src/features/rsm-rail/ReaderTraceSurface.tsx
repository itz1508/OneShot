"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RsmClient, RsmHttpError } from "@/lib/rsm-client";
import type { FailureInfo, ReaderTrace } from "@/types/bucket";

const rsm = new RsmClient();

type Props = {
  /** Bucket to observe. When null the surface collapses to its idle label. */
  bucketId: string | null;
  /** Poll interval in ms while reading is in progress. */
  pollMs?: number;
};

type TraceState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; trace: ReaderTrace }
  | { kind: "error"; message: string };

/**
 * ReaderTrace surface (ADR 0013 context control surface; §7 of the Reader
 * architecture).
 *
 * Renders ONE continuous bar whose fill is `latest_index / discovered`, with
 * the latest File reached shown on the right. Isolated failures are listed
 * flat below.
 *
 * This is NOT a dashboard, NOT a workflow panel, NOT a per-File list of bars.
 * It only reflects authoritative backend Reader state.
 */
export function ReaderTraceSurface({ bucketId, pollMs = 1500 }: Props) {
  const [state, setState] = useState<TraceState>({ kind: "idle" });
  const prevIdRef = useRef<string | null>(null);

  const fetchTrace = useCallback(async (id: string) => {
    try {
      const trace = await rsm.readerTrace(id);
      setState({ kind: "ready", trace });
      return trace;
    } catch (e) {
      const code = e instanceof RsmHttpError ? e.code : null;
      const msg = e instanceof Error ? e.message : String(e);
      setState({ kind: "error", message: code ? `${code}: ${msg}` : msg });
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;
    if (!bucketId) {
      prevIdRef.current = null;
      void (async () => {
        if (!cancelled) setState({ kind: "idle" });
      })();
      return () => { cancelled = true; };
    }
    prevIdRef.current = bucketId;
    void (async () => {
      if (cancelled) return;
      setState({ kind: "loading" });
      const first = await fetchTrace(bucketId);
      if (cancelled || !first) return;
      // Reader is deterministic and synchronous server-side today; `complete`
      // is already `true` after one call. We still poll briefly so a future
      // async Reader can advance the bar without any browser-side invention.
      if (!first.complete) {
        timer = window.setInterval(() => {
          void (async () => {
            const next = await fetchTrace(bucketId);
            if (!next || next.complete) {
              if (timer !== null) {
                window.clearInterval(timer);
                timer = null;
              }
            }
          })();
        }, pollMs);
      }
    })();
    return () => {
      cancelled = true;
      if (timer !== null) window.clearInterval(timer);
    };
  }, [bucketId, fetchTrace, pollMs]);

  if (!bucketId) {
    return (
      <section
        aria-label="RSM Reader trace"
        className="mt-4 rounded border px-4 py-3 text-xs opacity-60"
      >
        Reader trace will appear here once external context is captured.
      </section>
    );
  }

  if (state.kind === "loading" || state.kind === "idle") {
    return (
      <section aria-label="RSM Reader trace" aria-busy="true" className="mt-4 rounded border px-4 py-3 text-xs">
        <ReaderBar discovered={0} latest={0} compact label="Preparing Reader\u2026" />
      </section>
    );
  }

  if (state.kind === "error") {
    return (
      <section aria-label="RSM Reader trace" className="mt-4 rounded border px-4 py-3 text-xs text-red-600">
        {state.message}
      </section>
    );
  }

  const t = state.trace;
  return (
    <section
      aria-label="RSM Reader trace"
      aria-live="polite"
      aria-atomic="false"
      className="mt-4 rounded border px-4 py-3 text-xs"
    >
      <ReaderBar discovered={t.discovered} latest={t.latest_index} />
      <ReaderCounts trace={t} />
      {t.failures.length > 0 && <FailuresList failures={t.failures} />}
    </section>
  );
}

function ReaderBar({
  discovered,
  latest,
  compact,
  label,
}: {
  discovered: number;
  latest: number;
  compact?: boolean;
  label?: string;
}) {
  const safeDiscovered = Math.max(0, discovered);
  const safeLatest = Math.max(0, Math.min(latest, safeDiscovered));
  const pct =
    safeDiscovered > 0 ? Math.round((safeLatest / safeDiscovered) * 100) : 0;
  const right = safeDiscovered > 0 ? safeLatest.toLocaleString() : "\u2014";

  return (
    <div className="flex items-center gap-3">
      <span className="font-mono opacity-60">| 1</span>
      <div
        className="relative h-2 flex-1 overflow-hidden rounded bg-black/10 dark:bg-white/10"
        role="progressbar"
        aria-label={label ?? "Reader coverage"}
        aria-valuemin={0}
        aria-valuemax={safeDiscovered || 1}
        aria-valuenow={safeLatest}
      >
        <div
          className="absolute inset-y-0 left-0 bg-black/70 motion-reduce:bg-black/60 dark:bg-white/70"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono tabular-nums">{right}</span>
      {compact && label && <span className="ml-2 opacity-50">{label}</span>}
    </div>
  );
}

function ReaderCounts({ trace }: { trace: ReaderTrace }) {
  return (
    <p className="mt-2 flex gap-4 opacity-70">
      <span>
        observed <strong className="tabular-nums">{trace.observed_count}</strong>
      </span>
      {trace.partial_count > 0 && (
        <span>
          partial <strong className="tabular-nums">{trace.partial_count}</strong>
        </span>
      )}
      {trace.failed_count > 0 && (
        <span>
          failed <strong className="tabular-nums">{trace.failed_count}</strong>
        </span>
      )}
      <span className="ml-auto opacity-50">
        {trace.complete ? "complete" : "reading\u2026"}
      </span>
    </p>
  );
}

function FailuresList({ failures }: { failures: FailureInfo[] }) {
  // Keep the UI small: list the latest 8 failures (full list is in the
  // backend's trace).
  const latest = failures.slice(-8).reverse();
  return (
    <details className="mt-2 opacity-80">
      <summary className="cursor-pointer select-none">
        Failures ({failures.length})
      </summary>
      <ul className="mt-1 space-y-0.5 font-mono text-[11px] opacity-70">
        {latest.map((f) => (
          <li key={f.file_id}>
            {f.index.toLocaleString()} \u2014 {f.reason}
          </li>
        ))}
        {failures.length > latest.length && (
          <li className="opacity-50">\u2026 {failures.length - latest.length} earlier</li>
        )}
      </ul>
    </details>
  );
}
