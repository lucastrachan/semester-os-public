// MAIN-world observer (read-only). Blackboard's own page asks its REST API for the course content tree; this script only LISTENS to
// those responses (same-origin /learn/api/v1/courses/<id>/contents/...) and posts a SANITISED subset to the extension:
// ids, titles, handler type, file name/mime/size and the permanent file address, external link addresses. No names, emails,
// grades, tokens, bodies or request headers ever leave this function. It never makes a request of its own.
(function () {
  if (window.__sosHook) return;
  window.__sosHook = true;
  var RE = /\/learn\/api\/v1\/courses\/(_\d+_1)\/contents\/(_\d+_1)\/children/;
  var CHAN = '__sosFeed';
  function clean(s, n) { return String(s == null ? '' : s).replace(/\s+/g, ' ').trim().slice(0, n); }
  function sanitise(course, parent, results) {
    var out = [];
    (Array.isArray(results) ? results : []).slice(0, 400).forEach(function (x) {
      if (!x || !/^_\d+_1$/.test(String(x.id || ''))) return;
      var h = clean(x.contentHandler, 60), it = { id: x.id, title: clean(x.title, 120), h: h };
      var d = x.contentDetail || {};
      var f = d['resource/x-bb-file'] && d['resource/x-bb-file'].file;
      if (f && /^\/bbcswebdav\/[\w\-\/.%]+$/.test(String(f.permanentUrl || ''))) it.file = { name: clean(f.fileName, 100), mime: clean(f.mimeType, 100), size: Number(f.fileSize) || 0, url: String(f.permanentUrl).slice(0, 200) };
      var l = d['resource/x-bb-externallink'] && d['resource/x-bb-externallink'].url;
      if (l && /^https:\/\/[^\s]{4,500}$/.test(String(l))) it.link = String(l).slice(0, 500);
      out.push(it);
    });
    return out;
  }
  function emit(course, parent, results) {
    try { var items = sanitise(course, parent, results); if (items.length) window.postMessage({ __sosFeed: 1, course: course, parent: parent, items: items }, location.origin); } catch (e) { /* never break the page */ }
  }
  var xo = XMLHttpRequest.prototype.open, xs = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { try { this.__sosU = String(u); } catch (e) { /* ignore */ } return xo.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () {
    try { this.addEventListener('load', function () { try { var m = RE.exec(this.__sosU || ''); if (m && this.status === 200) emit(m[1], m[2], JSON.parse(this.responseText).results); } catch (e) { /* ignore */ } }); } catch (e) { /* ignore */ }
    return xs.apply(this, arguments);
  };
  var of = window.fetch;
  if (of) window.fetch = function (i) {
    var u = ''; try { u = typeof i === 'string' ? i : (i && i.url) || ''; } catch (e) { /* ignore */ }
    var p = of.apply(this, arguments);
    try { var m = RE.exec(u); if (m) p.then(function (r) { return r.clone().json(); }).then(function (j) { emit(m[1], m[2], j.results); }).catch(function () { /* ignore */ }); } catch (e) { /* ignore */ }
    return p;
  };
})();
