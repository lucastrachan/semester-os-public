// Mock-chrome test of the scan start path (run: node extension/tests/test_start_path.js).
// Proves: (1) pressing Scan creates the scan window and does NOT close it before the page answers;
// (2) a stale 'state' poll that read an OLD error state cannot overwrite a newer run (the silent-stop race);
// (3) a crash while starting always leaves a visible error state; (4) only tabs the helper created are ever closed.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.join(__dirname, '..');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const zlib = require('zlib');
function crc32(buf) { let c, crc = 0xFFFFFFFF; for (let n = 0; n < buf.length; n++) { c = (crc ^ buf[n]) & 0xFF; for (let k = 0; k < 8; k++) c = c & 1 ? (c >>> 1) ^ 0xEDB88320 : c >>> 1; crc = (crc >>> 8) ^ c; } return (crc ^ 0xFFFFFFFF) >>> 0; }
function makeZip(entries) {
  const parts = [], central = []; let off = 0;
  for (const [name, text] of entries) {
    const raw = Buffer.from(text), def = zlib.deflateRawSync(raw), nm = Buffer.from(name), crc = crc32(raw);
    const lh = Buffer.alloc(30); lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(8, 8); lh.writeUInt32LE(crc, 14); lh.writeUInt32LE(def.length, 18); lh.writeUInt32LE(raw.length, 22); lh.writeUInt16LE(nm.length, 26);
    parts.push(lh, nm, def);
    const ch = Buffer.alloc(46); ch.writeUInt32LE(0x02014b50, 0); ch.writeUInt16LE(20, 4); ch.writeUInt16LE(20, 6); ch.writeUInt16LE(8, 10); ch.writeUInt32LE(crc, 16); ch.writeUInt32LE(def.length, 20); ch.writeUInt32LE(raw.length, 24); ch.writeUInt16LE(nm.length, 28); ch.writeUInt32LE(off, 42);
    central.push(ch, nm); off += 30 + nm.length + def.length;
  }
  const cd = Buffer.concat(central), eocd = Buffer.alloc(22); eocd.writeUInt32LE(0x06054b50, 0); eocd.writeUInt16LE(entries.length, 8); eocd.writeUInt16LE(entries.length, 10); eocd.writeUInt32LE(cd.length, 12); eocd.writeUInt32LE(off, 16);
  return Buffer.concat([...parts, cd, eocd]);
}


