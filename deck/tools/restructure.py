import re, pathlib
here = pathlib.Path(__file__).parent
p = here / 'template.html'
t = p.read_text(encoding='utf-8')
start = t.index('<!-- 1 COVER -->')
end = t.index('</div></div>\n<div id="hud">')
head, body, tail = t[:start], t[start:end], t[end:]
parts = re.split(r'(?=<!-- \d+ [A-Z0-9 ]+ -->)', body)
parts = [x for x in parts if x.strip()]
S = {}
for x in parts:
    n = int(re.match(r'<!-- (\d+) ', x).group(1))
    S[n] = x.rstrip() + '\n\n'
assert sorted(S) == list(range(1, 14)), sorted(S)


def notes(n, text):
    S[n] = re.sub(r'<aside class="notes">.*?</aside>', lambda m: '<aside class="notes">' + text + '</aside>', S[n], flags=re.S)


notes(1, '''4-MINUTE SCRIPT (core slides 1-10, then Appendix for Q&A). Timer starts here.
0:00-0:15 Title.
Say: "I am Luca, solo. Semester OS: upload your syllabi, and the rest builds itself. Scan the code any time to try it."
Next: the problem.''')
notes(2, '''0:15-0:35 (20 s) Problem.
Say: "A student runs a semester across six tools, and when they need a book they browse a marketplace that has no idea what they need."
Next: the idea.''')
notes(3, '''0:35-1:00 (25 s) Innovation.
Say: "Every campus marketplace asks you to browse. Here the syllabus decides what you need: one agent per class, a calendar that updates itself, and books matched across campuses. The marketplace comes to you."
Next: demo.''')
notes(6, '''1:00-2:15 (75 s) LIVE DEMO. CLICK PATH: sign-up page, type a school email, page re-themes to the campus, sign in with the demo account, open the Study tab with a built class, Ctrl/Cmd+K, ask "what is due in MIS 430, and quiz me", banner "Switching you to your MIS 430 agent", app re-themes, show the tool chips.
Say: "No one set this school up. Ask the general agent about a class and it hands you over, with Undo."
FALLBACK: Wi-Fi or Bedrock fails: use the pre-built class and the backup recording.
Next: marketplace.''')
notes(7, '''2:15-2:35 (20 s) Cross-campus.
Say: "The book you need at another school shows up, always labelled with the campus. Books, tickets, tutors; in-app chat; no payments."
Show: Marketplace, class books. Photos and payments are roadmap; listings are demo data.
Next: criteria.''')
notes(11, '''2:35-3:10 (35 s) Criteria.
Say: "In the organisers' words: innovation, multi-tenant, campus-verified, cross-campus, actually works, then functionality, new-campus deploy, polish. Each row has one proof you can see: any .edu email creates its campus, about 250 are pre-seeded with verified colours, and an admin can create one in seconds."
Re-run the test count on demo day (510 at build time).
Next: architecture.''')
notes(10, '''3:10-3:30 (20 s) Architecture.
Say: "Serverless on AWS: CloudFront and S3, API Gateway with two JWT authorizers, Lambda, one DynamoDB table, and a four-model Bedrock chain so one model outage does not stop the app."
Green means live, amber dashed means in progress. RE-CHECK before presenting.
Next: security.''')
notes(9, '''3:30-3:45 (15 s) Security.
Say: "Verified students, a separate staff pool with TOTP, an audited admin console, and an AI that treats uploads as untrusted data with every tool call gated."
Next: real vs roadmap.''')
notes(12, '''3:45-3:55 (10 s) Real vs roadmap.
Say: "Green is live, amber is pending, grey is roadmap. Demo data is always labelled."
UPDATE this slide on demo day if more has deployed.
Next: close.''')
notes(13, '''3:55-4:00 (5 s) Close.
Say: "Scan, sign up with your .edu email, any US college works. Thank you."
Judges without a .edu address can ask for a demo login. Do NOT put credentials on any slide.
Appendix follows for Q&A.''')
for n in (4, 5, 8):
    notes(n, 'APPENDIX (Q&A only, not in the 4-minute pitch). Use if a judge asks about this topic.')
# labels
S[4] = S[4].replace('<span class="eyebrow">The agents</span>', '<span class="eyebrow">Appendix &middot; The agents</span>')
S[5] = S[5].replace('<span class="eyebrow">Live demo 1</span>', '<span class="eyebrow">Appendix &middot; Study hub</span>')
S[8] = S[8].replace('<span class="eyebrow">Any campus, instantly</span>', '<span class="eyebrow">Appendix &middot; Any campus, instantly</span>')
S[6] = S[6].replace('Live demo 2 &middot; the handoff', 'Live demo &middot; the handoff')
S[7] = S[7].replace('Marketplace &middot; the track', 'Live demo &middot; marketplace')
# criteria slide
i = S[11].index('<table')
j = S[11].index('</table>') + 8
S[11] = S[11][:i] + '''<table class="map tight" style="font-size:30px;flex:none"><thead><tr><th>Criterion</th><th>Our proof</th></tr></thead><tbody>
   <tr><td>Innovation</td><td>Need-first marketplace: the syllabus decides what you need</td></tr>
   <tr><td>Multi-tenant</td><td>One deployment serves every school; campus comes from the verified email</td></tr>
   <tr><td>Campus-verified</td><td>.edu email code for students; staff pool with TOTP</td></tr>
   <tr><td>Cross-campus</td><td>Book matches and listings across schools, labelled by campus</td></tr>
   <tr><td>Actually works</td><td>Live on AWS; {{TESTS}} backend tests pass</td></tr>
   <tr style="border-top:4px solid var(--accent)"><td>Functionality</td><td>Agent per class, handoff, calendar feed, marketplace chat</td></tr>
   <tr><td>New-campus deploy</td><td>Any .edu email creates its campus; {{COLORS}} pre-seeded colours; admin creates one in seconds</td></tr>
   <tr><td>Polish</td><td>AA-contrast themes, dark and light, class colours</td></tr>
  </tbody></table>''' + S[11][j:]
S[11] = S[11].replace('table.map.tight', 'table.map.tight')
S[11] = S[11].replace('<h1 class="title" style="font-size:72px">How we meet each one</h1>', '<h1 class="title" style="font-size:72px">How we meet each criterion</h1>')
# appendix divider
DIV = '''<!-- 14 APPENDIX -->
<section class="slide" style="justify-content:center;gap:28px">
  <span class="eyebrow">Appendix</span><h1 class="title title--xl">Details for Q&amp;A</h1>
  <p class="subtitle">The agents, the Study hub, and how any campus is created. Not part of the 4-minute pitch.</p>
  <div class="footer"><span>Semester OS</span><span>00</span></div>
  <aside class="notes">APPENDIX divider. The 4-minute pitch ended on the previous slide.</aside>
</section>

'''
order = [1, 2, 3, 6, 7, 11, 10, 9, 12, 13]
new = ''.join(S[n] for n in order) + DIV + ''.join(S[n] for n in (4, 5, 8))
p.write_text(head + new + tail, encoding='utf-8')
