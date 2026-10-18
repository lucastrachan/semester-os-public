// Service worker: holds the scan in session storage (memory only, cleared when the browser closes).
// No credentials ever pass through here.
importScripts('parse.js', 'files.js');
const BUILD_DATE = '2026-10-18'; // bump together with manifest.json "version" on every change
const buildLabel = () => 'build ' + chrome.runtime.getManifest().version + ' (' + BUILD_DATE + ')';
const SITE = 'https://<deployed-host-1>';
const BB = 'https://ualearn.blackboard.com';
const get = async () => (await chrome.storage.session.get('scan')).scan || { active: false, queue: [], captured: {}, sent: null, scan: null, import: null };
// Every handler reads the whole state, awaits other things, then writes it back. A snapshot taken before a new run started
// (for example by a once-a-second 'state' poll that found an old error) must NEVER overwrite that new run, or the run
// loses its runId, askTab reports 'cancelled', the scan tab is closed at once and the scan ends silently. So a write is
// dropped when the stored run has a runId that the written state does not carry. Starting/ending a run passes force.
let putChain = Promise.resolve(); // writes are serialized so the check and the write below are atomic
const put = (scan, force) => {
  const job = async () => {
    if (!force) {
      const cur = (await chrome.storage.session.get('scan')).scan;
      const cr = cur && cur.scan && cur.scan.runId, nr = scan && scan.scan && scan.scan.runId;
      if (cr && cr !== nr) return false;
    }
    if (scan && scan.scan && (scan.scan.phase === 'error' || scan.scan.phase === 'done') && !scan.scan.endedAt) scan.scan.endedAt = Date.now();
    await chrome.storage.session.set({ scan });
    return true;
  };
  const p = putChain.then(job, job);
  putChain = p.catch(() => {});
  return p;
};
const summary = (s) => ({
  active: s.active, sent: s.sent, queue: s.queue, current: s.current || null, scan: s.scan || null,
  captured: Object.fromEntries(Object.entries(s.captured).map(([k, v]) => [k, { kind: v.kind, chars: v.text ? v.text.length : 0, filename: v.filename || null }]))
});
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// The deep upload queue is stored under its own key and every change goes through this lock, because three mapping tabs
// and the site's once-a-second polls all touch it (a whole-state read-modify-write would silently drop queued items).
let qchain = Promise.resolve();
const locked = (fn) => { const p = qchain.then(fn, fn); qchain = p.catch(() => {}); return p; };
const qGet = async () => (await chrome.storage.session.get('deepq')).deepq || [];
const qPush = (item) => locked(async () => { const q = await qGet(); q.push(item); await chrome.storage.session.set({ deepq: q }); });
const qShift = (identifier) => locked(async () => { const q = await qGet(); if (!q.length || q[0].identifier !== identifier) return null; const h = q.shift(); await chrome.storage.session.set({ deepq: q }); return h; });
const rxGet = async () => (await chrome.storage.session.get('runx')).runx || { importDone: false, imported: null, classes: [] };
const rxPatch = (patch) => locked(async () => { const r = await rxGet(); await chrome.storage.session.set({ runx: Object.assign(r, patch) }); });
const rxReset = () => rxPatch({ importDone: false, imported: null, classes: [], sylAdded: 0, sylNeed: 0, sylPerm: false });
const rxAdd = (field, n) => locked(async () => { const r = await rxGet(); r[field] = (r[field] || 0) + n; await chrome.storage.session.set({ runx: r }); });
const qClear = () => locked(async () => { await chrome.storage.session.set({ deepq: [] }); });

// ---- One-click scan: course list tab, then calendar tab, both background tabs, both closed afterwards. Read-only. ----
async function setScan(patch) { const s = await get(); s.scan = Object.assign({}, s.scan || {}, patch); await put(s); }

const STALE_MS = 100000; // a scan older than this is dead (service worker restarted, tab hung): never block a new one
const RUNNING = ['courses', 'calendar', 'sending', 'deep']; // 'deep' refreshes startedAt on every step, so stale = no progress for 100 s
let scanTabs = []; // tabs this scan opened (so Cancel can close them)

function normalize(s) { // end stale runs with a clear message
  if (s.scan && RUNNING.indexOf(s.scan.phase) >= 0 && Date.now() - (s.scan.startedAt || 0) > STALE_MS) {
    s.scan = { runId: s.scan.runId, phase: 'error', msg: 'This scan stopped responding. Try again.' };
  }
  return s;
}
const getFresh = async () => normalize(await get());


// ---- Diagnostics: short event log kept in session storage. Phases, tab ids, timings and error strings only. ----
async function dlog(ev, isErr) {
  try {
    const r = (await chrome.storage.session.get('diag')).diag || { events: [], lastError: '' };
    r.events.push({ t: Date.now(), ev: String(ev).slice(0, 400) });
    if (r.events.length > 80) r.events = r.events.slice(-80);
    if (isErr) r.lastError = String(ev).slice(0, 160);
    await chrome.storage.session.set({ diag: r });
  } catch (e) { /* ignore */ }
}
async function diagText() {
  const s = await get();
  const r = (await chrome.storage.session.get('diag')).diag || { events: [], lastError: '' };
  const now = Date.now();
  const sc = s.scan || {};
  const lines = [
    buildLabel(), // FIRST line: which build is really running
    'Semester OS Connect diagnostics (no names, text or tokens)',
    'version ' + chrome.runtime.getManifest().version + ', now ' + new Date(now).toISOString(),
    'phase ' + (sc.phase || 'none') + ', pct ' + (sc.pct == null ? '-' : sc.pct) + ', heartbeat ' + (sc.startedAt ? Math.round((now - sc.startedAt) / 1000) + 's ago' : '-'),
    'msg: ' + String(sc.msg || '').replace(/[A-Z]{2,5} \d{3}/g, 'XXX 000'),
    'sent ' + s.sent + ', importDone ' + !!(await rxGet()).importDone + ', imported ' + JSON.stringify((await rxGet()).imported || null),
    'origin ' + JSON.stringify(s.origin || null) + ', canvasTab ' + (s.canvasTab || '-') + ', scanTabs ' + JSON.stringify(scanTabs) + ', scanWin ' + scanWin,
    'deep ' + (s.deep ? s.deep.state + ' queue ' + (await qGet()).length + ' pages ' + s.deep.pages + ' skipped ' + s.deep.skipped + '/' + s.deep.skippedClasses + ' note ' + (s.deep.note || '-') : 'none'),
    'lastError: ' + (r.lastError || '-'),
    'events (oldest first):'
    + (r.lastFetch ? '\nlast fetch: ' + r.lastFetch.line + ' (' + Math.round((now - r.lastFetch.t) / 1000) + 's ago)' : ''),
  ].concat(r.events.slice(-60).map(e => '  -' + Math.round((now - e.t) / 1000) + 's ' + e.ev));
  return lines.join('\n');
}

// ---- Scan pages open as INACTIVE tabs in the student's current window (this is what rendered Blackboard reliably).
// Blackboard Ultra switches to a narrow layout below ~1000 px, so a small window is never used; the only fallback is a
// full-size window (1280x900) if a tab cannot be created. Everything created is registered; only that is ever closed. ----
let scanWin = null;
async function openScanTab(url) {
  let tab = null;
  try { tab = await chrome.tabs.create({ url, active: false }); }
  catch (e) {
    await dlog('tab create failed: ' + e, true);
    let lf0 = null; try { lf0 = await chrome.windows.getLastFocused(); } catch (e2) { /* ignore */ }
    const w = await chrome.windows.create({ url, type: 'normal', width: 1280, height: 900, left: 0, top: 0, focused: false });
    if (lf0 && lf0.id != null) { try { await chrome.windows.update(lf0.id, { focused: true }); } catch (e2) { /* ignore */ } }
    scanWin = w.id; tab = w.tabs[0]; await dlog('fallback window ' + w.id);
  }
  scanTabs.push(tab.id);
  await regAdd(tab.id, scanWin);
  return tab;
}

// Registry (session storage) of tabs and the window this helper created. Nothing else is EVER closed, navigated or reloaded.
const getReg = async () => (await chrome.storage.session.get('created')).created || { tabs: [], win: null };
const putReg = (created) => chrome.storage.session.set({ created });
async function regAdd(tabId, winId) { const r = await getReg(); if (tabId != null && r.tabs.indexOf(tabId) < 0) r.tabs.push(tabId); if (winId != null) r.win = winId; await putReg(r); }
async function regDrop(tabId) { const r = await getReg(); r.tabs = r.tabs.filter(i => i !== tabId); await putReg(r); }
const ours = (url) => !url || url === 'about:blank' || url.startsWith(BB + '/') || url.startsWith(SITE + '/'); // our scan pages only
// Close a tab only if we created it, it still exists and its URL is a scan URL.
async function safeRemove(tabId, own) {
  const r = await getReg();
  if (r.tabs.indexOf(tabId) < 0) return false;
  try {
    const t = await chrome.tabs.get(tabId);
    if (own || ours(t.url || t.pendingUrl || '')) await chrome.tabs.remove(tabId); // own = a tab of this very run (it may have been redirected to single sign-on)
  } catch (e) { /* already gone */ }
  await regDrop(tabId);
  return true;
}
async function closeScanTabs(keepTabId) {
  const r = await getReg();
  if (keepTabId != null && r.tabs.indexOf(keepTabId) >= 0) { await regDrop(keepTabId); await dlog('kept origin tab ' + keepTabId + ' (it was a leftover helper tab)'); } // now treated as the student's
  for (const id of (await getReg()).tabs.slice()) await safeRemove(id, true);
  scanTabs = [];
  if (r.win != null) { // the small window goes only if nothing but our tabs is in it (it normally closes with its last tab)
    try {
      const w = await chrome.windows.get(r.win, { populate: true });
      if (!(w.tabs || []).length) await chrome.windows.remove(r.win);
    } catch (e) { /* already closed */ }
  }
  scanWin = null;
  const r2 = await getReg(); r2.win = null; await putReg(r2);
}

