// Popup: same look as the on-page panel (styles and helpers come from common.js). Only the layout changed; every message, storage key and flow is as before:
// one primary Scan button, a status card, the class rows, quiet links, then Settings and Advanced in collapsible sections.
SOS.applyCss(document);
const app = document.getElementById('app');

// Blackboard tab (or no LMS tab): the Blackboard scan. Any other page: inject the Canvas reader into this tab only
// (activeTab, granted by opening the popup); it checks /api/v1/users/self/profile and falls back to Blackboard if it is not Canvas.
const FILE_ORIGINS_P = ['https://*.blackboard.com/*', 'https://*.blackboardcdn.com/*', 'https://*.amazonaws.com/*', 'https://docs.google.com/*', 'https://drive.google.com/*', 'https://*.googleusercontent.com/*', 'https://onedrive.live.com/*', 'https://1drv.ms/*', 'https://*.sharepoint.com/*', 'https://*.officeapps.live.com/*'];
async function scanMyClasses() {
  try { // first scan only: ask for file downloads BEFORE scanning (allowed or declined, the scan then runs)
    const has = await chrome.permissions.contains({ origins: FILE_ORIGINS_P });
    const asked = (await chrome.storage.local.get('fileAsk')).fileAsk;
    if (!has && !asked) { await chrome.storage.local.set({ fileAsk: true }); await new Promise(r => chrome.permissions.request({ origins: FILE_ORIGINS_P }, () => r())); }
  } catch (e) { /* ask failed: scan anyway */ }
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const onBB = tab && tab.url && tab.url.startsWith('https://ualearn.blackboard.com/');
    if (tab && tab.id != null && /^https:/.test(tab.url || '') && !onBB && !(tab.url || '').startsWith('https://<deployed-host-1>/')) {
      await chrome.runtime.sendMessage({ type: 'canvasStart', tabId: tab.id });
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['parse.js', 'canvas.js'] });
      return window.close();
    }
  } catch (e) { /* not injectable (browser page, no access): use the Blackboard scan */ }
  let tabId = null;
  try { tabId = (await chrome.tabs.query({ active: true, currentWindow: true }))[0].id; } catch (e) { /* ignore */ }
  chrome.runtime.sendMessage({ type: 'scan', tabId }, () => window.close());
}

function section(title, kids) {
  const d = SOS.el('details', { 'class': 'sec' });
  d.appendChild(SOS.el('summary', { text: title }));
  const body = SOS.el('div', { 'class': 'sec-b' });
  kids.forEach(k => body.appendChild(k));
  d.appendChild(body);
  return d;
}

