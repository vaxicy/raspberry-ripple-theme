"""Raspberry Ripple Theme - logo generator.

Two modes:

    python3 scripts/generate-logo.py candidates          # exploration sheet
    python3 scripts/generate-logo.py final [slug] [colorway]

`candidates` draws every flat-vector concept in two colorways (pale card +
berry card) at 8x supersampling, writes 512px previews plus a 1280x800 contact
sheet into store-assets/icon-candidates/.

`final` renders the chosen concept on the chosen card and writes the single
128px icon a Chrome theme needs: logo/logo.png.

Every colour is read from manifest.json (theme.colors) so the mark can never
drift away from the theme it belongs to.
"""

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

SS = 8                      # supersample factor
SIZE = 128                  # Chrome themes only need one icon size: 128
S = SIZE * SS
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "store-assets" / "icon-candidates"
CARD_RADIUS = 0.22          # corner radius as a fraction of the icon size


# --- palette (single source of truth: manifest.json) -------------------------
def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def load_palette():
    data = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    cols = {k: tuple(v) for k, v in data["theme"]["colors"].items()}

    frame = cols["frame"]                  # D790BB main raspberry pink
    incog = cols["frame_incognito"]        # CF7AAD deeper pink
    plum = cols["tab_text"]                # 512740 dark plum
    midplum = cols["ntp_link"]             # 794463 mid plum
    toolbar = cols["toolbar"]              # F6F0F4 pale pink
    soft = cols["background_tab"]          # EDD7E7 soft pink
    ntp = cols["ntp_background"]           # FCF8FB near white
    white = cols["omnibox_background"]     # FFFFFF

    mark = mix(incog, plum, 0.30)          # deep raspberry, ~3.9:1 on the pale card

    colorways = {
        "light": {"card": toolbar, "mark": mark, "soft": mix(mark, toolbar, 0.45),
                  "accent": plum, "hilite": incog},
        "berry": {"card": frame, "mark": ntp, "soft": mix(ntp, frame, 0.55),
                  "accent": plum, "hilite": white},
    }
    ui = {"frame": frame, "incog": incog, "plum": plum, "midplum": midplum,
          "toolbar": toolbar, "soft": soft, "ntp": ntp, "white": white}
    return colorways, ui


# --- mask helpers ------------------------------------------------------------
def _blank():
    return Image.new("L", (S, S), 0)


def m_circle(cx, cy, r):
    m = _blank()
    ImageDraw.Draw(m).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    return m


def m_capsule(p0, p1, width):
    """Straight line with rounded ends (no sharp corners)."""
    m = _blank()
    d = ImageDraw.Draw(m)
    d.line([p0, p1], fill=255, width=int(round(width)))
    r = width / 2
    for x, y in (p0, p1):
        d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    return m


def m_ellipse(cx, cy, rx, ry, angle=0.0):
    m = _blank()
    ImageDraw.Draw(m).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
    if angle:
        m = m.rotate(angle, resample=Image.BICUBIC, center=(cx, cy))
    return m


def m_lens(cx, cy, hw, hh, angle=0.0):
    """Pointed oval (long axis vertical) = intersection of two circles."""
    d = (hh * hh - hw * hw) / (2 * hw)
    r = hw + d
    m = ImageChops.darker(m_circle(cx - d, cy, r), m_circle(cx + d, cy, r))
    if angle:
        m = m.rotate(angle, resample=Image.BICUBIC, center=(cx, cy))
    return m


def m_ring(cx, cy, r, w):
    return ImageChops.difference(m_circle(cx, cy, r + w / 2), m_circle(cx, cy, r - w / 2))


def m_wave(y0, amp, x0, x1, w, phase=0.0, n=200, taper=False):
    """Sine polyline stroked with round caps: a soft ripple line."""
    m = _blank()
    d = ImageDraw.Draw(m)
    for i in range(n + 1):
        t = i / n
        x = x0 + (x1 - x0) * t
        y = y0 + amp * math.sin(phase + t * math.pi * 1.6)
        r = max(w / 2 * (0.22 + 0.78 * math.sin(math.pi * t) ** 0.6 if taper else 1.0), 1.0)
        d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    return m