const allEnvs = [];
function makeChrome(opts) {
  opts = opts || {};
  const mem = { session: {}, local: { version: 'test' } };
  const log = { windowsCreated: [], tabsRemoved: [], tabsCreated: [], windowsRemoved: [], tabsReloaded: [], alarms: [], winUpdates: [], tabUpdates: [], order: [] };
  const userTab = { id: 1, url: 'https://ualearn.blackboard.com/ultra/course', windowId: 100 }; // the student's own tab
  const tabs = { 1: userTab };
  let nextId = 50, sendCount = 0;
  const area = (name) => ({
    get: async (key) => { await sleep(opts.storageDelay || 1); const k = typeof key === 'string' ? key : null; return k ? (k in mem[name] ? { [k]: JSON.parse(JSON.stringify(mem[name][k])) } : {}) : JSON.parse(JSON.stringify(mem[name])); },
    clear: async () => { Object.keys(mem[name]).forEach(k => delete mem[name][k]); },
    remove: async (keys) => { [].concat(keys).forEach(k => delete mem[name][k]); },
    set: async (obj) => { await sleep((opts.slowOld && obj.scan && obj.scan.scan && obj.scan.scan.runId === 'old') ? 80 : (opts.storageDelay || 1)); Object.keys(obj).forEach(k => { mem[name][k] = JSON.parse(JSON.stringify(obj[k])); }); }
  });
  let listener = null;
  const chrome = {
    runtime: {
      id: 'x', getManifest: () => ({ version: 'test' }), getURL: (f) => 'chrome-extension://x/' + f,
      onMessage: { addListener: (fn) => { listener = fn; } },
      onStartup: { addListener() {} }, onInstalled: { addListener() {} }
    },
    storage: { session: area('session'), local: Object.assign(area('local'), { set: async (obj) => { Object.keys(obj).forEach(k => { mem.local[k] = JSON.parse(JSON.stringify(obj[k])); }); } }) },
    alarms: { get: async () => null, create: (n, i) => { log.alarms.push(n); }, clear() {}, clearAll: async () => { log.alarms.length = 0; log.alarmsCleared = (log.alarmsCleared || 0) + 1; }, onAlarm: { addListener() {} } },
    permissions: { contains: async () => !!opts.filesAllowed, request: async () => true },
    action: { setBadgeText: async () => {}, setBadgeBackgroundColor: async () => {}, getBadgeText: async () => '' },
    windows: {
      create: async (o) => { // Chrome: bounds must be at least 50% within the visible screen (1920x1080 here)
        if (o.left !== undefined && (o.left + (o.width || 0) / 2 > 1920 || o.top + (o.height || 0) / 2 > 1080)) throw new Error('Invalid value for bounds. Bounds must be at least 50% within visible screen space.');
        const id = 200 + log.windowsCreated.length; const t = { id: nextId++, url: o.url, windowId: id }; tabs[t.id] = t; log.windowsCreated.push({ id, url: o.url, focused: o.focused, type: o.type, left: o.left, top: o.top }); log.order.push('create'); return { id, tabs: opts.noTabsInWindow ? undefined : [t] }; },
      get: async (id) => ({ id, tabs: [] }), getLastFocused: async () => ({ id: 100, left: 0, top: 0, width: 1600, height: 900 }), remove: async (id) => { log.windowsRemoved.push(id); }, update: async (id, o) => { log.winUpdates.push({ id, focused: o.focused }); log.order.push('winUpdate:' + id); }
    },
    tabs: {
      create: async (o) => { if (opts.noTabsInWindow) throw new Error('tabs.create blocked'); const t = { id: nextId++, url: o.url, windowId: o.windowId || 100 }; tabs[t.id] = t; log.tabsCreated.push({ id: t.id, active: o.active }); return t; },
      get: async (id) => { if (!tabs[id]) throw new Error('No tab'); return tabs[id]; },
      remove: async (id) => { log.tabsRemoved.push(id); delete tabs[id]; },
      update: async (id, o) => { log.tabUpdates.push({ id, active: o && o.active }); if (o && o.url && tabs[id]) { tabs[id].url = o.url; tabs[id].status = 'complete'; } return {}; },
      reload: async (id) => { log.tabsReloaded.push(id); },
      query: async () => [userTab],
      sendMessage: async (id, m) => {
        sendCount++;
        if (opts.send) return opts.send(id, m, sendCount, tabs);
        if (sendCount === 1) throw new Error('Could not establish connection'); // content script not ready yet
        if (m.type === 'scrapeCourses') return { courses: [{ identifier: '202640-EN-210-010', id: '_1_1', instructor: '' }] };
        if (m.type === 'scrapeCalendar') return { text: '' };
        return {};
      }
    }
  };
  const envObj = { chrome, mem, log, userTab, send: (m, sender) => new Promise(res => { listener(m, sender || {}, res); }) };
  allEnvs.push(envObj);
  return envObj;
}

function load(env, extra) {
  const ctx = vm.createContext(Object.assign({ chrome: env.chrome, console, setTimeout, clearTimeout, Date, Promise, JSON, Math, Object, Array, Set, String, Number, Error, parseInt, URL, TextDecoder, TextEncoder, Blob, Response, DecompressionStream, btoa, atob }, extra || {}));
  ctx.importScripts = (...fs_) => fs_.forEach((f) => vm.runInContext(fs.readFileSync(path.join(ROOT, f), 'utf8'), ctx));
  vm.runInContext(fs.readFileSync(path.join(ROOT, 'background.js'), 'utf8'), ctx);
  return ctx;
}
const popup = {}; // no sender.tab = popup
const scanState = (env) => (env.mem.session.scan || {}).scan || null;

