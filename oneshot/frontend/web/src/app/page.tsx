"use client";

/**
 * Host application shell (SECONDARY-RSM product model).
 *
 * This file deliberately does NOT model the RSM domain. RSM is attached as a
 * right-rail control surface on every page via `RsmRail` in `app/layout.tsx`.
 * This page represents the CONSUMING APPLICATION — a minimum workspace shell
 * sufficient to demonstrate the RSM integration boundary.
 *
 * It is NOT:
 *   - a Bucket manager
 *   - an Ingest workflow
 *   - a Replay destination
 *   - an RSM dashboard
 *   - a chat / assistant / agent
 *
 * The small "Capture external context" disclosure is the ONLY ingestion
 * affordance from this shell. It is intentionally secondary — a contextual
 * entry into RSM at the system boundary — not the primary workflow.
 */

import { useCallback, useEffect, useState } from "react";
import { RsmHttpError } from "@/lib/rsm-client";
import { createRsmClient } from "@/lib/rsm";
import { getInteractionId } from "@/apps/features/rsm/rsmInteractionId";
import { ReaderTraceSurface } from "@/apps/features/rsm/ReaderTraceSurface";

const rsm = createRsmClient();

type HostState = {
  daemon: "unknown" | "ok" | "unreachable";
  schemaVersion: string | null;
  err: string | null;
  captureOpen: boolean;
  captureText: string;
  captureBusy: boolean;
  captureFlash: string | null;
  selectedBucketId: string | null;
};

function initial(): HostState {
  return {
    daemon: "unknown",
    schemaVersion: null,
    err: null,
    captureOpen: false,
    captureText: "",
    captureBusy: false,
    captureFlash: null,
    selectedBucketId: null,
  };
}

export default function HostWorkspace() {
  const [s, setS] = useState<HostState>(initial);

  const refreshSelection = useCallback(async () => {
    try {
      const rec = await rsm.getInteraction(getInteractionId());
      setS((cur) => ({ ...cur, selectedBucketId: rec.selected_bucket_id }));
    } catch {
      // Non-fatal — the host workspace must not crash on RSM read errors.
    }
  }, []);

  const ping = useCallback(async () => {
    try {
      const h = await rsm.health();
      setS((cur) => ({
        ...cur,
        daemon: "ok",
        schemaVersion: h.schema_version,
        err: null,
      }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setS((cur) => ({ ...cur, daemon: "unreachable", err: msg }));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!cancelled) {
        await ping();
        await refreshSelection();
      }
    })();
    const onUpdate = () => { void refreshSelection(); };
    window.addEventListener("rsm:source-updated", onUpdate);
    return () => {
      cancelled = true;
      window.removeEventListener("rsm:source-updated", onUpdate);
    };
  }, [ping, refreshSelection]);

  const captureAndSelect = useCallback(async () => {
    if (!s.captureText.trim()) return;
    setS((cur) => ({ ...cur, captureBusy: true, err: null, captureFlash: null }));
    try {
      // 1. Backend captures the external context as an authoritative Bucket.
      const payload = await rsm.ingestText(s.captureText, { kind: "pasted" });
      const bid = payload.bucket.bucket_id;
      // 2. Attach it to the current interaction so the RSM rail can replay it.
      await rsm.putInteraction(getInteractionId(), { selectedBucketId: bid });
      setS((cur) => ({
        ...initial(),
        daemon: cur.daemon,
        schemaVersion: cur.schemaVersion,
        selectedBucketId: bid,
        captureFlash: `Captured ${bid}. Use the RSM rail to replay.`,
      }));
      // Notify the rail (and this page's ReaderTrace) to refresh.
      window.dispatchEvent(new CustomEvent("rsm:source-updated"));
    } catch (e) {
      const code = e instanceof RsmHttpError ? e.code : null;
      const msg = e instanceof Error ? e.message : String(e);
      setS((cur) => ({
        ...cur,
        captureBusy: false,
        err: code ? `${code}: ${msg}` : msg,
      }));
    }
  }, [s.captureText]);

  return (
    <main className="min-h-screen px-6 py-10 pr-80">
      <header className="mx-auto max-w-3xl">
        <p className="text-xs uppercase tracking-wide opacity-50">Host application</p>
        <h1 className="mt-1 text-3xl font-semibold">Workspace</h1>
        <p className="mt-2 text-sm opacity-70">
          This is the consuming application. Do your normal work here. RSM is
          attached as the right-side control surface — it participates in the
          interaction when you turn it ON.
        </p>
      </header>

      <section className="mx-auto mt-10 max-w-3xl rounded-lg border p-6">
        <h2 className="text-sm font-medium">Your workspace</h2>
        <p className="mt-1 text-sm opacity-70">
          The host application&apos;s own content lives here. RSM does not own
          this area.
        </p>
        <div
          aria-label="host workspace content area (demonstration)"
          className="mt-4 h-48 rounded border border-dashed p-4 text-sm opacity-60"
        >
          <p>Primary user work goes here (chat, editor, review surface, …).</p>
          <p className="mt-2">
            In a real integration, this area belongs entirely to the host
            application. RSM never writes here.
          </p>
        </div>
      </section>

      <section className="mx-auto mt-6 max-w-3xl">
        <details
          open={s.captureOpen}
          onToggle={(e) =>
            setS((cur) => ({
              ...cur,
              captureOpen: (e.target as HTMLDetailsElement).open,
            }))
          }
          className="rounded border px-4 py-3 text-sm"
        >
          <summary className="cursor-pointer select-none opacity-80">
            Capture external context into RSM
          </summary>
          <p className="mt-2 text-xs opacity-60">
            This is a system-boundary entry point into RSM — not the primary
            workflow. The host application would normally invoke this when
            external context (a document, a page, a selection) is handed over.
          </p>

          <label htmlFor="capture-text" className="mt-3 block text-xs opacity-60">
            Captured text
          </label>
          <textarea
            id="capture-text"
            rows={3}
            value={s.captureText}
            onChange={(e) =>
              setS((cur) => ({ ...cur, captureText: e.target.value }))
            }
            disabled={s.captureBusy}
            className="mt-1 w-full rounded border p-2 font-mono text-xs"
            placeholder="External context handed in by the host app…"
          />
          <div className="mt-2 flex items-center justify-between">
            <p className="text-xs opacity-50">
              Captured context becomes the current RSM source for this
              interaction.
            </p>
            <button
              type="button"
              onClick={captureAndSelect}
              disabled={s.captureBusy || !s.captureText.trim()}
              className="rounded bg-black px-3 py-1 text-xs text-white disabled:opacity-40 dark:bg-white dark:text-black"
            >
              {s.captureBusy ? "Capturing…" : "Capture"}
            </button>
          </div>
          {s.captureFlash && (
            <p className="mt-2 text-xs text-emerald-700 dark:text-emerald-400">
              {s.captureFlash}
            </p>
          )}
          {s.err && <p className="mt-2 text-xs text-red-600">{s.err}</p>}
        </details>

        <ReaderTraceSurface bucketId={s.selectedBucketId} />
      </section>

      <footer className="mx-auto mt-10 max-w-3xl text-xs opacity-40">
        <p>
          daemon: {s.daemon}
          {s.schemaVersion ? ` (schema ${s.schemaVersion})` : ""}
        </p>
      </footer>
    </main>
  );
}
