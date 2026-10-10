// Saved versions are immutable; a draft is independent until Save succeeds.
export function normalizeRevisions(file) {
  let changed = false;
  if (!Array.isArray(file.revisions)) { file.revisions = []; changed = true; }
  if (!file.revisionId) {
    file.revisionId = crypto.randomUUID(); changed = true;
    if (typeof file.saved === 'string') file.revisions.push({id:file.revisionId,text:file.saved,time:new Date().toISOString()});
  }
  return changed;
}

export function saveVersion(file) {
  normalizeRevisions(file);
  file.revisionId = crypto.randomUUID();
  file.saved = file.draft;
  file.revisions = [...file.revisions,{id:file.revisionId,text:file.saved,time:new Date().toISOString()}];
}

export function resultFreshness(result, sources) {
  if (!result?.generated) return {status:'current',changed:[]};
  if (!result.sourceRefs?.length) return {status:'unknown',changed:[]};
  const changed = result.sourceRefs.filter(ref => {
    const source = sources.find(file=>file.id===ref.sourceId);
    return !source || source.revisionId !== ref.revisionId || source.inScope === false;
  });
  return {status:changed.length?'changed':'current',changed};
}

export function revisionText(file, id) {
  return file?.revisions?.find(revision=>revision.id===id)?.text ?? null;
}