async function askTab(tabId, message, ms, runId) {
  const t0 = Date.now();
  for (;;) {
    const s = await get();
    if (runId !== 'fetch' && (!s.scan || s.scan.runId !== runId)) return { error: 'cancelled' };
    try { const r = await chrome.tabs.sendMessage(tabId, message); if (r) return r; } catch (e) { /* content script not ready yet */ }
    if (Date.now() - t0 > ms) return { error: 'timeout' };
    await sleep(1000);
  }
}

// Background tabs can be throttled by Chrome and the page may not render; if nothing comes back, bring the tab forward and retry once.
// Where the student pressed the button: that tab stays focused and shows the progress panel (Blackboard /ultra or /webapps,
// or the Semester OS site). Anything else (e.g. Canvas, no content script) is kind 'other': progress shows on the Semester OS tab.
async function originOf(tabId) {
  if (!tabId) return { tabId: null, kind: 'other' };
  try {
    const t = await chrome.tabs.get(tabId); // url is only visible for hosts we may access
    const u = t.url || '';
    const paneled = u.startsWith(BB + '/ultra/') || u.startsWith(BB + '/webapps/') || u.startsWith(SITE + '/');
    return { tabId, kind: paneled ? 'panel' : 'other', isSite: u.startsWith(SITE + '/') };
  } catch (e) { return { tabId, kind: 'other' }; }
}
async function refocusOrigin() {
  const s = await get();
  /* intentionally empty: the helper never navigates, activates or reuses the student's own tabs */
}
// Hand-off to the student site: never steals focus. If the scan was started ON the site, that tab does the work (reloaded).
async function openSite(path) {
  const s = await get();
  const tab = await openScanTab(SITE + path); // its own tab (in the small scan window), even if the student is already on the site
  await dlog('hand-off tab ' + tab.id);
}

const ATTEMPT_MS = (typeof __SOS_TEST_ATTEMPT_MS !== 'undefined') ? __SOS_TEST_ATTEMPT_MS : 55000; // the page waits up to 45 s itself
const LOGIN_MSG = 'Blackboard asked you to sign in again: sign in on your Blackboard tab, then press Scan.';

// Final address of a helper tab, path only (the query may hold tokens), for the diagnostics and for the reason text.
async function inspectTab(tabId) {
  try {
    const t = await chrome.tabs.get(tabId);
    const u = new URL(t.url || t.pendingUrl || 'about:blank');
    return { host: u.hostname, path: u.pathname.slice(0, 60), title: !!t.title, status: t.status || '' };
  } catch (e) { return null; }
}
function whyFailed(diag, tabInfo) { // plain-language reason for the student
  const host = (diag && diag.host) || (tabInfo && tabInfo.host) || '';
  const path = (diag && diag.path) || (tabInfo && tabInfo.path) || '';
  if ((host && host !== 'ualearn.blackboard.com') || (diag && diag.login) || (path && !/^\/ultra/.test(path))) return LOGIN_MSG;
  if (diag && (diag.spinner || diag.textLen < 400)) return 'Blackboard is still loading. Try again in a minute.';
  return 'Blackboard did not load the course list. Try again.';
}

// Up to 3 attempts per page: attempt 1 in the background, attempt 2 reloads our tab and brings it forward once (student's tab restored),
// attempt 3 reloads again. Heartbeat is refreshed per attempt so the 100 s watchdog never ends a healthy retry.
async function readIn(path, message, runId) {
  const tab = await openScanTab(BB + path);
  await dlog('opened ' + path + ' tab ' + tab.id);
  let r = { error: 'timeout' }, info = null, prev = null;
  try {
    for (let attempt = 1; attempt <= 3; attempt++) {
      if (attempt > 1) {
        if ((await getReg()).tabs.indexOf(tab.id) < 0) break; // only ever touch our own tab
        try { await chrome.tabs.reload(tab.id); } catch (e) { /* ignore */ }
        await sleep(1500);
      }
      await setScanIf(runId, { startedAt: Date.now() });
      r = await askTab(tab.id, message, ATTEMPT_MS, runId);
      info = await inspectTab(tab.id);
      await dlog(path + ' attempt ' + attempt + ': ' + (r.error || ('ok' + (r.via ? ' via ' + r.via : ''))) + ' | ' + JSON.stringify({ url: info, diag: r.diag || null }), !!r.error && r.error !== 'cancelled');
      if (!r.error || r.error === 'cancelled') break;
      if (r.diag && r.diag.login) break; // a login page will not fix itself by reloading
      if (info && info.host && info.host !== 'ualearn.blackboard.com') break; // redirected to single sign-on
    }
    if (r.error && r.error !== 'cancelled') r.why = whyFailed(r.diag, info);
    return r;
  } finally { scanTabs = scanTabs.filter(i => i !== tab.id); await safeRemove(tab.id, true); }
}

async function stillMine(runId) { const s = await get(); return !!(s.scan && s.scan.runId === runId); }

async function runScan(origin, opts) { // top-level guard: never die silently
  try { await runScanInner(origin, opts); }
  catch (e) {
    const msg = 'Could not start the scan: ' + String(e && e.message || e).slice(0, 100);
    try { await dlog('runScan crashed: ' + msg, true); const s = await get(); s.scan = { runId: 'crash' + Date.now(), phase: 'error', msg }; s.quiet = false; await put(s, true); } catch (e2) { /* nothing more to do */ }
  }
}
async function runScanInner(origin, opts) { // pressing Scan always starts fresh: any previous run state is discarded
  await closeScanTabs(origin && origin.tabId);
  const runId = String(Date.now()) + Math.random().toString(36).slice(2, 6);
  const cur = await get();
  cur.scan = { phase: 'courses', courses: 0, deadlines: 0, msg: 'Reading your courses', runId, startedAt: Date.now(), pct: 10 };
  cur.deep = null; cur.importDone = false;
  if (origin) cur.origin = origin;
  cur.sent = null; cur.import = null; cur.canvasTab = null; cur.quiet = !!(opts && opts.quiet); await put(cur, true); await rxReset();
  await dlog((cur.quiet ? 'quiet ' : '') + 'scan start, origin ' + JSON.stringify(origin || null));
  const fail = async (msg, signin) => {
    await dlog('FAIL: ' + msg, true);
    if (!(await stillMine(runId))) return;
    if (cur.quiet) return quietEnd(signin ? 'needs-signin' : 'error');
    await setScan({ phase: 'error', msg });
    const s0 = await get(); s0.import = null; s0.sent = null; s0.deep = null; await put(s0);
  };
  try {
    const c = await readIn('/ultra/course', { type: 'scrapeCourses' }, runId);
    if (c.error === 'cancelled') return;
    if (c.error || !Array.isArray(c.courses) || !c.courses.length) return fail(c.why || 'Blackboard did not load the course list. Try again.', true);
    await dlog('course list via ' + (c.via || '?') + ' n=' + c.courses.length);
    const probe = SOSParse.buildImport(c.courses, []);
    if (!(await stillMine(runId))) return;
    await setScan({ phase: 'calendar', courses: probe.classes.length, msg: 'Reading your due dates', pct: 25, startedAt: Date.now() });
    const d = await readIn('/ultra/calendar', { type: 'scrapeCalendar' }, runId);
    if (d.error === 'cancelled') return;
    if (d.why === LOGIN_MSG) return fail(LOGIN_MSG, true); // the session ended between pages
    const deadlines = d.text ? SOSParse.parseDeadlines(d.text) : [];
    const data = SOSParse.buildImport(c.courses, deadlines);
    await dlog('calendar ' + (d.error || 'ok') + ': ' + deadlines.length + ' deadlines, ' + data.classes.length + ' classes');
    const n = data.classes.reduce((a, x) => a + x.assignments.length, 0);
    const s = await get();
    if (!s.scan || s.scan.runId !== runId) return;
    s.import = data; s.sent = 'pending';
    s.scan = { phase: 'sending', courses: data.classes.length, deadlines: n, msg: 'Sending classes' + (d.text ? '' : ' (no due dates found)'), runId, startedAt: Date.now(), pct: 35 };
    s.scan.pct = 35; s.deep = { state: 'waiting', pages: 0, ok: [], skipped: 0, skippedClasses: 0 }; await qClear(); await rxReset();
    await put(s);
    await openSite('/onboarding');
    await dlog('hand-off tab requested');
    await deepPhase(runId, c.courses, data);
  } catch (e) {
    await fail('Scan stopped: ' + String(e && e.message || e).slice(0, 80));
  }
}