def m_below_wave(y0, amp, x0, x1, y_bottom, phase=0.0, n=200):
    """Everything under a sine edge: the 'liquid level' region of a shape."""
    pts = [(x0 + (x1 - x0) * i / n,
            y0 + amp * math.sin(phase + (i / n) * math.pi * 1.6)) for i in range(n + 1)]
    pts += [(x1, y_bottom), (x0, y_bottom)]
    m = _blank()
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def m_spiral(cx, cy, r0, r1, w0, w1, turns, t_from=0.0, t_to=1.0, n=520):
    """Archimedean spiral stroked with a tapering width."""
    m = _blank()
    d = ImageDraw.Draw(m)
    for i in range(n + 1):
        t = t_from + (t_to - t_from) * i / n
        a = t * turns * 2 * math.pi - math.pi * 0.5
        r = r0 + (r1 - r0) * (t ** 0.85)
        w = w0 + (w1 - w0) * (t ** 0.80)
        rr = max(w / 2, 1.0)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=255)
    return m


def m_drop(apex_y, cy, r, n=180):
    """Classic water droplet: apex point + tangent lines into a lower circle."""
    cx = 0.5 * S
    py, pcy = apex_y, cy
    d = pcy - py
    ang_c = math.degrees(math.acos(min(r / d, 1.0)))      # angle at the circle centre
    base = math.radians(-90.0)                            # direction circle -> apex
    # sweep the MAJOR arc (T1 -> bottom -> T2) so the belly is included
    a_start = base + math.radians(ang_c)
    sweep = math.radians(360.0 - 2 * ang_c)
    pts = [(cx, py)]
    for i in range(n + 1):
        a = a_start + sweep * i / n
        pts.append((cx + r * math.cos(a), pcy + r * math.sin(a)))
    m = _blank()
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def union(*masks):
    out = masks[0]
    for m in masks[1:]:
        out = ImageChops.lighter(out, m)
    return out


def intersect(*masks):
    out = masks[0]
    for m in masks[1:]:
        out = ImageChops.darker(out, m)
    return out


def paint(layer, mask, rgb):
    layer.paste(Image.new("RGBA", (S, S), rgb + (255,)), (0, 0), mask)


# --- concepts ----------------------------------------------------------------
def c_rings(cw):
    """Ripple rings: three tapering rings around a solid core."""
    L = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cx = cy = 0.5 * S
    paint(L, m_ring(cx, cy, 0.140 * S, 0.070 * S), cw["mark"])
    paint(L, m_ring(cx, cy, 0.256 * S, 0.052 * S), cw["mark"])
    paint(L, m_ring(cx, cy, 0.346 * S, 0.034 * S), cw["hilite"])
    paint(L, m_circle(cx, cy, 0.055 * S), cw["accent"])
    return L


def c_berry(cw):
    """Raspberry: drupelet cluster (a soft halo keeps the seeds apart) + stem/leaf."""
    L = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    paint(L, m_lens(0.592 * S, 0.236 * S, 0.052 * S, 0.092 * S, 40), cw["accent"])
    paint(L, m_capsule((0.5 * S, 0.380 * S), (0.534 * S, 0.150 * S), 0.030 * S), cw["accent"])

    rows = [
        (0.340, 0.100, [0.352, 0.500, 0.648]),
        (0.492, 0.100, [0.300, 0.433, 0.567, 0.700]),
        (0.648, 0.096, [0.372, 0.500, 0.628]),
        (0.778, 0.086, [0.500]),
    ]
    halo = union(*[m_circle(x * S, cy * S, (r + 0.016) * S) for cy, r, xs in rows for x in xs])
    seeds = union(*[m_circle(x * S, cy * S, r * S) for cy, r, xs in rows for x in xs])
    paint(L, halo, cw["soft"])
    paint(L, seeds, cw["mark"])
    paint(L, m_circle(0.330 * S, 0.312 * S, 0.046 * S), cw["hilite"])
    return L


def c_swirl(cw):
    """Ripple swirl: a soft-serve spiral, the tail fading into the light tone."""
    L = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cx = cy = 0.5 * S
    paint(L, m_spiral(cx, cy, 0.030 * S, 0.360 * S, 0.104 * S, 0.024 * S, 2.05), cw["mark"])
    paint(L, m_spiral(cx, cy, 0.030 * S, 0.360 * S, 0.104 * S, 0.024 * S, 2.05,
                      t_from=0.72, t_to=1.0), cw["hilite"])
    return L


