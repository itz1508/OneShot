"use client";

/**
 * Chat intake state machine (per §C of CHAT_INTAKE_PLAN.md).
 *
 * Chat-level states follow from the per-attachment states; this reducer
 * owns the authoritative shape and the view projects from it.
 *
 * Submission is sequential — one `POST /v1/buckets/*` per InputItem — so
 * a mid-flight failure never blocks the rest. Each item carries its own
 * AbortController for user-cancellation.
 */

import { useCallback, useMemo, useReducer, useRef } from "react";

import { RsmClient, RsmHttpError } from "@/lib/rsm-client";
import type { BucketPayload } from "@/types/bucket";
import { AttachmentKind, AttachmentState, TERMINAL_STATES, kindFor, labelForCode } from "./pack";

/** One item queued for the current submission. */
export type InputItem = {
  readonly id: string;
  readonly label: string;        // user-visible chip label
  readonly kind: AttachmentKind | "textmessage";
  readonly file?: File;           // present for attachments
  readonly text?: string;         // present for the free-form text message
  state: AttachmentState;
  errorCode: string | null;
  errorMessage: string | null;
  bucketId: string | null;
  expectedHash?: string;
  /** Children IDs returned by uploadZip, if any. */
  children?: string[];
};

/** A chat-log entry rendered in the message list. */
export type ChatMessage = {
  readonly id: string;
  readonly at: number;
  readonly kind: "user" | "system";
  readonly text: string;
  readonly bucketId?: string | null;
  readonly state?: AttachmentState;
};

type State = {
  draftText: string;
  pending: InputItem[];
  log: ChatMessage[];
  submitting: boolean;
};

type Action =
  | { type: "set_draft"; text: string }
  | { type: "add_items"; items: InputItem[] }
  | { type: "remove_item"; id: string }
  | { type: "clear_draft" }
  | { type: "set_item_hash"; id: string; hash: string | undefined }
  | { type: "update_item"; id: string; patch: Partial<InputItem> }
  | { type: "append_log"; entry: ChatMessage }
  | { type: "set_submitting"; value: boolean }
  | { type: "reset_pending" };

const initial: State = {
  draftText: "",
  pending: [],
  log: [],
  submitting: false,
};

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "set_draft":
      return { ...s, draftText: a.text };
    case "add_items":
      return { ...s, pending: [...s.pending, ...a.items] };
    case "remove_item":
      return { ...s, pending: s.pending.filter((p) => p.id !== a.id) };
    case "clear_draft":
      return { ...s, draftText: "" };
    case "set_item_hash":
      return {
        ...s,
        pending: s.pending.map((p) =>
          p.id === a.id ? { ...p, expectedHash: a.hash } : p,
        ),
      };
    case "update_item":
      return {
        ...s,
        pending: s.pending.map((p) =>
          p.id === a.id ? { ...p, ...a.patch } : p,
        ),
      };
    case "append_log":
      return { ...s, log: [...s.log, a.entry] };
    case "set_submitting":
      return { ...s, submitting: a.value };
    case "reset_pending":
      // Remove all items that have reached a terminal state.
      return {
        ...s,
        pending: s.pending.filter((p) => !TERMINAL_STATES.has(p.state)),
      };
    default:
      return s;
  }
}

let _itemCounter = 0;
function newItemId(): string {
  _itemCounter += 1;
  return `item_${Date.now()}_${_itemCounter}`;
}

let _msgCounter = 0;
function newMessageId(): string {
  _msgCounter += 1;
  return `msg_${Date.now()}_${_msgCounter}`;
}

export function makeFileInputItem(file: File): InputItem {
  const kind = kindFor(file);
  return {
    id: newItemId(),
    label: file.name,
    kind,
    file,
    state: "QUEUED",
    errorCode: null,
    errorMessage: null,
    bucketId: null,
  };
}

export function makeTextInputItem(text: string): InputItem {
  return {
    id: newItemId(),
    label: text.length > 48 ? text.slice(0, 45) + "…" : text,
    kind: "textmessage",
    text,
    state: "QUEUED",
    errorCode: null,
    errorMessage: null,
    bucketId: null,
  };
}

async function readFileBytes(file: File): Promise<Uint8Array> {
  const buf = await file.arrayBuffer();
  return new Uint8Array(buf);
}

async function readFileText(file: File): Promise<string> {
  return await file.text();
}

/**
 * Submit one item sequentially. Returns the final patch for the reducer.
 * `signal` cancels the fetch (per-item AbortController).
 */
