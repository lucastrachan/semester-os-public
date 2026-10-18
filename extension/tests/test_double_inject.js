// Mock-DOM test of site.js: double injection must be a no-op, messages steady at ~1/s, no DOM work while idle,
// and an orphaned copy (extension reloaded) shuts itself down. Run: node extension/tests/test_double_inject.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');
const ROOT = path.join(__dirname, '..');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const mkJwt = (expMs) => 'h.' + Buffer.from(JSON.stringify({ exp: Math.floor(expMs / 1000) })).toString('base64url') + '.s';
global.__idTok = mkJwt(Date.now() + 3600000);

const posts = [];
let created = 0, alive = true;
const noop = () => {};
const elStub = () => { created++; return { setAttribute: noop, appendChild(c) { this.firstChild = this.firstChild || c; return c; }, textContent: '', addEventListener: noop, style: { setProperty: noop, cssText: '' }, attachShadow: () => ({ appendChild: noop }), remove: noop }; };
const ctx = vm.createContext({
  console, setTimeout, clearTimeout, setInterval, clearInterval, atob, btoa, Date, Promise, JSON, Math, Object, Array, Set, String, Number, Error, parseInt, URL, RegExp, encodeURIComponent,
  localStorage: { length: 4, key: (i) => ['CognitoIdentityServiceProvider.CLI.LastAuthUser', 'CognitoIdentityServiceProvider.CLI.u1.idToken', 'CognitoIdentityServiceProvider.CLI.u1.refreshToken', 'other'][i], getItem: (k) => (/LastAuthUser/.test(k) ? 'u1' : /idToken/.test(k) ? global.__idTok : /refreshToken/.test(k) ? 'rt' : null) },
  location: { origin: 'https://site.test', pathname: '/onboarding', href: 'https://site.test/onboarding' },
  document: { readyState: 'complete', visibilityState: 'visible', addEventListener: noop, getElementById: () => null, createElement: elStub, createElementNS: elStub, documentElement: { appendChild: noop }, body: { appendChild: noop } },
  CSSStyleSheet: function () { this.replaceSync = noop; },
  fetch: async (u, o) => global.__fetch(u, o),
  FormData: function () {}, Blob: function () {}, MouseEvent: function () {},
  chrome: {
    runtime: {
      get id() { return alive ? 'x' : undefined; },
      onMessage: { addListener: noop },
      getManifest: () => ({ version: '0.3.0' }),
      sendMessage: (m, cb) => { (global.__sent = global.__sent || []).push(m); if (!alive) throw new Error('Extension context invalidated.'); setTimeout(() => cb(m.type === 'state' ? { scan: global.__scan === undefined ? null : global.__scan, queue: [], captured: {}, diag: { now: Date.now() } } : (m.type === 'pending' ? { items: [], import: null } : (m.type === 'fetchItem' ? global.__fetchItemReply : {}))), 1); }
    },
    storage: { local: { get: (k, cb) => cb({}), set: noop }, onChanged: { addListener: noop } }
  }
});
ctx.window = ctx;
const listeners = {}; ctx.addEventListener = (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); }; const emit = (type, ev) => (listeners[type] || []).forEach(f => f(ev)); // window.addEventListener (fetch bridge)
global.__fetch = async () => ({ ok: true, status: 200, json: async () => ({}), headers: { get: () => null } });
ctx.postMessage = (msg) => { posts.push(msg); };
const run = (f) => vm.runInContext(fs.readFileSync(path.join(ROOT, f), 'utf8'), ctx);