def c_drop(cw):
    """Ripple drop: droplet with a wavy liquid level and a soft shine."""
    L = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    drop = m_drop(0.140 * S, 0.575 * S, 0.228 * S)
    paint(L, drop, cw["mark"])
    level = m_below_wave(0.648 * S, 0.028 * S, 0.15 * S, 0.85 * S, 0.95 * S, phase=0.35)
    paint(L, intersect(level, drop), cw["soft"])
    paint(L, m_ellipse(0.418 * S, 0.478 * S, 0.027 * S, 0.045 * S, 16), cw["hilite"])
    return L


def c_pinwheel(cw):
    """Petal pinwheel: four pointed petals woven around a solid core."""
    L = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    for i in range(4):
        a = math.radians(45 + 90 * i)
        cx = 0.5 * S + 0.150 * S * math.cos(a)
        cy = 0.5 * S + 0.150 * S * math.sin(a)
        petal = m_lens(cx, cy, 0.102 * S, 0.190 * S, 45 + 90 * i - 90)
        paint(L, petal, cw["mark"] if i % 2 == 0 else cw["soft"])
    paint(L, m_circle(0.5 * S, 0.5 * S, 0.070 * S), cw["accent"])
    return L


def c_waves(cw):
    """Ripple waves: three parallel tapered strokes, the middle one emphasised."""
    L = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bands = [
        (0.360, 0.052, 0.180, 0.820, 0.098, "soft"),
        (0.500, 0.058, 0.150, 0.850, 0.112, "mark"),
        (0.640, 0.052, 0.180, 0.820, 0.098, "soft"),
    ]
    for y, amp, x0, x1, w, tone in bands:
        paint(L, m_wave(y * S, amp * S, x0 * S, x1 * S, w * S, taper=True), cw[tone])
    return L


CONCEPTS = [
    ("01", "rings", "Ripple rings", "波纹环", c_rings),
    ("02", "berry", "Raspberry", "树莓", c_berry),
    ("03", "swirl", "Ripple swirl", "漩涡", c_swirl),
    ("04", "drop", "Ripple drop", "涟漪水滴", c_drop),
    ("05", "pinwheel", "Petal pinwheel", "四瓣旋花", c_pinwheel),
    ("06", "waves", "Ripple waves", "三重波纹", c_waves),
]

CHOSEN = "waves"          # user picked candidate 06, pale card
CHOSEN_CW = "light"


# --- composition -------------------------------------------------------------
def card(card_rgb):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    plate = _blank()
    ImageDraw.Draw(plate).rounded_rectangle([0, 0, S - 1, S - 1],
                                            radius=CARD_RADIUS * S, fill=255)
    img.paste(Image.new("RGBA", (S, S), card_rgb + (255,)), (0, 0), plate)
    return img


def compose(concept, cw):
    """Draw the mark centred on its own outline, inside the rounded card."""
    layer = concept(cw)
    box = layer.split()[3].getbbox()
    assert box is not None, "nothing drawn"
    centered = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    centered.alpha_composite(layer, (int(round(S / 2 - (box[0] + box[2]) / 2)),
                                     int(round(S / 2 - (box[1] + box[3]) / 2))))
    b = centered.split()[3].getbbox()
    margin = 0.12 * S
    assert b[0] >= margin and b[1] >= margin, f"mark too close to card edge: {b}"
    assert b[2] <= S - margin and b[3] <= S - margin, f"mark too close to card edge: {b}"
    out = card(cw["card"])
    out.alpha_composite(centered)
    return out


def outlined(img_rgba, color, radius_frac, width=2, alpha=70):
    """Hairline outline so a pale card stays readable on a pale sheet."""
    img = img_rgba.copy()
    ImageDraw.Draw(img).rounded_rectangle(
        [0, 0, img.width - 1, img.height - 1], radius=radius_frac * img.width,
        outline=color + (alpha,), width=width)
    return img


def load_font(size, bold=False):
    names = (("msyhbd.ttc", "segoeuib.ttf", "arialbd.ttf") if bold
             else ("msyh.ttc", "segoeui.ttf", "arial.ttf"))
    for name in names:
        p = Path("C:/Windows/Fonts") / name
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                continue
    return ImageFont.load_default()


