"""Generates the slide-10 architecture SVG with official AWS Architecture Icons and Simple Icons, all inline."""
import re, pathlib

ICONS = pathlib.Path(__file__).resolve().parents[1] / 'assets' / 'icons'
SI_COLORS = {'react': '#087EA4', 'vite': '#646CFF', 'typescript': '#3178C6', 'expo': '#000020',
             'openai': '#412991', 'anthropic': '#D97757', 'python': '#3776AB'}
FS = 25
INK = '#12151C'
LINE = '#586071'
GREEN = '#067647'
AMBER = '#8A5A00'


def icon(kind, name, x, y, size):
    s = (ICONS / f'{kind}-{name}.svg').read_text(encoding='utf-8')
    s = re.sub(r'<\?xml[^>]*\?>', '', s)
    s = re.sub(r'<title>.*?</title>', '', s, flags=re.S)
    s = re.sub(r'\sid="[^"]*"', '', s)
    if kind == 'aws':
        head = f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="0 0 80 80">'
    else:
        head = f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="{SI_COLORS[name]}">'
    s = re.sub(r'<svg[^>]*>', head, s, count=1)
    return s


def node(x, y, w, h, icons, l1, l2, live=True, isize=56):
    stroke = GREEN if live else AMBER
    dash = '' if live else ' stroke-dasharray="10 6"'
    o = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="#fff" stroke="{stroke}" stroke-width="3"{dash}/>'
    n = len(icons)
    gap = 14
    tot = n * isize + (n - 1) * gap
    ix = x + (w - tot) / 2
    for k, (kind, name) in enumerate(icons):
        o += icon(kind, name, round(ix + k * (isize + gap), 1), y + 12, isize)
    cx = x + w / 2
    o += f'<text x="{cx}" y="{y + 70 + 28}" text-anchor="middle" font-size="{FS}" font-weight="700" fill="{INK}">{l1}</text>'
    if l2:
        o += f'<text x="{cx}" y="{y + 70 + 28 + 28}" text-anchor="middle" font-size="{FS}" fill="#3d4556">{l2}</text>'
    return o


def arrow(d, label=None, lx=0, ly=0):
    o = f'<path d="{d}" stroke="{LINE}" stroke-width="3" fill="none" marker-end="url(#ar)"/>'
    if label:
        o += f'<text x="{lx}" y="{ly}" text-anchor="middle" font-size="{FS}" font-weight="600" fill="{LINE}">{label}</text>'
    return o


def badge(x, y, text, color):
    return (f'<rect x="{x}" y="{y}" width="40" height="40" rx="10" fill="{color}"/>'
            f'<text x="{x + 20}" y="{y + 29}" text-anchor="middle" font-size="24" font-weight="800" fill="#fff">{text}</text>')


