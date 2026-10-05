/**
 * Inline-stub tests for `pack.ts` (no vitest, no new dev dependency).
 *
 * Run with:
 *     bun run src/features/chat/__tests__/pack.test.ts
 *   or:
 *     npx tsx frontend/web/src/features/chat/__tests__/pack.test.ts
 *
 * The test file itself is the harness — one `expect(label, cond)` per assertion.
 */

import { kindFor, isValidSha256Hex, labelForCode, TERMINAL_STATES } from "../pack";

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

function mockFile(name: string, type = ""): File {
  // Node 18+ ships a global File constructor; in the browser likewise.
  return new File([new Uint8Array([0])], name, { type });
}

console.log("pack.test.ts");

expect("md → markdown", kindFor(mockFile("notes.md")) === "markdown");
expect("markdown ext → markdown", kindFor(mockFile("notes.markdown")) === "markdown");
expect("pdf → pdf", kindFor(mockFile("doc.pdf")) === "pdf");
expect("zip → zip", kindFor(mockFile("pack.zip")) === "zip");
expect("txt → text", kindFor(mockFile("notes.txt")) === "text");
expect("log → text", kindFor(mockFile("app.log")) === "text");
expect("json → chatgpt_export", kindFor(mockFile("conv.json")) === "chatgpt_export");
expect("png → opaque", kindFor(mockFile("pic.png")) === "opaque");

expect("64 hex ok", isValidSha256Hex("a".repeat(64)));
expect("63 hex rejected", !isValidSha256Hex("a".repeat(63)));
expect("64 non-hex rejected", !isValidSha256Hex("z".repeat(64)));

expect("HASH_MISMATCH label", labelForCode("HASH_MISMATCH").toLowerCase().includes("hash"));
expect("ARCHIVE_SAFETY label", labelForCode("ARCHIVE_SAFETY").toLowerCase().includes("archive"));
expect("null code falls back", labelForCode(null) === "Rejected");
expect("unknown code preserved", labelForCode("WEIRD").endsWith("WEIRD"));

expect("ACCEPTED terminal", TERMINAL_STATES.has("ACCEPTED"));
expect("STAGING not terminal", !TERMINAL_STATES.has("STAGING"));

console.log(`\nsummary: ${_passed} passed, ${_failed} failed`);
if (_failed > 0) process.exit(1);
