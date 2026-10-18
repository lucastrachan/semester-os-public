// Blackboard (Ultra) content script. READ-ONLY. Does nothing visible-but-inert until the student presses the button.
// Guided mode: Blackboard blocks background framing and cookie-only API calls (verified 403), so the student
// opens each course and its syllabus; we capture what is on screen when they press "Capture".
(function () {
  if (window.__sosBB) return; // idempotent: never two panels or two polls on one page
  window.__sosBB = true;
  var TERM_RE = /\b(\d{6})-([A-Z]{2,5})-(\d{3,4}[A-Z]?)-([A-Z0-9]+)\b/;
  var busy = false, note = '';

  function courseIdFromUrl() {
    var m = location.pathname.match(/\/ultra\/courses\/(_\d+_1)\//) || location.search.match(/[?&]course_id=(_\d+_1)/);
    return m ? m[1] : null;
  }
  var lastScanKey = '', lastToast = '';
  // The page's own content-tree responses, sanitised in the MAIN world (main_hook.js), arrive as window messages.
  window.addEventListener('message', function (ev) {
    var d = ev.data;
    if (ev.source !== window || ev.origin !== location.origin || !d || d.__sosFeed !== 1 || !Array.isArray(d.items)) return;
    if (!/^_\d+_1$/.test(String(d.course || ''))) return;
    var items = d.items.slice(0, 400).filter(function (i) { return i && /^_\d+_1$/.test(String(i.id)); }).map(function (i) {
      var o = { id: i.id, title: String(i.title || '').slice(0, 120), h: String(i.h || '').slice(0, 60) };
      if (i.file && /^\/bbcswebdav\/[\w\-\/.%]+$/.test(String(i.file.url || ''))) o.file = { name: String(i.file.name || '').slice(0, 100), mime: String(i.file.mime || '').slice(0, 100), size: Number(i.file.size) || 0, url: i.file.url };
      if (i.link && /^https:\/\/[^\s]{4,500}$/.test(String(i.link))) o.link = String(i.link).slice(0, 500);
      return o;
    });
    if (items.length) SOS.msg({ type: 'feed', course: d.course, items: items });
  });
  var bbTimer = setInterval(async function () {
    var st = await SOS.msg({ type: 'state' });
    if (!st || st.error) { clearInterval(bbTimer); var oh = document.getElementById('semesteros-connect'); if (oh) oh.remove(); return; } // orphaned after an extension reload
    if (st && st.quiet) { var qh = document.getElementById('semesteros-connect'); if (qh) qh.remove(); return; } // daily run: no panel on the student's tabs
    var key = JSON.stringify(st && st.scan || null);
    var running = st && st.scan && /^(courses|calendar|sending|deep)$/.test(st.scan.phase);
    var finished = st && st.scan && (st.scan.phase === 'done' || st.scan.phase === 'error');
    SOS.updatePill(running ? (st.scan.pct || 0) : (st.scan && st.scan.phase === 'done') ? 'done' : null);
    if (finished && key !== lastScanKey) { var fk = st.scan.phase + (st.scan.msg || ''); if (fk !== lastToast) { lastToast = fk; SOS.toast(st.scan.phase === 'done' ? (st.scan.partial ? 'Semester OS: classes added, page reading stopped' : 'Semester OS finished scanning') : 'Semester OS scan stopped', st.scan.phase === 'error'); } }
    var gone = !document.getElementById('semesteros-connect') && !SOS.ui.hidden;
    if (key !== lastScanKey || gone) { lastScanKey = key; render(st); }
  }, 1000);
  var lastUrl = location.href;
  setInterval(async function () { if (location.href !== lastUrl) { lastUrl = location.href; render(await SOS.msg({ type: 'state' })); } }, 1000);

  // Open a course the way the student would: a real click on its card, so Blackboard's own page handles Ultra and Original courses.
  async function openCourse(q) {
    note = ''; await SOS.msg({ type: 'setCurrent', id: q.id });
    var card = document.getElementById('course-list-course-' + q.id);
    var target = card && (card.querySelector('a.course-title, h4 a, a') || card);
    if (!target) { note = 'Could not open this course; open it yourself from the list and press Capture.'; return render(await SOS.msg({ type: 'state' })); }
    var before = location.href;
    target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    for (var i = 0; i < 16 && location.href === before; i++) await new Promise(function (r) { setTimeout(r, 500); });
    if (location.href === before) note = 'Could not open this course; open it yourself from the list and press Capture.';
    render(await SOS.msg({ type: 'state' }));
  }
  function onCourseList() { return /^\/ultra\/course\/?$/.test(location.pathname); }

  function readCourseCards() {
    var cards = document.querySelectorAll('article[id^="course-list-course-"]');
    var found = [];
    cards.forEach(function (a) {
      var id = a.id.replace('course-list-course-', '');
      if (!/^_\d+_1$/.test(id)) return;
      var m = (a.textContent || '').match(TERM_RE);
      if (m) found.push({ id: id, code: m[0], term: m[1] });
    });
    if (!found.length) return [];
    var newest = found.reduce(function (x, c) { return c.term > x ? c.term : x; }, '000000');
    var seen = {};
    return found.filter(function (c) { if (c.term !== newest || seen[c.id]) return false; seen[c.id] = 1; return true; });
  }

  function waitFor(fn, ms) {
    return new Promise(function (res) {
      var t0 = Date.now();
      (function tick() { var v = fn(); if (v && v.length) return res(v); if (Date.now() - t0 > ms) return res(null); setTimeout(tick, 500); })();
    });
  }

  function b64(buf) {
    var bytes = new Uint8Array(buf), s = '', i, CH = 0x8000;
    for (i = 0; i < bytes.length; i += CH) s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
    return btoa(s);
  }

  async function findPdf() {
    var links = Array.prototype.slice.call(document.querySelectorAll('a[href]')).map(function (a) { return a.href; })
      .filter(function (h) { return h.indexOf(location.origin + '/') === 0 && (/\.pdf(\?|$)/i.test(h) || /bbcswebdav|\/resources\//i.test(h)); });
    for (var i = 0; i < Math.min(links.length, 3); i++) {
      try {
        var r = await fetch(links[i], { credentials: 'same-origin' }); // GET of a file the student can already open
        var ct = (r.headers.get('content-type') || '').toLowerCase();
        if (!r.ok || ct.indexOf('pdf') < 0) continue;
        var buf = await r.arrayBuffer();
        if (buf.byteLength > SOS.MAX_PDF || new Uint8Array(buf.slice(0, 4)).join() !== '37,80,68,70') continue; // %PDF
        return b64(buf);
      } catch (e) { /* try next */ }
    }
    return null;
  }

  async function capture(code) {
    busy = true; note = 'Capturing...'; render(await SOS.msg({ type: 'state' }));
    var pdf = await findPdf();
    if (pdf) {
      await SOS.msg({ type: 'capture', item: { kind: 'pdf', code: code, filename: 'syllabus-' + code.replace(/[^A-Za-z0-9]/g, '') + '.pdf', b64: pdf } });
      note = 'Captured a PDF.';
    } else {
      var raw = document.body.innerText || '';
      Array.prototype.slice.call(document.querySelectorAll('iframe,frame')).forEach(function (f) {
        try { if (f.contentDocument && f.contentDocument.body) raw += '\n' + f.contentDocument.body.innerText; } catch (e) { /* cross-origin: skip */ }
      });
      var text = raw.replace(/\s+\n/g, '\n').trim().slice(0, SOS.MAX_TEXT);
      if (text.length < SOS.MIN_TEXT) note = 'Nothing readable on screen yet. Open the syllabus first, wait a few seconds, then capture again.';
      else { await SOS.msg({ type: 'capture', item: { kind: 'text', code: code, text: 'Course ' + code + '\n\n' + text } }); note = 'Captured page text (' + text.length + ' characters).'; }
    }
    busy = false; render(await SOS.msg({ type: 'state' }));
  }

  // ---- One-click scan helpers (run in a background tab opened by the service worker). READ-ONLY. ----
  function sleepMs(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  // Cards: the wide layout uses article#course-list-course-_N_1; other layouts may not, so also fall back to any element
  // that holds a course identifier (and its nearest course-list id when there is one).
  function cardElements() {
    var arts = document.querySelectorAll('article[id^="course-list-course-"], [id^="course-list-course-"]');
    if (arts.length) return Array.prototype.slice.call(arts);
    var out = [];
    Array.prototype.forEach.call(document.querySelectorAll('a, h3, h4, span, div'), function (e) {
      if (e.children.length === 0 && SOSParse.ID_RE.test(e.textContent || '')) out.push(e);
    });
    return out;
  }

  // Why did nothing load? Path only (no query), readyState, text length, login form, spinner. No page text.
  function diagnose() {
    var text = (document.body && document.body.innerText) || '';
    return {
      path: location.pathname.slice(0, 60), host: location.hostname, ready: document.readyState, textLen: text.length,
      login: !!document.querySelector('input[type="password"], form[action*="login" i], #loginForm') || /\/(login|sso|cas|saml)/i.test(location.pathname),
      articles: document.querySelectorAll('article').length, cardIds: document.querySelectorAll('[id^="course-list"]').length,
      pathMatch: /^\/ultra\/course/.test(location.pathname),
      spinner: !!document.querySelector('[class*="spinner" i], [class*="loading" i], [role="progressbar"], bb-loading') && text.length < 400
    };
  }

  // Course data without any rendering: the same-origin REST the page itself uses (read-only GET with the student's session).
  // May be refused (403); then we fall back to the DOM. Never throws.
  async function restCourses() {
    try {
      var ctl = new AbortController(), timer = setTimeout(function () { ctl.abort(); }, 8000);
      var r = await fetch('/learn/api/v1/users/me/memberships?expand=course&limit=200&fields=course.id,course.courseId,course.name', { credentials: 'include', signal: ctl.signal, headers: { Accept: 'application/json' } });
      clearTimeout(timer);
      if (!r.ok) return null;
      var j = await r.json();
      var out = [], seen = {};
      (j.results || []).forEach(function (m) {
        var c = m && m.course; if (!c) return;
        var ident = String(c.courseId || c.name || '').match(SOSParse.ID_RE);
        if (!ident || seen[ident[0]]) return;
        seen[ident[0]] = 1;
        out.push({ identifier: ident[0], id: /^_\d+_1$/.test(String(c.id || '')) ? c.id : '', instructor: '' });
      });
      return out.length ? out : null;
    } catch (e) { return null; }
  }

  // Collect real course identifiers (cards, or the page text). Skeleton cards exist with ids before any text: they do NOT count.
  function collectCourses() {
    var out = [], seen = {};
    cardElements().forEach(function (a) {
      var m = (a.textContent || '').match(SOSParse.ID_RE);
      if (!m || seen[m[0]]) return;
      seen[m[0]] = 1;
      var holder = a.closest ? a.closest('[id^="course-list-course-"]') : null;
      var who = (holder || a).querySelector ? (holder || a).querySelector('bdi') : null;
      out.push({ identifier: m[0], id: holder ? holder.id.replace('course-list-course-', '') : '', instructor: who ? who.textContent.trim().slice(0, 80) : '' });
    });
    if (!out.length) SOSParse.idsInText((document.body && document.body.innerText) || '').forEach(function (id) { out.push({ identifier: id, id: '', instructor: '' }); });
    return out;
  }

  async function scrapeCourses() {
    // The REST fallback runs in parallel (and again every 10 s); the DOM is polled every 500 ms for up to 45 s.
    var restDone = false, restOut = null, restRuns = 0;
    function startRest() { restDone = false; restRuns++; restCourses().then(function (r) { restOut = r; restDone = true; }); }
    startRest();
    var t0 = Date.now(), domOut = [], lastRest = Date.now();
    while (Date.now() - t0 < 45000) {
      if (restOut && restOut.length) { SOS.msg({ type: 'scanProgress', courses: restOut.length }); return { courses: restOut.slice(0, 60), via: 'rest', n: restOut.length }; }
      domOut = collectCourses();
      if (domOut.length) break;
      if (restDone && !restOut && Date.now() - lastRest > 10000) { lastRest = Date.now(); startRest(); }
      await sleepMs(500);
    }
    if (!domOut.length) return { error: 'no-cards', diag: Object.assign(diagnose(), { restRuns: restRuns }) };
    await sleepMs(1500); // let the rest of the list render, then read again
    var again = collectCourses();
    if (again.length >= domOut.length) domOut = again;
    SOS.msg({ type: 'scanProgress', courses: domOut.length });
    return { courses: domOut.slice(0, 60), via: 'dom', n: domOut.length };
  }

  async function scrapeCalendar() {
    var btn = await waitFor(function () {
      var b = Array.prototype.filter.call(document.querySelectorAll('button, [role="tab"], [role="button"], a'), function (x) {
        var label = (x.getAttribute('aria-label') || '') + ' ' + (x.textContent || '');
        return /due dates( view)?/i.test(label) && label.length < 60;
      });
      return b.length ? b : null;
    }, 45000);
    if (!btn) return { error: 'no-button', diag: diagnose() };
    btn[0].dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window })); // only switches the calendar view
    var ok = await waitFor(function () { return /Due date:/.test(document.body.innerText) ? [1] : null; }, 30000);
    if (!ok) return { error: 'no-list', diag: diagnose() };
    var last = -1, same = 0, text = '';
    for (var i = 0; i < 10 && same < 2; i++) {
      await sleepMs(1200);
      text = document.body.innerText;
      var n = SOSParse.parseDeadlines(text).length;
      same = n === last ? same + 1 : 0; last = n;
      // scroll any scrollable container that holds the list (a scroll never changes data)
      window.scrollTo(0, document.body.scrollHeight);
      Array.prototype.forEach.call(document.querySelectorAll('div,section,ul'), function (e) {
        if (e.scrollHeight > e.clientHeight + 40 && /Due date:/.test(e.innerText || '')) e.scrollTop = e.scrollHeight;
      });
    }
    return { text: text.slice(0, 400000) };
  }


  // ---- Deep scan (text only). Runs in a tab the service worker opened per class and per item. READ-ONLY:
  // the only clicks are folder expanders (aria-expanded) that Blackboard shows inline; nothing is submitted or changed.
  // INDEX crawl: expand folders (fast: click all closed expanders per round, wait until the list stops growing) and map
  // folder path, item title, type and link. Items are NOT opened. Depth 3 (three rounds), 300 items, hard 36 s.
  async function mapOutline() {
    var deadline = Date.now() + 36000;
    var list = await waitFor(function () { return document.querySelectorAll('.content-list-item'); }, 20000);
    if (!list) return { error: 'no-outline', diag: diagnose() };
    await sleepMs(600);
    var count = function () { return document.querySelectorAll('.content-list-item').length; };
    for (var round = 0; round < 3 && Date.now() < deadline && count() < 300; round++) {
      var closed = Array.prototype.slice.call(document.querySelectorAll('.content-list-item button[aria-expanded="false"]')).slice(0, 40);
      if (!closed.length) break;
      closed.forEach(function (b) { b.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window })); });
      var last = count(), stableSince = Date.now(), t0 = Date.now();
      while (Date.now() < deadline && Date.now() - t0 < 6000) { // done when the item count has not grown for 700 ms
        await sleepMs(150);
        var n = count();
        if (n !== last) { last = n; stableSince = Date.now(); } else if (Date.now() - stableSince > 700) break;
      }
    }
    var titleOf = function (el) {
      var t = el.querySelector('.ax-focusable-title');
      var raw = t ? (t.getAttribute('aria-label') || t.innerText || t.textContent || '') : '';
      if (!raw || raw.length > 160) raw = (el.innerText || '').split('\n')[0];
      return raw.replace(/\s+/g, ' ').trim().slice(0, 120);
    };
    var items = [];
    Array.prototype.forEach.call(document.querySelectorAll('.content-list-item'), function (el) {
      if (items.length >= 300) return;
      var t = el.querySelector('.ax-focusable-title');
      if (!t || t.tagName !== 'A' || !t.href) return; // folders (buttons) only contribute to the path
      var u; try { u = new URL(t.href); } catch (e) { return; }
      var external = u.origin !== location.origin; // links out of Blackboard (Google Docs, OneDrive...) are listed too
      if (external && !/^https?:$/.test(u.protocol)) return;
      if (!external && u.pathname.indexOf('/ultra/courses/') !== 0) return;
      var path = [], p = el.parentElement ? el.parentElement.closest('.content-list-item') : null;
      while (p && path.length < 3) { path.unshift(titleOf(p)); p = p.parentElement ? p.parentElement.closest('.content-list-item') : null; }
      items.push({ path: path.join(' > '), title: titleOf(el), type: external ? 'link' : SOSParse.itemType(u.pathname), href: external ? (u.origin + u.pathname).slice(0, 300) : u.pathname + u.search });
    });
    return { items: items, truncated: count() >= 300 };
  }

  // One item page: poll up to 25 s for REAL content (over 300 characters, not the app shell, not a loading screen, not just the
  // course menu), stable for two checks. A page that never gets there is an error: nothing is returned, nothing is uploaded.
  async function deepItem() {
    var last = -1, stable = 0, t0 = Date.now(), text = '';
    var isDoc = /\/document\//.test(location.pathname); // an Ultra Document: its body is often only a few lines, in .ql-editor / main
    while (Date.now() - t0 < 25000 && stable < 2) {
      await sleepMs(300);
      var el = isDoc ? (document.querySelector('.ql-editor') || document.querySelector('main')) : (document.querySelector('#main-content-inner') || document.body);
      text = (el && el.innerText) || '';
      var real = isDoc ? (text.trim().length >= 15 && !/javascript is required|enable javascript|^\s*(loading|please wait)/i.test(text)) : !SOSParse.looksJunk(text);
      stable = real && text.length === last ? stable + 1 : 0; last = text.length;
    }
    if (stable < 2) return { error: 'not-rendered', diag: diagnose() };
    var h = document.querySelector('h1, h2, [class*="page-title"], [class*="content-title"]');
    var title = ((h && (h.innerText || h.textContent)) || (document.title || '')).replace(/\s+/g, ' ').trim().slice(0, 100);
    return { title: title, text: text.replace(/\s+\n/g, '\n').trim().slice(0, 30000), doc: isDoc };
  }

  // A file item page shows the file in a viewer: find its same-origin /bbcswebdav/ address (iframe, download link, embed).
  async function findFile() {
    var t0 = Date.now(), src = '';
    while (Date.now() - t0 < 25000 && !src) {
      var el = document.querySelector('iframe[src*="/bbcswebdav/"], a[href*="/bbcswebdav/"], embed[src*="/bbcswebdav/"], object[data*="/bbcswebdav/"]');
      var raw = el ? (el.getAttribute('src') || el.getAttribute('href') || el.getAttribute('data') || '') : '';
      try { var u = new URL(raw, location.href); if (u.origin === location.origin && u.pathname.indexOf('/bbcswebdav/') === 0) src = u.pathname + u.search; } catch (e) { /* keep waiting */ }
      if (!src) await sleepMs(500);
    }
    if (!src) return { error: 'no-file-url', diag: diagnose() };
    var h = document.querySelector('h1, h2, [class*="page-title"], [class*="content-title"]');
    var title = ((h && (h.innerText || h.textContent)) || (document.title || '')).replace(/\s+/g, ' ').trim().slice(0, 100);
    return { src: src, title: title };
  }

  chrome.runtime.onMessage.addListener(function (m, sender, reply) {
    if (sender.id !== chrome.runtime.id || !m) return;
    if (m.type === 'scrapeCourses') { scrapeCourses().then(reply); return true; }
    if (m.type === 'mapOutline') { mapOutline().then(reply); return true; }
    if (m.type === 'deepItem') { deepItem().then(reply); return true; }
    if (m.type === 'findFile') { findFile().then(reply); return true; }
    if (m.type === 'scrapeCalendar') { scrapeCalendar().then(reply); return true; }
  });

  async function render(s) {
    if (!s || s.error || s.quiet) return;
    var root = SOS.panel('semesteros-connect');
    var box = SOS.el('div', { 'class': 'b' });
    root.appendChild(box);
    var bd = SOS.el('div', { 'class': 'bd' });
    function frame(chip) { box.appendChild(SOS.header(chip)); box.appendChild(bd); }
    function say(text, cls) { bd.appendChild(SOS.el('p', { 'class': cls || 'lead', text: text })); }
    function btn(label, cls, handler) { return SOS.el('button', { 'class': cls, text: label, on: handler }); }

    var sc = s.scan;
    if (sc && !SOS.recent(sc, sc.phase === 'error' ? 600000 : 1800000)) sc = null; // old errors/results do not greet every page load
    if (sc && (sc.phase === 'courses' || sc.phase === 'calendar' || sc.phase === 'sending' || sc.phase === 'deep')) {
      frame('Scanning');
      bd.appendChild(SOS.el('div', { 'class': 'row' }, [SOS.el('span', { 'class': 'spin' }), SOS.el('span', { text: sc.phase === 'deep' ? (sc.msg || 'Deep scan') : sc.phase === 'courses' ? 'Reading your courses' + (sc.courses ? ' (' + sc.courses + ')' : '') : sc.phase === 'calendar' ? 'Reading your due dates' : 'Sending classes' })]));
      bd.appendChild(SOS.barView(sc.pct || 5, sc.sub || sc.msg || ''));
      bd.appendChild(SOS.diagView(s));
      if (sc.classes && sc.classes.length) { say('Your classes (open one now):', 'note'); bd.appendChild(SOS.classRows(sc.classes)); }
      say('Background tabs open and close by themselves. Nothing is changed in Blackboard. You can close this panel; the scan keeps going.', 'note');
      bd.appendChild(SOS.el('div', { 'class': 'btns' }, [btn('Cancel scan', 's', async function () { render(await SOS.msg({ type: 'cancelScan' })); })]));
      return;
    }
    if (sc && sc.phase === 'done' && s.sent === 'done') {
      frame(sc.partial ? 'Partly done' : 'Done');
      var okRow = SOS.el('div', { 'class': 'row' }, [SOS.icon('check', 22), SOS.el('span', { 'class': 'lead', text: sc.msg || 'Done.' })]);
      okRow.firstChild.style.setProperty('color', 'var(--ok)'); // CSSOM, not a style attribute
      bd.appendChild(okRow);
      if (sc.hint) bd.appendChild(SOS.el('p', { 'class': 'note', text: sc.hint }));
      if (sc.classes && sc.classes.length) bd.appendChild(SOS.classRows(sc.classes));
      bd.appendChild(SOS.el('div', { 'class': 'btns' }, [SOS.openSite(), btn('Close', 't', async function () { render(await SOS.msg({ type: 'reset' })); })]));
      return;
    }
    if (sc && sc.phase === 'error') {
      frame('Scan');
      say(sc.msg || 'The scan did not finish.', 'note err');
      bd.appendChild(SOS.diagView(s));
      bd.appendChild(SOS.el('div', { 'class': 'btns' }, [btn('Try again', 'pri', async function () { render({ active: false, queue: [], captured: {}, sent: null, scan: { phase: 'courses', pct: 3, msg: 'Starting\u2026' }, diag: { now: Date.now() } }); render(await SOS.msg({ type: 'scan' })); }), btn('Dismiss', 't', async function () { render(await SOS.msg({ type: 'reset' })); })]));
      return;
    }
    if (!s.active && s.sent !== 'pending') {
      frame('');
      say('Bring your classes and due dates into Semester OS in one click.');
      bd.appendChild(SOS.el('p', { 'class': 'consent', text: 'Reads your course list, due dates and course pages while you watch. Never your password. Sends them only to your Semester OS account.' }));
      bd.appendChild(SOS.el('div', { 'class': 'btns' }, [
        btn('Scan my classes', 'pri', async function () {
          if (s.filePerm && !s.filePerm.granted && !s.filePerm.asked) { await SOS.msg({ type: 'openAllow' }); return; } // first scan: ask about file downloads first
          render({ active: false, queue: [], captured: {}, sent: null, scan: { phase: 'courses', pct: 3, msg: 'Starting\u2026' }, diag: { now: Date.now() } }); // instant feedback
          render(await SOS.msg({ type: 'scan' }));
        }),
      ]));
      bd.appendChild(SOS.dailyView(s.daily, async function () { render(await SOS.msg({ type: 'state' })); }));
      return;
    }
    if (s.sent === 'pending') {
      frame('Sent');
      var okRow = SOS.el('div', { 'class': 'row' }, [SOS.icon('check', 20), SOS.el('span', { text: 'Sent. Finish in the Semester OS tab.' })]);
      okRow.firstChild.style.color = 'var(--ok)'; // CSSOM, not a style attribute (works under strict page CSPs)
      bd.appendChild(okRow);
      return;
    }
    if (!s.queue.length) {
      frame('Step 1 of 3');
      if (!onCourseList()) {
        say('Open your course list first.');
        bd.appendChild(SOS.el('div', { 'class': 'btns' }, [btn('Go to my courses', 'pri', function () { location.href = '/ultra/course'; })]));
        return;
      }
      bd.appendChild(SOS.el('div', { 'class': 'row' }, [SOS.el('span', { 'class': 'spin' }), SOS.el('span', { text: 'Looking for your current-term classes...' })]));
      var cards = await waitFor(readCourseCards, 25000);
      if (!cards) { say('Could not find any classes on this page. Scroll the list, then reload.', 'note err'); return; }
      render(await SOS.msg({ type: 'setQueue', queue: cards }));
      return;
    }
    var cur = courseIdFromUrl();
    var here = s.queue.find(function (q) { return q.id === (cur || s.current); });
    if (onCourseList()) here = null;
    var gotCount = s.queue.filter(function (q) { return s.captured[q.code]; }).length;
    frame('Step 2 of 3 · ' + gotCount + '/' + s.queue.length);
    var ul = SOS.el('ul', { 'class': 'cl' });
    s.queue.forEach(function (q) {
      var c = s.captured[q.code];
      var isHere = here && here.id === q.id;
      var cls = c && c.kind !== 'skipped' ? 'ok' : isHere ? 'here' : '';
      var status = c ? (c.kind === 'skipped' ? 'skipped' : 'got it') : isHere ? 'you are here' : 'to do';
      var icon = c && c.kind !== 'skipped' ? SOS.icon('check') : c ? SOS.icon('skip') : isHere ? SOS.icon('arrow') : SOS.icon('dot');
      ul.appendChild(SOS.el('li', { 'class': cls }, [icon, SOS.el('span', { 'class': 'code', text: q.code }), SOS.el('span', { 'class': 'st', text: status })]));
    });
    bd.appendChild(ul);
    var next = s.queue.find(function (q) { return !s.captured[q.code]; });
    var done = s.queue.some(function (q) { var c = s.captured[q.code]; return c && c.kind !== 'skipped'; });
    var btns = SOS.el('div', { 'class': 'btns' });
    if (here && !s.captured[here.code]) {
      say('Open this class\'s Schedule & Syllabus and the syllabus itself, then press Capture.', 'note');
      btns.appendChild(btn('Capture this syllabus', 'pri', function () { if (!busy) capture(here.code); }));
      btns.appendChild(btn('Skip class', 's', async function () { render(await SOS.msg({ type: 'skip', code: here.code })); }));
    } else if (next) {
      if (onCourseList()) btns.appendChild(btn('Open ' + next.code, 'pri', function () { openCourse(next); }));
      else btns.appendChild(btn('Back to my courses', 'pri', function () { location.href = '/ultra/course'; }));
    }
    if (done) btns.appendChild(btn('Finish and send to Semester OS', next ? 's' : 'pri', async function () { render(await SOS.msg({ type: 'send' })); }));
    btns.appendChild(btn('Cancel', 't', async function () { render(await SOS.msg({ type: 'reset' })); }));
    bd.appendChild(btns);
    if (note) bd.appendChild(SOS.el('p', { 'class': /^(Could not|Nothing readable)/.test(note) ? 'note err' : 'note', text: note }));
  }

  (async function init() { render(await SOS.msg({ type: 'state' })); })();
})();
