import pathlib
here = pathlib.Path(__file__).parent
p = here / 'template.html'
t = p.read_text(encoding='utf-8')
# slide 1: small QR bottom right
a = '<div class="footer"><span>HackBama_01'
assert a in t
t = t.replace(a, '<div style="position:absolute;right:120px;bottom:84px;text-align:center;background:#fff;padding:0;border-radius:14px;width:180px;overflow:hidden">{{QR:180}}</div>\n  ' + a, 1)
# slide 13 rewrite
i = t.index('<!-- 13 CLOSE -->')
j = t.index('</section>', i) + len('</section>')
new = '''<!-- 13 CLOSE -->
<section class="slide" style="justify-content:center">
  <div class="row" style="gap:110px;align-items:center;justify-content:center">
   <div style="display:flex;flex-direction:column;gap:36px;max-width:1000px">
    <img src="assets/logo/semester-os-mark.svg" style="height:150px;align-self:flex-start" alt="">
    <h1 class="title title--xl">Try it now</h1>
    <p class="subtitle">Sign up with your school email (.edu). Any US college works.</p>
    <div class="row" style="flex-wrap:wrap;gap:16px"><span class="pill pill--solid">Live demo</span><span class="pill">Canvas connect</span><span class="pill">Browser helper (prototype)</span><span class="pill">Listing photos</span></div>
    <p class="caption">Next (roadmap): Canvas connect, guided browser extension (prototype), listing photos. Thank you, team luca.</p>
   </div>
   <div style="text-align:center;flex:none">
    <div style="background:#fff;border-radius:24px;width:480px;height:480px;overflow:hidden">{{QR:480}}</div>
    <p class="body" style="margin-top:20px;font-weight:700">Try it now</p>
    <p class="caption mono"><deployed-host-1></p>
   </div>
  </div>
  <div class="footer"><span>Thank you</span><span>13</span></div>
  <aside class="notes">Time 0:15 (running about 8:00). Say: "Scan the code, sign up with your .edu email, and any US college works. Semester OS: add your syllabi and the rest builds itself. Questions?"
Judges without a .edu address can ask for a demo login. Do NOT put credentials on any slide.</aside>
</section>'''
t = t[:i] + new + t[j:]
p.write_text(t, encoding='utf-8')

b = (here / 'build.py').read_text(encoding='utf-8')
b = b.replace("import sys, datetime", """import sys, datetime, segno
def qr(m):
    px = m.group(1)
    s = segno.make('https://<deployed-host-1>', error='m').svg_inline(border=4, dark='#000000', light='#ffffff', omitsize=True)
    return s.replace('<svg ', f'<svg width="{px}" height="{px}" shape-rendering="crispEdges" role="img" aria-label="QR code: https://<deployed-host-1>" ', 1)
t = re.sub(r'\\{\\{QR:(\\d+)\\}\\}', qr, t)""", 1)
(here / 'build.py').write_text(b, encoding='utf-8')