(async () => {
  // 1. normal start: an inactive tab is created, kept open until the page answers, then closed; the student's own tab is never touched
  {
    const env = makeChrome(); load(env);
    await env.send({ type: 'scan', tabId: 1 }, popup);
    const early = env.log.tabsRemoved.slice();
    assert.strictEqual(env.log.windowsCreated.length, 0, 'no small window (it triggered the narrow layout)');
    assert.ok(env.log.tabsCreated.length === 1 && env.log.tabsCreated[0].active === false, 'one inactive tab in the current window');
    assert.deepStrictEqual(early, [], 'nothing closed right after pressing Scan');
    assert.ok(scanState(env) && scanState(env).phase === 'courses', 'visible state right away');
    await sleep(2600); // first sendMessage fails, then the course list answers, then the calendar window opens
    assert.ok(!env.log.tabsRemoved.includes(1), "the student's own tab was never closed");
    const ph = scanState(env) && scanState(env).phase;
    assert.ok(ph === 'calendar' || ph === 'sending' || ph === 'deep', 'run progressed past the course list, phase=' + ph);
    await env.send({ type: 'cancelScan' }, popup);
    assert.ok(env.log.tabsRemoved.every(id => id >= 50), 'only helper-created tabs closed');
    console.log('ok 1 start path keeps the inactive tab until the page answers');
  }
  // 2. stale 'state' poll holding an OLD error must not overwrite the new run
  {
    const env = makeChrome({ storageDelay: 5, slowOld: true }); load(env);
    env.mem.session.scan = { scan: { runId: 'old', phase: 'courses', msg: 'old run', startedAt: Date.now() }, queue: [], captured: {} };
    const bbSender = { tab: { id: 77 }, url: 'https://ualearn.blackboard.com/ultra/course' };
    const stale = env.send({ type: 'scanProgress', courses: 3 }, bbSender); // reads the OLD state, writes it back later...
    await sleep(2);
    await env.send({ type: 'scan', tabId: 1 }, popup); // ...while a new run starts
    await stale;
    await sleep(300);
    const st = scanState(env);
    assert.ok(st && st.runId !== 'old' && st.phase !== 'error', 'new run survived the stale poll: ' + JSON.stringify(st));
    await env.send({ type: 'cancelScan' }, popup);
    console.log('ok 2 stale state poll cannot overwrite a newer run');
  }
  // 3. a crash while starting (window and tab creation both fail) is always visible
  {
    const env = makeChrome({ noTabsInWindow: true }); load(env);
    await env.send({ type: 'scan', tabId: 1 }, popup);
    await sleep(500);
    const st = scanState(env);
    assert.ok(st && st.phase === 'error' && /Could not|stopped/i.test(st.msg), 'visible error state: ' + JSON.stringify(st));
    console.log('ok 3 start failure leaves a visible error: ' + st.msg);
  }
  // 4. a safeRemove of a tab the helper did not create is refused
  {
    const env = makeChrome(); load(env);
    await env.send({ type: 'cancelScan' }, popup);
    assert.ok(!env.log.tabsRemoved.includes(1), 'cancel never closes the student tab');
    console.log('ok 4 cancel never closes foreign tabs');
  }

  // 5. spinner-only page on attempt 1, courses on attempt 2: the helper tab is reloaded (never the student's) and the run proceeds
  {
    const env = makeChrome({ send: async (id, m, n) => (n < 2 ? { error: 'no-cards', diag: { host: 'ualearn.blackboard.com', path: '/ultra/course', textLen: 120, spinner: true } } : (m.type === 'scrapeCourses' ? { courses: [{ identifier: '202640-EN-210-010', id: '_1_1', instructor: '' }], via: 'rest' } : { text: '' })) });
    load(env, { __SOS_TEST_ATTEMPT_MS: 3000 });
    await env.send({ type: 'scan', tabId: 1 }, popup);
    await sleep(2500);
    const st = scanState(env);
    assert.ok(st && st.phase !== 'error', 'retry recovered, phase=' + (st && st.phase));
    assert.ok(env.log.tabsReloaded.length === 1 && env.log.tabsReloaded[0] >= 50, 'only the helper tab is reloaded');
    assert.ok(!env.log.tabsReloaded.includes(1) && !env.log.tabsRemoved.includes(1), "student's tab untouched");
    await env.send({ type: 'cancelScan' }, popup);
    console.log('ok 5 attempt 2 reloads our tab and recovers');
  }
  // 6. login/SSO redirect is reported plainly and not retried
  {
    const env = makeChrome({ send: async () => ({ error: 'no-cards', diag: { host: 'sso.example.edu', path: '/login', textLen: 900, login: true } }) });
    load(env, { __SOS_TEST_ATTEMPT_MS: 3000 });
    await env.send({ type: 'scan', tabId: 1 }, popup);
    await sleep(1500);
    const st = scanState(env);
    assert.ok(st && st.phase === 'error' && /sign in again/i.test(st.msg), 'login reason: ' + JSON.stringify(st));
    assert.strictEqual(env.log.tabsReloaded.length, 0, 'no pointless reload on a login page');
    const dg = env.mem.session.diag; assert.ok(dg && dg.events.some(e => /attempt 1/.test(e.ev) && /sso\.example\.edu/.test(e.ev)), 'diagnostics carry host and path');
    assert.ok(!JSON.stringify(dg).includes('?'), 'no query strings in diagnostics');
    console.log('ok 6 login page reported: ' + st.msg);
  }
  // 7. a loading page that never fills: three attempts, then "still loading"; a new Scan starts again (no cooldown)
  {
    const env = makeChrome({ send: async () => ({ error: 'no-cards', diag: { host: 'ualearn.blackboard.com', path: '/ultra/course', textLen: 50, spinner: true } }) });
    load(env, { __SOS_TEST_ATTEMPT_MS: 2000 });
    await env.send({ type: 'scan', tabId: 1 }, popup);
    await sleep(6500);
    const st = scanState(env);
    assert.ok(st && st.phase === 'error' && /still loading/i.test(st.msg), 'loading reason: ' + JSON.stringify(st));
    assert.strictEqual(env.log.tabsReloaded.length, 2, 'two reloads (attempts 2 and 3)');
    await env.send({ type: 'scan', tabId: 1 }, popup);
    const again = scanState(env);
    assert.ok(again && again.phase === 'courses', 'a new scan starts right away after a failure');
    await env.send({ type: 'cancelScan' }, popup);
    console.log('ok 7 still-loading reason, 3 attempts, no cooldown');
  }

  // 8. Reset helper wipes everything, keeps only the default daily alarm, and never touches foreign tabs
  {
    const env = makeChrome(); load(env);
    env.mem.local.deepDone = { x: ['a'] }; env.mem.local.fps = { x: 'b' }; env.mem.local.daily = { on: false, lastOkAt: 5 };
    env.mem.session.scan = { scan: { runId: 'r', phase: 'sending', startedAt: Date.now() }, import: { classes: [] }, queue: [], captured: {} };
    env.mem.session.diag = { events: [{ t: 1, ev: 'old' }], lastError: 'old' };
    const r = await env.send({ type: 'resetHelper' }, popup);
    assert.ok(r.ok, 'reply ok');
    assert.ok(!env.mem.local.deepDone && !env.mem.local.fps && !env.mem.local.daily, 'local data cleared (daily back to default ON)');
    assert.ok(!env.mem.session.scan && !(env.mem.session.diag && env.mem.session.diag.lastError), 'run state and diagnostics cleared');
    assert.strictEqual(env.mem.local.version, 'test', 'version marker re-stored');
    assert.ok(env.mem.local.resetAt, 'resetAt stored for the page status');
    assert.deepStrictEqual(env.log.alarms, ['daily-rescan'], 'only the default daily alarm remains');
    assert.ok(!env.log.tabsRemoved.includes(1), 'foreign tab untouched');
    const st = await env.send({ type: 'state' }, popup);
    assert.ok(st.daily && st.daily.on === true && st.resetAt, 'daily default ON after reset');
    console.log('ok 8 reset helper wipes stored data and re-creates only the default alarm');
  }
  // 9. a version change at startup triggers the same reset once
  {
    const env = makeChrome(); env.mem.local.version = '0.1.0'; env.mem.local.deepDone = { x: ['a'] }; env.mem.local.fps = { x: 'h' }; env.mem.local.daily = { on: false }; env.mem.local.fileAsk = true; env.mem.local.tree = { _1_1: {} };
    load(env);
    await sleep(300);
    assert.ok(!env.mem.local.deepDone && !env.mem.local.fps, 'a new build forgets the uploaded-item memory');
    assert.ok(env.mem.local.daily && env.mem.local.daily.on === false && env.mem.local.fileAsk === true && env.mem.local.tree, 'but keeps the settings, the permission answer and the content tree');
    assert.strictEqual(env.mem.local.version, 'test', 'new version recorded');
    console.log('ok 9 version change resets once at startup');
  }

  // 10. index crawl: up to 3 class tabs at once, one index text per class in the upload queue, nothing opened beyond the outline
  {
    let active = 0, maxActive = 0, mapped = 0;
    const env = makeChrome({ send: async (id, m) => {
      if (m.type === 'scrapeCourses') return { courses: [1, 2, 3, 4, 5].map(i => ({ identifier: '202640-EN-21' + i + '-001', id: '_' + i + '_1', instructor: '' })), via: 'rest', n: 5 };
      if (m.type === 'scrapeCalendar') return { text: '' };
      if (m.type === 'mapOutline') { active++; maxActive = Math.max(maxActive, active); await sleep(250); active--; mapped++; return { items: [{ path: 'Folder', title: 'Syllabus', type: 'file', href: '/ultra/courses/_1_1/file/_2_1' }, { path: '', title: 'Welcome', type: 'document', href: '/ultra/courses/_1_1/outline/edit/document/_3_1' }] }; }
      return {};
    } });
    load(env, { __SOS_TEST_ATTEMPT_MS: 3000 });
    await env.send({ type: 'scan', tabId: 1 }, popup);
    for (let i = 0; i < 60 && !(scanState(env) && scanState(env).phase === 'sending'); i++) await sleep(100);
    await env.send({ type: 'importDelivered', classes: 5, deadlines: 0 }, { tab: { id: 99 }, url: 'https://<deployed-host-1>/onboarding' });
    for (let i = 0; i < 80 && mapped < 5; i++) await sleep(100);
    await sleep(300);
    assert.strictEqual(mapped, 5, 'all 5 classes mapped');
    assert.ok(maxActive >= 2 && maxActive <= 3, 'parallel up to 3 tabs, saw ' + maxActive);
    const q = env.mem.session.deepq || [];
    assert.strictEqual(q.length, 5, 'one index per class queued');
    assert.ok(q.every(x => /\[file\] <https:\/\/ualearn\.blackboard\.com\/ultra\/courses\//.test(x.text) && x.fp), 'index lines with full Blackboard URLs');
    await env.send({ type: 'cancelScan' }, popup);
    console.log('ok 10 index crawl: ' + mapped + ' classes, max ' + maxActive + ' tabs at once, 5 indexes queued');
  }

  // 11. on-demand fetch: only Blackboard course links, files are reported not read, one page -> text + title back
  {
    const env = makeChrome({ send: async (id, m) => (m.type === 'deepItem' ? { title: 'Week 1 Notes', text: 'Lab 3 instructions. Install the Kleopatra tool, create a key pair, and sign the provided file. '.repeat(6) } : {}) });
    load(env);
    const site = { tab: { id: 99 }, url: 'https://<deployed-host-1>/study' };
    let r = await env.send({ type: 'fetchItem', path: 'https://evil.example/x' }, site);
    assert.ok(!r.ok, 'foreign link refused: ' + r.line);
    await sleep(5100);
    r = await env.send({ type: 'fetchItem', path: '/ultra/courses/_1_1/outline/edit/document/_3_1' }, site);
    assert.ok(r.ok && r.title === 'Week 1 Notes' && r.text.length > 300, 'page text and title returned: ' + JSON.stringify(r).slice(0, 80));
    r = await env.send({ type: 'fetchItem', path: '/ultra/courses/_1_1/assessment/_9_1/overview' }, site);
    assert.ok(!r.ok && /assessment: open it in Blackboard/.test(r.line), 'quiz and exam contents are never read');
    await sleep(5100);
    r = await env.send({ type: 'fetchItem', path: '/ultra/courses/_1_1/file/_2_1?courseId=_1_1' }, site);
    assert.ok(!r.ok && /Allow file downloads/.test(r.line), 'files need the one-time permission first');
    r = await env.send({ type: 'fetchItem', path: '/ultra/courses/_1_1/outline/edit/document/_4_1' }, site);
    assert.ok(!r.ok && /wait a few seconds/.test(r.line), 'rate limited');
    await env.send({ type: 'closeReader' }, { });
    assert.ok(env.log.tabsRemoved.length >= 1 && env.log.tabsRemoved.every(id => id >= 50), 'the helper tab is closed afterwards');
    r = await env.send({ type: 'fetchItem', path: '/ultra/courses/_1_1/outline/edit/document/_3_1' }, popup);
    assert.strictEqual(JSON.stringify(r), '{}', 'only the student-site script may ask');
    console.log('ok 11 on-demand fetch validation, file refusal, rate limit, tab cleanup');
  }

  // 12. links: Google Doc export, Drive PDF, OneDrive download, junk page rejection, private doc, only indexed links
  {
    const realText = 'Course syllabus. Week 1 covers the basics of secure mobile design, and the project is due in week 12. '.repeat(6);
    const hdr = (ct) => ({ get: (k) => (k.toLowerCase() === 'content-type' ? ct : '') });
    const calls = [];
    const fakeFetch = async (u) => {
      calls.push(u);
      const mk = (body, ct, url) => ({ ok: true, status: 200, url: url || u, headers: hdr(ct), arrayBuffer: async () => new TextEncoder().encode(body).buffer });
      if (/docs\.google\.com\/document\/d\/PRIV\//.test(u)) return mk('<html>Sign in</html>', 'text/html', 'https://accounts.google.com/signin');
      if (/docs\.google\.com\/document\/d\/GOOD\/export/.test(u)) return mk(realText, 'text/plain');
      if (/drive\.google\.com\/uc/.test(u)) return { ok: true, status: 200, url: u, headers: hdr('application/pdf'), arrayBuffer: async () => new Uint8Array([0x25, 0x50, 0x44, 0x46, 1, 2, 3]).buffer };
      if (/1drv\.ms/.test(u) && /download=1/.test(u)) return mk(realText, 'text/plain');
      if (/docs\.google\.com\/document\/d\/JUNK\/export/.test(u)) return mk('JavaScript is required to view this page. '.repeat(20), 'text/plain');
      return { ok: false, status: 404, url: u, headers: hdr(''), arrayBuffer: async () => new ArrayBuffer(0) };
    };
    const env = makeChrome({ filesAllowed: true });
    load(env, { fetch: fakeFetch });
    const site = { tab: { id: 99 }, url: 'https://<deployed-host-1>/study' };
    const urls = ['https://docs.google.com/document/d/GOOD/edit', 'https://docs.google.com/document/d/PRIV/edit', 'https://docs.google.com/document/d/JUNK/edit', 'https://drive.google.com/file/d/PDF1/view', 'https://1drv.ms/w/s!abc'];
    // only addresses the helper recorded in an index may be fetched (an empty record = an older build: known document hosts accepted)
    env.mem.local.idxHrefs = { other: 1 };
    let r = await env.send({ type: 'fetchItem', path: urls[0] }, site);
    assert.ok(!r.ok && /not in the class index/.test(r.line), 'unindexed link refused: ' + JSON.stringify(r));
    // record them the way an index map does (hash of the address without query)
    const hk = (u) => { let h = 5381; const s = u.split('#')[0].split('?')[0]; for (let i = 0; i < s.length; i++) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0; return h.toString(36); };
    env.mem.local.idxHrefs = {}; urls.forEach(u => { env.mem.local.idxHrefs[hk(u)] = 1; });
    await sleep(5100);
    r = await env.send({ type: 'fetchItem', path: urls[0] }, site);
    assert.ok(r.ok && r.kind === 'text' && r.text.length > 300 && calls.some(c => /export\?format=txt/.test(c)), 'google doc exported as text: ' + JSON.stringify(r).slice(0, 80));
    await sleep(5100);
    r = await env.send({ type: 'fetchItem', path: urls[1] }, site);
    assert.ok(!r.ok && /private/.test(r.line), 'private doc reported: ' + JSON.stringify(r));
    await sleep(5100);
    r = await env.send({ type: 'fetchItem', path: urls[2] }, site);
    assert.ok(!r.ok, 'junk export is never returned');
    await sleep(5100);
    r = await env.send({ type: 'fetchItem', path: urls[3] }, site);
    assert.ok(r.ok && r.kind === 'pdf' && r.b64 && /\.pdf$/.test(r.filename), 'drive pdf returned as bytes for the upload route');
    await sleep(5100);
    r = await env.send({ type: 'fetchItem', path: urls[4] }, site);
    assert.ok(r.ok && r.kind === 'text' && calls.some(c => /1drv\.ms.*download=1/.test(c)), 'onedrive tried with download=1');
    assert.ok(!r.ok || !JSON.stringify(env.mem.session.diag || {}).includes(realText.slice(0, 30)), 'no content in the diagnostics');
    console.log('ok 12 links: google doc, private doc, junk rejected, drive pdf, onedrive download, index-only allow-list');
  }

  // 13. the live failure: a short Ultra "Text Document" taken from the index text is read, not refused
  {
    const env = makeChrome({ send: async (id, m) => (m.type === 'deepItem' ? { title: 'Class Subnet Activity', text: 'Subnet the 10.0.0.0/8 network for 4 labs.', doc: true } : {}) });
    load(env);
    const site = { tab: { id: 99 }, url: 'https://<deployed-host-1>/study/abcd1234' };
    const r = await env.send({ type: 'fetchItem', path: '/ultra/courses/_407459_1/document/_14730940_1?view=content&state=view' }, site);
    assert.ok(r.ok && r.doc && r.title === 'Class Subnet Activity' && r.text.length >= 20 && /^Class Subnet Activity\n/.test(r.text), 'short document returned with its title: ' + JSON.stringify(r).slice(0, 120));
    const ev = (env.mem.session.diag && env.mem.session.diag.events || []).map(e => e.ev).join(' | ');
    assert.ok(/fetch request received/.test(ev) && /item page read/.test(ev), 'diagnostics carry the fetch path: ' + ev.slice(0, 160));
    assert.ok(!/Subnet the 10/.test(ev), 'no content in the diagnostics');
    const st13 = await env.send({ type: 'state' }, { });
    assert.ok(st13.lastFetch && /read \d+ chars/.test(st13.lastFetch.line), 'state carries the last fetch result: ' + JSON.stringify(st13.lastFetch));
    const dt = (await env.send({ type: 'diagText' }, {})).text;
    assert.ok(/last fetch: read/.test(dt) && /fetch guard: allowed internal/.test(dt) && /version /.test(dt), 'diagnostics text carries version, guard and last fetch');
    assert.ok(st13.build && st13.build.version === 'test' && /^build test \(\d{4}-\d{2}-\d{2}\)$/.test(st13.build.label), 'state carries the build: ' + JSON.stringify(st13.build));
    assert.ok(dt.split(String.fromCharCode(10))[0] === st13.build.label, 'the build label is the FIRST line of the diagnostics');
    console.log('ok 13 short Ultra document read with its title, fetch events logged');
  }

  // 14. page reads happen in an unfocused sliver window: focus goes straight back, his tab is never activated, the window is closed
  {
    const env = makeChrome({ send: async (id, m) => (m.type === 'deepItem' ? { title: 'Lab', text: 'Subnet the lab network and record the masks for each of the four departments.', doc: true } : {}) });
    load(env);
    const site = { tab: { id: 99 }, url: 'https://<deployed-host-1>/study/abcd1234' };
    const r = await env.send({ type: 'fetchItem', path: '/ultra/courses/_1_1/document/_5_1?view=content' }, site);
    assert.ok(r.ok, 'read ok');
    const w = env.log.windowsCreated[0];
    assert.ok(w && w.type === 'popup' && w.focused === false, 'popup window, not focused');
    assert.ok(w.left + 640 <= 1920 && w.top + 400 <= 1080 && w.left >= 600, 'at least half of the window on screen, low in the corner of his window: ' + w.left + ',' + w.top);
    const firstFocus = env.log.order.indexOf('winUpdate:100');
    assert.ok(firstFocus > env.log.order.indexOf('create'), 'focus handed back to his window right after the create');
    assert.ok(env.log.winUpdates.every(u => u.id === 100 && u.focused === true), 'only ever focuses HIS window');
    assert.ok(!env.log.tabUpdates.some(u => u.active === true), 'no tab was ever activated');
    assert.strictEqual(env.log.tabsRemoved.length, 0, 'the reader stays warm for the next fetch');
    await env.send({ type: 'closeReader' }, { });
    assert.ok(env.log.tabsRemoved.length >= 1 && env.log.tabsRemoved.every(id => id >= 50) && !env.log.tabsRemoved.includes(1), 'closed on demand, his tab untouched');
    console.log('ok 14 reader window: unfocused, focus returned, no tab activated, closed');
  }
  // 15. nothing renders in the off-corner window: the answer is ok:false, NOTHING is brought to the front to try again
  {
    let n = 0;
    const env = makeChrome({ send: async (id, m) => { if (m.type !== 'deepItem') return {}; n++; return { error: 'not-rendered' }; } });
    load(env);
    const site = { tab: { id: 99 }, url: 'https://<deployed-host-1>/study/abcd1234' };
    const r = await env.send({ type: 'fetchItem', path: '/ultra/courses/_1_1/document/_6_1?view=content' }, site);
    assert.ok(!r.ok && /Could not read it/.test(r.line) && n === 1, 'ok:false with a plain line, one attempt only: ' + JSON.stringify(r) + ' n=' + n);
    assert.ok(!env.log.tabUpdates.some(u => u.active === true), 'no visible-tab fallback any more');
    console.log('ok 15 no fallback: unreadable page answers ok:false, nothing activated');
  }
  // 16. FOCUS AUDIT over every flow above (scan, fetch, links, cancel, reset, index): no tab was ever activated, no helper window focused
  {
    for (const e of allEnvs) {
      assert.ok(!e.log.tabUpdates.some(u => u.active === true), 'a tab was activated: ' + JSON.stringify(e.log.tabUpdates));
      assert.ok(e.log.winUpdates.every(u => u.id === 100), 'a helper window was focused: ' + JSON.stringify(e.log.winUpdates)); // 100 = the student's own window
      assert.ok(e.log.windowsCreated.every(w => w.focused === false), 'a window was created focused');
      assert.ok(e.log.tabsCreated.every(t => t.active === false), 'a tab was created active');
    }
    console.log('ok 16 focus audit: ' + allEnvs.length + ' flows, no activation, no helper focus, everything created in the background');
  }

  // 17. content tree from the page's own REST responses -> real file address -> docx text, with no viewer window
  {
    const docx = makeZip([['word/document.xml', '<w:document><w:body><w:p><w:r><w:t>Kleopatra lab: create a key pair and sign the provided file.</w:t></w:r></w:p></w:body></w:document>']]);
    const fakeFetch = async (u) => {
      if (/ualearn\.blackboard\.com\/bbcswebdav\/pid-x-dt-content-rid-1_1\/xid-1_1/.test(u)) {
        const ab = docx.buffer.slice(docx.byteOffset, docx.byteOffset + docx.byteLength);
        return { ok: true, status: 200, url: 'https://files.example-cdn.test/f?sig=1', headers: { get: (k) => (k.toLowerCase() === 'content-type' ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' : '') }, arrayBuffer: async () => ab };
      }
      return { ok: false, status: 404, url: u, headers: { get: () => '' }, arrayBuffer: async () => new ArrayBuffer(0) };
    };
    const env = makeChrome({ filesAllowed: true });
    load(env, { fetch: fakeFetch });
    const bb = { tab: { id: 77 }, url: 'https://ualearn.blackboard.com/ultra/courses/_1_1/outline' };
    await env.send({ type: 'feed', course: '_1_1', items: [{ id: '_9_1', title: 'Lab 3', h: 'resource/x-bb-file', file: { name: 'Lab3.docx', mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', size: docx.length, url: '/bbcswebdav/pid-x-dt-content-rid-1_1/xid-1_1' } }, { id: '_8_1', title: 'Syllabus', h: 'resource/x-bb-externallink', link: 'https://docs.google.com/document/d/ABC/edit' }] }, bb);
    assert.ok(env.mem.local.tree && env.mem.local.tree._1_1 && env.mem.local.tree._1_1._9_1.f.u, 'tree stored');
    assert.ok(Object.keys(env.mem.local.idxHrefs || {}).length === 1, 'the page-listed external link is on the allow-list');
    await env.send({ type: 'feed', course: 'bad', items: [{ id: '_1_1', title: 'x' }] }, bb);
    assert.ok(!env.mem.local.tree.bad, 'a bad course id is ignored');
    const site = { tab: { id: 99 }, url: 'https://<deployed-host-1>/study/abcd1234' };
    const r = await env.send({ type: 'fetchItem', path: '/ultra/courses/_1_1/file/_9_1?courseId=_1_1' }, site);
    assert.ok(r.ok && r.kind === 'text' && /Kleopatra lab/.test(r.text) && r.title === 'Lab 3', 'docx read from the tree address: ' + JSON.stringify(r).slice(0, 140));
    assert.strictEqual(env.log.windowsCreated.length, 0, 'no viewer window was needed');
    const ev = (env.mem.session.diag.events || []).map(e => e.ev).join('|');
    assert.ok(/file address from the content tree/.test(ev) && /file fetch 200 via files\.example-cdn\.test/.test(ev), 'diagnostics log the tree address and the final host');
    assert.ok(!/sig=1/.test(JSON.stringify(env.mem.session.diag)), 'no query string in the diagnostics');
    console.log('ok 17 feed -> tree -> docx text, no window, redirect host logged without query');
  }

  // 18. warm reader: two fetches in a row use ONE window; the tab only navigates; idle close works
  {
    const env = makeChrome({ send: async (id, m) => (m.type === 'deepItem' ? { title: 'Lab', text: 'Subnet the lab network and record the masks for each of the four departments.', doc: true } : {}) });
    load(env);
    const site = { tab: { id: 99 }, url: 'https://<deployed-host-1>/study/abcd1234' };
    let r = await env.send({ type: 'fetchItem', path: '/ultra/courses/_1_1/document/_5_1?view=content' }, site);
    assert.ok(r.ok);
    await sleep(5100);
    r = await env.send({ type: 'fetchItem', path: '/ultra/courses/_1_1/document/_6_1?view=content' }, site);
    assert.ok(r.ok, 'second read ok');
    assert.strictEqual(env.log.windowsCreated.length, 1, 'one reader window for two fetches');
    assert.ok(env.log.tabUpdates.some(u => !u.active), 'the reader tab was only navigated');
    assert.ok(!env.log.tabUpdates.some(u => u.active === true), 'never activated');
    const st = await env.send({ type: 'fetchStatus' }, site);
    assert.ok(st.line && st.pct > 0, 'a fetch step is published: ' + JSON.stringify(st));
    const ev = (env.mem.session.diag.events || []).map(e => e.ev).join('|');
    assert.ok(/reader window reused/.test(ev) && /read \d+\.\ds/.test(ev) && /fetch worker total/.test(ev), 'timings and reuse are logged');
    await env.send({ type: 'closeReader' }, { });
    console.log('ok 18 warm reader reused, steps published, timings logged');
  }
  process.exit(0);
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