// ---- Deep scan (text only, opt-in, cancellable). One combined material per class (the materials API allows 5 per minute
// and 40 per day, so per-item uploads would not fit). Items already sent in an earlier run are skipped (hashes only). ----
const MAX_ITEMS_PER_CLASS = 12, MAX_ITEMS_PER_RUN = 60, MAX_CLASS_CHARS = 100000;
const hash = (str) => { let h = 5381; for (let i = 0; i < str.length; i++) h = ((h * 33) ^ str.charCodeAt(i)) >>> 0; return h.toString(36); };
async function setScanIf(runId, patch) { const s = await get(); if (s.scan && s.scan.runId === runId) { s.scan = Object.assign({}, s.scan, patch); await put(s); return true; } return false; }
const progress = (runId, patch) => setScanIf(runId, Object.assign({ startedAt: Date.now() }, patch));


// Marks the run finished. Idempotent. Called when the site reports the last upload, and by the worker itself as a fallback
// (so a dead or throttled hand-off tab can never leave the origin panel without a result).
async function finalizeDone() {
  const s = await get();
  const rx = await rxGet();
  if (!s.scan || s.scan.phase === 'done' || s.scan.phase === 'error' || !rx.imported) return;
  const d = s.deep || { pages: 0, skipped: 0, skippedClasses: 0 };
  const n = (rx.classes && rx.classes.length) || rx.imported.classes || 0;
  const stopped = d.note === 'error' || d.note === 'not-imported';
  const msg = stopped
    ? 'Classes added (' + n + '); page reading stopped.'
    : n + ' classes added, ' + (d.items || 0) + ' content items mapped' + ((d.skipped || 0) + (d.skippedClasses || 0) ? ', ' + ((d.skipped || 0) + (d.skippedClasses || 0)) + ' unchanged or skipped' : '')
      + (rx.sylAdded || rx.sylNeed ? '. ' + (rx.sylAdded || 0) + ' syllabi added' + (rx.sylNeed ? ', ' + rx.sylNeed + ' need a click' : '') : '');
  const hint = rx.sylNeed ? (rx.sylPerm ? 'Allow file downloads in the helper popup, then scan again.' : 'Ask the agent for a missing syllabus and it will fetch it, or open it in Blackboard.') : '';
  s.scan = { runId: s.scan.runId, phase: 'done', pct: 100, classes: rx.classes || [], courses: n, imported: rx.imported, deadlines: rx.imported.deadlines || 0, msg, hint, finishedAt: Date.now(), partial: stopped };
  s.sent = 'done'; s.import = null;
  await put(s);
  const dl = await getDaily();
  dl.lastOkAt = Date.now(); dl.lastAttemptAt = dl.lastOkAt; dl.lastStatus = 'ok'; dl.lastClasses = n; dl.lastNewDeadlines = (rx.imported && rx.imported.newDeadlines) || 0;
  await putDaily(dl);
  if (s.quiet) { // daily run: no panel, no toast; badge shows the number of new deadlines for a short time
    if (dl.lastNewDeadlines > 0) { await setBadge(String(Math.min(dl.lastNewDeadlines, 99)), '#4F46E5'); chrome.alarms.create('clear-badge', { delayInMinutes: 30 }); }
    else if ((await chrome.action.getBadgeText({})) === '!') await setBadge('');
    setTimeout(() => { closeScanTabs(); }, 8000);
    const s2 = await get(); s2.scan = null; s2.sent = null; s2.import = null; s2.deep = null; s2.quiet = false; await put(s2, true); await rxReset(); await qClear();
    return;
  }
  chrome.storage.local.set({ ui: { min: false, hidden: false } }); // re-open the origin panel expanded
  if (!s.origin || s.origin.kind === 'panel') setTimeout(() => { closeScanTabs(); }, 8000); // the helper's own window and tabs only
}

// Runs AFTER the classes were imported. Failure or Cancel here never undoes the import; the result is partial success.
// INDEX crawl: per class one helper tab maps folders/items (no item is opened); up to 3 classes at once, hard 40 s per class.
async function deepPhase(runId, courses, importData) {
  const finish = async (note) => { const s = await get(); if (s.deep) { s.deep.state = 'finished'; if (note) s.deep.note = note; await put(s); } };
  try {
    let t0 = Date.now(), ready = false;
    while (Date.now() - t0 < 90000) { // wait for the student site to confirm the import (it needs the student signed in there)
      const s = await get();
      if (!s.scan || s.scan.runId !== runId) return;
      if ((await rxGet()).importDone) { ready = true; break; }
      await progress(runId, { phase: 'sending', msg: 'Sending classes', pct: 35 });
      await sleep(1000);
    }
    if (!ready) { if ((await get()).quiet) { await finish('not-imported'); return quietEnd('needs-signin'); } if (await stillMine(runId)) await setScan({ phase: 'error', msg: 'Could not reach Semester OS. Sign in there, then try again.' }); return finish('not-imported'); }
    const imported = new Set(importData.classes.map(x => x.identifier));
    const classes = courses.filter(x => imported.has(x.identifier) && /^_\d+_1$/.test(x.id || '')).slice(0, 12);
    const fps = (await chrome.storage.local.get('fps')).fps || {}; // index fingerprints of what was uploaded (hashes only)
    let started = 0, finished = 0, skippedClasses = 0, unchanged = 0, itemsTotal = 0, next = 0;
    const N = classes.length;
    const pctAt = (k) => 35 + Math.round(65 * k / Math.max(1, N));
    const syl = (await chrome.storage.local.get('syl')).syl || {}; // identifier -> key of the syllabus already added
    const mapOne = async (cl) => {
      const p = SOSParse.splitIdentifier(cl.identifier);
      const k = ++started;
      if (!(await progress(runId, { phase: 'deep', msg: 'Mapping ' + p.code + ' (' + k + ' of ' + N + ')', pct: pctAt(finished) }))) return;
      const tab = await openScanTab(BB + '/ultra/courses/' + cl.id + '/outline');
      let o;
      try { // hard 40 s per class; the outline tab is closed as soon as the map is in
        o = await askTab(tab.id, { type: 'mapOutline' }, 40000, runId);
      } finally { scanTabs = scanTabs.filter(i => i !== tab.id); await safeRemove(tab.id, true); }
      try {
        if (o.error === 'cancelled') return;
        if (o.error || !Array.isArray(o.items)) { skippedClasses++; await dlog('map ' + p.code + ' failed: ' + (o.error || 'no items'), true); return; }
        const fp = SOSParse.indexFingerprint(o.items);
        itemsTotal += o.items.length;
        const indexNew = fps[cl.identifier] !== fp;
        let text = indexNew ? SOSParse.buildIndexText(p.code, o.items, BB, 60000) : null;
        const cand0 = SOSParse.pickSyllabus(o.items);
        await recordHrefs(o.items);
        const byType = {}; o.items.forEach(i => { byType[i.type] = (byType[i.type] || 0) + 1; });
        await dlog('mapped ' + p.code + ': ' + o.items.length + ' items ' + JSON.stringify(byType) + (o.truncated ? ' (capped)' : '') + (cand0 ? ', syllabus candidate: ' + cand0.type : ', no syllabus candidate'));
        // the class's syllabus: one targeted item, 25 s cap, remembered on success
        let sylItem = null, sylKey = '';
        const ranked = SOSParse.rankSyllabus(o.items, 3);
        const cand = ranked[0];
        if (!cand) { await rxAdd('sylNeed', 1); }
        else if (syl[cl.identifier] && ranked.some(c0 => syl[cl.identifier] === SOSParse.hash36(String(c0.href).split('?')[0]))) { /* already added in an earlier run */ }
        else {
          await progress(runId, { phase: 'deep', msg: 'Getting the syllabus for ' + p.code + ' (' + k + ' of ' + N + ')', pct: pctAt(finished) });
          let res = { ok: false, line: 'none' }, used = cand;
          for (const c0 of ranked) { // document first, then file, then link: the first one that reads wins
            used = c0; sylKey = SOSParse.hash36(String(c0.href).split('?')[0]);
            res = await Promise.race([fetchContent(c0.href), sleep(25000).then(() => ({ ok: false, line: 'timeout' }))]);
            if (res.ok || /Allow (links and )?files? ?(downloads)?|Allow this site|Allow links/.test(res.line || '')) break; // a missing permission will not fix itself on the next candidate
          }
          if (!res.ok) sylKey = ''; // only a syllabus that was actually read is ever remembered as added
          await dlog('syllabus ' + p.code + ': ' + (res.ok ? res.kind : 'no (' + String(res.line || '').slice(0, 60) + ')'), !res.ok);
          if (!res.ok) { await rxAdd('sylNeed', 1); if (/Allow file downloads/.test(res.line || '')) await rxPatch({ sylPerm: true }); }
          else if (res.kind === 'text') {
            const title = String(used.title || res.title || 'Syllabus').slice(0, 100);
            if (text) text = (text + '\n\n== Syllabus: ' + title + ' ==\n' + res.text).slice(0, 100000); // one upload for index and syllabus
            else sylItem = { kind: 'text', title: 'Syllabus (' + p.code + ')', text: res.text };
          } else sylItem = { kind: 'pdf', title: 'Syllabus (' + p.code + ')', b64: res.b64, filename: res.filename };
        }
        if (!text && !sylItem && !sylKey) { unchanged++; return; } // nothing new for this class
        if (!(await stillMine(runId))) return;
        await qPush({ identifier: cl.identifier, code: p.code, text, items: o.items.length, fp, syl: sylItem, sylKey, sylInIndex: !!(text && sylKey && !sylItem) }); // the site uploads it now
      } finally {
        finished++;
        await progress(runId, { pct: pctAt(finished) });
      }
    };
    const worker = async () => { for (;;) { const i = next++; if (i >= N) return; await mapOne(classes[i]); } };
    await Promise.all([worker(), worker(), worker()]); // up to 3 tabs at once
    const s = await get();
    if (s.scan && s.scan.runId === runId && s.deep) { s.deep.skipped = unchanged; s.deep.skippedClasses = skippedClasses; s.deep.items = itemsTotal; await put(s); }
    await finish();
    await waitForDrain(runId);
    await finalizeDone();
  } catch (e) { await finish('error'); await waitForDrain(runId); await finalizeDone(); }
}
async function waitForDrain(runId) { // up to ~6 minutes, only while the site tab keeps polling (heartbeat < 45 s old)
  const t0 = Date.now();
  while (Date.now() - t0 < 360000) {
    const s = await get();
    if (!s.scan || s.scan.runId !== runId && s.scan.phase !== 'deep' && s.scan.phase !== 'sending') return;
    if (!s.deep || !(await qGet()).length) return;
    if (Date.now() - (s.scan.startedAt || 0) > 45000) return;
    await sleep(1500);
  }
}


