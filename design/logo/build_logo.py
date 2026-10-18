"""Generates the Semester OS logo SVGs (Designer). Run: python design/logo/build_logo.py
Mark = a rounded "window" tile (the OS idea) with title-bar dots and a bold S (Semester).
Brand colour is indigo #4F46E5 (white on it is 6.3:1); the tinted variants take any colour via currentColor.
Text in lockups is live <text> with a system font stack; PNG exports (see export_png.js) are rendered from it.
"""
import os

OUT = os.path.dirname(os.path.abspath(__file__))
BRAND = '#4F46E5'
BRAND_DEEP = '#3B33C9'
INK = '#12151C'
DARK_BG = '#0B0D11'

# The S: one stroked cubic path, round caps and joins. Coordinates are in the 128 x 128 mark space.
S_PATH = 'M83 60 C83 49 74 44 63 44 C52 44 44 50 44 58 C44 68 53 70 64 72 C75 74 84 78 84 88 C84 97 75 103 64 103 C53 103 45 98 43 88'
S_STROKE = 12
DOTS = [(31, 29, 1.0), (43, 29, 0.6), (55, 29, 0.35)]  # x, y, opacity (title-bar dots)

def mark_body(fill='#FFFFFF'):
    dots = ''.join(f'<circle cx="{x}" cy="{y}" r="4" fill="{fill}" opacity="{o}"/>' for x, y, o in DOTS)
    return f'{dots}<path d="{S_PATH}" fill="none" stroke="{fill}" stroke-width="{S_STROKE}" stroke-linecap="round" stroke-linejoin="round"/>'

def svg(w, h, vb, body, title, extra_attrs=''):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{w}" height="{h}" role="img" aria-label="{title}" {extra_attrs}>\n'
            f'  <title>{title}</title>\n{body}\n</svg>\n')

def write(name, content):
    with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
        f.write(content)

# ---- 1. Colour mark (brand) -----------------------------------------------------------------
grad = (f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BRAND}"/>'
        f'<stop offset="1" stop-color="{BRAND_DEEP}"/></linearGradient></defs>')
tile = f'<rect x="4" y="4" width="120" height="120" rx="30" fill="{BRAND}"/>'  # flat brand colour: compresses well and stays crisp at 16px
write('semester-os-mark.svg', svg(128, 128, '0 0 128 128', f'  {grad}\n  {tile}\n  {mark_body()}', 'Semester OS'))

# ---- 2. Tintable mark: tile follows currentColor (campus or class colour), glyph is white ------
write('semester-os-mark-tint.svg', svg(128, 128, '0 0 128 128',
      f'  <rect x="4" y="4" width="120" height="120" rx="30" fill="currentColor"/>\n  {mark_body()}', 'Semester OS', 'fill="none"'))

# ---- 3. Monochrome (single colour, glyph cut out of the tile). currentColor: set CSS color / RN color ----
def mono(fg):
    mask = (f'<defs><mask id="m" maskUnits="userSpaceOnUse" x="0" y="0" width="128" height="128">'
            f'<rect width="128" height="128" fill="#FFFFFF"/>{mark_body("#000000")}</mask></defs>')
    return f'  {mask}\n  <rect x="4" y="4" width="120" height="120" rx="30" fill="{fg}" mask="url(#m)"/>'
write('semester-os-mark-mono.svg', svg(128, 128, '0 0 128 128', mono('currentColor'), 'Semester OS'))
write('semester-os-mark-black.svg', svg(128, 128, '0 0 128 128', mono('#000000'), 'Semester OS'))
write('semester-os-mark-white.svg', svg(128, 128, '0 0 128 128', mono('#FFFFFF'), 'Semester OS'))

# ---- 4. Favicon (small sizes: a simpler, bolder glyph, no dots) ----------------------------------
fav_s = f'<path d="{S_PATH}" fill="none" stroke="#FFFFFF" stroke-width="15" stroke-linecap="round" stroke-linejoin="round"/>'
write('favicon.svg', svg(32, 32, '0 0 128 128', f'  <rect x="0" y="0" width="128" height="128" rx="32" fill="{BRAND}"/>\n  {fav_s}', 'Semester OS'))

# ---- 5. Maskable app icon: full-bleed square, glyph inside the 80% safe zone ---------------------------
mask_s = f'<g transform="translate(64 64) scale(0.78) translate(-64 -66)">{mark_body()}</g>'
write('app-icon-maskable.svg', svg(512, 512, '0 0 128 128', f'  {grad}\n  <rect width="128" height="128" fill="{BRAND}"/>\n  {mask_s}', 'Semester OS'))
write('app-icon-square.svg', svg(1024, 1024, '0 0 128 128', f'  <rect width="128" height="128" fill="{BRAND}"/>\n  {mark_body()}', 'Semester OS'))  # iOS: opaque square, the OS rounds it
write('app-icon.svg', svg(512, 512, '0 0 128 128', f'  {grad}\n  <rect width="128" height="128" rx="28" fill="{BRAND}"/>\n  {mark_body()}', 'Semester OS'))

# ---- 6. Lockups --------------------------------------------------------------------------------
FONT = "font-family=\"Inter, 'Segoe UI', system-ui, -apple-system, Roboto, sans-serif\""
MONO = "font-family=\"ui-monospace, 'JetBrains Mono', Menlo, Consolas, monospace\""

