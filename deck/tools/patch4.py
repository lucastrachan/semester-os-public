import pathlib
here = pathlib.Path(__file__).parent
a = here / 'arch.py'
s = a.read_text(encoding='utf-8').replace('Checked {{{{NOW}}}}', 'Checked {{{{NOWT}}}}')
a.write_text(s, encoding='utf-8')
p = here / 'template.html'
t = p.read_text(encoding='utf-8')
i = t.index('<!-- 10 ARCHITECTURE -->')
j = t.index('<div class="diagram grow">', i)
k = t.index('</svg></div>', j) + len('</svg></div>')
t = t[:j] + '<div class="diagram grow" style="padding:14px 20px">{{ARCH}}</div>' + t[k:]
# footer with credit on slide 10
seg_start = i
f = '<div class="footer"><span>Semester OS</span><span>10</span></div>'
idx = t.index(f, seg_start)
t = t[:idx] + '<div class="footer" style="font-size:24px"><span>Semester OS &middot; Icons: AWS Architecture Icons, Simple Icons</span><span>10</span></div>' + t[idx + len(f):]
t = t.replace('.diagram img', '.diagram img')
p.write_text(t, encoding='utf-8')

b = (here / 'build.py').read_text(encoding='utf-8')
b = b.replace("import sys, datetime, segno", """import sys, datetime, segno, importlib.util
_sp = importlib.util.spec_from_file_location('arch', root / 'deck/tools/arch.py')
_arch = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(_arch)
t = t.replace('{{ARCH}}', _arch.build())""", 1)
b = b.replace("t = t.replace('{{NOW}}'", "t = t.replace('{{NOWT}}', datetime.datetime.now().strftime('%H:%M')).replace('{{NOW}}'", 1)
(here / 'build.py').write_text(b, encoding='utf-8')
r = here.parent / 'README.md'
r.write_text(r.read_text(encoding='utf-8') + '\nIcons: the architecture slide uses the official AWS Architecture Icons (aws.amazon.com/architecture/icons) and Simple Icons (CC0, simple-icons 13.15.0), copied to deck/assets/icons and inlined by deck/tools/arch.py at build time. Mistral, Z.ai GLM and Amazon Nova are text badges (no icon available). AWS icons are used to depict AWS services only.\n', encoding='utf-8')