(async () => {
  run('common.js'); run('parse.js');
  const base = created;
  run('site.js'); run('site.js'); // double injection
  await sleep(2600);
  const hellos = posts.filter(p => p.source === 'blackboard' && p.type === 'hello').length;
  assert.ok(hellos >= 2 && hellos <= 4, 'steady single interval, hello count over 2.6 s = ' + hellos + ' (a second instance would give 5+)');
  assert.strictEqual(created - base, 0, 'no DOM work while idle (nothing created)');
  assert.ok(!posts.some(p => p.type === 'failed' || p.type === 'sending' || p.type === 'progress'), 'idle page gets no failed/sending/progress messages');
  assert.ok(posts.some(p => p.source === 'blackboard' && p.type === 'hello' && p.build === '0.3.0'), 'hello carries the build');
  const notes = (global.__sent || []).filter(m => m.type === 'siteNote').map(m => m.note);
  assert.ok(notes.some(n => /^bridge ready/.test(n)), 'bridge ready logged on load: ' + notes.join('|'));
  emit('message', { source: {}, origin: 'https://evil.test', data: { source: 'sos-site', type: 'fetch', courseId: 'abcd1234', url: 'https://ualearn.blackboard.com/ultra/courses/_1_1/document/_2_1' } }); // wrong source and origin
  await sleep(50);
  const notes2 = (global.__sent || []).filter(m => m.type === 'siteNote').map(m => m.note);
  assert.ok(notes2.some(n => /fetch message received from page \(REJECTED/.test(n)), 'a rejected request is still logged first: ' + notes2.join('|'));
  console.log('ok 1 double injection is a no-op, steady messages (' + hellos + ' hellos), no idle DOM changes');

  // a finished run: ONE final progress (phase done, 100) plus done, then no more progress; an old finished run posts nothing
  {
    const before = posts.length;
    global.__scan = { phase: 'done', pct: 100, msg: 'Done: 5 classes', endedAt: Date.now(), classes: [] };
    await sleep(3300);
    const mine = posts.slice(before).filter(p => p.source === 'blackboard');
    const prog = mine.filter(p => p.type === 'progress'), done = mine.filter(p => p.type === 'done');
    assert.strictEqual(prog.length, 1, 'exactly one final progress, got ' + prog.length);
    assert.ok(prog[0].phase === 'done' && prog[0].percent === 100, 'final progress is phase done at 100');
    assert.strictEqual(done.length, 1, 'one done message');
    const before2 = posts.length;
    global.__scan = { phase: 'done', pct: 100, msg: 'Done', endedAt: Date.now() - 120000, classes: [] }; // a long-finished run
    await sleep(2300);
    assert.ok(!posts.slice(before2).some(p => p.type === 'progress' || p.type === 'done'), 'nothing about an old finished run');
    global.__scan = null;
    console.log('ok 3 no progress after done: one final progress and one done, then silence');
  }
  // cancel: a running run that vanishes -> one 'cancelled' and one idle progress, then silence
  {
    global.__scan = { phase: 'courses', pct: 10, msg: 'Reading your courses', startedAt: Date.now() };
    await sleep(1500);
    const mark = posts.length;
    global.__scan = null; // Cancel clears the state
    await sleep(3300);
    const after = posts.slice(mark).filter(p => p.source === 'blackboard');
    assert.strictEqual(after.filter(p => p.type === 'cancelled').length, 1, 'one cancelled message');
    const idle = after.filter(p => p.type === 'progress');
    assert.ok(idle.length === 1 && idle[0].phase === 'idle' && idle[0].percent === 0 && idle[0].line === '', 'one idle progress at 0');
    console.log('ok 4 cancel: one cancelled + one idle progress, then silence');
  }

  // fetch: the page text is uploaded with the title first, and `fetched ok:true` is sent only AFTER the material is READY
  {
    const order = [];
    let polls = 0;
    global.__fetchItemReply = { ok: true, kind: 'text', title: 'Text Document, Project 2 Objectives', text: 'Objective 1: subnet the network.\nObjective 2: document the masks and gateways.', doc: true };
    global.__fetch = async (u, o) => {
      const method = (o && o.method) || 'GET';
      const mk = (status, body) => ({ ok: status < 400, status, json: async () => body, headers: { get: () => null } });
      if (/config\.json/.test(u)) return mk(200, { apiUrl: 'https://api.test' });
      if (method === 'POST' && /\/courses\/abcd1234\/materials\/text$/.test(u)) { const b = JSON.parse(o.body); order.push('POST title=' + b.title + ' first=' + b.text.split('\n')[0]); return mk(202, { material: { id: 'm1', status: 'processing' } }); }
      if (method === 'GET' && /\/courses\/abcd1234\/materials$/.test(u)) { polls++; order.push('poll ' + polls); return mk(200, { materials: [{ id: 'm1', title: 'Project 2 Objectives', status: polls >= 2 ? 'ready' : 'processing' }] }); }
      return mk(404, {});
    };
    const mark = posts.length;
    emit('message', { source: vm.runInContext('window', ctx), origin: 'https://site.test', data: { source: 'sos-site', type: 'fetch', courseId: 'abcd1234', url: 'https://ualearn.blackboard.com/ultra/courses/_1_1/document/_2_1?view=content' } });
    await sleep(5000);
    const replies = posts.slice(mark).filter(p => p.type === 'fetched');
    assert.strictEqual(replies.length, 1, 'exactly one fetched reply');
    assert.ok(replies[0].ok && replies[0].title === 'Project 2 Objectives' && replies[0].materialId === 'm1', 'ready: ok with the normalised title and material id: ' + JSON.stringify(replies[0]));
    assert.ok(order[0] === 'POST title=Project 2 Objectives first=Project 2 Objectives', 'text uploaded with the title as the first line: ' + order[0]);
    assert.ok(polls >= 2, 'polled until ready (polls ' + polls + ')');
    // the reply came after the last poll: the progress messages show phase fetch until then
    assert.ok(posts.slice(mark).some(p => p.type === 'progress' && p.phase === 'fetch'), 'progress (phase fetch) while waiting');
    const lines = posts.slice(mark).filter(p => p.type === 'progress' && p.phase === 'fetch').map(p => p.line);
    assert.ok(lines.includes('Finding it in your course…') && lines.some(l => /^Saving it to /.test(l)) && lines.includes('Ready, reading what it says…'), 'the exact step lines were shown: ' + [...new Set(lines)].join(' | '));
    assert.strictEqual(replies[0].ready, true, 'the final reply says ready:true');
    console.log('ok 5 fetch: upload -> ready -> reply (' + order.join(' | ') + ')');
  }

  // tokens: an expired stored token is never used; the refresh path gets a fresh one; a 401 refreshes once and retries once
  {
    const winObj = vm.runInContext('window', ctx);
    const doc = { source: 'sos-site', type: 'fetch', courseId: 'abcd1234', url: 'https://ualearn.blackboard.com/ultra/courses/_1_1/document/_3_1?view=content' };
    const used = []; let posts401 = 0, cognito = 0;
    const fresh1 = mkJwt(Date.now() + 3600000), fresh2 = mkJwt(Date.now() + 3500000);
    global.__idTok = mkJwt(Date.now() - 60000); // expired
    let newTok = fresh1;
    global.__fetch = async (u, o) => {
      const method = (o && o.method) || 'GET';
      const mk = (status, body) => ({ ok: status < 400, status, json: async () => body, headers: { get: () => null } });
      if (/config\.json/.test(u)) return mk(200, { apiUrl: 'https://api.test', region: 'us-east-1' });
      if (/cognito-idp/.test(u)) { cognito++; assert.strictEqual(JSON.parse(o.body).AuthFlow, 'REFRESH_TOKEN_AUTH'); assert.strictEqual(JSON.parse(o.body).AuthParameters.REFRESH_TOKEN, 'rt'); const t = newTok; newTok = fresh2; return mk(200, { AuthenticationResult: { IdToken: t } }); }
      if (method === 'POST' && /materials\/text$/.test(u)) { used.push(o.headers.Authorization); posts401++; if (posts401 === 1) return mk(401, {}); return mk(202, { material: { id: 'm9', status: 'ready' } }); }
      if (method === 'GET' && /materials$/.test(u)) { used.push(o.headers.Authorization); return mk(200, { materials: [{ id: 'm9', title: 'Lab', status: 'ready' }] }); }
      return mk(404, {});
    };
    global.__fetchItemReply = { ok: true, kind: 'text', title: 'Lab', text: 'Subnet the lab network and record the masks for each of the four departments in the plan.', doc: true };
    const mark = posts.length;
    emit('message', { source: winObj, origin: 'https://site.test', data: doc });
    await sleep(9000);
    const rep = posts.slice(mark).filter(p => p.type === 'fetched');
    assert.strictEqual(rep.length, 1, 'one reply');
    assert.ok(rep[0].ok, 'the fetch succeeded after refresh and retry: ' + JSON.stringify(rep[0]));
    assert.strictEqual(cognito, 1, 'one Cognito refresh, triggered by the 401 (the token cached from the earlier case was still valid)');
    assert.ok(used[0] !== 'Bearer ' + fresh1 && used[1] === 'Bearer ' + fresh1, 'the retry carried the refreshed token: ' + used.slice(0, 2).map(s => s && s.slice(-8)));
    assert.ok(!used.some(a => /Bearer h\.[^.]+\.s$/.test(a) && a.indexOf(String(Math.floor((Date.now() - 60000) / 1000))) >= 0), 'the expired token was never sent');
    global.__idTok = mkJwt(Date.now() + 3600000);
    console.log('ok 6 tokens: expired -> refresh, 401 -> refresh once -> retry once');
  }
  alive = false; // the extension was reloaded: this copy is orphaned
  await sleep(1200);
  const before = posts.length;
  await sleep(2200);
  assert.strictEqual(posts.length, before, 'orphaned copy stopped posting');
  console.log('ok 2 orphaned copy shuts itself down');
  process.exit(0);
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
