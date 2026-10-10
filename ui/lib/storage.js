// IndexedDB stores Blobs and saved/draft revisions without stringifying files.
const DATABASE = 'oneshot-local-workspace';
const STORE = 'workspace';
let connection = null;
let writeQueue = Promise.resolve();
let expectedRevision = null;

export class WorkspaceConflictError extends Error {
  constructor(expected, actual) {
    super('Another OneShot tab saved newer workspace changes. Export this tab\'s work, then load the latest workspace before continuing.');
    this.name = 'WorkspaceConflictError';
    this.code = 'WORKSPACE_CONFLICT';
    this.expectedRevision = expected;
    this.actualRevision = actual;
  }
}

export const isWorkspaceConflict = error => error?.code === 'WORKSPACE_CONFLICT';

function revisionOf(data) {
  const revision = data?._storageRevision ?? 0;
  if (!Number.isSafeInteger(revision) || revision < 0) throw new Error('The saved workspace revision is invalid. Export a recovery copy before replacing it.');
  return revision;
}

function openDatabase() {
  if (connection) return connection;
  connection = new Promise((resolve, reject) => {
    if (!globalThis.indexedDB) {
      reject(new Error('Browser storage is unavailable. Workspace changes cannot persist across reloads.'));
      return;
    }
    const request = indexedDB.open(DATABASE, 1);
    let rejected = false;
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) request.result.createObjectStore(STORE);
    };
    request.onerror = () => reject(request.error || new Error('The local workspace database could not be opened.'));
    request.onblocked = () => {
      rejected = true;
      reject(new Error('The workspace database is blocked by another tab. Close other OneShot tabs and try again.'));
    };
    request.onsuccess = () => {
      const database = request.result;
      if (rejected) { database.close(); return; }
      database.onversionchange = () => { database.close(); connection = null; };
      database.onclose = () => { connection = null; };
      resolve(database);
    };
  }).catch(error => { connection = null; throw error; });
  return connection;
}

export async function loadWorkspace() {
  await writeQueue;
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE, 'readonly');
    const request = transaction.objectStore(STORE).get('current');
    let data = null;
    request.onsuccess = () => { data = request.result ?? null; };
    transaction.oncomplete = () => {
      try { expectedRevision = revisionOf(data); resolve(data); }
      catch (error) { reject(error); }
    };
    transaction.onabort = () => reject(transaction.error || request.error || new Error('The local workspace could not be loaded.'));
    transaction.onerror = () => {}; // Abort provides the single failure outcome.
  });
}

export function saveWorkspace(data) {
  let snapshot;
  try { snapshot = structuredClone(data); } catch (error) { return Promise.reject(error); }
  const pending = writeQueue.then(async () => {
    if (expectedRevision === null) throw new Error('Load the current workspace before saving changes.');
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE, 'readwrite');
      const store = transaction.objectStore(STORE);
      const request = store.get('current');
      let failure = null, write = null, nextRevision;
      request.onsuccess = () => {
        try {
          const actualRevision = revisionOf(request.result);
          if (actualRevision !== expectedRevision) throw new WorkspaceConflictError(expectedRevision, actualRevision);
          if (actualRevision === Number.MAX_SAFE_INTEGER) throw new Error('Workspace revision limit reached. Export your workspace before continuing.');
          nextRevision = actualRevision + 1;
          // The comparison and replacement share one transaction. A transaction in
          // another tab cannot commit a newer revision between these two requests.
          write = store.put({ ...snapshot, _storageRevision: nextRevision }, 'current');
        } catch (error) { failure = error; transaction.abort(); }
      };
      transaction.oncomplete = () => { expectedRevision = nextRevision; resolve(nextRevision); };
      transaction.onabort = () => reject(failure || transaction.error || write?.error || request.error || new Error('The local workspace could not be saved.'));
      transaction.onerror = () => {};
    });
  });
  // A failed write is reported to its caller and does not block later retries.
  writeQueue = pending.catch(() => {});
  return pending;
}

// Recovery is explicit: export the stale in-memory state first, call loadWorkspace,
// replace the application's state with that result, then resume saves. Loading only
// to acquire a newer revision and saving an old snapshot would defeat protection.
