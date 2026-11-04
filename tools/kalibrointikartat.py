#!/usr/bin/env python3
"""
Printgen FLOW — kalibroinnin testikartat (A4, 300 DPI)

Koottu 2026-11-04 keskustelun "DTF-työkalun kalibrointi ja käyttöliittymä"
(2026-09-01) kolmesta skriptistä: make_charts.py, make_extra.py ja alpha.py.
Piirtologiikka on alkuperäinen. Muutokset: komentoriviliittymä, fonttien
haku myös macOS:ltä, sävyportaat parametrina ja peittotarkistus (--tarkista).
Tulosteita ei ole verrattu bitintarkasti alkuperäisiin; fontti- ja
Pillow-versio voivat muuttaa tekstien piirtoa, mutta eivät rasteripisteitä.

Kartat:
  maxlpi    max-LPI-haitari (LPI × peitto)             → raster.maxLpi
  kutistuma kutistumaristikko + 50 mm kalibrointijana  → material.shrinkX/Y
  loki      mittausloki (paperilomake)
  tiheys    tiheysporras, valkoinen kanava             → base.requiredDensity
  choke     choke-pari: väri + valkoinen                → base.choke

Käyttö:
  python3 tools/kalibrointikartat.py                    # kaikki, ./kartat/
  python3 tools/kalibrointikartat.py --vain maxlpi
  python3 tools/kalibrointikartat.py --savyt 5,10,15,20,30,50,70,90
  python3 tools/kalibrointikartat.py --tarkista         # peitto vs. otsikko

Riippuvuudet: numpy, Pillow (pip install numpy pillow).

Rasterin pistekaava (halftone_patch):
  solu  c = DPI / LPI            liukuluku, EI pyöristetä → rivit ovat todellisia LPI-arvoja
  säde  R = c · sqrt(t / π)      PINTA-ALAKORJATTU: ympyrän ala = t · c²
  kun R > c/2, naapurisolujen pisteet sulautuvat (varjot geometrisesti oikein)
  4× ylinäytteistys + LANCZOS → antialiasoidut reunat, ei pikseliruudukon moiréa
Printgenin oma shader (index.html, FS_COLOR) käyttää toistaiseksi säde ∝ tummuus
-kaavaa; ks. docs/TIEKARTTA.md vaihe A2.
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

DPI = 300
MM = DPI / 25.4                      # px per mm  (~11.811)
W = round(210 * MM)                  # 2480  (A4 pysty)
H = round(297 * MM)                  # 3508

OUT = "kartat"                       # asetetaan main():ssa

# max-LPI-haitarin oletusportaat (koeajo 1, 2026-11)
SAVYT_OLETUS = [0.05, 0.15, 0.30, 0.50, 0.70, 0.90]
LPIT = [25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75]

# ------------------------------------------------------------------ fontit
FONTTIHAKEMISTOT = [
    os.environ.get("PRINTGEN_FONTS", ""),
    "/usr/share/fonts/truetype/dejavu/",                 # Linux (alkuperäinen ympäristö)
    os.path.expanduser("~/Library/Fonts/"),              # macOS, käyttäjä
    "/Library/Fonts/",                                   # macOS, järjestelmä
    "/opt/homebrew/share/fonts/",                        # Homebrew
]
_varoitettu = False

def _f(nimi, px):
    global _varoitettu
    for d in FONTTIHAKEMISTOT:
        if d and os.path.exists(os.path.join(d, nimi)):
            return ImageFont.truetype(os.path.join(d, nimi), px)
    if not _varoitettu:
        print("VAROITUS: DejaVu-fontteja ei löytynyt, käytetään Pillow'n oletusfonttia.\n"
              "  Asennus macOS:lle: brew install --cask font-dejavu\n"
              "  tai aseta PRINTGEN_FONTS=/polku/fontteihin", file=sys.stderr)
        _varoitettu = True
    return ImageFont.load_default(size=px)               # Pillow >= 10.1

SANS   = lambda px: _f("DejaVuSans.ttf", px)
SANS_B = lambda px: _f("DejaVuSans-Bold.ttf", px)
MONO   = lambda px: _f("DejaVuSansMono.ttf", px)
MONO_B = lambda px: _f("DejaVuSansMono-Bold.ttf", px)

INK = 0
PAPER = 255
GRAY = 150
FAINT = 205
BLACK = (0, 0, 0); WHITE = (255, 255, 255)
GRAYC = (150, 150, 150); FAINTC = (205, 205, 205); DK = (60, 60, 60); MD = (110, 110, 110)


# ======================================================================
# RASTERI
# ======================================================================
def halftone_patch(w, h, tone, lpi, dpi=DPI, angle_deg=45.0):
    """AM-rasteriruutu. tone: musteen peitto 0..1. Palauttaa uint8 (h,w), 0 = muste."""
    c = dpi / lpi                                   # solukoko px, todellinen taajuus
    th = np.radians(angle_deg)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    u = xs * np.cos(th) + ys * np.sin(th)
    v = -xs * np.sin(th) + ys * np.cos(th)
    fu = u / c - np.floor(u / c) - 0.5              # -0.5..0.5 solun sisällä
    fv = v / c - np.floor(v / c) - 0.5
    R = c * np.sqrt(max(tone, 0.0) / np.pi)         # pisteen säde peitosta
    d = np.hypot(fu * c, fv * c)
    ink = d <= R
    if R > c * 0.5:                                 # varjoissa pisteet sulautuvat
        for oi in (-1, 0, 1):
            for oj in (-1, 0, 1):
                if oi == 0 and oj == 0:
                    continue
                dn = np.hypot((fu - oi) * c, (fv - oj) * c)
                ink |= dn <= R
    return np.where(ink, INK, PAPER).astype(np.uint8)


def halftone_patch_aa(w, h, tone, lpi, angle_deg=45.0, S=4):
    """Ylinäytteistetty rasteri → antialiasoidut pisteet ilman pikseliruudukon moiréa."""
    big = halftone_patch(w * S, h * S, tone, lpi, dpi=DPI * S, angle_deg=angle_deg)
    im = Image.fromarray(big, "L").resize((w, h), Image.LANCZOS)
    return np.asarray(im)


def ctext(draw, cx, y, s, fnt, fill=INK, anchor="ma"):
    draw.text((cx, y), s, font=fnt, fill=fill, anchor=anchor)


# ======================================================================
# KARTTA 1 — max-LPI-haitari
# ======================================================================
def chart_maxlpi(tones):
    img = Image.new("RGB", (W, H), (PAPER, PAPER, PAPER))
    d = ImageDraw.Draw(img)

    mx = round(14 * MM)
    y = round(12 * MM)
    d.text((mx, y), "PRINTGEN FLOW", font=MONO(30), fill=(GRAY, GRAY, GRAY))
    y += 46
    d.text((mx, y), "max-LPI -haitari", font=SANS_B(70), fill=(INK, INK, INK))
    y += 96
    d.text((mx, y),
           "Etsi ylin LPI-rivi, jolla pisteet ovat yhä terävät eivätkä sävyt tukkeudu tai katoa.",
           font=SANS(30), fill=(60, 60, 60))
    y += 44
    d.text((mx, y),
           "300 DPI  ·  kulma 45°  ·  pyöreä piste  ·  lue filmiltä hyvässä valossa (loupe auttaa)",
           font=MONO(26), fill=(GRAY, GRAY, GRAY))
    y += 60

    tlabel = [f"{round(t * 100)}" for t in tones]
    lpis = LPIT

    label_col = round(30 * MM)
    grid_left = mx + label_col
    grid_right = W - mx
    ncol = len(tones)
    gap = 14
    patch_w = (grid_right - grid_left - gap * (ncol - 1)) // ncol

    header_y = y
    d.text((mx, header_y + 6), "PEITTO %", font=MONO(24), fill=(GRAY, GRAY, GRAY))
    for j, tl in enumerate(tlabel):
        cx = grid_left + j * (patch_w + gap) + patch_w // 2
        ctext(d, cx, header_y, tl, MONO_B(32))
    y = header_y + 52

    grid_top = y
    footer_h = round(30 * MM)
    avail_h = H - footer_h - grid_top
    nrow = len(lpis)
    rgap = 14
    patch_h = (avail_h - rgap * (nrow - 1)) // nrow
    patch_h = min(patch_h, patch_w)
    if patch_h < 120:
        patch_h = 120

    for i, lpi in enumerate(lpis):
        ry = grid_top + i * (patch_h + rgap)
        cell_px = round(300 / lpi)
        d.text((mx, ry + patch_h // 2 - 34), str(lpi), font=MONO_B(52), fill=(INK, INK, INK))
        d.text((mx + 96, ry + patch_h // 2 - 30), "LPI", font=MONO(28), fill=(90, 90, 90))
        d.text((mx, ry + patch_h // 2 + 20),
               f"solu≈{cell_px}px", font=MONO(22), fill=(GRAY, GRAY, GRAY))
        for j, tone in enumerate(tones):
            px = grid_left + j * (patch_w + gap)
            arr = halftone_patch_aa(patch_w, patch_h, tone, lpi)
            img.paste(Image.fromarray(arr, "L").convert("RGB"), (px, ry))
            d.rectangle([px, ry, px + patch_w - 1, ry + patch_h - 1],
                        outline=(FAINT, FAINT, FAINT), width=1)

    fy = H - footer_h + round(4 * MM)
    d.line([mx, fy - 18, W - mx, fy - 18], fill=(FAINT, FAINT, FAINT), width=2)
    d.text((mx, fy), "→ profiili:  raster.maxLpi = ylin toimiva rivi",
           font=MONO_B(28), fill=(INK, INK, INK))
    d.text((mx, fy + 42),
           "Huom: työkalu kvantisoi solun kokonaislukuun 300 DPI:llä, joten sen erottelevat portaat ovat ~{25,30,33,38,43,50,60,75}.",
           font=MONO(23), fill=(110, 110, 110))
    d.text((mx, fy + 76),
           "Löydetty katto riittää — työkalu valitsee lähimmän kokonaislukusolun sen alta.",
           font=MONO(23), fill=(110, 110, 110))

    out = f"{OUT}/printgen_test_maxLPI_A4_300dpi.png"
    img.save(out, dpi=(DPI, DPI))
    return out


# ======================================================================
# KARTTA 2 — kutistumaristikko
# ======================================================================
def cross(d, cx, cy, arm_mm=6.0, w=3):
    a = round(arm_mm * MM)
    d.line([cx - a, cy, cx + a, cy], fill=(INK, INK, INK), width=w)
    d.line([cx, cy - a, cx, cy + a], fill=(INK, INK, INK), width=w)


def dim_line(d, x1, y1, x2, y2, label, fnt, vertical=False):
    d.line([x1, y1, x2, y2], fill=(90, 90, 90), width=2)
    t = round(2.2 * MM)
    if vertical:
        d.line([x1 - t, y1, x1 + t, y1], fill=(90, 90, 90), width=2)
        d.line([x2 - t, y2, x2 + t, y2], fill=(90, 90, 90), width=2)
    else:
        d.line([x1, y1 - t, x1, y1 + t], fill=(90, 90, 90), width=2)
        d.line([x2, y2 - t, x2, y2 + t], fill=(90, 90, 90), width=2)
    mx_, my_ = (x1 + x2) // 2, (y1 + y2) // 2
    tw = d.textlength(label, font=fnt)
    d.rectangle([mx_ - tw // 2 - 8, my_ - 20, mx_ + tw // 2 + 8, my_ + 20],
                fill=(PAPER, PAPER, PAPER))
    d.text((mx_, my_), label, font=fnt, fill=(60, 60, 60), anchor="mm")


def chart_shrink():
    img = Image.new("RGB", (W, H), (PAPER, PAPER, PAPER))
    d = ImageDraw.Draw(img)
    mx = round(14 * MM)

    y = round(12 * MM)
    d.text((mx, y), "PRINTGEN FLOW", font=MONO(30), fill=(GRAY, GRAY, GRAY))
    y += 46
    d.text((mx, y), "kutistumaristikko", font=SANS_B(70), fill=(INK, INK, INK))
    y += 100
    d.text((mx, y), "TULOSTA 100 % — EI \"sovita sivulle\" / scale to fit",
           font=SANS_B(34), fill=(INK, INK, INK))
    y += 50
    d.text((mx, y),
           "Mittaa ristien keskipisteiden väli työntömitalla ENNEN prässäystä (filmiltä)",
           font=SANS(28), fill=(60, 60, 60))
    y += 40
    d.text((mx, y),
           "ja JÄLKEEN prässäyksen (kankaalta). Erotus = materiaalin todellinen kutistuma.",
           font=SANS(28), fill=(60, 60, 60))

    xs_mm = [25.0, 105.0, 185.0]          # X-span 160 mm (väli 80)
    ys_mm = [64.0, 124.0, 184.0, 244.0]   # Y-span 180 mm (väli 60)
    px_of = lambda m: round(m * MM)

    for xm in xs_mm:
        d.line([px_of(xm), px_of(ys_mm[0]), px_of(xm), px_of(ys_mm[-1])],
               fill=(FAINT, FAINT, FAINT), width=1)
    for ym in ys_mm:
        d.line([px_of(xs_mm[0]), px_of(ym), px_of(xs_mm[-1]), px_of(ym)],
               fill=(FAINT, FAINT, FAINT), width=1)

    for ym in ys_mm:
        for xm in xs_mm:
            cx, cy = px_of(xm), px_of(ym)
            cross(d, cx, cy, arm_mm=6.0, w=3)
            d.text((cx + 18, cy + 14), f"{xm:.0f},{ym:.0f}",
                   font=MONO(22), fill=(120, 120, 120))

    fnt = MONO_B(30)
    yv = px_of(ys_mm[0]) - round(9 * MM)
    dim_line(d, px_of(xs_mm[0]), yv, px_of(xs_mm[-1]), yv, "X  160,0 mm", fnt)
    xv = px_of(xs_mm[0]) - round(9 * MM)
    dim_line(d, xv, px_of(ys_mm[0]), xv, px_of(ys_mm[-1]), "Y  180,0 mm", fnt, vertical=True)

    cyb = px_of(ys_mm[-1]) + round(16 * MM)
    x0 = px_of(xs_mm[0]); x1 = px_of(xs_mm[0] + 50.0)
    d.line([x0, cyb, x1, cyb], fill=(INK, INK, INK), width=3)
    d.line([x0, cyb - 13, x0, cyb + 13], fill=(INK, INK, INK), width=3)
    d.line([x1, cyb - 13, x1, cyb + 13], fill=(INK, INK, INK), width=3)
    d.text((x1 + round(6 * MM), cyb - 30),
           "TARKISTA SKAALA: tämän janan pituus = 50,0 mm",
           font=MONO_B(27), fill=(INK, INK, INK))
    d.text((x1 + round(6 * MM), cyb + 6),
           "jos ei täsmää filmillä → printtaus skaalaa, korjaa se ensin",
           font=MONO(22), fill=(110, 110, 110))

    fy = cyb + round(11 * MM)
    d.line([mx, fy - 14, W - mx, fy - 14], fill=(FAINT, FAINT, FAINT), width=2)
    d.text((mx, fy), "kutistuma-% = (nimellinen − mitattu) / nimellinen",
           font=MONO_B(29), fill=(INK, INK, INK))
    d.text((mx, fy + 42),
           "→ profiili: material.shrinkX / shrinkY  ·  mittaa X ja Y erikseen (anisotrooppinen), keskeltä keskelle",
           font=MONO(22), fill=(110, 110, 110))

    for (cx, cy) in [(mx, mx), (W - mx, mx), (mx, H - mx), (W - mx, H - mx)]:
        a = round(4 * MM)
        d.line([cx - a, cy, cx + a, cy], fill=(INK, INK, INK), width=2)
        d.line([cx, cy - a, cx, cy + a], fill=(INK, INK, INK), width=2)

    out = f"{OUT}/printgen_test_kutistuma_A4_300dpi.png"
    img.save(out, dpi=(DPI, DPI))
    return out


# ======================================================================
# KARTTA 3 — mittausloki (paperilomake)
# ======================================================================
def chart_log():
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    mx = round(14 * MM); rx = W - mx
    y = round(12 * MM)
    d.text((mx, y), "PRINTGEN FLOW · KALIBROINTI", font=MONO(28), fill=GRAYC); y += 44
    d.text((mx, y), "mittausloki", font=SANS_B(68), fill=BLACK); y += 92
    d.text((mx, y), "Yksi käynti = yksi ketju. Merkitse luennat tähän ja rakenna profiili jälkikäteen.",
           font=SANS(28), fill=DK); y += round(9 * MM)

    def field(x, yy, w, label, hint=""):
        d.text((x, yy), label, font=MONO(24), fill=MD)
        by = yy + 32
        d.rectangle([x, by, x + w, by + 58], outline=(170, 170, 170), width=2)
        if hint:
            d.text((x + 12, by + 16), hint, font=MONO(22), fill=(190, 190, 190))
        return by + 58

    def section(yy, title):
        d.line([mx, yy, rx, yy], fill=FAINTC, width=2)
        d.text((mx, yy + 12), title, font=SANS_B(34), fill=BLACK)
        return yy + round(16 * MM)

    y = section(y, "1 · Ketju")
    colw = (rx - mx - 2 * round(6 * MM)) // 3
    gx = round(6 * MM)
    field(mx, y, colw, "PRINTERI")
    field(mx + colw + gx, y, colw, "MUSTE")
    field(mx + 2 * (colw + gx), y, colw, "FILMI")
    y2 = y + round(24 * MM)
    field(mx, y2, colw, "JAUHE")
    field(mx + colw + gx, y2, colw, "KANGAS (tumma?)")
    field(mx + 2 * (colw + gx), y2, colw, "PVM")
    y = y2 + round(26 * MM)
    d.text((mx, y), "VALKOISEN TEKIJÄ:", font=MONO(24), fill=MD)
    bx = mx + round(52 * MM)
    for lbl in ["pajan RIP tekee valkoisen", "syötämme oman valkoisen"]:
        d.rectangle([bx, y - 4, bx + 28, y + 24], outline=(120, 120, 120), width=2)
        d.text((bx + 40, y), lbl, font=SANS(26), fill=DK)
        bx += round(2 * MM) + 28 + 40 + int(d.textlength(lbl, font=SANS(26))) + round(8 * MM)
    y += round(14 * MM)

    y = section(y, "2 · max-LPI  (RIP-riippumaton)")
    d.text((mx, y), "Ylin rivi jolla pisteet terävät eikä sävyt tukkeudu/katoa:", font=SANS(27), fill=DK)
    d.rectangle([mx + round(112 * MM), y - 8, mx + round(140 * MM), y + 52], outline=(170, 170, 170), width=2)
    d.text((rx - round(24 * MM), y + 8), "LPI", font=MONO_B(30), fill=BLACK)
    d.text((mx, y + 64), "→ raster.maxLpi", font=MONO(24), fill=MD)
    y += round(20 * MM)

    y = section(y, "3 · Kutistuma  (RIP-riippumaton)")
    cols = ["", "nimellinen", "filmi (ennen)", "garment (jälkeen)", "kutistuma-%"]
    cw = [round(34 * MM), round(34 * MM), round(38 * MM), round(42 * MM), round(34 * MM)]
    x = mx
    ty = y
    for c, w in zip(cols, cw):
        d.text((x + 8, ty), c, font=MONO(23), fill=MD); x += w
    ty += 40
    rows = [("kalibrointijana", "50,0 mm"), ("X", "160,0 mm"), ("Y", "180,0 mm")]
    for name, nom in rows:
        x = mx
        d.rectangle([mx, ty, mx + sum(cw), ty + 56], outline=(200, 200, 200), width=1)
        d.text((x + 10, ty + 14), name, font=MONO(24), fill=BLACK); x += cw[0]
        d.text((x + 10, ty + 14), nom, font=MONO(24), fill=DK); x += cw[1]
        for w in cw[2:]:
            d.line([x, ty, x, ty + 56], fill=(200, 200, 200), width=1); x += w
        ty += 56
    d.text((mx, ty + 10), "kutistuma-% = (nimellinen − mitattu) / nimellinen   →  material.shrinkX / shrinkY",
           font=MONO(23), fill=MD)
    y = ty + round(16 * MM)

    y = section(y, "4 · Tiheys & choke  (vaativat oman valkoisen, tumma kangas)")
    d.text((mx, y), "Pienin täysin peittävä tiheysporras:", font=SANS(27), fill=DK)
    d.rectangle([mx + round(92 * MM), y - 8, mx + round(114 * MM), y + 52], outline=(170, 170, 170), width=2)
    d.text((mx + round(116 * MM), y + 8), "%", font=MONO_B(28), fill=BLACK)
    d.text((mx, y + 60), "→ base.requiredDensity", font=MONO(24), fill=MD)
    y += round(22 * MM)
    d.text((mx, y), "Pienin porras ilman valkohaloa:", font=SANS(27), fill=DK)
    d.rectangle([mx + round(84 * MM), y - 8, mx + round(106 * MM), y + 52], outline=(170, 170, 170), width=2)
    d.text((mx + round(108 * MM), y + 8), "mm", font=MONO_B(26), fill=BLACK)
    d.text((mx, y + 60), "→ base.choke   (sama luku ≈ havaittu kohdistusvirhe → registration)", font=MONO(24), fill=MD)
    y += round(22 * MM)

    y = section(y, "Muistiinpanot")
    for _ in range(3):
        d.line([mx, y + 34, rx, y + 34], fill=(210, 210, 210), width=2); y += round(10 * MM)

    out = f"{OUT}/printgen_kalibrointi_LOKI_A4.png"
    img.save(out, dpi=(DPI, DPI))
    return out


# ======================================================================
# KARTTA 4 — tiheysporras (valkoinen kanava)
# Portaat ovat TASAISIA HARMAITA (contone), eivät rasteroituja.
# Musta pohja = ei valkomustetta.
# ======================================================================
def chart_density():
    img = Image.new("RGB", (W, H), BLACK)
    d = ImageDraw.Draw(img)
    mx = round(14 * MM); rx = W - mx
    y = round(12 * MM)
    d.text((mx, y), "PRINTGEN FLOW · KALIBROINTI   ·   VALKOINEN KANAVA", font=MONO(26), fill=(150, 150, 150)); y += 42
    d.text((mx, y), "tiheysporras", font=SANS_B(68), fill=WHITE); y += 92
    d.text((mx, y), "Printtaa VALKOISENA tummalle kankaalle. Etsi pienin porras, joka on täysin", font=SANS(28), fill=(210, 210, 210)); y += 40
    d.text((mx, y), "peittävä valkoinen (ei harmaa, ei kangas läpi).  → base.requiredDensity", font=SANS(28), fill=(210, 210, 210)); y += 40
    d.text((mx, y), "valkoinen = valkomuste · musta = ei mustetta · tulosta 100 %", font=MONO(24), fill=(150, 150, 150)); y += round(12 * MM)

    steps = [30, 40, 50, 60, 70, 80, 90, 100]
    ncol = 4
    gx, gy = round(6 * MM), round(10 * MM)
    pw = (rx - mx - (ncol - 1) * gx) // ncol
    ph = round(52 * MM)
    top = y
    for i, s in enumerate(steps):
        r, c = divmod(i, ncol)
        x = mx + c * (pw + gx); yy = top + r * (ph + gy + round(14 * MM))
        v = round(255 * s / 100)
        d.rectangle([x, yy, x + pw, yy + ph], fill=(v, v, v))
        d.rectangle([x, yy, x + pw, yy + ph], outline=(90, 90, 90), width=1)
        d.text((x, yy + ph + 10), f"{s} %", font=MONO_B(34), fill=WHITE)
    for (cx, cy) in [(mx, mx), (rx, mx), (mx, H - mx), (rx, H - mx)]:
        a = round(4 * MM)
        d.line([cx - a, cy, cx + a, cy], fill=WHITE, width=2); d.line([cx, cy - a, cx, cy + a], fill=WHITE, width=2)
    fy = H - round(24 * MM)
    d.line([mx, fy, rx, fy], fill=(80, 80, 80), width=2)
    d.text((mx, fy + 12), "Huom: jos pajan RIP tekee valkoisen automaattisesti, tämä testaa RIPin valkoasetuksia.", font=MONO(23), fill=(150, 150, 150))
    out = f"{OUT}/printgen_kalibrointi_TIHEYS_valkokanava_A4.png"
    img.save(out, dpi=(DPI, DPI))
    return out


# ======================================================================
# KARTTA 5 — choke-porras (väri- ja valkokerros, kohdistettu pari)
# ======================================================================
CHOKE_MM = [0.00, 0.15, 0.30, 0.45, 0.60, 0.75]
SQ_MM = 34.0


def _choke_layout():
    mx = round(20 * MM); rx = W - mx
    ncol = 3
    gx = round(10 * MM); gy = round(24 * MM)
    top = round(70 * MM)
    sq = round(SQ_MM * MM)
    span = ncol * sq + (ncol - 1) * gx
    x0 = (W - span) // 2
    cells = []
    for i in range(len(CHOKE_MM)):
        r, c = divmod(i, ncol)
        x = x0 + c * (sq + gx); yy = top + r * (sq + gy)
        cells.append((x, yy, sq))
    reg = [(mx, mx), (rx, mx), (mx, H - mx), (rx, H - mx)]
    return cells, reg


def chart_choke_color():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))   # läpinäkyvä = ei väriä
    d = ImageDraw.Draw(img)
    cells, reg = _choke_layout()
    RED = (198, 38, 52, 255)
    rad = round(4 * MM)
    for (x, yy, sq) in cells:
        d.rounded_rectangle([x, yy, x + sq, yy + sq], radius=rad, fill=RED)
    for (cx, cy) in reg:
        a = round(4 * MM)
        d.line([cx - a, cy, cx + a, cy], fill=RED, width=3); d.line([cx, cy - a, cx, cy + a], fill=RED, width=3)
    out = f"{OUT}/printgen_kalibrointi_CHOKE_1_VARI_A4.png"
    img.save(out, dpi=(DPI, DPI))
    return out


def chart_choke_white():
    img = Image.new("RGB", (W, H), BLACK)
    d = ImageDraw.Draw(img)
    mx = round(20 * MM); rx = W - mx
    y = round(12 * MM)
    d.text((mx, y), "PRINTGEN FLOW · KALIBROINTI · VALKOINEN KANAVA (kohdistettava värin kanssa)", font=MONO(24), fill=(150, 150, 150)); y += 40
    d.text((mx, y), "choke-porras", font=SANS_B(60), fill=WHITE); y += 80
    d.text((mx, y), "Kohdista väri- ja valkokerros reg-ristien avulla. Etsi pienin choke ilman valkohaloa —", font=SANS(26), fill=(210, 210, 210)); y += 38
    d.text((mx, y), "muttei niin suuri että väriin jää tumma reunus.  → base.choke  ·  sama ≈ registration", font=SANS(26), fill=(210, 210, 210))
    cells, reg = _choke_layout()
    rad = round(4 * MM)
    for (x, yy, sq), ch in zip(cells, CHOKE_MM):
        ins = round(ch * MM)                         # valkoinen kutistettu choken verran
        d.rounded_rectangle([x + ins, yy + ins, x + sq - ins, yy + sq - ins], radius=max(1, rad - ins), fill=WHITE)
        d.text((x, yy + sq + 12), f"{ch:.2f} mm", font=MONO_B(32), fill=WHITE)
    for (cx, cy) in reg:
        a = round(4 * MM)
        d.line([cx - a, cy, cx + a, cy], fill=WHITE, width=3); d.line([cx, cy - a, cx, cy + a], fill=WHITE, width=3)
    fy = H - round(20 * MM)
    d.line([mx, fy, rx, fy], fill=(80, 80, 80), width=2)
    d.text((mx, fy + 12), "Printtaa: valkokerros ensin, väri päälle, kohdistettuna. Tumma kangas.", font=MONO(23), fill=(150, 150, 150))
    out = f"{OUT}/printgen_kalibrointi_CHOKE_2_VALKO_A4.png"
    img.save(out, dpi=(DPI, DPI))
    return out


# ======================================================================
# ALPHA-VERSIOT (alkuperäinen alpha.py)
# ======================================================================
def _lum(im):
    a = np.asarray(im.convert("RGB")).astype(np.float64)
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def alpha_white_bg(src, dst):
    """Värikanava: musta muste läpinäkyvällä. Valkoinen → läpinäkyvä, musta → peittävä."""
    L = _lum(Image.open(src))
    out = np.zeros((*L.shape, 4), np.uint8)
    out[..., 3] = np.clip(255 - L, 0, 255).astype(np.uint8)
    Image.fromarray(out, "RGBA").save(dst, dpi=(DPI, DPI))
    return dst


def alpha_black_bg(src, dst):
    """Valkokanava: valkoinen muste läpinäkyvällä. Musta → läpinäkyvä, valkoinen → peittävä.
    Tiheysportaan harmaa muuttuu alphaksi (30 % = valkoinen alpha 30 %)."""
    L = _lum(Image.open(src))
    out = np.zeros((*L.shape, 4), np.uint8)
    out[..., 0:3] = 255
    out[..., 3] = np.clip(L, 0, 255).astype(np.uint8)
    Image.fromarray(out, "RGBA").save(dst, dpi=(DPI, DPI))
    return dst


# ======================================================================
# TARKISTUS — rasterin peitto vs. sarakeotsikko
# ======================================================================
def tarkista(tones, koko=480):
    """Laskee jokaiselle sävy × LPI -ruudulle mustepeiton (1 − keskiarvo/255)
    ja vertaa otsikkoon. TIEKARTTA A2:n kriteeri on ±2 %-yksikköä."""
    print(f"{'LPI':>4} | " + " ".join(f"{round(t*100):>6}" for t in tones))
    print("-" * (7 + 7 * len(tones)))
    pahin = 0.0
    for lpi in LPIT:
        rivi = []
        for t in tones:
            arr = halftone_patch_aa(koko, koko, t, lpi).astype(np.float64)
            peitto = 1.0 - arr.mean() / 255.0
            pahin = max(pahin, abs(peitto - t))
            rivi.append(f"{peitto*100:6.1f}")
        print(f"{lpi:>4} | " + " ".join(rivi))
    print(f"\nSuurin poikkeama otsikosta: {pahin*100:.2f} %-yksikköä")
    return pahin


# ======================================================================
KARTAT = ["maxlpi", "kutistuma", "loki", "tiheys", "choke"]


def main():
    global OUT
    p = argparse.ArgumentParser(description="Printgen FLOW — kalibroinnin testikartat")
    p.add_argument("--out", default="kartat", help="tulostehakemisto (oletus: ./kartat)")
    p.add_argument("--vain", default=",".join(KARTAT),
                   help=f"pilkuin erotettu lista: {','.join(KARTAT)}")
    p.add_argument("--savyt", default=None,
                   help="max-LPI-haitarin peittoportaat prosentteina, esim. 5,10,15,20,30,50,70,90")
    p.add_argument("--ei-alpha", action="store_true", help="älä tee läpinäkyviä versioita")
    p.add_argument("--tarkista", action="store_true",
                   help="laske rasterin todellinen peitto, älä generoi kuvia")
    a = p.parse_args()

    tones = ([float(s) / 100 for s in a.savyt.split(",")] if a.savyt else SAVYT_OLETUS)

    if a.tarkista:
        tarkista(tones)
        return

    OUT = a.out
    os.makedirs(OUT, exist_ok=True)
    valitut = [s.strip() for s in a.vain.split(",") if s.strip()]
    tehdyt = []

    if "maxlpi" in valitut:
        f = chart_maxlpi(tones); tehdyt.append(f)
        if not a.ei_alpha:
            tehdyt.append(alpha_white_bg(f, f"{OUT}/printgen_test_maxLPI_A4_alpha.png"))
    if "kutistuma" in valitut:
        f = chart_shrink(); tehdyt.append(f)
        if not a.ei_alpha:
            tehdyt.append(alpha_white_bg(f, f"{OUT}/printgen_test_kutistuma_A4_alpha.png"))
    if "loki" in valitut:
        tehdyt.append(chart_log())
    if "tiheys" in valitut:
        f = chart_density(); tehdyt.append(f)
        if not a.ei_alpha:
            tehdyt.append(alpha_black_bg(f, f"{OUT}/printgen_kalibrointi_TIHEYS_valkokanava_alpha.png"))
    if "choke" in valitut:
        tehdyt.append(chart_choke_color())          # on jo valmiiksi läpinäkyvä
        f = chart_choke_white(); tehdyt.append(f)
        if not a.ei_alpha:
            tehdyt.append(alpha_black_bg(f, f"{OUT}/printgen_kalibrointi_CHOKE_2_VALKO_alpha.png"))

    for f in tehdyt:
        print(f)


if __name__ == "__main__":
    main()