// ---- Daily re-scan (opt-in, default off). Needs Chrome running. Quiet: no panel pop-ups, no focus, no prompts. ----
const DAY = 24 * 3600 * 1000;
const HOUR = 3600 * 1000;
const getDaily = async () => (await chrome.storage.local.get('daily')).daily || { on: true }; // default ON; the student can switch it off
const putDaily = (daily) => chrome.storage.local.set({ daily });
async function applyAlarm() {
  const dl = await getDaily();
  if (dl.on) { const a = await chrome.alarms.get('daily-rescan'); if (!a) chrome.alarms.create('daily-rescan', { periodInMinutes: 1440, when: Math.max(Date.now() + 60000, (dl.lastOkAt || Date.now()) + DAY) }); }
  else chrome.alarms.clear('daily-rescan');
}
async function setBadge(text, color) { try { await chrome.action.setBadgeText({ text }); if (color) await chrome.action.setBadgeBackgroundColor({ color }); } catch (e) { /* ignore */ } }
// Ends a quiet run without any UI: records the status, shows "!" when sign-in is needed, cleans up only our own tabs.
async function quietEnd(status) {
  await closeScanTabs();
  const dl = await getDaily(); dl.lastStatus = status; dl.lastAttemptAt = Date.now(); await putDaily(dl);
  if (status === 'needs-signin') await setBadge('!', '#B42318');
  const s = await get(); s.scan = null; s.sent = null; s.import = null; s.deep = null; s.quiet = false; await put(s, true); await rxReset(); await qClear();
}
async function runDaily(why) {
  const dl = await getDaily();
  if (!dl.on) return;
  if (Date.now() - (dl.lastOkAt || 0) < 20 * HOUR) return; // a good scan is under 20 h old: nothing to do
  if (Date.now() - (dl.lastAttemptAt || 0) < 20 * HOUR) return; // never more than one run per 20 h
  const s = await getFresh();
  if (s.scan && RUNNING.indexOf(s.scan.phase) >= 0) return; // a scan is already running
  dl.lastAttemptAt = Date.now(); await putDaily(dl);
  await dlog('daily rescan (' + why + ')');
  runScan({ tabId: null, kind: 'panel' }, { quiet: true });
}
async function catchUp() { // browser start / service worker wake: run if the last good scan is older than a day
  const dl = await getDaily();
  if (!dl.on) return;
  if (!dl.lastOkAt) return; // nothing to catch up before the student's first scan
  if (Date.now() - dl.lastOkAt > DAY) runDaily('catch-up');
}
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === 'daily-rescan') runDaily('alarm');
  if (a.name === 'close-reader') closeWarm();
  if (a.name === 'clear-badge') chrome.action.getBadgeText({}, (t) => { if (t !== '!') setBadge(''); });
});


// ---- Complete reset: forget everything this helper stored. Also runs once whenever the extension version changes. ----
async function resetHelper(reason) {
  try { await closeScanTabs(); } catch (e) { /* only helper-created tabs, nothing else */ }
  try { await chrome.storage.session.clear(); } catch (e) { /* ignore */ }
  try { await chrome.storage.local.clear(); } catch (e) { /* ignore */ }
  try { await chrome.alarms.clearAll(); } catch (e) { /* ignore */ }
  await setBadge('');
  scanTabs = []; scanWin = null;
  await chrome.storage.local.set({ version: chrome.runtime.getManifest().version, resetAt: Date.now() }); // defaults apply: daily ON, no hashes, no fingerprints
  await applyAlarm(); // re-creates only the default daily alarm
  await dlog('helper reset (' + reason + ')');
}
// A new build forgets only the uploaded-item memory (so everything is re-checked once) and the run state. Settings (daily re-scan),
// the "allow links and files" answer, the recorded content tree and the link allow-list are kept. The full wipe stays on the button.
async function softReset(reason) {
  try { await closeScanTabs(); await closeWarm(); } catch (e) { /* only helper-created tabs */ }
  try { await chrome.storage.session.clear(); } catch (e) { /* ignore */ }
  try { await chrome.storage.local.remove(['fps', 'syl', 'deepDone']); } catch (e) { /* ignore */ }
  await chrome.storage.local.set({ version: chrome.runtime.getManifest().version });
  await dlog('soft reset (' + reason + ')');
}
async function checkVersion() {
  try {
    const cur = chrome.runtime.getManifest().version;
    const seen = (await chrome.storage.local.get('version')).version;
    if (seen !== cur) await softReset(seen ? 'version ' + seen + ' to ' + cur : 'first run');
  } catch (e) { /* ignore */ }
}



const FILE_ORIGINS = ['https://*.blackboard.com/*', 'https://*.blackboardcdn.com/*', 'https://*.amazonaws.com/*', 'https://docs.google.com/*', 'https://drive.google.com/*', 'https://*.googleusercontent.com/*', 'https://onedrive.live.com/*', 'https://1drv.ms/*', 'https://*.sharepoint.com/*', 'https://*.officeapps.live.com/*'];
const MAX_FILE = 10 * 1024 * 1024;
const b64 = (u8) => { let s = ''; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); };
// FILES: find the real file address in the item's viewer (helper tab), then fetch it from the worker with the student's session.
// Needs the optional host permission (granted once from the popup button). Reads the bytes in memory only; nothing is saved to disk.
async function fetchFileItem(path) {
  let granted = false;
  try { granted = await chrome.permissions.contains({ origins: FILE_ORIGINS }); } catch (e) { /* ignore */ }
  if (!granted) return { ok: false, line: 'Allow file downloads once in the helper popup, then try again' };
  await fetchStep('Opening it in Blackboard…', 35);
  let found = await treeFile(path); // the page's own content tree already gave the real file address: no viewer window needed
  if (found) await dlog('file address from the content tree (' + SOSFiles.kindOf(found.mime, found.name) + ', ' + found.size + ' bytes)');
  if (!found) found = await withVisibleTab(BB + path, (tab) => askTab(tab.id, { type: 'findFile' }, 32000, 'fetch'), (x) => !x || x.error);
  if (!found || found.error || !/^\/bbcswebdav\//.test(found.src || '')) { await dlog('file url not found: ' + JSON.stringify((found && found.diag) || null), true); return { ok: false, line: 'Could not find the file on that page: open it in Blackboard' }; }
  let resp;
  await fetchStep('Reading the page…', 55);
  try { resp = await fetch(BB + found.src, { credentials: 'include', redirect: 'follow' }); }
  catch (e) { await dlog('file fetch failed: ' + String(e).slice(0, 80), true); return { ok: false, line: 'Blackboard would not hand over the file: open it in Blackboard' }; }
  try { const u = new URL(resp.url); await dlog('file fetch ' + resp.status + ' via ' + u.hostname + u.pathname.split('/').slice(0, 2).join('/') + ' type ' + (resp.headers.get('content-type') || '').split(';')[0]); } catch (e) { /* ignore */ }
  if (!resp.ok) return { ok: false, line: 'Blackboard refused the download (' + resp.status + ')' };
  const len = parseInt(resp.headers.get('content-length') || '0', 10);
  if (len > MAX_FILE) return { ok: false, line: 'That file is over 10 MB: open it in Blackboard' };
  const bytes = new Uint8Array(await resp.arrayBuffer());
  if (bytes.length > MAX_FILE) return { ok: false, line: 'That file is over 10 MB: open it in Blackboard' };
  const cd = resp.headers.get('content-disposition') || '';
  const nm = ((cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i) || [])[1] || '').trim();
  let name = nm; try { name = decodeURIComponent(nm); } catch (e) { /* keep raw */ }
  if (!name) { try { name = decodeURIComponent(new URL(resp.url).pathname.split('/').pop() || ''); } catch (e) { name = ''; } }
  const kind = SOSFiles.kindOf(resp.headers.get('content-type') || found.mime, name || found.name || found.src);
  if (!kind) return { ok: false, line: 'That file type cannot be read: open it in Blackboard' };
  const title = (found.title || name || found.name || 'Blackboard file').slice(0, 100);
  try {
    const r = await SOSFiles.toText(kind, bytes);
    if (r.pdf) return { ok: true, kind: 'pdf', b64: b64(bytes), filename: ((name || 'file.pdf').replace(/[^\w.\- ]+/g, '_').replace(/\.pdf$/i, '') + '.pdf').slice(0, 80), title, bytes: bytes.length };
    if (!r.text || r.text.trim().length < 20) return { ok: false, line: 'No readable text in that file: open it in Blackboard' };
    return { ok: true, kind: 'text', text: r.text, title, chars: r.text.length };
  } catch (e) { return { ok: false, line: String(e && e.message) === 'legacy' ? 'Save it as PDF or open it in Blackboard' : 'Could not read that file: open it in Blackboard' }; }
}


