async (page) => {
  const evidence = await page.evaluate(async () => {
    const { encodeWorkspace, decodeWorkspace } = await import('/lib/backup.js');
    const first = await import('/lib/storage.js?audit=first');
    const second = await import('/lib/storage.js?audit=second');
    const observer = await import('/lib/storage.js?audit=observer');
    const passed = [];
    const check = (condition, label) => { if (!condition) throw new Error(label); passed.push(label); };
    const stamp = new Date().toISOString();
    const source = {
      id:'source-one', name:'source.md', path:'Sources/source.md', type:'text/markdown', blob:new Blob(['Original café\r\n文'],{type:'text/markdown'}),
      original:'Original café\r\n文', saved:'Saved revision', draft:'Uncommitted draft', inScope:true, revisionId:'revision-one',
      revisions:[{id:'revision-one', text:'Saved revision', time:stamp}], position:{start:2,end:4,editScroll:42}
    };
    const binary = {id:'binary-one',name:'bytes.bin',path:'Retained/bytes.bin',type:'application/octet-stream',blob:new Blob([Uint8Array.from([0,1,127,128,254,255])],{type:'application/octet-stream'}),original:null,saved:null,draft:null,inScope:false};
    const result = {...structuredClone(source),id:'result-one',name:'result.md',path:'Prepared/result.md',generated:true,outcome:'partial',sourceRefs:[{sourceId:source.id,revisionId:'revision-one',name:source.name,path:source.path}]};
    const workspace = {version:1,sources:[source,binary],results:[result],selected:['source-one'],selectedFile:'source-one',history:[{id:'run-one',status:'partial',total:1,processed:1,characters:12,events:[{time:stamp,operation:'read',message:'Read source',status:'completed'}],findings:[{severity:'warning',message:'Missing context',sourceId:'source-one'}],resultId:'result-one'}],systemNotes:[{text:'System note',time:stamp}],agentNotes:[{text:'Saved agent draft',time:stamp,attachments:[{resultId:'result-one',revisionId:'revision-one',name:'result.md',outcome:'partial'}]}],agentDraft:'Current composer',systemDraft:'Unsaved note',agentAttachment:'result-one',theme:'dark',collapsed:['system'],folders:{'/Retained':false},editorMode:'edit',mobileView:'sources',activeRun:null,requestedTask:'inspect',lastNotice:null,referencePack:2};
    // Seed an actual legacy v1 record without any revision metadata.
    const database = await new Promise((resolve,reject)=>{const request=indexedDB.open('oneshot-local-workspace',1);request.onupgradeneeded=()=>request.result.createObjectStore('workspace');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
    await new Promise((resolve,reject)=>{const tx=database.transaction('workspace','readwrite');tx.objectStore('workspace').put(workspace,'current');tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error);});
    database.close();
    const tabA = await first.loadWorkspace(), tabB = await second.loadWorkspace();
    check(!('_storageRevision' in tabA) && tabA.sources.length===2,'Legacy v1 workspace loads without data migration or loss');
    tabA.agentDraft='Tab A saved'; await first.saveWorkspace(tabA);
    tabB.systemDraft='Tab B independent work';
    let conflict;
    try { await second.saveWorkspace(tabB); } catch (error) { conflict=error; }
    check(second.isWorkspaceConflict(conflict) && conflict.actualRevision===1 && conflict.expectedRevision===0,'Stale writer receives a typed conflict from the atomic write transaction');
    const persisted = await observer.loadWorkspace();
    check(persisted.agentDraft==='Tab A saved' && persisted.systemDraft==='Unsaved note','Rejected write preserves newer saved work');
    try { await second.saveWorkspace(tabB); conflict=null; } catch (error) { conflict=error; }
    check(second.isWorkspaceConflict(conflict),'A conflict remains blocked until explicit recovery');
    const recoveryCopy = await encodeWorkspace(tabB);
    check((await decodeWorkspace(recoveryCopy)).systemDraft==='Tab B independent work','Stale tab can export all of its unsaved work before loading the newer workspace');
    const recovered = await second.loadWorkspace(); recovered.systemDraft='Recovered on fresh baseline'; await second.saveWorkspace(recovered);
    check((await observer.loadWorkspace()).agentDraft==='Tab A saved','Explicit recovery retains first tab saved work');
    const queued = await first.loadWorkspace(); queued.agentDraft='Queue first'; const writeOne=first.saveWorkspace(queued);
    queued.agentDraft='Queue second'; const writeTwo=first.saveWorkspace(queued); queued.agentDraft='Mutation after call'; await Promise.all([writeOne,writeTwo]);
    const final = await observer.loadWorkspace();
    check(final.agentDraft==='Queue second' && final._storageRevision===4,'Queued writes advance committed revisions and capture snapshots at call time');
    const backup = await encodeWorkspace(final), decoded = await decodeWorkspace(new Blob([backup],{type:'application/json'}));
    check(!('_storageRevision' in decoded),'Portable restore has no live database ownership token');
    check(decoded.sources[0].original===source.original && decoded.sources[0].saved===source.saved && decoded.sources[0].draft===source.draft,'Backup retains original, saved, and working text independently');
    check(await decoded.sources[0].blob.text()===source.original && decoded.sources[0].blob.type==='text/markdown','Original UTF-8 bytes, CRLF and MIME survive roundtrip');
    check([...new Uint8Array(await decoded.sources[1].blob.arrayBuffer())].join(',')==='0,1,127,128,254,255' && decoded.sources[1].inScope===false,'Binary bytes and removed-source library membership survive roundtrip');
    check(decoded.agentNotes[0].attachments[0].resultId==='result-one' && decoded.agentAttachment==='result-one' && decoded.history[0].findings.length===1 && decoded.sources[0].revisions.length===1,'Notes, per-note and composer attachments, findings, and source versions survive roundtrip');
    const mutations = {
      'Unsupported backup version': archive=>archive.backupVersion=2,
      'Unsupported workspace version': archive=>archive.workspace.version=2,
      'Malformed source list': archive=>archive.workspace.sources={},
      'Duplicate source identity': archive=>archive.workspace.sources[1].id='source-one',
      'Unsafe identifier': archive=>archive.workspace.sources[0].id='\" onclick=\"alert(1)',
      'Missing selected source': archive=>archive.workspace.selected=['missing'],
      'Malformed history events': archive=>archive.workspace.history[0].events=null,
      'Malformed revisions': archive=>archive.workspace.sources[0].revisions=[null],
      'Malformed source provenance': archive=>archive.workspace.results[0].sourceRefs=[null],
      'Malformed attachments': archive=>archive.workspace.agentNotes[0].attachments={},
      'Missing attachment content': archive=>archive.workspace.agentNotes[0].attachments[0].resultId='missing',
      'Invalid reference protocol': archive=>archive.workspace.sources[0].reference='javascript:alert(1)',
      'Invalid panel names': archive=>archive.workspace.collapsed=['invalid[selector'],
      'Prototype keys': archive=>Object.defineProperty(archive.workspace,'__proto__',{value:{polluted:true},enumerable:true}),
      'Missing original binary': archive=>archive.workspace.sources[0].blob={__oneshot_blob__:999},
      'Malformed binary byte count': archive=>archive.blobs[0].size+=1,
      'Malformed binary alphabet': archive=>archive.blobs[0].base64='!'.repeat(archive.blobs[0].base64.length),
      'Malformed notice': archive=>archive.workspace.lastNotice={title:'Oops',message:null,status:'failed'},
      'Null workspace': archive=>archive.workspace=null,
    };
    for (const [label, mutate] of Object.entries(mutations)) { const archive=JSON.parse(backup); mutate(archive); let rejected=false; try { await decodeWorkspace(JSON.stringify(archive)); } catch(error) { rejected=error.code==='INVALID_WORKSPACE_BACKUP'; } check(rejected,`${label} rejected before apply`); }
    const afterInvalid = await observer.loadWorkspace();
    check(afterInvalid._storageRevision===4 && afterInvalid.agentDraft===final.agentDraft,'Malformed backup attempts never modify persisted workspace');
    // Exercise the supported file-size boundary without a pathological regex or
    // argument-spread stack overflow on a normal large binary source.
    const boundary = structuredClone(workspace); boundary.sources[1].blob=new Blob([new Uint8Array(10*1024*1024).fill(255)],{type:'application/octet-stream'});
    const boundaryRestored = await decodeWorkspace(await encodeWorkspace(boundary));
    check(boundaryRestored.sources[1].blob.size===10*1024*1024 && new Uint8Array(await boundaryRestored.sources[1].blob.slice(-1).arrayBuffer())[0]===255,'10 MiB binary source roundtrips at the supported limit');
    return {passed:passed.length, assertions:passed, capturedAt:new Date().toISOString()};
  });
  return evidence;
}
