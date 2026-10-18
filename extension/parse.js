// Pure parsers (no DOM, no network). Input is untrusted page text; output is plain data with caps.
// Loaded as a content script on Blackboard, via importScripts in the service worker, and by node for tests.
var SOSParse = (function () {
  var ID_RE = /\b(\d{6})-([A-Z]{2,5})-(\d{3,4}[A-Z]?)-([A-Z0-9]{1,6})\b/;
  var DUE_RE = /Due date:\s*(\d{1,2})\/(\d{1,2})\/(\d{2,4}),\s*(\d{1,2}):(\d{2})\s*(AM|PM)\s*\(([A-Za-z]{2,5})\)/;
  var MAX_DEADLINES = 500, MAX_TITLE = 200;

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  // "Due date: 10/19/26, 5:00 PM (CDT) ∙ 40541.202640: 202640-EN-210-010" preceded by a title line.
  function parseDeadlines(text) {
    var lines = String(text || '').split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
    var out = [], seen = {};
    for (var i = 0; i < lines.length && out.length < MAX_DEADLINES; i++) {
      var d = lines[i].match(DUE_RE);
      if (!d) continue;
      var idm = lines[i].match(ID_RE);
      if (!idm) continue;
      var title = i > 0 ? lines[i - 1] : '';
      if (/^- /.test(title) || DUE_RE.test(title)) title = ''; // a date heading or another deadline, not a title
      title = title.replace(/\s+/g, ' ').slice(0, MAX_TITLE);
      var h = parseInt(d[4], 10) % 12 + (d[6] === 'PM' ? 12 : 0);
      var yr = parseInt(d[3], 10); if (yr < 100) yr += 2000;
      var item = {
        title: title, dueDate: yr + '-' + pad(parseInt(d[1], 10)) + '-' + pad(parseInt(d[2], 10)),
        dueTime: pad(h) + ':' + d[5], tz: d[7].toUpperCase(), identifier: idm[0]
      };
      var key = item.identifier + '|' + item.dueDate + '|' + item.dueTime + '|' + item.title;
      if (seen[key]) continue;
      seen[key] = 1; out.push(item);
    }
    return out;
  }

  function splitIdentifier(identifier) {
    var m = String(identifier).match(ID_RE);
    return m ? { term: m[1], dept: m[2], num: m[3], section: m[4], code: m[2] + ' ' + m[3], identifier: m[0] } : null;
  }

  // courses: [{identifier, title?, instructor?}], deadlines: parseDeadlines output.
  // Keeps only the newest term and only classes that exist on the course list.
  function buildImport(courses, deadlines) {
    var list = [], terms = [];
    (courses || []).forEach(function (c) { var p = splitIdentifier(c.identifier); if (p) { list.push({ c: c, p: p }); terms.push(p.term); } });
    var newest = terms.reduce(function (a, t) { return t > a ? t : a; }, '000000');
    var byId = {}, classes = [];
    list.forEach(function (x) {
      if (x.p.term !== newest || byId[x.p.identifier]) return;
      var cls = { identifier: x.p.identifier, code: x.p.code, section: x.p.section, term: x.p.term, assignments: [] };
      if (x.c.title) cls.title = String(x.c.title).slice(0, 120);
      if (x.c.instructor) cls.instructor = String(x.c.instructor).slice(0, 80);
      byId[x.p.identifier] = cls; classes.push(cls);
    });
    (deadlines || []).forEach(function (d) {
      var cls = byId[d.identifier];
      if (cls) cls.assignments.push({ title: d.title, dueDate: d.dueDate, dueTime: d.dueTime, tz: d.tz });
    });
    return { source: 'blackboard', classes: classes };
  }

  // ---- Canvas (data comes from the student's own Canvas REST API, already parsed JSON; all of it untrusted) ----
  // The import endpoint only accepts source 'blackboard' today. Flip this to 'canvas' once the backend accepts it.
  var CANVAS_SOURCE = 'blackboard';

  // "MIS 430 001", "MIS430-001", "MIS-430", "Intro to X" (no code) -> {code, section}
  function parseCanvasCode(raw) {
    var s = String(raw || '').replace(/\s+/g, ' ').trim().slice(0, 40);
    var m = s.match(/^([A-Za-z]{2,6})[\s\-_.]*(\d{2,4}[A-Za-z]?)(?:[\s\-_.]+([A-Za-z0-9]{1,6}))?\b/);
    if (m) return { code: m[1].toUpperCase() + ' ' + m[2].toUpperCase(), section: (m[3] || '').toUpperCase() };
    return { code: s.toUpperCase().slice(0, 20), section: '' };
  }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  // ISO UTC instant -> {dueDate, dueTime, tz:'UTC'} or null
  function canvasDue(iso) {
    var d = new Date(String(iso || ''));
    if (isNaN(d.getTime())) return null;
    return { dueDate: d.getUTCFullYear() + '-' + pad2(d.getUTCMonth() + 1) + '-' + pad2(d.getUTCDate()), dueTime: pad2(d.getUTCHours()) + ':' + pad2(d.getUTCMinutes()), tz: 'UTC' };
  }

  // Keep the newest term only (by start_at; terms without dates count as oldest unless nothing has dates).
  function currentTermCourses(courses) {
    var list = (courses || []).filter(function (c) { return c && c.id != null && c.course_code; });
    var best = null, bestKey = null;
    list.forEach(function (c) {
      var t = c.term || {}, k = t.start_at ? Date.parse(t.start_at) : -1;
      if (bestKey === null || k > bestKey) { bestKey = k; best = String(t.id == null ? '' : t.id); }
    });
    return list.filter(function (c) { return String((c.term || {}).id == null ? '' : c.term.id) === best; });
  }

  // courses: /api/v1/courses JSON array; assignmentsByCourse: { "<id>": [assignment JSON] }
  function buildCanvasImport(courses, assignmentsByCourse) {
    var classes = [];
    currentTermCourses(courses).slice(0, 12).forEach(function (c) {
      var p = parseCanvasCode(c.course_code);
      var cls = { identifier: 'canvas:' + String(c.id).replace(/[^0-9]/g, '').slice(0, 20), code: p.code, assignments: [] };
      if (p.section) cls.section = p.section;
      if (c.name) cls.title = String(c.name).slice(0, 120);
      var t = (c.teachers || [])[0];
      if (t && t.display_name) cls.instructor = String(t.display_name).slice(0, 80);
      var seen = {};
      (assignmentsByCourse[String(c.id)] || []).slice(0, 400).forEach(function (a) {
        if (!a || !a.due_at || !a.name || cls.assignments.length >= 200) return;
        var w = canvasDue(a.due_at); if (!w) return;
        var title = String(a.name).replace(/\s+/g, ' ').trim().slice(0, MAX_TITLE);
        var key = title + '|' + w.dueDate; if (seen[key]) return; seen[key] = 1;
        cls.assignments.push({ title: title, dueDate: w.dueDate, dueTime: w.dueTime, tz: w.tz });
      });
      classes.push(cls);
    });
    return { source: CANVAS_SOURCE, classes: classes };
  }

  // Unique course identifiers in a block of text, in order. Readiness = this is non-empty (empty skeleton cards do not count).
  function idsInText(text) {
    var re = new RegExp(ID_RE.source, 'g'), out = [], seen = {}, m;
    var s = String(text || '');
    while ((m = re.exec(s)) && out.length < 80) { if (!seen[m[0]]) { seen[m[0]] = 1; out.push(m[0]); } }
    return out;
  }

  // ---- Content index (titles, types and links only; nothing from inside the items) ----
  var INDEX_MAX_BYTES = 60000;
  function hash36(str) { var h = 5381; for (var i = 0; i < str.length; i++) h = ((h * 33) ^ str.charCodeAt(i)) >>> 0; return h.toString(36); }
  function itemType(pathname) {
    var s = String(pathname || '');
    if (/\/file\//.test(s)) return 'file';
    if (/\/assessment\//.test(s)) return 'assessment';
    if (/\/discussion\//.test(s)) return 'discussion';
    if (/\/(edit\/)?document\//.test(s) || /\/outline\/.*document/.test(s)) return 'document';
    if (/\/(lti|link|weblink|url)\b/.test(s)) return 'link';
    return 'link';
  }
  // items: [{path:'Folder > Sub', title, type, href}] where href is a same-origin path. Cap ~60 KB.
  function buildIndexText(code, items, origin, maxBytes) {
    var cap = maxBytes || INDEX_MAX_BYTES;
    var lines = ['Blackboard content index for ' + code + ' (titles and links only: open a link in Blackboard to read the item)'];
    var size = lines[0].length;
    (items || []).forEach(function (it) {
      if (size >= cap) return;
      var line = (it.path ? it.path + ' > ' : '') + String(it.title || 'Untitled') + ' [' + it.type + '] <' + (/^https?:/.test(it.href) ? it.href : origin + it.href) + '>';
      size += line.length + 1;
      if (size <= cap) lines.push(line);
    });
    return lines.join('\n');
  }
  function indexFingerprint(items) { return hash36((items || []).length + '|' + (items || []).map(function (i) { return (i.path || '') + '/' + i.title + '/' + i.type; }).join('|')); }

  // Best syllabus candidate in an index: title first, then course outline/information/schedule, preferring files and documents
  // and shallow folders ("Schedule & Syllabus", "Course Information"). Returns the item or null (score under 60 is no candidate).
  function pickSyllabus(items) {
    var best = null, bestScore = 0;
    (items || []).forEach(function (it) {
      if (!it || it.type === 'assessment' || it.type === 'discussion') return;
      var title = String(it.title || ''), path = String(it.path || '');
      if (/^view\b/i.test(title)) return; // "View Discussion" and the like are never a syllabus
      if (it.type !== 'file' && it.type !== 'document' && it.type !== 'link') return;
      var score = 0;
      if (/syllab/i.test(title)) score = 100;
      else if (/course\s+(outline|information|info|schedule|overview)/i.test(title)) score = 60;
      else return;
      score += it.type === 'document' ? 14 : it.type === 'file' ? 10 : 0; // Ultra document first (it reads best), then files, then links
      if (/syllabus|course\s+information|course\s+info|schedule/i.test(path)) score += 20;
      score -= 5 * (path ? path.split(' > ').length : 0);
      if (score > bestScore) { bestScore = score; best = it; }
    });
    return bestScore >= 60 ? best : null;
  }
  // All plausible candidates, best first (the first-scan step tries them in turn until one reads).
  function rankSyllabus(items, limit) {
    var rest = (items || []).slice(), out = [];
    for (var i = 0; i < (limit || 3); i++) { var b = pickSyllabus(rest); if (!b) break; out.push(b); rest = rest.filter(function (x) { return x !== b; }); }
    return out;
  }

  // Text that is the SPA shell, a loading screen or the course menu instead of the item. Never upload such text.
  function looksJunk(text) {
    var s = String(text || '').replace(/\s+/g, ' ').trim();
    if (s.length < 300) return true;
    if (/javascript is required|enable javascript|you need to enable javascript|javascript must be enabled|this app works best with javascript|browser does not support/i.test(s)) return true;
    if (/^(loading|please wait)\b/i.test(s)) return true;
    var lines = String(text).split('\n').map(function (l) { return l.trim(); }).filter(Boolean);
    var short = lines.filter(function (l) { return l.length < 22; }).length;
    if (lines.length > 8 && short / lines.length > 0.7 && s.length < 900) return true; // mostly menu labels
    if (/\b(skip to main content|course content|calendar|discussions|gradebook|messages|books & tools)\b/i.test(s) && (s.match(/\b(calendar|discussions|gradebook|messages|books & tools|roster|attendance)\b/gi) || []).length >= 4 && s.length < 1200) return true;
    return false;
  }

  return { looksJunk: looksJunk, pickSyllabus: pickSyllabus, rankSyllabus: rankSyllabus, idsInText: idsInText, itemType: itemType, buildIndexText: buildIndexText, indexFingerprint: indexFingerprint, hash36: hash36, parseDeadlines: parseDeadlines, splitIdentifier: splitIdentifier, buildImport: buildImport, ID_RE: ID_RE,
           parseCanvasCode: parseCanvasCode, canvasDue: canvasDue, currentTermCourses: currentTermCourses, buildCanvasImport: buildCanvasImport };
})();
if (typeof module !== 'undefined') module.exports = SOSParse;