// ---- Content tree from the page's own REST responses: ids, titles, file addresses. Used for real file URLs and the link allow-list. ----
let feedChain = Promise.resolve();
function feedStore(course, items) {
  const job = async () => {
    if (!/^_\d+_1$/.test(course)) return;
    const all = (await chrome.storage.local.get('tree')).tree || {};
    const c = all[course] || {};
    items.slice(0, 400).forEach(i => {
      if (!i || !/^_\d+_1$/.test(String(i.id))) return;
      const o = { t: String(i.title || '').slice(0, 120), h: String(i.h || '').slice(0, 60) };
      if (i.file && /^\/bbcswebdav\//.test(String(i.file.url || ''))) o.f = { n: String(i.file.name || '').slice(0, 100), m: String(i.file.mime || '').slice(0, 100), s: Number(i.file.size) || 0, u: i.file.url };
      if (i.link && /^https:\/\//.test(String(i.link))) o.l = String(i.link).slice(0, 500);
      c[i.id] = o;
    });
    const keys = Object.keys(c); if (keys.length > 1500) keys.slice(0, keys.length - 1500).forEach(k => delete c[k]);
    all[course] = c;
    const ck = Object.keys(all); if (ck.length > 30) ck.slice(0, ck.length - 30).forEach(k => delete all[k]);
    await chrome.storage.local.set({ tree: all });
    await recordHrefs(Object.values(c).filter(x => x.l).map(x => ({ href: x.l }))); // external links the page itself listed are fetchable
  };
  const p = feedChain.then(job, job); feedChain = p.catch(() => {}); return p;
}
// A file item path /ultra/courses/_c_1/file/_id_1 -> the permanent file address the page told us about (no viewer tab needed).
async function treeFile(path) {
  const m = String(path).match(/^\/ultra\/courses\/(_\d+_1)\/file\/(_\d+_1)/);
  if (!m) return null;
  const all = (await chrome.storage.local.get('tree')).tree || {};
  const it = all[m[1]] && all[m[1]][m[2]];
  return it && it.f ? { src: it.f.u, name: it.f.n, mime: it.f.m, size: it.f.s, title: it.t } : null;
}

// ---- LINKS: items that point out of Blackboard (Google Docs, Drive, OneDrive/SharePoint, other pages). Only addresses the helper
// itself recorded in a class index may be fetched (a web page cannot make the helper fetch arbitrary URLs); https only; 10 MB cap. ----
const hrefKey = (u) => SOSParse.hash36(String(u).split('#')[0].split('?')[0].replace(/\/+$/, ''));
async function recordHrefs(items) { // called after each index map
  const set = (await chrome.storage.local.get('idxHrefs')).idxHrefs || {};
  (items || []).forEach(i => { if (/^https:/.test(i.href || '')) set[hrefKey(i.href)] = 1; });
  const keys = Object.keys(set); if (keys.length > 6000) keys.slice(0, keys.length - 6000).forEach(k => delete set[k]);
  await chrome.storage.local.set({ idxHrefs: set });
}
// Where to get the readable version of a link.
function linkPlan(urlStr) {
  let u; try { u = new URL(urlStr); } catch (e) { return null; }
  if (u.protocol !== 'https:' || u.username || u.password) return null;
  const h = u.hostname.toLowerCase(); let m;
  if (h === 'docs.google.com' && (m = u.pathname.match(/^\/document\/d\/([\w-]+)/))) return { kind: 'gdoc', urls: ['https://docs.google.com/document/d/' + m[1] + '/export?format=txt', 'https://docs.google.com/document/d/' + m[1] + '/mobilebasic'] };
  if (h === 'docs.google.com' && (m = u.pathname.match(/^\/presentation\/d\/([\w-]+)/))) return { kind: 'gdoc', urls: ['https://docs.google.com/presentation/d/' + m[1] + '/export?format=txt'] };
  if (h === 'drive.google.com' && (m = u.pathname.match(/^\/file\/d\/([\w-]+)/) || (u.searchParams.get('id') ? [0, u.searchParams.get('id')] : null))) return { kind: 'gdrive', urls: ['https://drive.google.com/uc?export=download&id=' + m[1]] };
  if (h === '1drv.ms' || h === 'onedrive.live.com' || h.endsWith('.sharepoint.com') || h.endsWith('.officeapps.live.com')) { const d2 = new URL(u.href); d2.searchParams.set('download', '1'); return { kind: 'onedrive', urls: [d2.href] }; }
  return { kind: 'page', urls: [u.href], origin: u.origin };
}
async function readBytesResponse(resp, fallbackName) {
  const len = parseInt(resp.headers.get('content-length') || '0', 10);
  if (len > MAX_FILE) return { ok: false, line: 'That file is over 10 MB: open it in Blackboard' };
  const bytes = new Uint8Array(await resp.arrayBuffer());
  if (bytes.length > MAX_FILE) return { ok: false, line: 'That file is over 10 MB: open it in Blackboard' };
  const cd = resp.headers.get('content-disposition') || '';
  let name = ((cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i) || [])[1] || '').trim();
  try { name = decodeURIComponent(name); } catch (e) { /* keep raw */ }
  let kind = SOSFiles.kindOf(resp.headers.get('content-type'), name || fallbackName || '');
  if (!kind && bytes.length > 4 && bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46) kind = 'pdf'; // %PDF
  if (!kind && bytes.length > 3 && bytes[0] === 0x50 && bytes[1] === 0x4b) kind = /ppt/i.test(name) ? 'pptx' : 'docx'; // zip: office file
  return { bytes, name, kind };
}
async function fetchExternal(urlStr) {
  let granted = false;
  try { granted = await chrome.permissions.contains({ origins: FILE_ORIGINS }); } catch (e) { /* ignore */ }
  if (!granted) return { ok: false, line: 'Allow links and files once in the helper popup, then try again' };
  const plan = linkPlan(urlStr);
  if (!plan) return { ok: false, line: 'That link cannot be read: open it in Blackboard' };
  const rec = (await chrome.storage.local.get('idxHrefs')).idxHrefs || {};
  const known = !!rec[hrefKey(urlStr)] || (Object.keys(rec).length === 0 && plan.kind !== 'page'); // an older build recorded nothing: then the known document hosts are accepted
  await dlog('link guard: ' + (known ? 'allowed' : 'refused (not in the class index)') + ' kind ' + plan.kind);
  if (!known) return { ok: false, line: 'That link is not in the class index: open it in Blackboard' }; // only recorded links
  if (!rec[hrefKey(urlStr)]) { rec[hrefKey(urlStr)] = 1; await chrome.storage.local.set({ idxHrefs: rec }); }
  if (plan.kind === 'page') return await fetchLinkedPage(plan);
  for (const u of plan.urls) {
    let resp;
    try { resp = await fetch(u, { credentials: 'include', redirect: 'follow' }); } catch (e) { await dlog('link fetch failed (' + plan.kind + '): ' + String(e).slice(0, 60), true); continue; }
    let host = ''; try { host = new URL(resp.url).hostname; } catch (e) { /* ignore */ }
    await dlog('link fetch ' + plan.kind + ' ' + resp.status + ' via ' + host);
    if (/(^|\.)accounts\.google\.com$|login\.microsoftonline\.com$|login\.live\.com$/.test(host)) return { ok: false, line: 'That document is private: open it in Blackboard' };
    if (!resp.ok) continue;
    const r = await readBytesResponse(resp, '');
    if (r.ok === false) return r;
    let kind = r.kind;
    if (plan.kind === 'gdoc' && !kind) kind = /export\?format=txt/.test(u) ? 'txt' : 'html';
    if (!kind) continue;
    try {
      const t = await SOSFiles.toText(kind, r.bytes);
      if (t.pdf) return { ok: true, kind: 'pdf', b64: b64(r.bytes), filename: ((r.name || 'syllabus').replace(/[^\w.\- ]+/g, '_').replace(/\.pdf$/i, '') + '.pdf').slice(0, 80), title: '', bytes: r.bytes.length };
      if (SOSParse.looksJunk(t.text)) continue; // a sign-in page or an empty shell: never upload it
      return { ok: true, kind: 'text', text: t.text, title: '', chars: t.text.length };
    } catch (e) { if (String(e && e.message) === 'legacy') return { ok: false, line: 'Save it as PDF or open it in Blackboard' }; }
  }
  if (plan.kind === 'onedrive') return await fetchLinkedPage({ urls: [urlStr], origin: new URL(urlStr).origin, kind: 'page' });
  return { ok: false, line: 'Could not read that link: open it in Blackboard' };
}
// Any other page (and OneDrive when the download route is refused): a visible helper tab, text read with the real-content checks.
// Needs the site's own permission (popup button "Allow this site"); no clicking, no forms, only reading.
async function fetchLinkedPage(plan) {
  let has = false;
  try { has = await chrome.permissions.contains({ origins: [plan.origin + '/*'] }); } catch (e) { /* ignore */ }
  if (!has) { await chrome.storage.local.set({ needOrigin: plan.origin }); return { ok: false, line: 'Allow this site in the helper popup (' + new URL(plan.origin).hostname + '), then try again' }; }
  try {
    return await withVisibleTab(plan.urls[0], async (tab) => {
      const t0 = Date.now(); let text = '';
      while (Date.now() - t0 < 25000) {
        await sleep(1200);
        try { const [r] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => (document.body && document.body.innerText) || '' }); text = (r && r.result) || ''; } catch (e) { text = ''; }
        if (text && !SOSParse.looksJunk(text)) break;
      }
      if (!text || SOSParse.looksJunk(text)) return { ok: false, line: 'Could not read it. Open it in Blackboard.' };
      return { ok: true, kind: 'text', text: text.replace(/\s+\n/g, '\n').trim().slice(0, 100000), title: '', chars: Math.min(text.length, 100000) };
    }, (x) => !x.ok);
  } catch (e) { return { ok: false, line: 'Could not open it: ' + String(e && e.message || e).slice(0, 60) }; }
}

