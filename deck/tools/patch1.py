import re, pathlib
here = pathlib.Path(__file__).parent
(here / 'flags.json').write_text('{"import_live": false}\n')
p = here / 'template.html'
t = p.read_text(encoding='utf-8')


def rep(a, b):
    global t
    assert a in t, a
    t = t.replace(a, b)


# 1 slide 9
rep('<section class="slide" data-theme="c3">', '<section class="slide">')
rep('.tabs span.on{', '.tabs.slate span.on{background:#3B4252;color:#ECEEF3;border-color:#3B4252}.tabs span.on{')
rep('<div class="tabs"><span>Campuses</span>', '<div class="tabs slate"><span>Campuses</span>')
rep('<span class="btn">Approve</span>', '<span class="btn" style="border-color:#98A0B0;color:#ECEEF3">Approve</span>')
# 5, 4 label sizes
rep('.demo-tag{font:600 20px', '.demo-tag{font:600 24px')
rep('.st{display:inline-block;font:700 22px', '.st{display:inline-block;font:700 26px')
# 2 slide 10
i = t.index('<g font-size="23"')
j = t.index('</svg>', i)
t = t[:i] + '''<g font-size="23" fill="#12151C" font-weight="500">
    <text x="10" y="450">Bedrock chain: GLM-5, gpt-oss-120b, Mistral Large 3,</text>
    <text x="10" y="480">Claude Sonnet 4.6; Nova Lite for fast tasks</text>
    <text x="10" y="525">Two JWT authorizers: student and staff (TOTP)</text>
    <text x="10" y="555">One DynamoDB table, campus-scoped keys</text>
    <g font-weight="700"><rect x="10" y="596" width="26" height="26" rx="6" fill="#DDF5E7" stroke="#067647" stroke-width="3"/><text x="48" y="618">Live, checked {{NOW}}</text><rect x="560" y="596" width="26" height="26" rx="6" fill="#FFF3D6" stroke="#8A5A00" stroke-width="3"/><text x="598" y="618">Pending: marketplace v2, Blackboard auto-import</text></g>
   </g>
  ''' + t[j:]
rep('<g fill="#FFF3D6" stroke="#8A5A00" stroke-width="3"><rect x="1320" y="170"', '<g fill="#DDF5E7" stroke="#067647" stroke-width="3"><rect x="1320" y="170"')
rep('Green means seen deployed, yellow means coded and waiting. RE-CHECK the colours on demo day before presenting.', 'Green means deployed, yellow means pending. RE-CHECK before presenting.')
# 3 table
i = t.index('<table class="map tight"')
j = t.index('</table>', i) + 8
t = t[:i] + '''<table class="map tight" style="font-size:30px;flex:none"><thead><tr><th>Criterion</th><th>What we built</th><th>See it</th></tr></thead><tbody>
   <tr><td>Multi-tenant</td><td>One deployment, every school</td><td>Sign-up</td></tr>
   <tr><td>Campus-verified</td><td>.edu email code; staff pool with TOTP</td><td>Admin</td></tr>
   <tr><td>Cross-campus</td><td>Listings and books across schools</td><td>Market</td></tr>
   <tr><td>Customisation</td><td>Per-campus colours, categories, ticket cap</td><td>Theme</td></tr>
   <tr><td>Actually works</td><td>Real AWS and Bedrock; {{TESTS}} tests pass</td><td>Demo</td></tr>
   <tr><td>New-campus deploy</td><td>Any .edu creates a campus; {{COLORS}} verified colours</td><td>Sign-up</td></tr>
   <tr><td>Security + polish</td><td>Gated tools, SSRF-safe fetch, audit log, AA themes</td><td>Slide 9</td></tr>
  </tbody></table>''' + t[j:]
