def ink(hex_color: str) -> str:
    """Return #FFFFFF or #000000 based on luminance of hex_color."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        return "#000000" if lum > 128 else "#FFFFFF"
    except Exception:
        return "#FFFFFF"