def lockup_h(text_fill, pill_fill, pill_text, bg=None):
    # mark 56px, then "Semester" + OS pill, on one line. viewBox 360 x 72.
    body = ''
    if bg:
        body += f'  <rect width="360" height="72" fill="{bg}"/>\n'
    body += (f'  {grad}\n  <g transform="translate(8 8) scale(0.4375)">{tile}{mark_body()}</g>\n'
             f'  <text x="76" y="47" {FONT} font-size="34" font-weight="800" letter-spacing="-1" fill="{text_fill}">Semester</text>\n'
             f'  <rect x="226" y="22" width="52" height="34" rx="9" fill="{pill_fill}"/>\n'
             f'  <text x="252" y="46" text-anchor="middle" {MONO} font-size="22" font-weight="700" letter-spacing="1" fill="{pill_text}">OS</text>')
    return svg(360, 72, '0 0 360 72', body, 'Semester OS')
write('semester-os-lockup.svg', lockup_h(INK, BRAND, '#FFFFFF'))
write('semester-os-lockup-on-dark.svg', lockup_h('#ECEEF3', '#847EED', '#10131A'))
def lockup_mono():
    # Single colour (currentColor): mark with the glyph cut out, wordmark, and an OS pill with the letters cut out.
    mask_m = (f'<mask id="m" maskUnits="userSpaceOnUse" x="0" y="0" width="128" height="128"><rect width="128" height="128" fill="#FFFFFF"/>{mark_body("#000000")}</mask>'
              f'<mask id="p" maskUnits="userSpaceOnUse" x="226" y="22" width="52" height="34"><rect x="226" y="22" width="52" height="34" fill="#FFFFFF"/>'
              f'<text x="252" y="46" text-anchor="middle" {MONO} font-size="22" font-weight="700" letter-spacing="1" fill="#000000">OS</text></mask>')
    body = (f'  <defs>{mask_m}</defs>\n'
            f'  <g transform="translate(8 8) scale(0.4375)"><rect x="4" y="4" width="120" height="120" rx="30" fill="currentColor" mask="url(#m)"/></g>\n'
            f'  <text x="76" y="47" {FONT} font-size="34" font-weight="800" letter-spacing="-1" fill="currentColor">Semester</text>\n'
            f'  <rect x="226" y="22" width="52" height="34" rx="9" fill="currentColor" mask="url(#p)"/>')
    return svg(360, 72, '0 0 360 72', body, 'Semester OS')
write('semester-os-lockup-mono.svg', lockup_mono())

def stacked(text_fill, pill_fill, pill_text):
    body = (f'  {grad}\n  <g transform="translate(100 8) scale(1.1)">{tile}{mark_body()}</g>\n'
            f'  <text x="170" y="196" text-anchor="middle" {FONT} font-size="46" font-weight="800" letter-spacing="-1.5" fill="{text_fill}">Semester</text>\n'
            f'  <rect x="138" y="208" width="64" height="40" rx="11" fill="{pill_fill}"/>\n'
            f'  <text x="170" y="237" text-anchor="middle" {MONO} font-size="26" font-weight="700" letter-spacing="1" fill="{pill_text}">OS</text>')
    return svg(340, 260, '0 0 340 260', body, 'Semester OS')
write('semester-os-stacked.svg', stacked(INK, BRAND, '#FFFFFF'))
write('semester-os-stacked-on-dark.svg', stacked('#ECEEF3', '#847EED', '#10131A'))

def lockup_inner(text_fill, pill_fill, pill_text):
    return (f'<g transform="translate(8 8) scale(0.4375)">{tile}{mark_body()}</g>'
            f'<text x="76" y="47" {FONT} font-size="34" font-weight="800" letter-spacing="-1" fill="{text_fill}">Semester</text>'
            f'<rect x="226" y="22" width="52" height="34" rx="9" fill="{pill_fill}"/>'
            f'<text x="252" y="46" text-anchor="middle" {MONO} font-size="22" font-weight="700" letter-spacing="1" fill="{pill_text}">OS</text>')

# ---- 7. Cover (slides / social): 1920 x 1080, dark, mark + wordmark + tagline + the five agent robots -----------
def robot_group(name, x, y, size, color):
    src = open(os.path.join(OUT, '..', 'robots', f'robot-{name}.svg'), encoding='utf-8').read()
    inner = src[src.index('</title>') + 8: src.rindex('</svg>')].strip()
    return f'<g transform="translate({x} {y}) scale({size / 96})" color="{color}" fill="none">{inner}</g>'

robots = ['chief-of-staff', 'class-tutor', 'class-tutor', 'class-tutor', 'class-tutor']  # agents v2: the general agent + one tutor per class
colors = ['#847EED', '#2FA399', '#DB7C10', '#E95878', '#28A57E']
rx0, rsize, gap = 1920 / 2 - (5 * 120 + 4 * 28) / 2, 120, 28
robot_svg = '\n  '.join(robot_group(n, rx0 + i * (rsize + gap), 800, rsize, colors[i]) for i, n in enumerate(robots))
cover = f'''  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BRAND}"/><stop offset="1" stop-color="{BRAND_DEEP}"/></linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0" r="0.8"><stop offset="0" stop-color="{BRAND}" stop-opacity="0.45"/><stop offset="1" stop-color="{BRAND}" stop-opacity="0"/></radialGradient>
  </defs>
  <rect width="1920" height="1080" fill="{DARK_BG}"/>
  <rect width="1920" height="1080" fill="url(#glow)"/>
  <g transform="translate(474 320) scale(3.4)">{lockup_inner('#ECEEF3', '#847EED', '#10131A')}</g>
  <text x="960" y="640" text-anchor="middle" {FONT} font-size="40" font-weight="500" fill="#98A0B0">Your college chief-of-staff</text>
  {robot_svg}'''
write('semester-os-cover.svg', svg(1920, 1080, '0 0 1920 1080', cover, 'Semester OS: your college chief-of-staff'))
print('logo files written to', OUT)