def build():
    A, B, C, D, E = 0, 335, 670, 1005, 1340
    W = 230
    R = [0, 170, 340, 510]
    H = 140
    o = ['<svg viewBox="0 0 1640 660" width="1640" height="660" font-family="Segoe UI, Inter, system-ui, sans-serif" role="img" aria-label="Semester OS architecture on AWS">',
         '<defs><marker id="ar" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0 0L10 5L0 10z" fill="#586071"/></marker></defs>']
    # arrows first (under nodes)
    o.append(arrow(f'M{A+W} 70 L{B} 70', 'HTTPS', 282, 56))
    o.append(arrow(f'M{A+W} 240 L{B} 240', 'JWT', 282, 226))
    o.append(arrow(f'M{A+W} 410 L{B} 410', 'JWT', 282, 396))
    o.append(arrow(f'M{B+W} 240 L{C} 240', 'invoke', 617, 226))
    o.append(arrow(f'M{D} 70 L{C+W} 70', 'event', 952, 56))
    o.append(arrow(f'M{C+W} 105 L952 105 L952 195 L{D} 195'))
    o.append(arrow(f'M{C+W} 250 L{D} 250', 'R/W', 952, 238))
    o.append(arrow(f'M{C+W} 410 L952 410 L952 295 L{D} 295'))
    o.append(arrow(f'M{C+W} 580 L952 580 L952 450 L{D} 450'))
    o.append(arrow(f'M{B+W} 580 L{C} 580', 'cron', 617, 566))
    o.append(arrow(f'M785 170 L785 155 L1287 155 L{E} 155'))
    o.append(f'<text x="1287" y="195" text-anchor="middle" font-size="{FS}" font-weight="600" fill="{LINE}">invoke</text>')
    # clients
    o.append(node(A, R[0], W, H, [('si', 'react'), ('si', 'vite'), ('si', 'typescript')], 'Student web app', 'React + Vite + TS', isize=48))
    o.append(node(A, R[1], W, H, [], 'Browser helper', 'Chrome extension'))
    o.append(badge(A + W / 2 - 20, R[1] + 24, 'S', '#4F46E5'))
    o.append(node(A, R[2], W, H, [('si', 'react')], 'Admin console', 'Staff site, TOTP'))
    # edge + api
    o.append(node(B, R[0], W, H, [('aws', 'cloudfront'), ('aws', 's3')], 'Edge + hosting', 'CloudFront, S3'))
    o.append(f'<rect x="{B}" y="{R[1]}" width="{W}" height="310" rx="16" fill="#fff" stroke="{GREEN}" stroke-width="3"/>')
    o.append(icon('aws', 'apigw', B + (W - 56) / 2, R[1] + 12, 56))
    o.append(f'<text x="{B+W/2}" y="{R[1]+98}" text-anchor="middle" font-size="{FS}" font-weight="700" fill="{INK}">API Gateway</text>')
    o.append(f'<text x="{B+W/2}" y="{R[1]+126}" text-anchor="middle" font-size="{FS}" fill="#3d4556">2 authorizers</text>')
    o.append(icon('aws', 'cognito', B + 10, R[1] + 150, 52))
    o.append(f'<text x="{B+68}" y="{R[1]+183}" font-size="{FS}" font-weight="600" fill="{INK}">Student pool</text>')
    o.append(icon('aws', 'cognito', B + 10, R[1] + 226, 52))
    o.append(f'<text x="{B+68}" y="{R[1]+252}" font-size="{FS}" font-weight="600" fill="{INK}">Staff pool</text>')
    o.append(f'<text x="{B+68}" y="{R[1]+280}" font-size="{FS}" fill="#3d4556">+ TOTP</text>')
    o.append(node(B, R[3], W, H, [('aws', 'eventbridge')], 'EventBridge', 'Scheduled sync'))
    # compute
    o.append(node(C, R[0], W, H, [('aws', 'lambda')], 'Syllabus worker', 'Reads uploads'))
    o.append(node(C, R[1], W, H, [('aws', 'lambda'), ('si', 'python')], 'API + agents', 'Python Lambda', isize=56))
    o.append(node(C, R[2], W, H, [('aws', 'lambda')], 'Colour finder', 'Worker Lambda'))
    o.append(node(C, R[3], W, H, [('aws', 'lambda')], 'Blackboard sync', 'Worker Lambda'))
    # data
    o.append(node(D, R[0], W, H, [('aws', 's3')], 'Syllabus uploads', 'Private bucket'))
    o.append(node(D, R[1], W, H, [('aws', 'dynamodb')], 'Single-table DB', 'Campus keys'))
    o.append(node(D, R[2], W, H, [('aws', 'kms')], 'KMS keys', 'Encrypt secrets'))
    o.append(node(D, R[3], W, H, [('aws', 'cloudwatch')], 'CloudWatch', 'Redacted logs'))
    # bedrock
    o.append(f'<rect x="{E}" y="0" width="300" height="500" rx="16" fill="#fff" stroke="{GREEN}" stroke-width="3"/>')
    o.append(icon('aws', 'bedrock', E + 122, 12, 56))
    o.append(f'<text x="{E+150}" y="98" text-anchor="middle" font-size="{FS}" font-weight="700" fill="{INK}">Bedrock model chain</text>')
    o.append(f'<text x="{E+150}" y="126" text-anchor="middle" font-size="{FS}" fill="#3d4556">falls back top to bottom</text>')
    rows = [('badge', 'Z', '#2D2D2D', 'GLM-5'), ('si', 'openai', None, 'gpt-oss-120b'), ('badge', 'M', '#FA520F', 'Mistral Large 3'),
            ('si', 'anthropic', None, 'Claude Sonnet 4.6'), ('badge', 'N', '#C77700', 'Nova Lite (fast)')]
    for k, (t, a, col, label) in enumerate(rows):
        y = 150 + k * 68
        if t == 'badge':
            o.append(badge(E + 20, y, a, col))
        else:
            o.append(icon('si', a, E + 20, y, 40))
        o.append(f'<text x="{E+74}" y="{y+29}" font-size="{FS}" font-weight="600" fill="{INK}">{label}</text>')
    # checked-at stamp (no legend: everything shown is live)
    o.append(f'<text x="{E+20}" y="640" font-size="{FS}" fill="#3d4556">Checked {{{{NOWT}}}}</text>')
    o.append('</svg>')
    return ''.join(o)
