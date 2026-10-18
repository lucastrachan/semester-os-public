// Shared helpers. Everything captured is untrusted data: shown via textContent only, never as HTML.
var SOS = {
  MAX_TEXT: 60000, MIN_TEXT: 50, MAX_PDF: 4 * 1024 * 1024,
  // Sends a message to the service worker. A sleeping worker is woken by the message itself; if the first attempts still find no
  // receiver ("Receiving end does not exist"), retry twice with a short pause before giving up.
  msg: function (m) {
    return new Promise(function (res) {
      var tries = 0;
      (function go() {
        try {
          chrome.runtime.sendMessage(m, function (r) {
            var err = chrome.runtime.lastError;
            if (err && tries < 2 && /receiving end|could not establish|message port closed|no matching/i.test(String(err.message))) { tries++; setTimeout(go, 400); return; }
            res(r || {});
          });
        } catch (e) { res({ error: String(e) }); }
      })();
    });
  },
  el: function (tag, props, kids) {
    var e = document.createElement(tag);
    Object.keys(props || {}).forEach(function (k) {
      if (k === 'text') e.textContent = props[k];
      else if (k === 'on') e.addEventListener('click', props[k]);
      else e.setAttribute(k, props[k]);
    });
    (kids || []).forEach(function (c) { e.appendChild(c); });
    return e;
  },

  // ---- presentation only (look and feel). No logic below this line depends on it. ----
  svg: function (paths, size, extra) {
    var NS = 'http://www.w3.org/2000/svg';
    var s = document.createElementNS(NS, 'svg');
    s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('width', String(size || 18)); s.setAttribute('height', String(size || 18));
    s.setAttribute('fill', 'none'); s.setAttribute('stroke', 'currentColor'); s.setAttribute('stroke-width', '2.4');
    s.setAttribute('stroke-linecap', 'round'); s.setAttribute('stroke-linejoin', 'round'); s.setAttribute('aria-hidden', 'true');
    if (extra) s.setAttribute('class', extra);
    paths.forEach(function (d) { var p = document.createElementNS(NS, 'path'); p.setAttribute('d', d); s.appendChild(p); });
    return s;
  },
  icon: function (name, size) {
    var d = { check: ['M5 12.5l4.5 4.5L19 7.5'], x: ['M6 6l12 12M18 6L6 18'], dot: ['M12 12h.01'], arrow: ['M5 12h14M13 6l6 6-6 6'], skip: ['M5 12h14'] }[name] || [];
    return SOS.svg(d, size || 16, 'ic ic-' + name);
  },
  // The Semester OS mark (window tile, title-bar dots, bold S), built with DOM calls (no innerHTML).
  logo: function (size) {
    var NS = 'http://www.w3.org/2000/svg';
    var s = document.createElementNS(NS, 'svg');
    s.setAttribute('viewBox', '0 0 128 128'); s.setAttribute('width', String(size || 28)); s.setAttribute('height', String(size || 28));
    s.setAttribute('aria-hidden', 'true'); s.setAttribute('class', 'logo');
    var r = document.createElementNS(NS, 'rect');
    ['x:4', 'y:4', 'width:120', 'height:120', 'rx:30', 'fill:#4F46E5'].forEach(function (kv) { var a = kv.split(':'); r.setAttribute(a[0], a[1]); });
    s.appendChild(r);
    [[31, 1], [43, 0.6], [55, 0.35]].forEach(function (d) {
      var c = document.createElementNS(NS, 'circle');
      c.setAttribute('cx', String(d[0])); c.setAttribute('cy', '29'); c.setAttribute('r', '4'); c.setAttribute('fill', '#fff'); c.setAttribute('opacity', String(d[1]));
      s.appendChild(c);
    });
    var p = document.createElementNS(NS, 'path');
    p.setAttribute('d', 'M83 60 C83 49 74 44 63 44 C52 44 44 50 44 58 C44 68 53 70 64 72 C75 74 84 78 84 88 C84 97 75 103 64 103 C53 103 45 98 43 88');
    p.setAttribute('fill', 'none'); p.setAttribute('stroke', '#fff'); p.setAttribute('stroke-width', '12'); p.setAttribute('stroke-linecap', 'round'); p.setAttribute('stroke-linejoin', 'round');
    s.appendChild(p);
    return s;
  },
  // Header used by the panel and the popup: logo, product name, optional small status chip.
  header: function (chip) {
    var kids = [SOS.logo(28), SOS.el('span', { 'class': 'name', text: 'Semester OS' })];
    if (chip) kids.push(SOS.el('span', { 'class': 'chip', text: chip }));
    if (SOS.inPage) kids.push(SOS.el('button', { 'class': 'ctl', 'aria-label': 'Minimize', title: 'Minimize', text: '–', on: function () { SOS.setUi({ min: true }); } }));
    kids.push(SOS.el('button', { 'class': 'ctl', 'aria-label': 'Close', title: 'Close', text: '×', on: function () { if (SOS.inPage) SOS.setUi({ hidden: true }); else window.close(); } }));
    return SOS.el('div', { 'class': 'hd' }, kids);
  },
  CSS: [
    ':host{all:initial}',
    '*{box-sizing:border-box}',
    '.b{--bg:#13161C;--surf:#1A1E26;--ink:#ECEEF3;--mut:#A3ABBB;--bd:#2B313C;--acc:#4F46E5;--accs:#A5A1F5;--tint:#23264F;--ok:#5FD39A;--err:#FF8A80;--warn:#F5B454;font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);border:1px solid var(--bd);border-radius:16px;width:340px;max-width:calc(100vw - 32px);box-shadow:0 18px 40px -12px rgba(0,0,0,.6);overflow:hidden}',
    '@media (prefers-color-scheme:light){.b{--bg:#fff;--surf:#F5F6F8;--ink:#12151C;--mut:#586071;--bd:#E1E4EA;--accs:#4F46E5;--tint:#ECEBFC;--ok:#067647;--err:#B42318;--warn:#8A5A00;box-shadow:0 18px 40px -12px rgba(18,21,28,.25)}}',
    '.hd{display:flex;align-items:center;gap:10px;padding:12px 14px 10px}',
    '.name{font-weight:750;font-size:16px;letter-spacing:-.01em;flex:1}',
    '.chip{font-size:12px;font-weight:650;padding:2px 9px;border-radius:999px;background:var(--tint);color:var(--accs)}',
    'button.ctl{min-height:28px;min-width:28px;padding:0;border-radius:8px;font-size:18px;line-height:1;color:var(--mut);background:none;border:0}',
    'button.ctl:hover{color:var(--ink);background:var(--surf)}',
    '.popup .ctl{display:none}',
    '.pill{display:none;font:650 13px system-ui,sans-serif;min-height:38px;padding:0 14px;border-radius:999px;background:var(--acc,#4F46E5);color:#fff;border:0;cursor:pointer;box-shadow:0 8px 20px -6px rgba(0,0,0,.5)}',
    ':host(.sos-min) .b{display:none}:host(.sos-min) .pill{display:inline-flex;align-items:center}',
    '.bd0{display:flex;flex-direction:column;gap:6px}',
    '.bd{padding:2px 14px 14px;display:flex;flex-direction:column;gap:12px}',
    '.lead{margin:0;font-size:14px}',
    '.note,small{display:block;margin:0;font-size:13px;color:var(--mut)}',
    '.consent{margin:0;font-size:12px;color:var(--mut);text-align:center}',
    '.err{color:var(--err);font-weight:600}',
    '.status{display:flex;flex-direction:column;gap:8px;padding:12px 14px;border-radius:12px;background:var(--surf);border:1px solid var(--bd)}',
    '.status[data-s="ok"]{border-color:var(--ok)}.status[data-s="err"]{border-color:var(--err)}.status[data-s="warn"]{border-color:var(--warn)}',
    '.st-t{display:flex;align-items:center;gap:8px;font-weight:700;font-size:15px}',
    '.st-t .ic{flex:none}.status[data-s="ok"] .ic{color:var(--ok)}.status[data-s="err"] .ic{color:var(--err)}.status[data-s="warn"] .ic{color:var(--warn)}',
    '.st-pct{margin-left:auto;font-variant-numeric:tabular-nums;color:var(--accs);font-weight:700}',
    '.status button.t{align-self:flex-start}',
    '.st-s{margin:0;font-size:13px;color:var(--mut);overflow-wrap:anywhere}',
    '.bar{height:6px;border-radius:999px;background:var(--bd);overflow:hidden}',
    '.bar>i{display:block;height:100%;border-radius:inherit;background:var(--acc);width:var(--v,0%);transition:width .4s ease}',
    'ul.cl{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:4px}',
    'ul.cl li{display:flex;align-items:center;gap:10px;min-height:38px;padding:6px 10px;border-radius:10px;background:var(--surf);border:1px solid transparent;font-size:14px}',
    'ul.cl li:hover{border-color:var(--bd)}',
    'ul.cl li .code{font-weight:650;flex:1;min-width:0}',
    'ul.cl li .st{font-size:12px;color:var(--mut)}',
    'ul.cl li.ok .ic{color:var(--ok)}ul.cl li.here{border-color:var(--accs);background:var(--tint)}',
    'ul.cl li .ic{flex:none}',
    'ul.cl li.lk{min-height:38px}',
    'ul.cl li .dot{flex:none;width:10px;height:10px;border-radius:50%;background:var(--acc)}',
    'ul.cl li a.code{color:var(--ink);text-decoration:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    'ul.cl li a.code:hover{text-decoration:underline}',
    'ul.cl li.lk::after{content:"\\203A";color:var(--mut);font-size:18px;line-height:1}',
    '.btns{display:flex;flex-direction:column;gap:8px}',
    'button{font:600 14px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;min-height:40px;padding:0 14px;border-radius:10px;border:1px solid transparent;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:8px;color:var(--ink);background:transparent}',
    'button.pri{background:var(--acc);color:#fff;width:100%;min-height:44px;font-size:15px}button.pri:hover{filter:brightness(1.1)}',
    'button.s{background:transparent;border-color:var(--bd)}button.s:hover{background:var(--surf)}',
    'button.t{background:none;color:var(--accs);min-height:30px;padding:0 2px;font-size:13px}button.t:hover{text-decoration:underline}',
    'a.openlink{display:inline-flex;align-items:center;justify-content:center;min-height:40px;border-radius:10px;background:var(--acc);color:#fff;font:600 14px system-ui,sans-serif;text-decoration:none}',
    'a.openlink:hover{filter:brightness(1.1)}',
    '.popup a.openlink{background:transparent;border:1px solid var(--bd);color:var(--ink)}.popup a.openlink:hover{background:var(--surf)}',
    'button:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid var(--accs);outline-offset:2px}',
    'button:disabled,button[aria-disabled="true"]{opacity:.55;cursor:default}',
    '.lnks{display:flex;flex-wrap:wrap;gap:2px 16px;justify-content:center}',
    'details.sec{border-top:1px solid var(--bd);margin:0 -14px;padding:0 14px}',
    'details.sec>summary{list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;min-height:40px;font-weight:650;font-size:13px;color:var(--mut)}',
    'details.sec>summary::-webkit-details-marker{display:none}',
    'details.sec>summary::after{content:"";width:7px;height:7px;border-right:2px solid currentColor;border-bottom:2px solid currentColor;transform:rotate(45deg);margin-right:4px;transition:transform .15s}',
    'details.sec[open]>summary::after{transform:rotate(-135deg)}',
    'details.sec[open]>summary{color:var(--ink)}',
    '.sec-b{display:flex;flex-direction:column;gap:10px;padding:2px 0 12px}',
    '.btns button[role="switch"]{justify-content:space-between;text-align:left;min-height:40px;width:100%}',
    '.btns button[role="switch"]::after{content:"";flex:none;width:34px;height:20px;border-radius:999px;background:var(--bd);box-shadow:inset 0 0 0 0 var(--acc)}',
    '.btns button[role="switch"][aria-checked="true"]::after{background:var(--acc)}',
    '.spin{width:16px;height:16px;border-radius:50%;border:2.5px solid var(--bd);border-top-color:var(--accs);animation:sp .8s linear infinite;flex:none}',
    '.row{display:flex;align-items:center;gap:10px}',
    '.msgs{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px;font-size:13px}',
    '.msgs li{display:flex;gap:8px;align-items:center}.msgs li.ok .ic{color:var(--ok)}.msgs li.bad .ic{color:var(--err)}',
    'ol.steps{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px;counter-reset:s}',
    'ol.steps li{counter-increment:s;display:flex;gap:10px;align-items:flex-start;font-size:13px}',
    'ol.steps li::before{content:counter(s);flex:none;width:20px;height:20px;border-radius:50%;background:var(--tint);color:var(--accs);font-weight:700;font-size:12px;display:grid;place-items:center}',
    '@keyframes sp{to{transform:rotate(360deg)}}',
    '@media (prefers-reduced-motion:reduce){.spin{animation:none;border-top-color:var(--bd);background:var(--tint)}*{transition:none!important;animation:none!important}}'
  ].join('\n'),
  // Shadow-root host fixed to the bottom-right. Styles go in through CSSOM (a constructed sheet), which strict page CSPs allow.
  panel: function (id) {
    var old = document.getElementById(id);
    if (old) old.remove();
    var host = document.createElement('div');
    host.id = id;
    host.style.cssText = 'all:initial;position:fixed;right:16px;bottom:16px;z-index:2147483647;';
    var root = host.attachShadow({ mode: 'open' });
    SOS.applyCss(root);
    SOS.inPage = true;
    root.appendChild(SOS.el('button', { 'class': 'pill', text: typeof SOS.pct === 'number' ? 'Semester OS ' + SOS.pct + '%' : 'Semester OS', on: function () { SOS.setUi({ min: false }); } }));
    if (SOS.ui.min) host.classList.add('sos-min');
    if (!SOS.ui.hidden) document.documentElement.appendChild(host);
    SOS.hosts[id] = host;
    return root;
  },
  // Panel UI flags (minimized / closed), remembered in chrome.storage.local. Not sensitive.
  ui: { min: false, hidden: false }, hosts: {}, inPage: false,
  pct: null,
  updatePill: function (pct) { // mini percentage on the minimized pill while a scan runs
    SOS.pct = pct;
    Object.keys(SOS.hosts).forEach(function (id) {
      var pill = SOS.hosts[id].shadowRoot && SOS.hosts[id].shadowRoot.querySelector('.pill');
      if (pill) pill.textContent = pct === 'done' ? 'Semester OS \u2713' : typeof pct === 'number' ? 'Semester OS ' + pct + '%' : 'Semester OS';
    });
  },
  // Determinate bar + one line under it. Built with CSSOM only.
  barView: function (pct, line) {
    var v = Math.max(0, Math.min(100, Math.round(pct || 0)));
    var bar = SOS.el('div', { 'class': 'bar', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': String(v) }, [SOS.el('i')]);
    bar.firstChild.style.setProperty('--v', v + '%');
    return SOS.el('div', { 'class': 'bd0' }, [bar, SOS.el('p', { 'class': 'note', text: v + '%  ' + (line || '') })]);
  },
  SITE: 'https://<deployed-host-1>',
  // Clickable class rows (code + title + colour dot). Links go only to our own site origin; ids and colours are validated.
  classRows: function (list) {
    var ul = SOS.el('ul', { 'class': 'cl' });
    (list || []).slice(0, 12).forEach(function (k) {
      if (!k || !/^[a-z0-9]{8}$/.test(String(k.id))) return;
      var dot = SOS.el('span', { 'class': 'dot' });
      if (/^#[0-9a-fA-F]{6}$/.test(String(k.color || ''))) dot.style.setProperty('background', k.color); // CSSOM
      var label = String(k.code || '') + (k.title && k.title !== k.code ? '  ' + String(k.title) : '');
      var a = SOS.el('a', { 'class': 'code', href: SOS.SITE + '/study/' + k.id, target: '_blank', rel: 'noopener noreferrer', text: label.slice(0, 80) });
      ul.appendChild(SOS.el('li', { 'class': 'lk' }, [dot, a]));
    });
    return ul;
  },
  openSite: function () {
    return SOS.el('a', { 'class': 'openlink', href: SOS.SITE + '/study', target: '_blank', rel: 'noopener noreferrer', text: 'Open Semester OS' });
  },
  // Short banner at the top of the page; dismisses itself. Text only.
  toast: function (text, bad) {
    try {
      var old = document.getElementById('semesteros-toast'); if (old) old.remove();
      var host = document.createElement('div'); host.id = 'semesteros-toast';
      host.style.cssText = 'all:initial;position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:2147483647;';
      var root = host.attachShadow({ mode: 'open' });
      SOS.applyCss(root);
      var box = SOS.el('div', { 'class': 'b' }, [SOS.el('div', { 'class': 'row', role: 'status' }, [SOS.icon(bad ? 'x' : 'check', 20), SOS.el('span', { text: text })])]);
      box.style.setProperty('padding', '12px 16px'); box.style.setProperty('width', 'auto');
      box.firstChild.firstChild.style.setProperty('color', bad ? 'var(--err)' : 'var(--ok)');
      box.addEventListener('click', function () { host.remove(); });
      root.appendChild(box);
      document.documentElement.appendChild(host);
      setTimeout(function () { host.remove(); }, 9000);
    } catch (e) { /* ignore */ }
  },
  // One diagnostic line (phase, seconds since the last heartbeat, last error) and a copy button. No names, text or tokens.
  diagView: function (st) {
    var sc = (st && st.scan) || null, dg = (st && st.diag) || {};
    var secs = sc && sc.startedAt && dg.now ? Math.max(0, Math.round((dg.now - sc.startedAt) / 1000)) : null;
    var line = 'Status: ' + (sc ? sc.phase : 'idle') + (secs != null ? ' \u00b7 ' + secs + 's since last update' : '') + (dg.lastError ? ' \u00b7 last error: ' + dg.lastError : '');
    var btn = SOS.el('button', { 'class': 't', text: 'Copy diagnostics', on: async function () {
      var r = await SOS.msg({ type: 'diagText' });
      var done = function (ok) { btn.textContent = ok ? 'Copied' : 'Copy failed'; setTimeout(function () { btn.textContent = 'Copy diagnostics'; }, 2500); };
      try { await navigator.clipboard.writeText(r.text || ''); done(true); }
      catch (e) { try { var ta = document.createElement('textarea'); ta.value = r.text || ''; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); done(true); } catch (e2) { done(false); } }
    } });
    return SOS.el('div', { 'class': 'bd0' }, [SOS.el('small', { text: line }), btn]);
  },
  // Opt-in daily re-scan toggle with last/next lines. daily = state.daily from the worker.
  dailyView: function (daily, after) {
    daily = daily || {};
    var fmt = function (t) { try { return new Date(t).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }); } catch (e) { return ''; } };
    var on = !!daily.on;
    var kids = [SOS.el('button', { 'class': 's', role: 'switch', 'aria-checked': on ? 'true' : 'false', text: 'Re-scan every day: ' + (on ? 'On (only new items)' : 'Off'),
      on: async function () { await SOS.msg({ type: 'dailySet', on: !on }); if (after) after(); } })];
    var lines = [];
    if (on && daily.lastStatus === 'needs-signin') lines.push('Needs sign-in: open Blackboard and Semester OS, then scan once.');
    else if (on && daily.lastStatus === 'error') lines.push('The last daily scan did not finish.');
    if (daily.lastOkAt) lines.push('Last scan: ' + fmt(daily.lastOkAt) + ', ' + (daily.lastClasses || 0) + ' classes, ' + (daily.lastNewDeadlines || 0) + ' new deadlines');
    if (on && daily.nextAt) lines.push('Next: ' + fmt(daily.nextAt) + ' (Chrome must be running)');
    lines.forEach(function (l) { kids.push(SOS.el('small', { 'class': l.indexOf('Needs sign-in') === 0 ? 'err' : '', text: l })); });
    return SOS.el('div', { 'class': 'bd0' }, kids);
  },
  // A finished or failed run is only worth showing for a while; older results must not greet every later page load.
  // Running states are trusted only when they carry a recent heartbeat (the worker already turns stale ones into errors).
  recent: function (sc, ms) {
    if (!sc) return false;
    if (sc.phase === 'done' || sc.phase === 'error') return !!sc.endedAt && Date.now() - sc.endedAt < ms;
    return true;
  },
  setUi: function (patch) {
    Object.keys(patch).forEach(function (k) { SOS.ui[k] = patch[k]; });
    SOS.applyUi();
    try { chrome.storage.local.set({ ui: SOS.ui }); } catch (e) { /* ignore */ }
  },
  applyUi: function () {
    Object.keys(SOS.hosts).forEach(function (id) {
      var h = SOS.hosts[id];
      h.classList.toggle('sos-min', !!SOS.ui.min);
      if (SOS.ui.hidden) h.remove(); else if (!h.isConnected) document.documentElement.appendChild(h);
    });
  },
  applyCss: function (root) {
    try {
      var sheet = new CSSStyleSheet();
      sheet.replaceSync(SOS.CSS);
      root.adoptedStyleSheets = [sheet];
    } catch (e) {
      var st = document.createElement('style');
      st.textContent = SOS.CSS;
      (root.head || root).appendChild(st);
    }
  }
};

try {
  chrome.storage.local.get('ui', function (r) { if (r && r.ui) { SOS.ui = { min: !!r.ui.min, hidden: !!r.ui.hidden }; SOS.applyUi(); } });
  chrome.storage.onChanged.addListener(function (ch, area) { if (area === 'local' && ch.ui && ch.ui.newValue) { SOS.ui = { min: !!ch.ui.newValue.min, hidden: !!ch.ui.newValue.hidden }; SOS.applyUi(); } });
} catch (e) { /* not in an extension context */ }
