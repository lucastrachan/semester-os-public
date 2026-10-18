// Canvas scan. Injected on demand into the ACTIVE tab (activeTab + scripting; no standing host access) after the student
// presses "Scan my classes". READ-ONLY: GET requests to this page's own /api/v1 using the student's existing session.
// No tokens are read or created. Never grades, submissions, messages or inbox. Everything returned is untrusted data.
(function () {
  if (window.__sosCanvasRunning) return;
  window.__sosCanvasRunning = true;
  var MAX_PAGES = 6, MAX_COURSES = 12, GAP_MS = 200;
  var send = function (m) { try { chrome.runtime.sendMessage(m); } catch (e) { /* ignore */ } };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };

  async function getJson(url) {
    var r = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json+canvas-string-ids, application/json' } });
    if (!r.ok) throw new Error('http ' + r.status);
    var t = (await r.text()).replace(/^while\(1\);/, ''); // Canvas prefixes JSON with this
    return { data: JSON.parse(t), link: r.headers.get('Link') || '' };
  }

  async function getAll(path) { // follows rel="next" on this origin only, hard-capped
    var url = path, out = [];
    for (var i = 0; i < MAX_PAGES && url; i++) {
      var r = await getJson(url);
      if (Array.isArray(r.data)) out = out.concat(r.data); else return r.data;
      var m = r.link.match(/<([^>]+)>;\s*rel="next"/);
      url = null;
      if (m) { try { var u = new URL(m[1], location.href); if (u.origin === location.origin && u.pathname.indexOf('/api/v1/') === 0) url = u.pathname + u.search; } catch (e) { /* stop */ } }
      await sleep(GAP_MS);
    }
    return out;
  }

  (async function () {
    try {
      var me;
      try { me = (await getJson('/api/v1/users/self/profile')).data; } catch (e) { me = null; }
      if (!me || me.id == null) return send({ type: 'canvasFail', reason: 'not-canvas' });
      send({ type: 'canvasProgress', phase: 'courses', n: 0 });
      var courses = await getAll('/api/v1/courses?enrollment_state=active&enrollment_type=student&include[]=term&include[]=teachers&per_page=50');
      var cur = SOSParse.currentTermCourses(Array.isArray(courses) ? courses : []).slice(0, MAX_COURSES);
      if (!cur.length) return send({ type: 'canvasFail', reason: 'none', msg: 'No current classes found in Canvas.' });
      send({ type: 'canvasProgress', phase: 'courses', n: cur.length });
      send({ type: 'canvasProgress', phase: 'calendar', n: cur.length });
      var byCourse = {};
      for (var i = 0; i < cur.length; i++) {
        try { byCourse[String(cur[i].id)] = await getAll('/api/v1/courses/' + encodeURIComponent(cur[i].id) + '/assignments?order_by=due_at&per_page=100'); }
        catch (e) { byCourse[String(cur[i].id)] = []; } // a class that hides assignments is still imported
        await sleep(GAP_MS);
      }
      var data = SOSParse.buildCanvasImport(cur, byCourse);
      send({ type: 'canvasData', data: data });
    } catch (e) {
      send({ type: 'canvasFail', reason: 'error', msg: 'Canvas scan stopped: ' + String(e && e.message || e).slice(0, 60) });
    } finally { window.__sosCanvasRunning = false; }
  })();
})();
