// Semester OS site content script. Uses the student's existing session (Amplify's token in this site's localStorage),
// read at the moment of use, never copied or stored by the extension. Runs only when a send is pending.
(function () {
  if (window.__sosSite) return; // idempotent: a second injection into the same page is a no-op (one interval, one panel)
  window.__sosSite = true;

  // ---- Sign-in token: NEVER use a stale one. Order: the page's fresh token (bridge), a still-valid stored token (more than 2 minutes
  // left), then a Cognito refresh with the stored refresh token. Results are kept in MEMORY only, never in extension storage. ----
  var memTok = null; // { tok, exp }
  function jwtExp(tok) { try { return JSON.parse(atob(String(tok).split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).exp * 1000; } catch (e) { return 0; } }
  function amplifyKeys() { // the pool's "<prefix>.<clientId>.LastAuthUser" key is found generically
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i), m = k && k.match(/^(CognitoIdentityServiceProvider\.([^.]+)\.)LastAuthUser$/);
        if (m) { var user = localStorage.getItem(k); if (user) return { prefix: m[1], client: m[2], user: user }; }
      }
    } catch (e) { /* ignore */ }
    return null;
  }
  function lsToken() { var k = amplifyKeys(); try { return k ? localStorage.getItem(k.prefix + k.user + '.idToken') : null; } catch (e) { return null; } }
  // Synchronous view used by the many existing call sites: the fresh in-memory token first, else whatever is stored.
  function idToken() { return memTok && memTok.exp - Date.now() > 30000 ? memTok.tok : lsToken(); }
  var lastTokNote = {};
  function tokNote(kind, text, err) { if (Date.now() - (lastTokNote[kind] || 0) > 60000 || err) { lastTokNote[kind] = Date.now(); SOS.msg({ type: 'siteNote', note: text, err: !!err }); } }
  var tokWaiter = null;
  window.addEventListener('message', function (ev) { // the site's answer to our getToken request
    var d = ev.data;
    if (ev.source !== window || ev.origin !== location.origin || !d || d.source !== 'sos-site' || d.type !== 'token' || typeof d.idToken !== 'string') return;
    if (tokWaiter) { var w = tokWaiter; tokWaiter = null; w(d.idToken); }
  });
  function pageToken() {
    return new Promise(function (res) {
      var timer = setTimeout(function () { tokWaiter = null; res(null); }, 1500);
      tokWaiter = function (v) { clearTimeout(timer); res(v); };
      try { window.postMessage({ source: 'sos-helper', type: 'getToken' }, location.origin); } catch (e) { clearTimeout(timer); tokWaiter = null; res(null); }
    });
  }
  async function cognitoRefresh() {
    var k = amplifyKeys(); if (!k) return null;
    var rt; try { rt = localStorage.getItem(k.prefix + k.user + '.refreshToken'); } catch (e) { rt = null; }
    if (!rt) return null;
    var region = 'us-east-1';
    try { region = (await (await fetch('/config.json')).json()).region || region; } catch (e) { /* default */ }
    try {
      var r = await fetch('https://cognito-idp.' + region + '.amazonaws.com/', { method: 'POST', headers: { 'Content-Type': 'application/x-amz-json-1.1', 'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth' }, body: JSON.stringify({ AuthFlow: 'REFRESH_TOKEN_AUTH', ClientId: k.client, AuthParameters: { REFRESH_TOKEN: rt } }) });
      if (!r.ok) { tokNote('rf', 'token refresh failed: ' + r.status, true); return null; }
      var j = await r.json();
      return (j.AuthenticationResult && j.AuthenticationResult.IdToken) || null;
    } catch (e) { tokNote('rf', 'token refresh failed: network', true); return null; }
  }
  async function freshToken(force) {
    var now = Date.now(), need = force ? 30000 : 120000;
    if (!force && memTok && memTok.exp - now > need) return memTok.tok;
    var pt = await pageToken();
    if (pt && jwtExp(pt) - Date.now() > need) { memTok = { tok: pt, exp: jwtExp(pt) }; tokNote('fresh', 'token fresh (' + Math.round((memTok.exp - Date.now()) / 1000) + 's left, from the page)'); return pt; }
    var ls = lsToken();
    if (!force && ls && jwtExp(ls) - Date.now() > need) { memTok = { tok: ls, exp: jwtExp(ls) }; tokNote('fresh', 'token fresh (' + Math.round((memTok.exp - Date.now()) / 1000) + 's left)'); return ls; }
    var rf = await cognitoRefresh();
    if (rf && jwtExp(rf) - Date.now() > 30000) { memTok = { tok: rf, exp: jwtExp(rf) }; tokNote('rf', 'token refreshed (' + Math.round((memTok.exp - Date.now()) / 1000) + 's left)'); return rf; }
    return ls || null; // nothing better: the 401 handler below reports the failure
  }
  // Every API call goes through here: it always sends a fresh token, and on a 401 refreshes once and retries once.
  async function sfetch(url, init) {
    init = init || {};
    var tok = await freshToken(false);
    var go = function (tk) { var h = Object.assign({}, init.headers || {}); if (tk) h.Authorization = 'Bearer ' + tk; return fetch(url, Object.assign({}, init, { headers: h })); };
    var r = await go(tok);
    if (r.status === 401) {
      tokNote('401', 'api answered 401: refreshing the token once', true);
      memTok = null;
      var tk2 = await freshToken(true);
      r = await go(tk2);
      if (r.status === 401) tokNote('401b', 'api still 401 after a refresh', true);
    }
    return r;
  }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function ui() {
    var root = SOS.panel('semesteros-connect-site');
    var box = SOS.el('div', { 'class': 'b' });
    root.appendChild(box);
    return function (lines, pct, classes) {
      box.textContent = '';
      var first = lines[0] || '';
      var m = first.match(/^Sending (\d+) of (\d+)/);
      box.appendChild(SOS.header(m ? 'Sending' : /sent\.|^Done/.test(first) ? 'Done' : ''));
      var bd = SOS.el('div', { 'class': 'bd' });
      box.appendChild(bd);
      bd.appendChild(SOS.el('div', { 'class': 'row' }, (m ? [SOS.el('span', { 'class': 'spin' })] : []).concat([SOS.el('span', { text: first })])));
      if (m) {
        var bar = SOS.el('div', { 'class': 'bar', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': m[2], 'aria-valuenow': String(Number(m[1]) - 1) }, [SOS.el('i')]);
        bar.firstChild.style.setProperty('--v', Math.round(((Number(m[1]) - 1) / Number(m[2])) * 100) + '%'); // CSSOM, not a style attribute
        bd.appendChild(bar);
      }
      if (typeof pct === 'number') bd.appendChild(SOS.barView(pct, ''));
      if (classes && classes.length) { bd.appendChild(SOS.classRows(classes)); }
      var rest = lines.slice(1);
      if (rest.length) {
        var ul = SOS.el('ul', { 'class': 'msgs' });
        rest.forEach(function (l) {
          var bad = /^Failed/.test(l), ok = /^Sent /.test(l);
          ul.appendChild(SOS.el('li', { 'class': bad ? 'bad' : ok ? 'ok' : '' }, [bad ? SOS.icon('x') : ok ? SOS.icon('check') : SOS.icon('dot'), SOS.el('span', { text: l })]));
        });
        bd.appendChild(ul);
      }
    };
  }

  async function api(base, token, path, body) {
    var r = await sfetch(base + path, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token }, body: JSON.stringify(body) });
    var j = {}; try { j = await r.json(); } catch (e) { /* ignore */ }
    return { status: r.status, body: j };
  }

  function bytes(b64) {
    var s = atob(b64), a = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) a[i] = s.charCodeAt(i);
    return a;
  }

  function tell(type, count, line) { try { window.postMessage({ source: 'blackboard', type: type, count: count, line: line ? String(line).slice(0, 160) : undefined }, location.origin); } catch (e) { /* ignore */ } }

  async function authedGet(base, token, path) {
    var r = await sfetch(base + path, { headers: { Authorization: 'Bearer ' + token } });
    var j = {}; try { j = await r.json(); } catch (e) { /* ignore */ }
    return { status: r.status, body: j };
  }

  // Find the class a syllabus belongs to: bbIdentifier first, then course code ("EN 210").
  function matchClass(courses, identifier) {
    var p = SOSParse.splitIdentifier(identifier);
    var hit = courses.filter(function (c) { return c.bbIdentifier === identifier; });
    if (!hit.length && p) hit = courses.filter(function (c) { return c.courseCode === p.code; });
    return hit.length ? hit[0] : null;
  }

  // The website detects the helper from any {source:'blackboard'} message: say hello at once on every page load, every second
  // while the page is open (see the poller below), and whenever the tab becomes visible, whether or not a scan is pending.
  SOS.msg({ type: 'siteNote', note: 'bridge ready (' + (location.pathname.split('/')[1] || 'root') + ')' }); // the fetch listener below is registered in this same run
  var BUILD = ''; try { BUILD = chrome.runtime.getManifest().version; } catch (e) { /* ignore */ }
  function hello() { try { window.postMessage({ source: 'blackboard', type: 'hello', build: BUILD }, location.origin); window.postMessage({ source: 'blackboard', type: 'helper', build: BUILD }, location.origin); } catch (e) { /* ignore */ } }
  hello();
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible') hello(); });
  var runActive = false, imp_body = {}, classList = [];
  // ---- On-demand fetch bridge: the site posts {source:'sos-site', type:'fetch', courseId, url}; every request gets a
  // {source:'blackboard', type:'fetched', courseId, ok, title, line?} reply. One at a time; Blackboard origin only. ----
  var BB_ORIGIN = 'https://ualearn.blackboard.com';
  function fetched(courseId, ok, title, line, chars, materialId, ready) { SOS.msg({ type: 'siteNote', note: 'fetch reply sent ok=' + !!ok + (line ? ' (' + String(line).slice(0, 50) + ')' : ''), err: !ok }); try { window.postMessage({ source: 'blackboard', type: 'fetched', courseId: courseId, ok: !!ok, title: title ? String(title).slice(0, 100) : '', line: line ? String(line).slice(0, 120) : undefined, chars: typeof chars === 'number' ? chars : undefined, materialId: materialId || undefined, ready: ready ? true : undefined }, location.origin); } catch (e) { /* ignore */ } }
  var fetchedCache = {}; // courseId|path -> {title, chars}: the same item is never uploaded twice
  var curPct = 15;
  function fetchProgress(line, pct) { if (typeof pct === 'number') curPct = pct; try { window.postMessage({ source: 'blackboard', type: 'progress', percent: curPct, line: line, phase: 'fetch' }, location.origin); } catch (e) { /* ignore */ } }
  var classCodes = {}; // courseId -> class code, for "Saving it to MIS 460…"
  var fetching = false;
  // Cleanup: remove junk text materials. Only the helper's own record (ids/titles it created) plus text materials whose summary
  // says the content did not transfer (JavaScript shell). Runs only when the student presses "Clean up bad pages" in the popup.
  chrome.runtime.onMessage.addListener(function (m, sender, reply) {
    if (!m || m.type !== 'cleanup' || sender.id !== chrome.runtime.id) return;
    (async function () {
      var token = idToken(); if (!token) return reply({ ok: false, line: 'Not signed in to Semester OS' });
      var base = (await (await fetch('/config.json')).json()).apiUrl, removed = 0;
      var BAD = /javascript|did not transfer|could not (read|access)|blackboard.{0,24}interface|app shell|no (actual )?content/i;
      var courses = (await authedGet(base, token, '/courses')).body.courses || [];
      var ours = {}; (m.made || []).forEach(function (x) { ours[x.id] = x.t; });
      for (var i = 0; i < courses.length && i < 20; i++) {
        var list = (await authedGet(base, token, '/courses/' + encodeURIComponent(courses[i].id) + '/materials')).body.materials || [];
        for (var j = 0; j < list.length; j++) {
          var x = list[j];
          var mine = ours[x.id] !== undefined;
          var junk = (x.kind === 'paste' || x.kind === 'text') && (BAD.test(String(x.summary || '')) || (mine && Number(x.chars) < 200));
          if (!junk || /^Blackboard content index$/.test(x.title)) continue;
          try { var dr = await sfetch(base + '/courses/' + encodeURIComponent(courses[i].id) + '/materials/' + encodeURIComponent(x.id), { method: 'DELETE', headers: { Authorization: 'Bearer ' + token } }); if (dr.ok) removed++; } catch (e) { /* ignore */ }
        }
      }
      reply({ ok: true, removed: removed });
    })().catch(function () { reply({ ok: false, line: 'Cleanup stopped' }); });
    return true;
  });
  window.addEventListener('message', async function (ev) {
    var d = ev.data;
    if (!d || d.source !== 'sos-site' || d.type !== 'fetch') return;
    var trusted = ev.source === window && ev.origin === location.origin;
    SOS.msg({ type: 'siteNote', note: 'fetch message received from page' + (trusted ? '' : ' (REJECTED: source/origin mismatch)'), err: !trusted }); // FIRST event of every request
    if (!trusted) return;
    var courseId = String(d.courseId || '');
    if (!/^[a-z0-9]{8}$/.test(courseId)) return fetched(courseId, false, '', 'Bad class id');
    var path = '';
    try { var u = new URL(String(d.url || ''), BB_ORIGIN); if (u.protocol !== 'https:') throw new Error('https'); path = u.origin === BB_ORIGIN ? u.pathname + u.search : u.href; } catch (e) { return fetched(courseId, false, '', 'Not a usable link'); }
    var ckey = courseId + '|' + path.split('?')[0];
    if (fetchedCache[ckey]) return fetched(courseId, true, fetchedCache[ckey].title, undefined, fetchedCache[ckey].chars); // already added
    if (fetching) return fetched(courseId, false, '', 'Another item is being fetched, try again in a moment');
    fetching = true;
    SOS.msg({ type: 'siteNote', note: 'fetch request forwarded to the helper' });
    var tFetch = Date.now(), workerPhase = true;
    var curLine = 'Finding it in your course…'; curPct = 15;
    var tokP = freshToken(false); // fetch the sign-in token while the helper reads the page
    var tick = setInterval(async function () { // every 500 ms: the page never sees silence while a fetch is pending
      if (workerPhase) { try { var fs_ = await SOS.msg({ type: 'fetchStatus' }); if (fs_ && fs_.line && workerPhase) { curLine = fs_.line; curPct = fs_.pct || curPct; } } catch (e) { /* ignore */ } }
      fetchProgress(curLine);
    }, 500);
    var done = false, guard = setTimeout(function () { if (!done) { done = true; fetching = false; fetched(courseId, false, '', 'Timed out: open it in Blackboard'); } }, 60000);
    try {
      fetchProgress(curLine, 15);
      var r = await SOS.msg({ type: 'fetchItem', path: path });
      workerPhase = false;
      var tRead = (Date.now() - tFetch) / 1000;
      SOS.msg({ type: 'siteNote', note: 'fetch read ' + tRead.toFixed(1) + 's' });
      if (done) return;
      if (!r.ok) { done = true; return fetched(courseId, false, '', r.line || 'Open it in Blackboard'); }
      if (r.kind !== 'pdf' && !r.doc && SOSParse.looksJunk(r.text)) { done = true; return fetched(courseId, false, '', 'Could not read it. Open it in Blackboard.'); } // never upload boilerplate
      var token = await tokP || idToken();
      if (!token) { done = true; return fetched(courseId, false, '', 'Not signed in to Semester OS'); }
      var base = (await (await fetch('/config.json')).json()).apiUrl;
      var title = (String(d.title || r.title || 'Blackboard page').replace(/\s+/g, ' ').replace(/^(text document|document|file|web ?link|link|folder|item|content|assignment),\s*/i, '').trim() || 'Blackboard page').slice(0, 100);
      var code = classCodes[courseId];
      if (!code) { try { var cr0 = await sfetch(base + '/courses', {}); var cs = (await cr0.json()).courses || []; cs.forEach(function (c) { classCodes[c.id] = c.courseCode || ''; }); code = classCodes[courseId]; } catch (e) { /* the label just stays generic */ } }
      curLine = 'Saving it to ' + (code || 'your class') + '…'; fetchProgress(curLine, 75);
      var tUp = Date.now();
      var hdr = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token };
      var okUp = false, status = 0, chars = 0, matId = '';
      var note = function (s, err) { SOS.msg({ type: 'siteNote', note: s, err: !!err }); };
      note('fetch upload started (' + (r.kind === 'pdf' ? 'pdf' : 'text') + ')');
      if (r.kind === 'pdf') { // the backend extracts the text of an uploaded PDF (existing materials upload route)
        var cr = await sfetch(base + '/courses/' + encodeURIComponent(courseId) + '/materials', { method: 'POST', headers: hdr, body: JSON.stringify({ filename: r.filename || 'file.pdf', contentType: 'application/pdf', title: title }) });
        status = cr.status;
        if (cr.status === 201) {
          var cj = await cr.json(); matId = (cj.material || {}).id || '';
          var fd = new FormData();
          Object.keys(cj.upload.fields).forEach(function (f) { fd.append(f, cj.upload.fields[f]); });
          fd.append('file', new Blob([bytes(r.b64)], { type: 'application/pdf' }), r.filename || 'file.pdf'); // file must be last
          var up = await fetch(cj.upload.url, { method: 'POST', body: fd });
          okUp = up.ok; status = up.status;
        }
      } else {
        // the title is the first line of the stored text
        var body = String(r.text), firstLine = body.split('\n')[0].trim();
        var text = (firstLine === title || body.indexOf(title) === 0) ? body : title + '\n' + body;
        var mr = await sfetch(base + '/courses/' + encodeURIComponent(courseId) + '/materials/text', { method: 'POST', headers: hdr, body: JSON.stringify({ title: title, text: text.slice(0, 100000) }) });
        status = mr.status; okUp = mr.status === 202 || mr.status === 201 || mr.status === 200; chars = text.length;
        if (okUp) { try { var mj = await mr.json(); matId = (mj.material || {}).id || ''; SOS.msg({ type: 'recordMaterial', courseId: courseId, id: matId, title: title }); } catch (e) { /* ignore */ } }
      }
      note('fetch upload status ' + status + ' (' + ((Date.now() - tUp) / 1000).toFixed(1) + 's)', !okUp);
      if (!okUp) { done = true; return fetched(courseId, false, title, status === 429 ? 'Upload limit reached, try again later' : 'Could not add it (' + status + ')'); }
      // reply only when the material is READY (chunked and searchable), so the page's re-ask finds it: poll every second, up to 20 s
      var t0 = Date.now(), ready = false, errored = false;
      curLine = 'Ready, reading what it says…'; fetchProgress(curLine, 90);
      while (Date.now() - t0 < 20000 && !ready && !errored) {
        await sleep(500);
        try {
          var lr = await authedGet(base, token, '/courses/' + encodeURIComponent(courseId) + '/materials');
          var mine = (lr.body.materials || []).filter(function (x) { return matId ? x.id === matId : x.title === title; })[0];
          if (mine && mine.status === 'ready') ready = true; else if (mine && mine.status === 'error') errored = true;
        } catch (e) { /* keep polling */ }
      }
      done = true;
      if (ready) { note('fetch material ready (' + ((Date.now() - t0) / 1000).toFixed(1) + 's), total ' + ((Date.now() - tFetch) / 1000).toFixed(1) + 's'); fetchedCache[ckey] = { title: title, chars: chars }; fetched(courseId, true, title, undefined, chars, matId, true); }
      else if (errored) { note('fetch material failed to process', true); fetched(courseId, false, title, 'It was added but could not be processed: open it in Blackboard'); }
      else { note('fetch material not ready after 20 s', true); fetched(courseId, false, title, 'Added, still being processed: ask again in a minute'); }
    } catch (e) { if (!done) { done = true; fetched(courseId, false, '', 'Could not fetch it: open it in Blackboard'); } }
    finally { clearTimeout(guard); clearInterval(tick); fetching = false; }
  });

  var lastLine = '';
  function setLine(text) { if (text !== lastLine) { lastLine = text; SOS.msg({ type: 'siteLine', line: text }); } }
  // Sleep that keeps the run visibly alive: updates the line every second ("Waiting before the next upload (9 s)").
  async function waitWithLine(seconds, label) {
    for (var s = seconds; s > 0; s--) { setLine(label + ' (' + s + ' s)'); await sleep(1000); }
  }
  async function run() {
    var p = await SOS.msg({ type: 'pending' });
    var quietRun = !!(await SOS.msg({ type: 'state' })).quiet;
    var items = p.items || [], imp = p.import;
    if (!items.length && !imp) return;
    runActive = true;
    var show = ui();
    show(['Got your Blackboard data.', 'Waiting for you to be signed in here...']);
    SOS.msg({ type: 'siteNote', note: 'site waiting for session token' });
    var token = null;
    if (quietRun) { await sleep(3000); if (!idToken()) { await SOS.msg({ type: 'needsSignin' }); return; } } // daily run: never wait or prompt
    for (var i = 0; i < 45 && !(token = idToken()); i++) await sleep(2000);
    if (!token) { SOS.msg({ type: 'siteNote', note: 'site gave up: no session token found in localStorage', err: true }); tell('failed', undefined, 'Not signed in to Semester OS'); return show(['Not signed in. Sign in, then press Scan my classes again.']); }
    SOS.msg({ type: 'siteNote', note: 'site has token, reading config' });
    var base = (await (await fetch('/config.json')).json()).apiUrl;
    var lines = [], doneClasses = 0, deadlines = 0, failed = false;

    if (imp) { // one-click scan: classes plus due dates in a single call
      SOS.msg({ type: 'siteNote', note: 'site posting /courses/import' });
      tell('sending');
      show(['Sending 1 of 1 (classes and due dates)...'], 35);
      try {
        var ir = await api(base, idToken() || token, '/courses/import', imp);
        if (ir.status !== 200 && ir.status !== 201) throw new Error('import ' + ir.status);
        var b = ir.body || {}; imp_body = b;
        doneClasses = ((b.created || []).length + (b.updated || []).length) || 0;
        deadlines = imp.classes.reduce(function (a, c) { return a + c.assignments.length; }, 0);
        tell('done', doneClasses);
        lines.push('Sent ' + doneClasses + ' classes');
      } catch (e) { failed = true; tell('failed', undefined, 'The import did not finish'); lines.push('Failed import (' + String(e.message || e).slice(0, 30) + ')'); }
    }


    var pages = 0, skippedPages = 0, deepNote = '', deepStarted = false;
    if (imp && failed) await SOS.msg({ type: 'importFailed' });
    if (imp && !failed) { // classes are in: tell the extension, then upload each class's text as it is read (never blocks the import)
      var newDl = ((imp_body.created || []).concat(imp_body.updated || [])).reduce(function (a, x) { return a + (Number(x.assignmentsAdded) || 0); }, 0);
      await SOS.msg({ type: 'importDelivered', classes: doneClasses, deadlines: deadlines, newDeadlines: newDl });
      try { // class rows: ids from the import response, titles and colours from GET /courses
        var ids = ((imp_body.created || []).concat(imp_body.updated || [])).map(function (x) { return x.id; });
        var allc = (await authedGet(base, idToken() || token, '/courses')).body.courses || [];
        classList = allc.filter(function (c) { return ids.indexOf(c.id) >= 0 || imp.classes.some(function (k) { return c.bbIdentifier === k.identifier; }); })
          .map(function (c) { return { id: c.id, code: c.courseCode, title: c.title, color: c.color }; });
        await SOS.msg({ type: 'classesReady', classes: classList });
      } catch (e) { /* rows are optional */ }
      var have = null, stopDeep = false, idle = 0, lastUploadAt = 0;
      for (var guard = 0; guard < 4000; guard++) {
        var nx = await SOS.msg({ type: 'deepNext' });
        if (nx.finished || nx.error) { pages = nx.pages || 0; skippedPages = nx.skipped || 0; deepNote = nx.note || ''; break; }
        if (!nx.item) { setLine(nx.progress || 'Reading your course pages'); show([nx.progress || 'Reading your course pages'].concat(lines), nx.pct, classList); await sleep(2000); continue; }
        if (stopDeep) { await SOS.msg({ type: 'deepSent', identifier: nx.item.identifier, ok: false }); continue; }
        var dc = nx.item, sent = false, sylOk = false;
        show(['Uploading ' + dc.code + ' content index...'].concat(lines), nx.pct, classList);
        try {
          token = idToken() || token;
          if (!have) have = (await authedGet(base, token, '/courses')).body.courses || [];
          var target = matchClass(have, dc.identifier);
          if (!target) { lines.push('Skipped ' + dc.code + ' (class not found)'); }
          else {
            var cid = encodeURIComponent(target.id);
            var hdrs = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token };
            // 5 uploads per minute: wait only as long as needed, only before the next upload; 429 backs off
            var pace = async function (label) {
              var wait = 13000 - (Date.now() - lastUploadAt);
              if (lastUploadAt && wait > 1000) await waitWithLine(Math.ceil(wait / 1000), 'Waiting before the next upload');
              setLine(label);
            };
            var withRetry = async function (doIt) {
              for (var attempt = 0; attempt < 3; attempt++) {
                var rs = await doIt();
                if (rs.ok) { lastUploadAt = Date.now(); return rs; }
                if (rs.status === 429) { var ra = parseInt(rs.retry || '', 10); await waitWithLine(Math.min(ra > 0 ? ra : 15 * (attempt + 1), 70), 'Upload limit reached, waiting'); continue; }
                if (rs.status === 401 || rs.status === 403) { stopDeep = true; throw new Error('not allowed ' + rs.status); }
                throw new Error('materials ' + rs.status);
              }
              stopDeep = true; throw new Error('rate limited');
            };
            var postText = function (title, text) { return withRetry(async function () {
              var r1 = await sfetch(base + '/courses/' + cid + '/materials/text', { method: 'POST', headers: hdrs, body: JSON.stringify({ title: title, text: String(text).slice(0, 100000) }) });
              var id = ''; if (r1.ok) { try { id = ((await r1.json()).material || {}).id || ''; } catch (e) { /* ignore */ } }
              return { ok: r1.status === 202 || r1.status === 201 || r1.status === 200, status: r1.status, retry: r1.headers.get('Retry-After'), id: id };
            }); };
            var postPdf = function (title, b64, filename) { return withRetry(async function () {
              var r1 = await sfetch(base + '/courses/' + cid + '/materials', { method: 'POST', headers: hdrs, body: JSON.stringify({ filename: filename || 'syllabus.pdf', contentType: 'application/pdf', title: title }) });
              if (r1.status !== 201) return { ok: false, status: r1.status, retry: r1.headers.get('Retry-After') };
              var cj = await r1.json(), fd = new FormData();
              Object.keys(cj.upload.fields).forEach(function (f) { fd.append(f, cj.upload.fields[f]); });
              fd.append('file', new Blob([bytes(b64)], { type: 'application/pdf' }), filename || 'syllabus.pdf'); // file must be last
              var up = await fetch(cj.upload.url, { method: 'POST', body: fd });
              return { ok: up.ok, status: up.status };
            }); };
            if (dc.text) { // the index (with the syllabus text appended when the worker could read it)
              await pace('Uploading ' + dc.code + ' index');
              var INDEX_TITLE = 'Blackboard content index', oldIds = [];
              try { // no replace-by-title in the materials API: delete older copies after the new one is stored
                var ml = (await authedGet(base, token, '/courses/' + cid + '/materials')).body.materials || [];
                oldIds = ml.filter(function (x) { return x && x.title === INDEX_TITLE; }).map(function (x) { return x.id; });
              } catch (e) { /* duplicates are better than losing the index */ }
              var res1 = await postText(INDEX_TITLE, dc.text);
              sent = true;
              for (var oi = 0; oi < oldIds.length; oi++) {
                if (oldIds[oi] === res1.id) continue;
                try { await sfetch(base + '/courses/' + cid + '/materials/' + encodeURIComponent(oldIds[oi]), { method: 'DELETE', headers: { Authorization: 'Bearer ' + token } }); } catch (e) { /* ignore */ }
              }
              lines.push('Sent ' + dc.code);
            }
            if (dc.syl) { // a syllabus that goes up on its own (PDF, or text when the index did not change)
              await pace('Uploading the ' + dc.code + ' syllabus');
              if (dc.syl.kind === 'pdf') await postPdf(dc.syl.title, dc.syl.b64, dc.syl.filename); else if (!SOSParse.looksJunk(dc.syl.text)) await postText(dc.syl.title, dc.syl.text); else throw new Error('syllabus text was not real content');
              sylOk = true; lines.push('Syllabus ' + dc.code);
            }
          }
        } catch (e) { lines.push('Failed ' + dc.code + ' (' + String(e.message || e).slice(0, 30) + ')'); }
        await SOS.msg({ type: 'deepSent', identifier: dc.identifier, ok: sent, sylOk: sylOk });
      }
    }

    var ok = 0, existing = null;
    for (var k = 0; k < items.length; k++) { // optional guided syllabi, attached to the same class when it exists
      var it = items[k];
      show(['Sending ' + (k + 1) + ' of ' + items.length + ' (syllabus)...'].concat(lines));
      try {
        token = idToken() || token;
        if (!existing) existing = (await authedGet(base, token, '/courses')).body.courses || [];
        var cls = matchClass(existing, it.code);
        var path = cls ? '/courses/' + cls.id + '/materials' : '/courses';
        var title = 'Syllabus ' + it.code;
        if (it.kind === 'pdf') {
          var r = await api(base, token, path, cls ? { filename: it.filename, contentType: 'application/pdf', title: title } : { filename: it.filename, contentType: 'application/pdf' });
          if (r.status !== 201 || !r.body.upload) throw new Error('create ' + r.status);
          var fd = new FormData();
          Object.keys(r.body.upload.fields).forEach(function (f) { fd.append(f, r.body.upload.fields[f]); });
          fd.append('file', new Blob([bytes(it.b64)], { type: 'application/pdf' }), it.filename); // file must be last
          var up = await fetch(r.body.upload.url, { method: 'POST', body: fd });
          if (!up.ok) throw new Error('upload ' + up.status);
        } else {
          var t = cls ? await api(base, token, path + '/text', { title: title, text: it.text.slice(0, 100000) }) : await api(base, token, path, { text: it.text });
          if (t.status !== 202) throw new Error('create ' + t.status);
        }
        ok++; lines.push('Sent ' + it.code);
      } catch (e) { lines.push('Failed ' + it.code + ' (' + String(e.message || e).slice(0, 30) + ')'); }
    }

    var any = (imp && !failed) || ok;
    var msg = imp ? (failed ? 'The import did not finish.' : 'Done: ' + doneClasses + ' classes, ' + pages + ' pages' + (skippedPages ? ', ' + skippedPages + ' skipped' : '') + deepNote) : ok + ' of ' + items.length + ' sent.';
    if (any) await SOS.msg({ type: 'delivered', result: { classes: doneClasses, deadlines: deadlines, msg: msg } });
    setLine('');
    show([msg].concat(lines), undefined, classList);
    if (any && !/^\/onboarding/.test(location.pathname)) { await sleep(2500); location.href = '/study'; }
  }
  run();

  // Progress panel for the reading phases (before the import reaches this page) and after reloads: polls the worker once a second.
  var lastKey = '', lastPost = '', lastClassesKey = '', lastFinal = '', wasRunning = false, lastReset = 0, bornAt = Date.now(), siteHost = null, siteBox = null, lastDisp = '';
  var sosTimer = setInterval(async function () {
    var alive = false;
    try { alive = !!(chrome.runtime && chrome.runtime.id); } catch (e) { alive = false; }
    var st = alive ? await SOS.msg({ type: 'state' }) : null;
    if (!alive || !st || st.error) { // the extension was reloaded or removed: this orphaned copy shuts itself down and leaves no UI behind
      clearInterval(sosTimer);
      if (siteHost) { siteHost.remove(); siteHost = null; }
      var orphan = document.getElementById('semesteros-connect-site'); if (orphan) orphan.remove();
      return;
    }
    hello(); // lets the page know the helper is installed (steady, once a second)
    if (st && st.quiet) { var qh = document.getElementById('semesteros-connect-site'); if (qh) qh.remove(); return; } // daily run: stay silent
    var sc = st && st.scan;
    if (sc && !SOS.recent(sc, 30000)) sc = null;
    // Tell the page (its own UI renders this inline) about every change; the worker state is the single source of truth.
    if (sc && !SOS.recent(sc, 30000)) sc = null; // stale results stay silent on plain page loads
    if (st && st.resetAt && Date.now() - st.resetAt < 30000 && lastReset !== st.resetAt) { // final status after a reset
      lastReset = st.resetAt;
      try { window.postMessage({ source: 'blackboard', type: 'reset', line: 'Helper reset' }, location.origin); window.postMessage({ source: 'blackboard', type: 'progress', percent: 0, line: 'Helper reset', phase: 'reset' }, location.origin); } catch (e) { /* ignore */ }
    }
    if (sc && sc.phase === 'error' && lastPost !== 'e' + sc.msg) { lastPost = 'e' + sc.msg; try { window.postMessage({ source: 'blackboard', type: 'failed', line: String(sc.msg || 'The scan did not finish').slice(0, 160) }, location.origin); } catch (e) { /* ignore */ } }
    var runningNow = sc && /^(courses|calendar|sending|deep)$/.test(sc.phase);
    var classesMsg = function () { return { source: 'blackboard', type: 'classes', items: sc.classes.slice(0, 12).map(function (k) { return { id: k.id, code: k.code, title: k.title, color: k.color }; }) }; };
    if (runningNow) wasRunning = true;
    else if (!sc && wasRunning) { // the run vanished without a result (Cancel in the popup or a panel, or a reset): tell the page once, then go quiet
      wasRunning = false;
      try { window.postMessage({ source: 'blackboard', type: 'cancelled' }, location.origin); window.postMessage({ source: 'blackboard', type: 'progress', percent: 0, line: '', phase: 'idle' }, location.origin); } catch (e) { /* ignore */ }
    } else if (sc) wasRunning = false; // finished or failed: the final message below covers it
    if (runningNow) { // every second WHILE the run is alive, so the page never sees silence
      try {
        window.postMessage({ source: 'blackboard', type: 'progress', percent: Math.max(0, Math.min(100, Math.round(sc.pct || 0))), line: String(sc.sub || sc.msg || '').slice(0, 120), phase: String(sc.phase || '') }, location.origin);
        var ck = JSON.stringify((sc.classes || []).map(function (k) { return k.id; }));
        if (sc.classes && sc.classes.length && (ck !== lastClassesKey || (Date.now() % 10000) < 1000)) { lastClassesKey = ck; window.postMessage(classesMsg(), location.origin); }
      } catch (e) { /* ignore */ }
    } else if (sc && (sc.phase === 'done' || sc.phase === 'error')) { // finished: ONE final message, then silence (only hello/helper continue)
      var fkey = sc.phase + '|' + (sc.endedAt || 0);
      if (fkey !== lastFinal) {
        lastFinal = fkey;
        try {
          window.postMessage({ source: 'blackboard', type: 'progress', percent: sc.phase === 'done' ? 100 : Math.max(0, Math.min(100, Math.round(sc.pct || 0))), line: String(sc.msg || '').slice(0, 120), phase: sc.phase === 'done' ? 'done' : 'error' }, location.origin);
          if (sc.phase === 'done') { window.postMessage({ source: 'blackboard', type: 'done', count: (sc.classes || []).length || sc.courses || 0 }, location.origin); if (sc.classes && sc.classes.length) window.postMessage(classesMsg(), location.origin); }
        } catch (e) { /* ignore */ }
      }
    }
    if (runActive) return;
    // The website has its own idle/onboarding card: the helper injects NOTHING unless a scan is alive, or ended under 30 s ago.
    var running = sc && /^(courses|calendar|sending|deep)$/.test(sc.phase);
    var justEnded = sc && (sc.phase === 'done' || sc.phase === 'error') && sc.endedAt && Date.now() - sc.endedAt < 30000;
    SOS.updatePill(running ? (sc.pct || 0) : null);
    if (!running && !justEnded) { // nothing to show: remove the panel once, then stay out of the way
      if (siteHost) { siteHost.remove(); siteHost = null; siteBox = null; lastDisp = ''; }
      return;
    }
    // Create the node ONCE; later ticks only touch it when what is displayed actually changed (no remove/re-add, no flashing).
    var disp = JSON.stringify([sc.phase, sc.msg, sc.sub, sc.pct, (sc.classes || []).map(function (k) { return k.id; })]);
    if (!siteHost) {
      var root = SOS.panel('semesteros-connect-site');
      siteBox = SOS.el('div', { 'class': 'b' });
      root.appendChild(siteBox);
      siteHost = document.getElementById('semesteros-connect-site') || SOS.hosts['semesteros-connect-site'];
      lastDisp = '';
    }
    if (disp === lastDisp) return;
    lastDisp = disp;
    siteBox.textContent = '';
    siteBox.appendChild(SOS.header(running ? 'Scanning' : sc.phase === 'done' ? 'Done' : 'Scan stopped'));
    var bd = SOS.el('div', { 'class': 'bd' });
    siteBox.appendChild(bd);
    if (running) {
      bd.appendChild(SOS.el('div', { 'class': 'row' }, [SOS.el('span', { 'class': 'spin' }), SOS.el('span', { text: sc.sub || sc.msg || 'Working' })]));
      bd.appendChild(SOS.barView(sc.pct || 5, ''));
    } else {
      bd.appendChild(SOS.el('p', { 'class': sc.phase === 'error' ? 'note err' : 'lead', text: sc.msg || (sc.phase === 'done' ? 'Done' : 'The scan did not finish') }));
    }
    if (sc.classes && sc.classes.length) bd.appendChild(SOS.classRows(sc.classes));
    if (running) bd.appendChild(SOS.el('div', { 'class': 'btns' }, [SOS.el('button', { 'class': 's', text: 'Cancel scan', on: async function () { await SOS.msg({ type: 'cancelScan' }); } })]));
  }, 1000);
})();
