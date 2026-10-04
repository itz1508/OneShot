"use client";

import { useState } from "react";
import type { InputItem } from "./useChatIntake";
import { isValidSha256Hex, labelForCode } from "./pack";

type Props = {
  items: InputItem[];
  onRemove: (id: string) => void;
  onSetHash: (id: string, hex: string | undefined) => void;
  busy: boolean;
};

function stateBadge(s: InputItem["state"]): { label: string; className: string } {
  switch (s) {
    case "QUEUED":    return { label: "Queued", className: "opacity-60" };
    case "STAGING":   return { label: "Preparing…", className: "text-amber-700" };
    case "LOADING":   return { label: "Loading…", className: "text-amber-700" };
    case "VERIFYING": return { label: "Verifying…", className: "text-amber-700" };
    case "ACCEPTED":  return { label: "Accepted", className: "text-emerald-700" };
    case "REJECTED":  return { label: "Rejected", className: "text-red-700" };
    case "FAILED":    return { label: "Failed", className: "text-red-700" };
    case "CANCELLED": return { label: "Cancelled", className: "opacity-60" };
  }
}

export function AttachmentChips({ items, onRemove, onSetHash, busy }: Props) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2 border-b border-dashed p-2 text-xs">
      {items.map((it) => (
        <ChipRow
          key={it.id}
          item={it}
          onRemove={onRemove}
          onSetHash={onSetHash}
          busy={busy}
        />
      ))}
    </div>
  );
}

function ChipRow({
  item,
  onRemove,
  onSetHash,
  busy,
}: {
  item: InputItem;
  onRemove: (id: string) => void;
  onSetHash: (id: string, hex: string | undefined) => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [hex, setHex] = useState(item.expectedHash ?? "");
  const badge = stateBadge(item.state);
  const removable = !busy || item.state === "STAGING" || item.state === "LOADING" || item.state === "VERIFYING";

  return (
    <div className="flex items-center gap-2 rounded border px-2 py-1">
      <span className="font-mono">{item.label}</span>
      {item.file && <span className="opacity-50">· {(item.file.size / 1024).toFixed(1)} KB</span>}
      <span className={`${badge.className}`}>· {badge.label}</span>
      {item.state === "REJECTED" || item.state === "FAILED" ? (
        <span className="text-[10px] opacity-70" title={item.errorMessage ?? ""}>
          — {labelForCode(item.errorCode, "Failed")}
        </span>
      ) : null}
      {item.state === "ACCEPTED" && item.bucketId ? (
        <span className="font-mono text-[10px] opacity-60">{item.bucketId.slice(0, 12)}…</span>
      ) : null}
      <button
        type="button"
        className="ml-1 text-xs opacity-50 hover:opacity-100"
        onClick={() => setOpen((v) => !v)}
      >
        hash
      </button>
      {removable && (
        <button
          type="button"
          onClick={() => onRemove(item.id)}
          className="opacity-50 hover:opacity-100"
          aria-label="Remove"
        >
          ×
        </button>
      )}
      {open && (
        <div className="ml-2 flex items-center gap-1">
          <input
            type="text"
            inputMode="text"
            spellCheck={false}
            autoCapitalize="none"
            autoCorrect="off"
            placeholder="sha256 (64 hex)"
            value={hex}
            onChange={(e) => setHex(e.target.value)}
            className="w-56 rounded border px-1 py-0.5 font-mono text-[10px]"
            disabled={busy || item.state !== "QUEUED"}
          />
          <button
            type="button"
            disabled={busy || item.state !== "QUEUED"}
            onClick={() => onSetHash(item.id, hex.trim() ? hex.trim().toLowerCase() : undefined)}
            className={`rounded px-1.5 py-0.5 text-[10px] ${
              isValidSha256Hex(hex) ? "bg-black text-white dark:bg-white dark:text-black" : "opacity-40"
            }`}
          >
            set
          </button>
        </div>
      )}
    </div>
  );
}
