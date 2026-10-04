/**
 * Ad-hoc test for traceSummary — same runner convention as chat/__tests__/pack.test.ts:
 *   cd frontend/web && pnpm dlx tsx src/features/rsm-rail/__tests__/traceSummary.test.ts
 */
import { summarizeTrace } from "../traceSummary";
import type { FileCoverage, ReaderTrace } from "@/types/bucket";

let _passed = 0;
let _failed = 0;
function expect(label: string, cond: unknown): void {
  if (cond) {
    _passed += 1;
    console.log(`  ok  — ${label}`);
  } else {
    _failed += 1;
    console.error(`  NOT OK — ${label}`);
  }
}

function cov(
  index: number,
  status: FileCoverage["status"],
  vision: boolean,
): FileCoverage {
  return {
    file_id: `b:f${index}`,
    index,
    status,
    method: vision ? "vision" : "text",
    vision,
    observed_bytes: 10,
    observed_chars: 10,
  };
}

function trace(partial: Partial<ReaderTrace>): ReaderTrace {
  return {
    schema_version: "1",
    bucket_id: "b",
    discovered: 0,
    latest_index: 0,
    observed_count: 0,
    partial_count: 0,
    failed_count: 0,
    complete: false,
    failures: [],
    coverage: [],
    ...partial,
  };
}

console.log("traceSummary.test.ts");

// Mockup case: 10,000 discovered, 247 observed = 42 vision + 205 text.
const mockup = summarizeTrace(
  trace({
    discovered: 10_000,
    latest_index: 247,
    observed_count: 247,
    coverage: [
      ...Array.from({ length: 42 }, (_, i) => cov(i + 1, "OBSERVED", true)),
      ...Array.from({ length: 205 }, (_, i) => cov(i + 43, "OBSERVED", false)),
    ],
  }),
);
expect("mockup observed=247", mockup.observed === 247);
expect("mockup discovered=10,000", mockup.discovered === 10_000);
expect("mockup vision=42", mockup.vision === 42);
expect("mockup text=205", mockup.text === 205);
expect("vision + text == observed", mockup.vision + mockup.text === mockup.observed);
expect("reading status", mockup.status === "READING");

// Completion flips status only.
expect(
  "complete status",
  summarizeTrace(trace({ complete: true, observed_count: 1, discovered: 1 })).status ===
    "COMPLETE",
);

// Failed / partial coverage never inflates vision or text counts.
const mixed = summarizeTrace(
  trace({
    observed_count: 1,
    partial_count: 1,
    failed_count: 1,
    discovered: 3,
    coverage: [
      cov(1, "OBSERVED", true),
      cov(2, "PARTIAL", true),
      cov(3, "FAILED", false),
    ],
  }),
);
expect("failed file not counted as vision", mixed.vision === 1);
expect("partial file not counted as text", mixed.text === 0);
expect("counts never negative", mixed.text >= 0);

// Empty trace is safe.
const empty = summarizeTrace(trace({}));
expect("empty observed=0", empty.observed === 0);
expect("empty vision=0 text=0", empty.vision === 0 && empty.text === 0);

console.log(`\nsummary: ${_passed} passed, ${_failed} failed`);
if (_failed > 0) process.exit(1);