// Item pages and file viewers only render when the tab is VISIBLE: open ours active for a moment (one at a time) and put the
// student's own tab back right afterwards. Our tab is registered and closed in finally.
let visChain = Promise.resolve();
// PRIMARY page reader: a small window that never takes focus. It sits mostly off the corner of the student's own window with a sliver
// on screen (so Chrome still renders it), focus is handed straight back to his window, and it is closed in finally. The student's
// tab and window are never activated, navigated or focused by this path. `empty(result)` says the window read produced nothing,
// in which case the answer is ok:false (nothing is ever brought to the front).
// A WARM reader window is reused for consecutive fetches (no new window, no new tab, no focus change each time) and closed after 20 s idle.
let warm = null, warmTimer = null; // { winId, tabId }
async function closeWarm() {
  clearTimeout(warmTimer); warmTimer = null;
  if (!warm) return;
  const w = warm; warm = null;
  scanTabs = scanTabs.filter(i => i !== w.tabId);
  await safeRemove(w.tabId, true);
  try { await chrome.windows.remove(w.winId); } catch (e) { /* already closed with its tab */ }
}
function touchWarm() { clearTimeout(warmTimer); warmTimer = setTimeout(() => { closeWarm(); }, 20000); try { chrome.alarms.create('close-reader', { delayInMinutes: 1 }); } catch (e) { /* ignore */ } }
async function navTab(tabId, url) { // point our own tab at a new address and wait until it has really loaded it
  const want = new URL(url).pathname;
  await chrome.tabs.update(tabId, { url });
  const t0 = Date.now();
  for (;;) {
    await sleep(120);
    let t; try { t = await chrome.tabs.get(tabId); } catch (e) { throw new Error('reader tab closed'); }
    let p = ''; try { p = new URL(t.url || '').pathname; } catch (e) { /* ignore */ }
    if (p === want && (!t.status || t.status === 'complete')) return;
    if (Date.now() - t0 > 15000) return; // let the content script answer decide
  }
}
// PRIMARY page reader (see above for placement and focus rules). `empty(result)` says the read produced nothing -> ok:false.
function withVisibleTab(url, fn, empty) {
  const job = async () => {
    let res = null, lf = null;
    try {
      let reuse = false;
      if (warm) { try { await chrome.tabs.get(warm.tabId); reuse = true; } catch (e) { warm = null; } }
      if (reuse) {
        await navTab(warm.tabId, url); // same window, same tab: only its address changes (never activated)
        await dlog('reader window reused');
        res = await fn({ id: warm.tabId });
      } else {
        try { lf = await chrome.windows.getLastFocused(); } catch (e) { /* ignore */ }
        // Chrome refuses bounds less than 50% on screen: at least 640x400 of the 1280x800 window stays visible, low in his window's corner.
        const left = lf ? Math.max(0, (lf.left || 0) + (lf.width || 1920) - 700) : 900;
        const top = lf ? Math.max(0, (lf.top || 0) + (lf.height || 1080) - 440) : 500;
        let win;
        try { win = await chrome.windows.create({ url, type: 'popup', state: 'normal', focused: false, width: 1280, height: 800, left, top }); }
        catch (e1) { await dlog('reader window bounds refused: ' + String(e1 && e1.message || e1).slice(0, 80), true); win = await chrome.windows.create({ url, type: 'popup', focused: false }); }
        const tab = win.tabs && win.tabs[0];
        if (lf && lf.id != null) { try { await chrome.windows.update(lf.id, { focused: true }); } catch (e) { /* ignore */ } } // hand focus straight back
        if (!tab) throw new Error('no tab in the reader window');
        await regAdd(tab.id, win.id); scanTabs.push(tab.id);
        warm = { winId: win.id, tabId: tab.id };
        await dlog('reader window opened');
        res = await fn(tab);
      }
    } catch (e) {
      await dlog('reader window failed: ' + String(e && e.message || e).slice(0, 60), true); res = null;
      await closeWarm(); // a broken reader is thrown away; the next fetch opens a fresh one
    }
    if (warm) touchWarm();
    if (lf && lf.id != null) { try { await chrome.windows.update(lf.id, { focused: true }); } catch (e) { /* ignore */ } }
    if (res && !(empty && empty(res))) return res;
    await dlog('reader window gave nothing', true);
    return res && res.ok === false ? res : { ok: false, line: 'Could not read it. Open it in Blackboard.' };
  };
  const p = visChain.then(job, job); visChain = p.catch(() => {}); return p;
}

// Fetch steps shown on the page ("Finding it in your course…" ...), polled by the site script.
async function fetchStep(line, pct) { try { await chrome.storage.session.set({ fetchStep: { line, pct, t: Date.now() } }); } catch (e) { /* ignore */ } }