def contact_sheet(rows, ui):
    """3 x 2 sheet; each tile shows the pale-card and the berry-card version."""
    W, H = 1280, 800
    MARGIN, GAP, HEADER = 60, 40, 110
    TILE_W = (W - 2 * MARGIN - 2 * GAP) // 3            # 360
    TILE_H = (H - HEADER - GAP - MARGIN) // 2           # 295
    PREV = 150

    sheet = Image.new("RGB", (W, H), ui["ntp"])
    d = ImageDraw.Draw(sheet)
    f_head = load_font(30, bold=True)
    f_sub = load_font(15)
    f_num = load_font(22, bold=True)
    f_name = load_font(22, bold=True)
    f_cap = load_font(15)

    d.text((MARGIN, 34), "Raspberry Ripple - Logo Candidates", font=f_head, fill=ui["plum"])
    d.text((MARGIN, 74), "left: pale card   .   right: berry card",
           font=f_sub, fill=ui["midplum"])

    for i, (num, _slug, en, cn, light, berry) in enumerate(rows):
        col, row = i % 3, i // 3
        x = MARGIN + col * (TILE_W + GAP)
        y = HEADER + row * (TILE_H + GAP)
        d.rounded_rectangle([x, y, x + TILE_W, y + TILE_H], radius=22,
                            fill=ui["white"], outline=ui["soft"], width=2)
        d.text((x + 24, y + 18), num, font=f_num, fill=ui["incog"])
        d.text((x + 66, y + 18), f"{en}  {cn}", font=f_name, fill=ui["plum"])

        px, py = x + 26, y + 64
        for j, img in enumerate((light, berry)):
            tile = outlined(img.resize((PREV, PREV), Image.LANCZOS),
                            ui["plum"], CARD_RADIUS)
            sheet.paste(tile, (px + j * (PREV + 12), py), tile)
        d.text((px, py + PREV + 6), "pale card", font=f_cap, fill=ui["midplum"])
        d.text((px + PREV + 12, py + PREV + 6), "berry card", font=f_cap, fill=ui["midplum"])

    dest = OUT / "contact-sheet.png"
    sheet.save(dest)
    print(f"wrote {dest.relative_to(ROOT)}")


def write_candidates():
    colorways, ui = load_palette()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for num, slug, en, cn, concept in CONCEPTS:
        imgs = {}
        for name in ("light", "berry"):
            img = compose(concept, colorways[name]).resize((512, 512), Image.LANCZOS)
            suffix = "" if name == "light" else "-berry"
            img.save(OUT / f"candidate-{num}-{slug}{suffix}.png")
            imgs[name] = img
        print(f"wrote candidate-{num}-{slug} (light + berry)")
        rows.append((num, slug, en, cn, imgs["light"], imgs["berry"]))
    contact_sheet(rows, ui)


def write_final(slug=CHOSEN, colorway=CHOSEN_CW):
    colorways, ui = load_palette()
    if colorway not in colorways:
        raise SystemExit(f"unknown colorway '{colorway}' - use light | berry")
    concept = next((c for _n, s, _e, _cn, c in CONCEPTS if s == slug), None)
    if concept is None:
        raise SystemExit(f"unknown concept '{slug}' - use one of: "
                         + ", ".join(s for _n, s, _e, _cn, _c in CONCEPTS))

    dest = ROOT / "logo"
    dest.mkdir(parents=True, exist_ok=True)
    icon = compose(concept, colorways[colorway]).resize((SIZE, SIZE), Image.LANCZOS)
    icon.save(dest / "logo.png")
    assert icon.size == (SIZE, SIZE)
    print(f"wrote logo/logo.png ({SIZE}x{SIZE}) - concept '{slug}', {colorway} card")
    print('manifest icons field: "icons": { "128": "logo/logo.png" }')


def main():
    args = sys.argv[1:]
    mode = args[0] if args else "candidates"
    if mode == "candidates":
        write_candidates()
    elif mode == "final":
        write_final(*(args[1:3] or [CHOSEN, CHOSEN_CW]))
    else:
        raise SystemExit(f"unknown mode '{mode}' - use 'candidates' or 'final'")


if __name__ == "__main__":
    main()
