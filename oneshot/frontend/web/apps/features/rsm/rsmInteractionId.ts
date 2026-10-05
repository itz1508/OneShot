"use client";

/**
 * Opaque, per-tab interaction id. V3's RSM delivery is per-interaction;
 * the runtime (the UI, in our case) owns the id. We regenerate it on each
 * page load, matching the daemon's process-lifetime discipline for
 * InteractionRecord (ADR 0009).
 */
let _id: string | null = null;

function _makeId(): string {
  // Robust across environments: prefer crypto.randomUUID when available.
  const g = globalThis as unknown as { crypto?: { randomUUID?: () => string } };
  if (g.crypto && typeof g.crypto.randomUUID === "function") {
    return `ui-${g.crypto.randomUUID()}`;
  }
  const rand = Math.random().toString(36).slice(2);
  return `ui-${Date.now().toString(36)}-${rand}`;
}

export function getInteractionId(): string {
  if (_id === null) _id = _makeId();
  return _id;
}

export function resetInteractionId(): string {
  _id = _makeId();
  return _id;
}