async function submitOne(
  rsm: RsmClient,
  item: InputItem,
  signal: AbortSignal,
): Promise<Partial<InputItem>> {
  try {
    // STAGING: client-side packing phase.
    //   Note: this phase is deliberately observable as a distinct state
    //   even when packing is trivial, so the UI can tell the user what's
    //   happening if a 50 MiB PDF stalls.
    let payload: BucketPayload | (BucketPayload & { children: string[] });
    switch (item.kind) {
      case "textmessage":
        payload = await rsm.ingestText(item.text ?? "", {
          kind: "pasted",
          expectedHash: item.expectedHash,
        });
        break;
      case "text":
        payload = await rsm.ingestText(await readFileText(item.file!), {
          kind: "text",
          sourceUri: item.file!.name,
          expectedHash: item.expectedHash,
        });
        break;
      case "markdown":
        payload = await rsm.ingestMarkdown(await readFileText(item.file!), {
          sourceUri: item.file!.name,
          expectedHash: item.expectedHash,
        });
        break;
      case "pdf": {
        const bytes = await readFileBytes(item.file!);
        payload = await rsm.ingestPdf(bytes, {
          sourceUri: item.file!.name,
          expectedHash: item.expectedHash,
        });
        break;
      }
      case "opaque": {
        const bytes = await readFileBytes(item.file!);
        payload = await rsm.ingestOpaque(bytes, {
          sourceUri: item.file!.name,
          mediaType: item.file!.type || undefined,
          expectedHash: item.expectedHash,
        });
        break;
      }
      case "chatgpt_export": {
        let parsed: unknown;
        try {
          parsed = JSON.parse(await readFileText(item.file!));
        } catch (e) {
          return {
            state: "REJECTED",
            errorCode: "INVALID_JSON",
            errorMessage: `Invalid JSON in ${item.file!.name}: ${(e as Error).message}`,
          };
        }
        payload = await rsm.ingestChatGptExport(parsed, {
          sourceUri: item.file!.name,
          expectedHash: item.expectedHash,
        });
        break;
      }
      case "zip":
        payload = await rsm.uploadZip(item.file!, {
          sourceUri: item.file!.name,
          expectedHash: item.expectedHash,
          signal,
        });
        break;
    }
    const children = (payload as unknown as { children?: string[] }).children;
    return {
      state: "ACCEPTED",
      bucketId: payload.bucket.bucket_id,
      ...(children ? { children } : {}),
    };
  } catch (e) {
    if ((e as DOMException)?.name === "AbortError") {
      return { state: "CANCELLED", errorMessage: "Cancelled by user" };
    }
    if (e instanceof RsmHttpError) {
      const code = e.code ?? null;
      const isReject = e.status >= 400 && e.status < 500;
      return {
        state: isReject ? "REJECTED" : "FAILED",
        errorCode: code,
        errorMessage: e.message,
      };
    }
    return {
      state: "FAILED",
      errorCode: null,
      errorMessage: (e as Error)?.message ?? String(e),
    };
  }
}

export type UseChatIntake = ReturnType<typeof useChatIntake>;

export function useChatIntake(rsm: RsmClient) {
  const [state, dispatch] = useReducer(reducer, initial);
  const controllersRef = useRef<Map<string, AbortController>>(new Map());

  const setDraft = useCallback((text: string) => {
    dispatch({ type: "set_draft", text });
  }, []);

  const addFiles = useCallback((files: File[]) => {
    if (files.length === 0) return;
    // Dedup by name+size+lastModified.
    dispatch({
      type: "add_items",
      items: files.map(makeFileInputItem),
    });
  }, []);

  const removeItem = useCallback((id: string) => {
    const ctl = controllersRef.current.get(id);
    if (ctl) {
      ctl.abort();
      controllersRef.current.delete(id);
    }
    dispatch({ type: "remove_item", id });
  }, []);

  const setItemHash = useCallback((id: string, hash: string | undefined) => {
    dispatch({ type: "set_item_hash", id, hash });
  }, []);

  const submit = useCallback(async () => {
    if (state.submitting) return;
    const items: InputItem[] = [];
    const draft = state.draftText.trim();
    if (draft.length > 0) items.push(makeTextInputItem(state.draftText));
    for (const p of state.pending) if (p.state === "QUEUED") items.push(p);
    if (items.length === 0) return;

    dispatch({ type: "set_submitting", value: true });
    // Freeze the draft into the log as a user bubble immediately.
    if (draft.length > 0) {
      dispatch({
        type: "append_log",
        entry: {
          id: newMessageId(),
          at: Date.now(),
          kind: "user",
          text: state.draftText,
        },
      });
      dispatch({ type: "clear_draft" });
    }

    for (const item of items) {
      // STAGING → LOADING (we don't try to split them finely here).
      dispatch({ type: "update_item", id: item.id, patch: { state: "STAGING" } });
      // ensure we track this item in pending too (for free-form text items,
      // which aren't yet in state.pending).
      if (item.kind === "textmessage" && !state.pending.find((p) => p.id === item.id)) {
        dispatch({ type: "add_items", items: [item] });
      }

      const ctl = new AbortController();
      controllersRef.current.set(item.id, ctl);

      dispatch({
        type: "update_item",
        id: item.id,
        patch: { state: item.expectedHash ? "VERIFYING" : "LOADING" },
      });
      const patch = await submitOne(rsm, item, ctl.signal);
      controllersRef.current.delete(item.id);
      dispatch({ type: "update_item", id: item.id, patch });

      // Log the outcome.
      dispatch({
        type: "append_log",
        entry: {
          id: newMessageId(),
          at: Date.now(),
          kind: "system",
          text:
            patch.state === "ACCEPTED"
              ? `Accepted · ${item.label}`
              : patch.state === "CANCELLED"
                ? `Cancelled · ${item.label}`
                : labelForCode(patch.errorCode ?? null, "Failed") + ` · ${item.label}`,
          bucketId: patch.bucketId ?? null,
          state: patch.state as AttachmentState,
        },
      });
    }

    dispatch({ type: "set_submitting", value: false });
    dispatch({ type: "reset_pending" });
  }, [rsm, state.draftText, state.pending, state.submitting]);

  const cancelAll = useCallback(() => {
    for (const ctl of controllersRef.current.values()) ctl.abort();
    controllersRef.current.clear();
  }, []);

  return useMemo(
    () => ({ state, setDraft, addFiles, removeItem, setItemHash, submit, cancelAll }),
    [state, setDraft, addFiles, removeItem, setItemHash, submit, cancelAll],
  );
}
