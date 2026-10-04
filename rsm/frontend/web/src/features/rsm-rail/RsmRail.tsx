"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RsmClient, RsmHttpError } from "@/lib/rsm-client";
import type { InteractionRecord, StreamPayload } from "@/types/bucket";
import { getInteractionId } from "./rsmInteractionId";
import { ReplayStreamingSurface, type StreamStage } from "./ReplayStreamingSurface";

const rsm = new RsmClient();

type Props = {
  /** When true, the rail opens the ephemeral stream surface on mount (V3 auto-delivery). */
  autoStreamOnMount?: boolean;
};

type RailState = {
  record: InteractionRecord | null;
  lastPayload: StreamPayload | null;
  err: string | null;
  loadingRecord: boolean;
  loadingBuckets: boolean;
  buckets: string[];
};

const DEFAULT_BUDGET = { budgetUnit: "characters" as const, budgetValue: 2000, reduce: "null" as const };

/**
 * V3 RSM right rail — context control surface (ADR 0013).
 *
 * Visible, non-modal, non-workspace. Owns:
 *   - ON/OFF switch (APG switch pattern).
 *   - Source selection (ingested Bucket ids from the daemon).
 *   - Snapshot readiness + Representation (preserved | reduced).
 *   - Context budget usage.
 *   - Manual [Replay] button — triggers the ephemeral stream surface.
 *
 * Does NOT own Main Chat, task list, dashboards, or persistent conversation
 * history.
 */