async function fetchContent(path) {
  if (/^https:\/\//.test(path)) return await fetchExternal(path); // links out of Blackboard: only ones recorded in the class index
  if (/\/discussion\//.test(path)) return { ok: false, line: 'discussion: open it in Blackboard' };
  if (/\/assessment\//.test(path)) return { ok: false, line: 'assessment: open it in Blackboard' }; // never read quiz, test or exam contents
  if (/\/file\//.test(path)) return await fetchFileItem(path);
  try {
    const t0 = Date.now();
    await fetchStep('Opening it in Blackboard…', 35);
    return await withVisibleTab(BB + path, async (tab) => {
      await fetchStep('Reading the page…', 55);
      const r = await askTab(tab.id, { type: 'deepItem' }, 35000, 'fetch');
      await dlog('read ' + ((Date.now() - t0) / 1000).toFixed(1) + 's');
      if (r.error || !r.text || (!r.doc && SOSParse.looksJunk(r.text))) { await dlog('page not readable: ' + (r.error || 'junk') + ' ' + JSON.stringify(r.diag || null), true); return { ok: false, line: 'Could not read it. Open it in Blackboard.' }; }
      const body = r.doc && r.title ? r.title + '\n' + r.text : r.text; // a short document still needs enough text to be stored
      await dlog('item page read: ' + body.length + ' chars' + (r.doc ? ' (document)' : ''));
      return { ok: true, kind: 'text', title: r.title || '', text: body, chars: body.length, doc: !!r.doc };
    }, (x) => !x.ok);
  } catch (e) { return { ok: false, line: 'Could not open it: ' + String(e && e.message || e).slice(0, 60) }; }
}

// ---- On-demand fetch of ONE item the student asked for on the site (read-only; same Blackboard origin only; one at a time) ----
let fetchBusy = false, lastFetchAt = 0;
async function noteFetch(line) { // the latest fetch result, shown in the popup and in the diagnostics
  try { const r = (await chrome.storage.session.get('diag')).diag || { events: [], lastError: '' }; r.lastFetch = { line: String(line).slice(0, 100), t: Date.now() }; await chrome.storage.session.set({ diag: r }); } catch (e) { /* ignore */ }
}
async function fetchOneItem(rawPath) {
  const path = String(rawPath || '');
  await dlog('fetch request received: ' + (/^https:/.test(path) ? 'external link' : path.replace(/_\d+_1/g, '_N_1').replace(/\?.*/, '').slice(0, 60)));
  const isExt = /^https:\/\/[^\s]{4,600}$/.test(path);
  if (!isExt && (!/^\/ultra\/courses\/_\d+_1\/[A-Za-z0-9_\/\-?=&%.]{1,240}$/.test(path) || path.indexOf('..') >= 0)) { await dlog('fetch guard: refused bad-path', true); await noteFetch('refused: not a Blackboard course link'); return { ok: false, line: 'Not a Blackboard course link' }; }
  if (/\/assessment\//.test(path)) { await dlog('fetch guard: refused assessment-path', true); await noteFetch('refused: assessment'); return { ok: false, line: 'assessment: open it in Blackboard' }; } // never read quiz, test or exam contents
  if (/\/discussion\//.test(path)) { await dlog('fetch guard: refused discussion-path', true); await noteFetch('refused: discussion'); return { ok: false, line: 'discussion: open it in Blackboard' }; }
  if (fetchBusy) { await dlog('fetch guard: refused busy', true); await noteFetch('refused: busy'); return { ok: false, line: 'Another item is being fetched, try again in a moment' }; }
  if (Date.now() - lastFetchAt < 5000) { await dlog('fetch guard: refused rate-limit', true); await noteFetch('refused: rate limit'); return { ok: false, line: 'Please wait a few seconds between items' }; }
  await dlog('fetch guard: allowed ' + (isExt ? 'external' : 'internal'));
  fetchBusy = true; lastFetchAt = Date.now();
  const tStart = Date.now();
  await fetchStep('Finding it in your course…', 15);
  try { const out = await fetchContent(path); await dlog('fetch worker total ' + ((Date.now() - tStart) / 1000).toFixed(1) + 's'); await noteFetch(out.ok ? 'read ' + (out.chars || out.bytes || 0) + (out.kind === 'pdf' ? ' bytes (pdf)' : ' chars') : 'failed: ' + String(out.line || '').slice(0, 60)); return out; }
  finally { fetchBusy = false; }
}

async function cancelScan() {
  await closeScanTabs(); await closeWarm();
  const s = await get();
  s.scan = null; s.import = null; s.deep = null; s.importDone = false; s.sent = null; s.canvasTab = null; s.active = false; s.origin = null;
  await put(s, true); await qClear(); await rxReset();
}

// True when a host is covered by the optional permission patterns ('https://*.x.com/*' = any subdomain of x.com, or x.com itself).
function hostAllowed(host) {
  return FILE_ORIGINS.some((p) => { const m = p.match(/^https:\/\/(\*\.)?([^/]+)\/\*$/); if (!m) return false; return m[1] ? (host === m[2] || host.endsWith('.' + m[2])) : host === m[2]; });
}
// Developer diagnostic: where does a Blackboard file download redirect to? Only the target HOST is kept (no path, no query).
try {
  chrome.webRequest.onBeforeRedirect.addListener(async (d) => {
    try {
      const host = new URL(d.redirectUrl).hostname;
      await dlog('file redirect to host ' + host + ' (status ' + d.statusCode + ')');
      await chrome.storage.session.set({ lastRedirectHost: host });
      const ok = hostAllowed(host);
      if (!ok) await chrome.storage.local.set({ needOrigin: 'https://' + host }); // the popup offers "Allow this site: <host>"
    } catch (e) { /* ignore */ }
  }, { urls: ['https://ualearn.blackboard.com/bbcswebdav/*'] });
} catch (e) { /* webRequest unavailable: no diagnostics, nothing else changes */ }

chrome.runtime.onStartup.addListener(async () => { const s = await get(); s.scan = null; s.sent = null; s.import = null; s.quiet = false; await put(s, true); await checkVersion(); await applyAlarm(); await catchUp(); });
checkVersion().then(() => { applyAlarm(); setTimeout(catchUp, 5000); }); // every service-worker wake: version check first
chrome.runtime.onInstalled.addListener(async () => { await cancelScan(); await checkVersion(); await applyAlarm(); });
// Watchdog: 'state' reads (popup and panel poll it) end a stale run with a clear message via normalize().

chrome.runtime.onMessage.addListener((m, sender, reply) => {
  (async () => {
    if (!m || typeof m.type !== 'string') return reply({});
    const url = sender.url || '';
    const fromBB = url.startsWith(BB + '/');
    const fromSite = url.startsWith(SITE + '/');
    const fromAllow = url.startsWith(chrome.runtime.getURL('allow.html')); // our own one-time question page
    const fromPopup = !sender.tab || fromAllow;
    const s = await getFresh();
    switch (m.type) {
      case 'state': {
        const dg = (await chrome.storage.session.get('diag')).diag || {};
        const daily = await getDaily(); const al = await chrome.alarms.get('daily-rescan');
        if (fromPopup) { const t = await chrome.action.getBadgeText({}); if (t && t !== '!') await setBadge(''); }
        const resetAt = (await chrome.storage.local.get('resetAt')).resetAt || 0;
        const rxs = await rxGet(); if (s.scan) { s.scan.classes = rxs.classes && rxs.classes.length ? rxs.classes : s.scan.classes; s.scan.imported = rxs.imported || s.scan.imported; }
        let filePerm = { granted: false, asked: false };
        try { filePerm = { granted: await chrome.permissions.contains({ origins: FILE_ORIGINS }), asked: !!(await chrome.storage.local.get('fileAsk')).fileAsk }; } catch (e) { /* ignore */ }
        return reply(Object.assign(summary(s), { build: { version: chrome.runtime.getManifest().version, date: BUILD_DATE, label: buildLabel() }, filePerm, lastFetch: dg.lastFetch || null, resetAt, quiet: !!s.quiet, daily: Object.assign({}, daily, { nextAt: al ? al.scheduledTime : null }), diag: { lastError: dg.lastError || '', now: Date.now() } }));
      }
      case 'fetchItem': { // site -> worker: one item, one tab, then the text goes back to the site for upload
        if (!fromSite) return reply({});
        return reply(await fetchOneItem(m.path));
      }
      case 'openAllow': // panel on a Blackboard/site tab: the permission question must be asked from an extension page
        if (!(fromBB || fromSite) || !sender.tab) return reply({});
        await chrome.windows.create({ url: chrome.runtime.getURL('allow.html') + '?tab=' + sender.tab.id, type: 'popup', width: 400, height: 300, focused: true });
        return reply({ ok: true });
      case 'recordMaterial': { // site: a material this helper created (ids only, for a later cleanup)
        if (!fromSite) return reply({});
        const made = (await chrome.storage.local.get('made')).made || [];
        made.push({ c: String(m.courseId || '').slice(0, 12), id: String(m.id || '').slice(0, 24), t: String(m.title || '').slice(0, 100) });
        await chrome.storage.local.set({ made: made.slice(-300) }); return reply({ ok: true });
      }
      case 'cleanupBad': { // popup: ask an open Semester OS tab to remove junk materials (it holds the session)
        if (!fromPopup) return reply({});
        const tabs = await chrome.tabs.query({ url: SITE + '/*' });
        if (!tabs.length) return reply({ ok: false, line: 'Open Semester OS in a tab first' });
        const made = (await chrome.storage.local.get('made')).made || [];
        try { return reply(await chrome.tabs.sendMessage(tabs[0].id, { type: 'cleanup', made })); } catch (e) { return reply({ ok: false, line: 'Reload the Semester OS tab (F5) and try again' }); }
      }
      case 'resetHelper': // popup only, after its inline confirm
        if (!fromPopup) return reply({});
        await resetHelper('button'); return reply({ ok: true });
      case 'dailySet': { // popup or panel toggle
        if (!(fromPopup || fromBB)) return reply({});
        const dl = await getDaily(); dl.on = !!m.on; await putDaily(dl); await applyAlarm();
        if (dl.on) await catchUp();
        return reply({ ok: true });
      }
      case 'siteLine': { // the hand-off tab's live sub-line ("Waiting before the next upload (9 s)"); doubles as a heartbeat
        if (!fromSite || !s.scan || !(s.scan.phase === 'deep' || s.scan.phase === 'sending')) return reply({});
        s.scan.sub = String(m.line || '').slice(0, 100); s.scan.startedAt = Date.now();
        await put(s); return reply({ ok: true });
      }
      case 'feed': { // sanitised content tree seen by the Blackboard page itself (main_hook.js -> bb.js)
        if (!fromBB) return reply({});
        await feedStore(String(m.course || ''), Array.isArray(m.items) ? m.items : []);
        return reply({ ok: true });
      }
      case 'fetchStatus': { if (!fromSite) return reply({}); const fs_ = (await chrome.storage.session.get('fetchStep')).fetchStep; return reply(fs_ && Date.now() - fs_.t < 60000 ? { line: fs_.line, pct: fs_.pct } : {}); }
      case 'closeReader': if (!fromPopup) return reply({}); await closeWarm(); return reply({ ok: true });
      case 'siteNote': if (fromSite) { await dlog(String(m.note || '').slice(0, 100), !!m.err); if (/^fetch (reply sent|upload|material)/.test(String(m.note || ''))) await noteFetch(String(m.note).slice(0, 100)); } return reply({});
      case 'diagText': return reply({ text: await diagText() });
      case 'cancelScan':
        if (!(fromBB || fromPopup || fromSite)) return reply({});
        await cancelScan(); return reply(summary(await get()));
      case 'scan': // the student pressed "Scan my Blackboard" (popup or page panel)
        if (!(fromBB || fromPopup)) return reply({});
        chrome.storage.local.set({ ui: { min: false, hidden: false } });
        { const st = await get(); st.scan = { runId: 'start' + Date.now(), phase: 'courses', courses: 0, deadlines: 0, msg: 'Starting…', pct: 3, startedAt: Date.now() }; st.quiet = false; st.sent = null; await put(st, true); }
        runScan(await originOf((sender.tab && !fromAllow) ? sender.tab.id : Number(m.tabId) || null)); // progress is read through 'state'
        await sleep(300);
        return reply(summary(await get()));
      case 'importDelivered': // site confirms classes and deadlines are in; the deep phase may now upload
        if (!fromSite) return reply({});
        await rxPatch({ importDone: true, imported: { classes: Number(m.classes) || 0, deadlines: Number(m.deadlines) || 0, newDeadlines: Math.max(0, Math.min(999, Number(m.newDeadlines) || 0)) } });
        s.import = null; s.sent = 'delivered'; await dlog('import delivered by site');
        await put(s); return reply({ ok: true });
      case 'classesReady': { // site: the classes this scan added, with ids for the "open this class" rows
        if (!fromSite || !s.scan) return reply({});
        const cl = (Array.isArray(m.classes) ? m.classes : []).slice(0, 12)
          .filter(k => k && /^[a-z0-9]{8}$/.test(String(k.id)))
          .map(k => ({ id: String(k.id), code: String(k.code || '').slice(0, 30), title: String(k.title || '').slice(0, 60), color: /^#[0-9a-fA-F]{6}$/.test(String(k.color || '')) ? String(k.color) : '' }));
        await rxPatch({ classes: cl }); return reply({ ok: true });
      }
      case 'focusSite': // at Done, only when the scan was started somewhere with no panel
        if (!fromSite || !sender.tab || !s.origin || s.origin.kind !== 'other') return reply({});
        if ((await getReg()).tabs.indexOf(sender.tab.id) < 0) return reply({}); // only the helper's own hand-off tab
        /* intentionally nothing: the result is shown silently, no tab or window is ever brought to the front */
        return reply({ ok: true });
      case 'needsSignin': // quiet run: the student site has no session; end quietly
        if (!fromSite) return reply({});
        if (s.deep) s.deep.state = 'finished';
        await quietEnd('needs-signin'); return reply({ ok: true });
      case 'importFailed':
        if (!fromSite) return reply({});
        if (s.quiet) { await quietEnd('error'); return reply({ ok: true }); }
        if (s.deep) s.deep.state = 'finished';
        await dlog('site reported import failure', true);
        s.scan = { runId: s.scan && s.scan.runId, phase: 'error', msg: 'Semester OS could not import your classes. Try again.' }; s.sent = null; s.import = null;
        await put(s); return reply({ ok: true });
      case 'deepNext': { // site asks for the next class text to upload
        if (!fromSite) return reply({ finished: true });
        const d = s.deep;
        const prog = s.scan && s.scan.msg || '';
        if (s.scan && (s.scan.phase === 'deep' || s.scan.phase === 'sending')) await setScanIf(s.scan.runId, { startedAt: Date.now() });
        const dq = await qGet();
        if (!d || (d.state === 'finished' && !dq.length)) {
          await finalizeDone();
          const im = (await rxGet()).imported || {};
          const note = d && d.note === 'error' ? ' (course pages stopped early)' : '';
          return reply({ finished: true, classes: im.classes || 0, deadlines: im.deadlines || 0, pages: d ? d.pages : 0, skipped: d ? (d.skipped || 0) + (d.skippedClasses || 0) : 0, note });
        }
        if (dq.length) return reply({ item: dq[0], progress: prog, pct: s.scan && s.scan.pct });
        return reply({ wait: true, progress: prog, pct: s.scan && s.scan.pct });
      }
      case 'deepSent': {
        if (!fromSite || !s.deep) return reply({});
        const head = await qShift(String(m.identifier));
        if (!head) return reply({});
        if (m.ok && head.text) {
          const fps = (await chrome.storage.local.get('fps')).fps || {};
          fps[head.identifier] = head.fp; await chrome.storage.local.set({ fps });
          const s2 = await get(); // fresh copy: never write back a stale snapshot
          if (s2.deep) { s2.deep.pages += head.items; s2.deep.ok.push(head.identifier); await put(s2); }
        }
        if (head.sylKey && (m.sylOk || (m.ok && head.sylInIndex))) {
          const syl = (await chrome.storage.local.get('syl')).syl || {};
          syl[head.identifier] = head.sylKey; await chrome.storage.local.set({ syl });
          await rxAdd('sylAdded', 1);
        }
        return reply({ ok: true });
      }
      case 'canvasStart': // popup, after the student pressed the button and the active tab was injected
        if (!fromPopup) return reply({});
        s.canvasTab = Number(m.tabId) || null; s.sent = null; s.import = null;
        s.origin = { tabId: s.canvasTab, kind: 'other' };
        s.scan = { runId: 'canvas' + Date.now(), phase: 'courses', courses: 0, deadlines: 0, msg: 'Reading your courses', startedAt: Date.now() }; await put(s, true);
        return reply(summary(s));
      case 'canvasProgress':
        if (!sender.tab || sender.tab.id !== s.canvasTab || !s.scan) return reply({});
        s.scan.phase = m.phase === 'calendar' ? 'calendar' : 'courses';
        s.scan.courses = Math.min(Number(m.n) || 0, 99); await put(s); return reply({});
      case 'canvasFail':
        if (!sender.tab || sender.tab.id !== s.canvasTab) return reply({});
        s.canvasTab = null; await put(s);
        if (m.reason === 'not-canvas') { runScan(); return reply({}); } // not a Canvas page: fall back to the Blackboard scan
        await setScan({ phase: 'error', msg: String(m.msg || 'Could not read your Canvas classes.').slice(0, 120) });
        return reply({});
      case 'canvasData': {
        if (!sender.tab || sender.tab.id !== s.canvasTab) return reply({});
        const d = m.data || {};
        const classes = (Array.isArray(d.classes) ? d.classes : []).slice(0, 12);
        s.canvasTab = null;
        if (!classes.length) { s.scan = { runId: s.scan && s.scan.runId, phase: 'error', msg: 'No current classes found in Canvas.' }; await put(s); return reply({}); }
        s.import = { source: d.source === 'canvas' ? 'canvas' : 'blackboard', classes };
        s.sent = 'pending';
        s.scan = { runId: s.scan && s.scan.runId, phase: 'sending', pct: 35, startedAt: Date.now(), courses: classes.length, deadlines: classes.reduce((a, x) => a + (x.assignments || []).length, 0), msg: 'Sending classes' };
        s.deep = null; await rxReset(); await qClear();
        await put(s);
        await openSite('/onboarding');
        return reply({});
      }
      case 'scanProgress':
        if (!fromBB) return reply({});
        if (s.scan && s.scan.phase === 'courses') { s.scan.courses = Math.min(Number(m.courses) || 0, 99); await put(s); }
        return reply({});
      case 'start': // the student pressed the guided syllabus button
        if (!(fromBB || fromPopup)) return reply({});
        s.active = true; s.sent = null; await put(s);
        if (fromPopup) await chrome.tabs.create({ url: BB + '/ultra/course', active: false });
        return reply(summary(s));
      case 'setQueue':
        if (!fromBB) return reply({});
        s.queue = (Array.isArray(m.queue) ? m.queue : []).slice(0, 12)
          .map(q => ({ id: String(q.id).slice(0, 40), code: String(q.code).slice(0, 40) }));
        await put(s); return reply(summary(s));
      case 'capture': {
        if (!fromBB) return reply({});
        const c = m.item || {};
        const item = { kind: c.kind === 'pdf' ? 'pdf' : 'text', filename: String(c.filename || 'syllabus.pdf').slice(0, 80), code: String(c.code || '').slice(0, 40) };
        if (item.kind === 'pdf') item.b64 = String(c.b64 || '').slice(0, 6 * 1024 * 1024);
        else item.text = String(c.text || '').slice(0, 60000);
        s.captured[item.code] = item; await put(s); return reply(summary(s));
      }
      case 'setCurrent':
        if (!fromBB) return reply({});
        s.current = String(m.id).slice(0, 40); await put(s); return reply(summary(s));
      case 'skip':
        if (!fromBB) return reply({});
        s.captured[String(m.code).slice(0, 40)] = { kind: 'skipped' }; await put(s); return reply(summary(s));
      case 'reset':
        s.active = false; s.queue = []; s.captured = {}; s.sent = null; s.scan = null; s.import = null; await put(s, true); return reply(summary(s));
      case 'send': // open the student site; its content script pulls the items
        if (!(fromBB || fromPopup)) return reply({});
        s.active = false; s.sent = 'pending'; await put(s);
        await chrome.tabs.create({ url: SITE + '/study', active: false });
        return reply(summary(s));
      case 'pending': {
        if (fromSite) await dlog('site asked for pending (sent=' + s.sent + ', hasImport=' + !!s.import + ')');
        const live = s.scan && (s.scan.phase === 'sending' || s.scan.phase === 'deep') && Date.now() - (s.scan.startedAt || 0) < 100000;
        if (s.import && !live) { s.import = null; if (s.sent === 'pending') s.sent = null; await put(s); } // stale: never post an old import on a plain page load
        if (!fromSite || s.sent !== 'pending' || (s.import && !live)) return reply({ items: [], import: null, deep: null });
        return reply({ items: Object.values(s.captured).filter(v => v.kind === 'pdf' || v.kind === 'text'), import: s.import || null, deep: null });
      }
      case 'delivered':
        if (!fromSite) return reply({});
        s.sent = 'done'; s.captured = {}; s.queue = []; s.import = null;
        if (m.result && s.scan && s.scan.phase !== 'done') s.scan = { runId: s.scan.runId, phase: 'done', pct: 100, classes: (await rxGet()).classes || [], courses: Number(m.result.classes) || 0, deadlines: Number(m.result.deadlines) || 0, msg: String(m.result.msg || '').slice(0, 120) };
        await put(s); return reply({ ok: true });
    }
    reply({});
  })();
  return true;
});
