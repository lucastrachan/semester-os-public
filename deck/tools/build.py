import re, json, pathlib
root = pathlib.Path(__file__).resolve().parents[2]
t = (root / 'deck/tools/template.html').read_text(encoding='utf-8')


def robot(m):
    name, color, px = m.group(1), m.group(2), m.group(3)
    s = (root / f'deck/assets/robots/robot-{name}.svg').read_text(encoding='utf-8')
    s = re.sub(r'width="96" height="96"', f'width="{px}" height="{px}"', s, 1)
    return s.replace('<svg ', f'<svg style="color:{color}" ', 1)


t = re.sub(r'\{\{R:([a-z-]+):([^:]+):(\d+)\}\}', robot, t)
colors = len(json.load(open(root / 'backend/data/school_colors.json')))
schools = len(json.load(open(root / 'backend/data/us_schools.json')))
t = t.replace('{{COLORS}}', str(colors)).replace('{{SCHOOLS}}', f'{schools:,}').replace('{{TESTS}}', '510')
import sys, datetime, segno, importlib.util
_sp = importlib.util.spec_from_file_location('arch', root / 'deck/tools/arch.py')
_arch = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(_arch)
t = t.replace('{{ARCH}}', _arch.build())
def qr(m):
    px = m.group(1)
    s = segno.make('https://<deployed-host-1>', error='m').svg_inline(border=4, dark='#000000', light='#ffffff', omitsize=True)
    return s.replace('<svg ', f'<svg width="{px}" height="{px}" shape-rendering="crispEdges" role="img" aria-label="QR code: https://<deployed-host-1>" ', 1)
t = re.sub(r'\{\{QR:(\d+)\}\}', qr, t)
live = ('--import-live' in sys.argv) or json.load(open(root / 'deck/tools/flags.json')).get('import_live', False)
t = re.sub(r'\[\[BB:(.*?)\|(.*?)\]\]', lambda m: m.group(2) if live else m.group(1), t, flags=re.S)
t = t.replace('{{NOWT}}', datetime.datetime.now().strftime('%H:%M')).replace('{{NOW}}', datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
_secs = t.split('<section class="slide')
t = _secs[0] + ''.join('<section class="slide' + re.sub(r'<span>\d\d</span></div>', '<span>%02d</span></div>' % k, s) for k, s in enumerate(_secs[1:], 1))
(root / 'deck/index.html').write_text(t, encoding='utf-8')
print(colors, schools)