export function RsmRail({ autoStreamOnMount = false }: Props) {
  const interactionId = getInteractionId();

  const [open, setOpen] = useState<boolean>(true);
  const [state, setState] = useState<RailState>({
    record: null,
    lastPayload: null,
    err: null,
    loadingRecord: false,
    loadingBuckets: false,
    buckets: [],
  });
  const [stage, setStage] = useState<StreamStage>("idle");

  // Abort controller for an in-flight stream.
  const abortRef = useRef<AbortController | null>(null);

  const loadRecord = useCallback(async () => {
    setState((s) => ({ ...s, loadingRecord: true, err: null }));
    try {
      const record = await rsm.getInteraction(interactionId);
      setState((s) => ({ ...s, record, loadingRecord: false }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setState((s) => ({ ...s, loadingRecord: false, err: msg }));
    }
  }, [interactionId]);

  const loadBuckets = useCallback(async () => {
    setState((s) => ({ ...s, loadingBuckets: true }));
    try {
      const buckets = await rsm.listBuckets();
      setState((s) => ({ ...s, buckets, loadingBuckets: false }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setState((s) => ({ ...s, loadingBuckets: false, err: msg }));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!cancelled) {
        await loadRecord();
        await loadBuckets();
      }
    })();
    const onUpdate = () => {
      void loadRecord();
      void loadBuckets();
    };
    window.addEventListener("rsm:source-updated", onUpdate);
    return () => {
      cancelled = true;
      window.removeEventListener("rsm:source-updated", onUpdate);
    };
  }, [loadRecord, loadBuckets]);

  const runStream = useCallback(async () => {
    const record = state.record;
    if (!record || !record.rsm_enabled || !record.selected_bucket_id) {
      setStage("failed");
      setState((s) => ({ ...s, err: "RSM is OFF or no source selected" }));
      return;
    }
    setStage("preparing");
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      setStage("streaming");
      let payload: StreamPayload | null = null;
      for await (const chunk of rsm.streamInteraction(interactionId, {
        ...DEFAULT_BUDGET,
        signal: ac.signal,
      })) {
        payload = chunk;
      }
      if (payload) {
        setState((s) => ({ ...s, lastPayload: payload }));
        setStage("complete");
      } else {
        setStage("failed");
      }
    } catch (e) {
      if ((e as { name?: string } | null)?.name === "AbortError") {
        setStage("cancelled");
        return;
      }
      const code = e instanceof RsmHttpError ? e.code : null;
      const msg = e instanceof Error ? e.message : String(e);
      setState((s) => ({ ...s, err: code ? `${code}: ${msg}` : msg }));
      setStage("failed");
    } finally {
      abortRef.current = null;
      // Refresh last_streamed_at + record.
      void loadRecord();
    }
  }, [interactionId, loadRecord, state.record]);

  const dismissStream = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    setStage("idle");
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (autoStreamOnMount && state.record && state.record.rsm_enabled && state.record.selected_bucket_id) {
      void (async () => { if (!cancelled) await runStream(); })();
    }
    return () => { cancelled = true; };
    // Intentionally depends only on the record identity; subsequent toggles use [Replay].
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.record?.interaction_id]);

  const setEnabled = useCallback(async (next: boolean) => {
    try {
      const updated = await rsm.putInteraction(interactionId, { rsmEnabled: next });
      setState((s) => ({ ...s, record: updated, err: null }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setState((s) => ({ ...s, err: msg }));
    }
  }, [interactionId]);

  const setBucket = useCallback(async (bucketId: string | null) => {
    try {
      const updated = await rsm.putInteraction(interactionId, { selectedBucketId: bucketId });
      setState((s) => ({ ...s, record: updated, err: null }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setState((s) => ({ ...s, err: msg }));
    }
  }, [interactionId]);

  const record = state.record;
  const snapshot = state.lastPayload?.snapshot ?? null;
  const representation: string = snapshot ? snapshot.content.kind.toUpperCase() : "\u2014";
  const snapReady = snapshot ? "READY" : "NOT READY";
  const sizeChars = snapshot?.content.size_chars ?? 0;
  const budgetValue = snapshot?.context_budget.value ?? DEFAULT_BUDGET.budgetValue;
  const budgetUnit = snapshot?.context_budget.unit ?? DEFAULT_BUDGET.budgetUnit;
  const contextPct = budgetValue > 0
    ? Math.min(100, Math.round((snapshot ? snapshot.source_size_chars : sizeChars) * 100 / Math.max(1, budgetValue)))
    : 0;

  return (
    <>
      {!open && (
        <button
          type="button"
          aria-expanded={false}
          aria-controls="rsm-rail-panel"
          onClick={() => setOpen(true)}
          className="fixed right-2 top-1/2 z-30 -translate-y-1/2 rounded border bg-white px-2 py-1 text-xs shadow dark:bg-neutral-900"
        >
          RSM &gt;
        </button>
      )}

      {open && (
        <aside
          id="rsm-rail-panel"
          role="complementary"
          aria-label="RSM external context"
          className="fixed right-0 top-0 z-30 flex h-full w-72 flex-col border-l bg-white p-4 text-sm shadow-lg dark:bg-neutral-900"
        >
          <header className="flex items-center justify-between">
            <h2 className="text-base font-medium">RSM</h2>
            <button
              type="button"
              aria-expanded={true}
              aria-controls="rsm-rail-panel"
              onClick={() => setOpen(false)}
              className="rounded border px-2 py-0.5 text-xs"
            >
              Hide
            </button>
          </header>

          <section className="mt-4 space-y-1" aria-live="polite">
            <p>
              <span className="opacity-60">Sources: </span>
              <strong>{state.loadingBuckets ? "\u2026" : state.buckets.length}</strong>
            </p>
            <p>
              <span className="opacity-60">Snapshot: </span>
              <strong>{snapReady}</strong>
            </p>
            <p>
              <span className="opacity-60">Representation: </span>
              <strong>{representation}</strong>
            </p>
            <p>
              <span className="opacity-60">Context: </span>
              <strong>{contextPct}%</strong>
              <span className="opacity-50"> ({budgetValue} {budgetUnit})</span>
            </p>
          </section>

          <section className="mt-4">
            <div className="flex items-center justify-between gap-2">
              <label className="text-xs opacity-60" htmlFor="rsm-switch">RSM</label>
              <button
                id="rsm-switch"
                type="button"
                role="switch"
                aria-checked={!!record?.rsm_enabled}
                disabled={state.loadingRecord || !record}
                onClick={() => record && setEnabled(!record.rsm_enabled)}
                className={
                  "relative inline-flex h-6 w-11 items-center rounded-full transition-colors " +
                  (record?.rsm_enabled ? "bg-black dark:bg-white" : "bg-black/20 dark:bg-white/20")
                }
              >
                <span
                  aria-hidden="true"
                  className={
                    "inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform dark:bg-neutral-900 " +
                    (record?.rsm_enabled ? "translate-x-5" : "translate-x-1")
                  }
                />
                <span className="sr-only">{record?.rsm_enabled ? "ON" : "OFF"}</span>
              </button>
            </div>

            <label className="mt-3 block text-xs opacity-60" htmlFor="rsm-bucket">Source Bucket</label>
            <select
              id="rsm-bucket"
              value={record?.selected_bucket_id ?? ""}
              onChange={(e) => setBucket(e.target.value || null)}
              className="mt-1 w-full rounded border px-2 py-1 text-xs"
              disabled={!record}
            >
              <option value="">\u2014 none \u2014</option>
              {state.buckets.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          </section>

          <section className="mt-4">
            <button
              type="button"
              onClick={runStream}
              disabled={!record?.rsm_enabled || !record?.selected_bucket_id || stage === "preparing" || stage === "streaming"}
              className="w-full rounded bg-black px-3 py-1 text-sm text-white disabled:opacity-40 dark:bg-white dark:text-black"
            >
              Replay
            </button>
            <p className="mt-1 text-xs opacity-50">
              Delivers the current Snapshot via ReplayStreaming.
            </p>
          </section>

          {state.err && (
            <p className="mt-3 text-xs text-red-600">{state.err}</p>
          )}

          {record?.last_streamed_at && (
            <p className="mt-3 text-xs opacity-40">
              last streamed: <time dateTime={record.last_streamed_at}>{record.last_streamed_at}</time>
            </p>
          )}
        </aside>
      )}

      <ReplayStreamingSurface
        stage={stage}
        errorMessage={state.err}
        onDismiss={dismissStream}
      />
    </>
  );
}