rep('table.map.tight td{padding:11px 20px}table.map.tight td:first-child{width:26%}', 'table.map.tight td{padding:16px 20px}table.map.tight td:first-child{width:28%}table.map.tight td:last-child{width:14%}')
# 4 slide 12
i = t.index('<div class="cols-3 grow" style="align-items:stretch">\n   <div class="card"><span class="st live">')
j = t.index('<p class="caption">Screens in this deck', i)
t = t[:i] + '''<div class="cols-3 grow" style="align-items:stretch">
   <div class="card"><span class="st live">LIVE</span><h3 style="margin-top:16px">Checked {{NOW}}</h3><p>Sites, API with student and staff auth, syllabus processing, any-.edu campus creation, colour worker and admin review, Blackboard sync, listing chat, class memory and materials.</p></div>
   <div class="card"><span class="st code">PENDING</span><h3 style="margin-top:16px">Coded, deploy pending</h3><p>Marketplace v2 redesign, For-you and tutors routes, Blackboard auto-import.</p></div>
   <div class="card"><span class="st plan">ROADMAP</span><h3 style="margin-top:16px">Not built</h3><p>Canvas scan, browser extension, listing photos, payments, more countries.</p></div>
  </div>
  ''' + t[j:]
rep('UPDATE this slide on demo day if more has deployed since 13:2x.', 'UPDATE this slide on demo day if more has deployed.')
rep('were coded but not deployed at 13:2x.', 'were reported deployed at 13:45.')
# 6 slide 7
k = t.index('<!-- 7 MARKETPLACE')
i = t.index('<div class="main">', k)
j = t.index('</div></div></div>', t.index('No payments in the app', k))
t = t[:i] + '''<div class="main">
     <div class="row" style="gap:16px"><div style="flex:1;padding:18px 26px;border-radius:16px;background:var(--surface);border:2px solid var(--border);font-size:30px;color:var(--muted)">Search books, tickets, tutors, anything</div><span class="btn" style="margin:0">Filters</span><span class="btn" style="margin:0;background:var(--accent);color:var(--accent-ink);border-color:var(--accent)">Sell or post something</span></div>
     <div class="tabs"><span class="on">All</span><span>Books</span><span>Tickets</span><span>Tutors</span><span>Supplies</span><span>Dorm</span><span>More</span></div>
     <div class="mk">
      <div class="mc"><span class="badge" style="align-self:flex-start">Your class: MIS 430</span><h5>Systems Analysis, 11th ed.</h5><span class="pr" style="font-size:54px">$45</span><p class="sub">Demo University &middot; Good</p></div>
      <div class="mc"><span class="badge" style="align-self:flex-start">Other campus</span><h5>Systems Analysis, 11th ed.</h5><span class="pr" style="font-size:54px">$38</span><p class="sub">Other campus &middot; Like new</p></div>
      <div class="mc"><span class="badge" style="align-self:flex-start">Tutor</span><h5>MIS 430 tutor</h5><span class="pr" style="font-size:54px">$20/h</span><p class="sub">Demo University &middot; In person</p></div>
     </div>
     <p class="sub" style="margin-top:auto">Demo listings. No payments in the app; meet at a campus pickup spot. Ticket resale capped at face value by default.</p>
    ''' + t[j:]
# flagged copy
rep('Upload your syllabi. Get an AI agent', '[[BB:Upload your syllabi|Connect Blackboard]]. Get an AI agent')
rep('<li style="font-size:36px">Drop the syllabi, once</li>', '<li style="font-size:36px">[[BB:Drop the syllabi, once|Connect Blackboard once]]</li>')
rep('<div class="node">Syllabus<small>you upload it</small></div>', '<div class="node">[[BB:Syllabus|Blackboard]]<small>[[BB:you upload it|connect and import your classes]]</small></div>')
rep('Sign up, drop a syllabus, the agent builds itself', '[[BB:Sign up, drop a syllabus, the agent builds itself|Sign up, connect Blackboard, your classes build themselves]]')
rep('Drop a syllabus PDF here to add a class', '[[BB:Drop a syllabus PDF here to add a class|Connect Blackboard to import your classes]]')
rep('<span class="btn">Upload</span>', '<span class="btn">[[BB:Upload|Connect]]</span>')
p.write_text(t, encoding='utf-8')

b = (here / 'build.py').read_text(encoding='utf-8')
b = b.replace("(root / 'deck/index.html').write_text", """import sys, datetime
live = ('--import-live' in sys.argv) or json.load(open(root / 'deck/tools/flags.json')).get('import_live', False)
t = re.sub(r'\\[\\[BB:(.*?)\\|(.*?)\\]\\]', lambda m: m.group(2) if live else m.group(1), t, flags=re.S)
t = t.replace('{{NOW}}', datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
(root / 'deck/index.html').write_text""")
(here / 'build.py').write_text(b, encoding='utf-8')
