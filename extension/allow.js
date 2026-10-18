// One-time question before the first scan: allow reading files (PDF, Word, PowerPoint) you can already open in Blackboard?
// Asking needs a click on an extension page; the scan starts right after the answer, allowed or not.
SOS.applyCss(document);
const FILE_ORIGINS = ['https://*.blackboard.com/*', 'https://*.blackboardcdn.com/*', 'https://*.amazonaws.com/*', 'https://docs.google.com/*', 'https://drive.google.com/*', 'https://*.googleusercontent.com/*', 'https://onedrive.live.com/*', 'https://1drv.ms/*', 'https://*.sharepoint.com/*', 'https://*.officeapps.live.com/*'];
const tabId = Number(new URLSearchParams(location.search).get('tab')) || null;
const box = SOS.el('div', { 'class': 'b' });
document.getElementById('app').appendChild(box);
box.appendChild(SOS.header(''));
const bd = SOS.el('div', { 'class': 'bd' });
box.appendChild(bd);
bd.appendChild(SOS.el('p', { 'class': 'lead', text: 'Let the helper read your class links and files?' }));
bd.appendChild(SOS.el('p', { 'class': 'note', text: 'So it can fetch each class syllabus and any Google Doc, OneDrive link, PDF, Word or PowerPoint file you ask the agent about. Only things you can already open. You can say no and still scan.' }));
const go = (allow) => {
  chrome.storage.local.set({ fileAsk: true }, () => {
    const start = () => chrome.runtime.sendMessage({ type: 'scan', tabId }, () => window.close());
    if (allow) chrome.permissions.request({ origins: FILE_ORIGINS }, () => start()); else start();
  });
};
bd.appendChild(SOS.el('div', { 'class': 'btns' }, [
  SOS.el('button', { 'class': 'pri', text: 'Allow links and files, then scan', on: () => go(true) }),
  SOS.el('button', { 'class': 't', text: 'Scan without files', on: () => go(false) })
]));
