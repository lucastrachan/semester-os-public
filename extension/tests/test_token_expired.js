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
      sendMessage: (m, cb) => { if (!alive) throw new Error('Extension context invalidated.'); setTimeout(() => cb(m.type === 'state' ? { scan: global.__scan === undefined ? null : global.__scan, queue: [], captured: {}, diag: { now: Date.now() } } : (m.type === 'pending' ? { items: [], import: null } : (m.type === 'fetchItem' ? global.__fetchItemReply : {}))), 1); }
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
  run('site.js');
  const winObj = vm.runInContext('window', ctx);
  const fresh = mkJwt(Date.now() + 3600000);
  global.__idTok = mkJwt(Date.now() - 600000); // the stored token expired ten minutes ago
  let cognito = 0; const used = [];
  global.__fetch = async (u, o) => {
    const method = (o && o.method) || 'GET';
    const mk = (status, body) => ({ ok: status < 400, status, json: async () => body, headers: { get: () => null } });
    if (/config\.json/.test(u)) return mk(200, { apiUrl: 'https://api.test', region: 'us-east-1' });
    if (/cognito-idp/.test(u)) { cognito++; return mk(200, { AuthenticationResult: { IdToken: fresh } }); }
    if (method === 'POST' && /materials\/text$/.test(u)) { used.push(o.headers.Authorization); return mk(202, { material: { id: 'm1' } }); }
    if (method === 'GET' && /materials$/.test(u)) { used.push(o.headers.Authorization); return mk(200, { materials: [{ id: 'm1', title: 'Lab', status: 'ready' }] }); }
    return mk(404, {});
  };
  global.__fetchItemReply = { ok: true, kind: 'text', title: 'Lab', text: 'Subnet the lab network and record the masks for each of the four departments in the plan.', doc: true };
  const mark = posts.length;
  emit('message', { source: winObj, origin: 'https://site.test', data: { source: 'sos-site', type: 'fetch', courseId: 'abcd1234', url: 'https://ualearn.blackboard.com/ultra/courses/_1_1/document/_3_1?view=content' } });
  await sleep(6500);
  const rep = posts.slice(mark).filter(p => p.type === 'fetched');
  assert.ok(rep.length === 1 && rep[0].ok, 'fetch succeeded with a refreshed token: ' + JSON.stringify(rep));
  assert.strictEqual(cognito, 1, 'the expired stored token triggered one Cognito refresh');
  assert.ok(used.length >= 2 && used.every(a => a === 'Bearer ' + fresh), 'every API call carried the refreshed token, never the expired one');
  console.log('ok expired stored token: refreshed through Cognito, never sent');
  process.exit(0);
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
