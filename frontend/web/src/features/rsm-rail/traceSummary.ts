/**
 * Reader panel summary — derived strictly from the authoritative ReaderTrace
 * payload delivered by the daemon (§9: the browser never invents progress).
 *
 * Vision/Text are a partition of the OBSERVED files: vision-flagged
 * observations vs. everything else. Both come from `coverage[]`, which the
 * backend derives from the actual Reader event stream.
 */
import type { ReaderTrace } from "@/types/bucket";

export type TraceSummary = {
  observed: number;
  discovered: number;
  vision: number;
  text: number;
  status: "READING" | "COMPLETE";
};

export function summarizeTrace(trace: ReaderTrace): TraceSummary {
  const vision = trace.coverage.filter(
    (f) => f.vision && f.status === "OBSERVED",
  ).length;
  return {
    observed: trace.observed_count,
    discovered: trace.discovered,
    vision,
    text: Math.max(0, trace.observed_count - vision),
    status: trace.complete ? "COMPLETE" : "READING",
  };
}