function render(s) {
  s = s || {};
  app.textContent = '';
  const box = SOS.el('div', { 'class': 'b' });
  app.appendChild(box);
  box.appendChild(SOS.header(''));
  const bd = SOS.el('div', { 'class': 'bd' });
  box.appendChild(bd);

  const sc = s.scan || null;
  const phase = sc && sc.phase;
  const running = phase === 'courses' || phase === 'calendar' || phase === 'sending' || phase === 'deep';
  const errored = phase === 'error';
  const daily = s.daily || {};

  // ---- status card: one plain-words state ----
  let st = 's', title = 'Ready', sub = 'Open Blackboard or Canvas, then press Scan.', icon = null, pct = null;
  if (running) {
    st = 'run'; title = 'Scanning'; pct = Math.max(0, Math.min(100, Math.round(sc.pct || 5)));
    sub = phase === 'courses' ? 'Reading your courses' + (sc.courses ? ' (' + sc.courses + ')' : '')
      : phase === 'calendar' ? 'Reading your due dates (' + (sc.courses || 0) + ' classes)'
      : phase === 'deep' ? (sc.msg || 'Reading your course pages') : 'Sending classes';
  } else if (errored) {
    st = 'err'; title = 'Something went wrong'; sub = sc.msg || 'The scan did not finish.'; icon = 'x';
  } else if (phase === 'done' || s.sent === 'done') {
    st = 'ok'; title = 'Done'; sub = (sc && sc.msg) || 'Sent to Semester OS.'; icon = 'check';
  } else if (s.sent === 'pending') {
    st = 'warn'; title = 'Waiting for Semester OS'; sub = 'Sign in there if asked.';
  } else if (daily.lastStatus === 'needs-signin') {
    st = 'warn'; title = 'Needs sign-in'; sub = 'Open Blackboard and Semester OS, then scan once.';
  } else if (s.active) {
    title = 'Run in progress'; sub = 'Follow the panel on the Blackboard tab.';
  }
  const card = SOS.el('div', { 'class': 'status', 'data-s': st, role: 'status' });
  const tt = SOS.el('div', { 'class': 'st-t' }, []);
  if (running) tt.appendChild(SOS.el('span', { 'class': 'spin' }));
  else if (icon) tt.appendChild(SOS.icon(icon, 18));
  tt.appendChild(SOS.el('span', { text: title }));
  if (pct !== null) tt.appendChild(SOS.el('span', { 'class': 'st-pct', text: pct + '%' }));
  card.appendChild(tt);
  if (running) {
    const bar = SOS.el('div', { 'class': 'bar', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': String(pct) }, [SOS.el('i')]);
    bar.firstChild.style.setProperty('--v', pct + '%');
    card.appendChild(bar);
  }
  card.appendChild(SOS.el('p', { 'class': 'st-s', text: sub }));
  if (phase === 'done' && sc.hint) card.appendChild(SOS.el('p', { 'class': 'st-s', text: sc.hint }));
  if (running) card.appendChild(SOS.el('button', { 'class': 't', text: 'Cancel scan', on: () => chrome.runtime.sendMessage({ type: 'cancelScan' }, render) }));
  bd.appendChild(card);

  // ---- the one primary action ----
  const go = SOS.el('button', { 'class': 'pri', text: errored ? 'Try again' : 'Scan my classes', on: () => { if (!running) scanMyClasses(); } });
  if (running) go.setAttribute('aria-disabled', 'true');
  bd.appendChild(go);

  // ---- classes (colour dots, clickable) ----
  if (sc && sc.classes && sc.classes.length) bd.appendChild(SOS.classRows(sc.classes));
  if (phase === 'done') bd.appendChild(SOS.openSite());
  if (s.queue && s.queue.length) { // the older guided syllabus capture
    const ul = SOS.el('ul', { 'class': 'cl' });
    s.queue.forEach(q => {
      const c = (s.captured || {})[q.code];
      const ok = c && c.kind !== 'skipped';
      ul.appendChild(SOS.el('li', { 'class': ok ? 'ok' : '' }, [
        ok ? SOS.icon('check') : c ? SOS.icon('skip') : SOS.icon('dot'),
        SOS.el('span', { 'class': 'code', text: q.code }),
        SOS.el('span', { 'class': 'st', text: c ? (c.kind === 'skipped' ? 'skipped' : c.kind + ' captured') : 'to do' }),
      ]));
    });
    bd.appendChild(ul);
  }

  // ---- quiet links ----
  const lnks = SOS.el('div', { 'class': 'lnks' });
  lnks.appendChild(SOS.el('button', { 'class': 't', text: 'Open Blackboard', on: () => chrome.tabs.create({ url: 'https://ualearn.blackboard.com/ultra/course' }) }));
  lnks.appendChild(SOS.el('button', { 'class': 't', text: 'Show panel on the page', on: () => chrome.storage.local.set({ ui: { min: false, hidden: false } }) }));
  lnks.appendChild(SOS.el('button', { 'class': 't', text: 'Clear this run', on: () => chrome.runtime.sendMessage({ type: 'reset' }, render) }));
  bd.appendChild(lnks);
  bd.appendChild(SOS.el('p', { 'class': 'consent', text: 'Reads only what you can already see. Never your password.' }));

  // ---- Settings ----
  const FILE_ORIGINS = ['https://*.blackboard.com/*', 'https://*.blackboardcdn.com/*', 'https://*.amazonaws.com/*', 'https://docs.google.com/*', 'https://drive.google.com/*', 'https://*.googleusercontent.com/*', 'https://onedrive.live.com/*', 'https://1drv.ms/*', 'https://*.sharepoint.com/*', 'https://*.officeapps.live.com/*'];
  const allow = SOS.el('div', { 'class': 'btns' });
  chrome.permissions.contains({ origins: FILE_ORIGINS }, (has) => { // asked once; Chrome remembers the choice
    if (has) { allow.appendChild(SOS.el('small', { text: 'Links and files: allowed' })); return; }
    allow.appendChild(SOS.el('button', { 'class': 's', text: 'Allow links and files', on: () => chrome.permissions.request({ origins: FILE_ORIGINS }, (ok) => { allow.textContent = ok ? 'Links and files: allowed' : 'Not allowed (you can try again)'; }) }));
    allow.appendChild(SOS.el('small', { text: 'Lets the helper read a Google Doc, OneDrive link, PDF, Word or PowerPoint file you ask the agent about. Only things you can already open.' }));
  });
  const site = SOS.el('div', { 'class': 'btns' });
  chrome.storage.local.get('needOrigin', (r) => { // a link on another site was refused: offer to allow just that site
    const o = r && r.needOrigin; if (!o || !/^https:\/\/[a-z0-9.-]+$/i.test(o)) return;
    site.appendChild(SOS.el('button', { 'class': 's', text: 'Allow this site: ' + o.replace('https://', ''), on: () => chrome.permissions.request({ origins: [o + '/*'] }, (ok) => { if (ok) chrome.storage.local.remove('needOrigin'); }) }));
  });
  const clean = SOS.el('div', { 'class': 'btns' });
  clean.appendChild(SOS.el('button', { 'class': 's', text: 'Clean up bad pages', on: () => { clean.textContent = 'Checking materials...'; chrome.runtime.sendMessage({ type: 'cleanupBad' }, (r) => { clean.textContent = r && r.ok ? 'Removed ' + (r.removed || 0) + ' bad page(s)' : (r && r.line) || 'Could not clean up'; }); } }));
  const reset = SOS.el('div', { 'class': 'btns' });
  const askReset = () => {
    reset.textContent = '';
    reset.appendChild(SOS.el('small', { 'class': 'err', text: 'Forget everything this helper stored?' }));
    reset.appendChild(SOS.el('button', { 'class': 's', text: 'Yes, reset', on: () => chrome.runtime.sendMessage({ type: 'resetHelper' }, () => { reset.textContent = 'Helper reset'; load(); }) }));
    reset.appendChild(SOS.el('button', { 'class': 't', text: 'Cancel', on: () => { reset.textContent = ''; reset.appendChild(SOS.el('button', { 'class': 't', text: 'Reset helper', on: askReset })); } }));
  };
  reset.appendChild(SOS.el('button', { 'class': 't', text: 'Reset helper', on: askReset }));
  bd.appendChild(section('Settings', [SOS.dailyView(s.daily, load), allow, site, clean, reset]));

  // ---- Advanced ----
  bd.appendChild(section('Advanced', [
    SOS.el('small', { text: 'Last fetch: ' + (s.lastFetch ? s.lastFetch.line + ' (' + Math.max(0, Math.round((Date.now() - s.lastFetch.t) / 1000)) + ' s ago)' : 'none yet') }),
    SOS.diagView(s),
  ]));
}

function load() { chrome.runtime.sendMessage({ type: 'state' }, render); }
load();
