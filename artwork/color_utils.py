"""Color helpers shared by models, views, and PDF rendering.

Kept free of model/Django imports so it can be imported anywhere without
creating circular-import problems.
"""
import re

_NUMBER_RE = re.compile(r'\d+(?:\.\d+)?')


def cmyk_to_hex(cmyk_str):
    """Convert a free-form CMYK string into an approximate ``#RRGGBB`` color.

    Parses the first four numbers found (interpreted as C, M, Y, K in the
    0–100 range), e.g. ``"100 0 0 0"`` or ``"C(100) M(0) Y(0) K(0)"``.
    Returns an empty string when fewer than four numbers are present.
    """
    if not cmyk_str:
        return ''
    numbers = _NUMBER_RE.findall(str(cmyk_str))
    if len(numbers) < 4:
        return ''
    try:
        c, m, y, k = (min(100.0, max(0.0, float(n))) / 100.0 for n in numbers[:4])
    except (TypeError, ValueError):
        return ''
    r = round(255 * (1 - c) * (1 - k))
    g = round(255 * (1 - m) * (1 - k))
    b = round(255 * (1 - y) * (1 - k))
    return '#{:02X}{:02X}{:02X}'.format(r, g, b)
