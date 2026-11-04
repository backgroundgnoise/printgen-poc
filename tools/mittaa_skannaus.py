#!/usr/bin/env python3
"""
Printgen FLOW — max-LPI-haitarin skannauksen mittaus

Mittaa painetun max-LPI-haitarin (tools/kalibrointikartat.py, kartta "maxlpi")
skannauksesta jokaisen ruudun todellisen solukoon, fyysisen peiton ja pisteen
halkaisijan. Menetelmä on sama kuin vaiheessa 0 (docs/TIEKARTTA.md, luku 2).

Ruutujen paikantaminen:
  Anna kahden näkyvän ruudun keskipisteet skannauksen pikseleinä:
      --piste LPI:SÄVY:X,Y   (kahdesti), esim. --piste 25:90:801,561
  Muiden ruutujen paikat lasketaan generaattorin asettelusta. Kierto ja
  skaalaus ratkeavat kahdesta pisteestä (oletus: kuva ei ole peilattu).
  Tarkista osuma aina: --nayta alueet.png piirtää mittausalueet kuvaan.

Mitattavat suureet (ruuduittain):
  solu    pisteväli autokorrelaatiosta, mm (odotus 25,4 / LPI). Suhde odotukseen
          paljastaa kutistuman ja varmistaa, että alue osui oikeaan ruutuun.
  tied.   tiedoston todellinen peitto. Yli 78,5 %:n sävyissä pisteet menevät
          päällekkäin, joten esim. "90" on tiedostossa noin 86 %.
  peitto  fyysinen peitto: kynnys puolivälissä kankaan ja musteen välillä
          (ruudun omat persentiilit 95 % ja 0,5 %, Gauss-sumennus σ = 1 px).
  gain    peitto − tied. eli painon dot gain %-yksikköinä.
  Ø       pisteen halkaisija peitosta: solu · √(4 · peitto / π). Vain kun
          pisteet eivät ole sulautuneet (peitto ≤ 78,5 %).
  MD      Murray–Davies-peitto keskitummuudesta, jos --paita ja --umpi on
          annettu. Sisältää myös kankaan optisen dot gainin.
  tila    vain kun --paita ja --umpi on annettu. Kiinteä kynnys kankaan ja
          umpivärin puolivälissä:
            hävinnyt     alle 1 % pikseleistä kynnystä tummempia
            umpeutunut   yli 99 % kynnystä tummempia
            osin hävinnyt / osin umpeutunut
                         kiinteän kynnyksen peitto (tai sen puute) on alle
                         puolet ruudun omalla kynnyksellä mitatusta.
          Ruudun oma kynnys olettaa, että ruudussa on sekä kangasta että
          mustetta, joten hävinneissä ja umpeutuneissa ruuduissa peittoa ei
          näytetä. Kiinteää kynnystä ei käytetä peittoon, koska välisävyissä
          pisteiden välinen kangas tummuu ja peitto yliarvioituu.
  Solukokoa ei näytetä, jos se poikkeaa ruudukon mittakaavasta yli 10 %
  (neulospinnan oma jakso, noin 0,5 mm, voi näyttää rasterilta), eikä
  hävinneissä tai osin hävinneissä ruuduissa.

Käyttö:
  python3 tools/mittaa_skannaus.py skannaus.tif \\
      --piste 25:90:801,561 --piste 75:90:5626,416 --nayta alueet.png
  lisävalinnat: --paita X,Y --umpi X,Y --csv tulos.csv --dpi 600 --savyt 5,15,...

Riippuvuudet: numpy, Pillow (samat kuin generaattorilla).
"""

import argparse
import csv
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kalibrointikartat as gen  # noqa: E402  (rivit, sarakkeet ja asettelu)

Image.MAX_IMAGE_PIXELS = None
RAJA_SULAUTUU = math.pi / 4          # tästä ylöspäin pisteet menevät päällekkäin


# ----------------------------------------------------------------------
# Generaattorin asettelu (kopio chart_maxlpi-funktion laskusta)
# ----------------------------------------------------------------------
def asettelu(tones):
    """Palauttaa ruutujen keskipisteiden laskentaan tarvittavat arvot kartan
    pikseleinä (300 DPI). Pidä synkronissa chart_maxlpi-funktion kanssa."""
    mx = round(14 * gen.MM)
    grid_left = mx + round(30 * gen.MM)
    grid_right = gen.W - mx
    ncol, gap = len(tones), 14
    patch_w = (grid_right - grid_left - gap * (ncol - 1)) // ncol
    grid_top = round(12 * gen.MM) + 46 + 96 + 44 + 60 + 52
    avail_h = gen.H - round(30 * gen.MM) - grid_top
    nrow, rgap = len(gen.LPIT), 14
    patch_h = min((avail_h - rgap * (nrow - 1)) // nrow, patch_w)
    patch_h = max(patch_h, 120)
    return dict(grid_left=grid_left, grid_top=grid_top, patch_w=patch_w,
                patch_h=patch_h, col_pitch=patch_w + gap, row_pitch=patch_h + rgap)


def ruudun_keskus(L, i, j):
    """Rivin i (LPI) ja sarakkeen j (sävy) keskipiste kompleksilukuna, kartan px."""
    x = L["grid_left"] + j * L["col_pitch"] + L["patch_w"] / 2
    y = L["grid_top"] + i * L["row_pitch"] + L["patch_h"] / 2
    return complex(x, y)


# ----------------------------------------------------------------------
# Apufunktiot
# ----------------------------------------------------------------------
def tiedoston_peitto(t):
    """Generaattorin pisteen todellinen peitto: ympyrä (ala t · c²) ∩ solu."""
    r, h = math.sqrt(t / math.pi), 0.5
    a = math.pi * r * r
    if r > h:
        a -= 4 * (r * r * math.acos(h / r) - h * math.sqrt(r * r - h * h))
    return min(a, 1.0)


def gauss(p, sigma=1.0):
    """Erotuva Gauss-sumennus numpylla (vastaa scipy.ndimage.gaussian_filteriä)."""
    rad = int(4 * sigma + 0.5)
    x = np.arange(-rad, rad + 1)
    k = np.exp(-x * x / (2 * sigma * sigma)); k /= k.sum()
    q = np.pad(p, rad, mode="reflect")
    q = np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 0, q)
    return np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 1, q)


def solukoko(s, odotus_px):
    """Lähimmän naapuripisteen etäisyys autokorrelaatiosta. Haku rajataan
    renkaaseen 0,7–1,3 × odotus, ettei 45°-ruudukon lävistäjä (√2) kelpaa."""
    q = s - s.mean()
    F = np.fft.fft2(q)
    ac = np.fft.fftshift(np.real(np.fft.ifft2(np.abs(F) ** 2)))
    if ac.max() <= 0:
        return None, 0.0
    c0 = np.array(ac.shape) // 2
    ac = ac / ac[c0[0], c0[1]]
    R = int(odotus_px * 1.3) + 2
    win = ac[c0[0] - R:c0[0] + R + 1, c0[1] - R:c0[1] + R + 1]
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1]
    dist = np.hypot(yy, xx)
    rengas = (dist >= 0.7 * odotus_px) & (dist <= 1.3 * odotus_px)
    w = np.where(rengas, win, -np.inf)
    iy, ix = np.unravel_index(np.argmax(w), w.shape)
    return float(dist[iy, ix]), float(win[iy, ix])


def piste_arg(s):
    """'25:90:801,561' → (25, 0.90, complex(801, 561))"""
    try:
        lpi, savy, xy = s.split(":")
        x, y = (float(v) for v in xy.split(","))
        return int(lpi), float(savy) / 100, complex(x, y)
    except ValueError:
        raise argparse.ArgumentTypeError(f"muoto LPI:SÄVY:X,Y, saatiin '{s}'")


def xy_arg(s):
    x, y = (float(v) for v in s.split(","))
    return complex(x, y)


def mediaani_alue(img, z, r=40):
    x, y = int(z.real), int(z.imag)
    return float(np.median(img[max(0, y - r):y + r, max(0, x - r):x + r]))


# ----------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="max-LPI-haitarin skannauksen mittaus")
    p.add_argument("skannaus", help="skannattu kuva (esim. 600 DPI TIF)")
    p.add_argument("--piste", type=piste_arg, action="append", required=True,
                   help="ruudun keskipiste LPI:SÄVY:X,Y (anna kahdesti)")
    p.add_argument("--savyt", default=None, help="kartan sävyt prosentteina, oletus generaattorin")
    p.add_argument("--dpi", type=float, default=None, help="skannauksen DPI, oletus kuvan tiedoista")
    p.add_argument("--paita", type=xy_arg, help="painamaton kangas X,Y (Murray–Davies)")
    p.add_argument("--umpi", type=xy_arg, help="umpimusta alue X,Y (Murray–Davies)")
    p.add_argument("--nayta", help="tallenna mittausalueet piirrettynä tähän PNG-tiedostoon")
    p.add_argument("--csv", help="tallenna tulokset CSV-tiedostoon")
    a = p.parse_args()

    if len(a.piste) != 2:
        p.error("anna --piste täsmälleen kahdesti")
    tones = ([float(s) / 100 for s in a.savyt.split(",")] if a.savyt else gen.SAVYT_OLETUS)
    L = asettelu(tones)

    def indeksi(lpi, t):
        try:
            return gen.LPIT.index(lpi), min(range(len(tones)), key=lambda j: abs(tones[j] - t))
        except ValueError:
            p.error(f"LPI {lpi} ei ole kartalla {gen.LPIT}")

    (la, ta, za), (lb, tb, zb) = a.piste
    ca, cb = ruudun_keskus(L, *indeksi(la, ta)), ruudun_keskus(L, *indeksi(lb, tb))
    if ca == cb:
        p.error("pisteiden on oltava eri ruuduissa")
    # Yhdenmuotoisuusmuunnos kompleksiluvuilla: skannaus = k · kartta + b
    k = (zb - za) / (cb - ca)
    b = za - k * ca
    mittakaava = abs(k)                      # skannauksen px / kartan px

    src = Image.open(a.skannaus)
    dpi = a.dpi or (src.info.get("dpi") or (None,))[0]
    if not dpi:
        p.error("skannauksen DPI puuttuu kuvan tiedoista, anna --dpi")
    dpi = float(dpi)
    img = np.asarray(src.convert("L")).astype(np.float64)
    px_mm = 25.4 / dpi
    ruudukko = mittakaava * gen.DPI / dpi      # ruudukon koko suhteessa karttaan (kutistuma)
    print(f"Skannaus {img.shape[1]}×{img.shape[0]} px, {dpi:.0f} DPI. "
          f"Kierto {math.degrees(math.atan2(k.imag, k.real)):.1f}°, "
          f"ruudukon mittakaava {ruudukko * 100:.1f} % kartan koosta.")

    paperi = mediaani_alue(img, a.paita) if a.paita else None
    umpi = mediaani_alue(img, a.umpi) if a.umpi else None
    if (paperi is None) != (umpi is None):
        print("HUOM: Murray–Davies vaatii sekä --paita että --umpi; ohitetaan.", file=sys.stderr)
    md_kaytossa = paperi is not None and umpi is not None
    if md_kaytossa:
        print(f"Murray–Davies: kangas {paperi:.0f}, umpi {umpi:.0f}")
    else:
        print("HUOM: ilman --paita ja --umpi hävinneitä ja umpeutuneita ruutuja ei tunnisteta,\n"
              "      ja niiden peittoluvut ovat merkityksettömiä.", file=sys.stderr)

    puoli = int(0.3 * min(L["patch_w"], L["patch_h"]) * mittakaava)   # alueen puolikas, px
    rivit, alueet = [], []
    for i, lpi in enumerate(gen.LPIT):
        odotus_mm = 25.4 / lpi
        odotus_px = odotus_mm / px_mm
        for j, t in enumerate(tones):
            z = k * ruudun_keskus(L, i, j) + b
            x, y = int(round(z.real)), int(round(z.imag))
            y0, y1, x0, x1 = y - puoli, y + puoli, x - puoli, x + puoli
            alueet.append((x0, y0, x1, y1))
            if y0 < 0 or x0 < 0 or y1 > img.shape[0] or x1 > img.shape[1]:
                print(f"VAROITUS: {lpi} LPI / {round(t*100)} % on kuvan ulkopuolella", file=sys.stderr)
                continue
            patch = img[y0:y1, x0:x1]
            s = gauss(patch)
            tausta, muste = np.percentile(s, 95), np.percentile(s, 0.5)
            peitto = float((s < (tausta + muste) / 2).mean())       # ruudun oma kynnys

            tila = ""
            if md_kaytossa:
                kiintea = float((s < (paperi + umpi) / 2).mean())  # kiinteä kynnys
                if kiintea < 0.01:
                    tila = "hävinnyt"
                elif kiintea > 0.99:
                    tila = "umpeutunut"
                elif kiintea < 0.5 * peitto:
                    tila = "osin hävinnyt"
                elif (1 - kiintea) < 0.5 * (1 - peitto):
                    tila = "osin umpeutunut"
            nayta_peitto = tila not in ("hävinnyt", "umpeutunut")

            solu_px, _ = solukoko(s, odotus_px)
            luotettava = (solu_px is not None and "hävinnyt" not in tila and tila != "umpeutunut"
                          and abs(solu_px * px_mm / odotus_mm - ruudukko) <= 0.10)
            solu_mm = solu_px * px_mm if luotettava else odotus_mm * ruudukko
            halk = (solu_mm * math.sqrt(4 * peitto / math.pi)
                    if nayta_peitto and peitto <= RAJA_SULAUTUU else None)
            tied = tiedoston_peitto(t)
            md = (paperi - patch.mean()) / (paperi - umpi) if md_kaytossa else None
            rivit.append(dict(
                lpi=lpi, savy=round(t * 100), tiedosto=tied * 100,
                solu_mm=solu_px * px_mm if luotettava else None, odotus_mm=odotus_mm,
                kutistuma=solu_px * px_mm / odotus_mm * 100 if luotettava else None,
                peitto=peitto * 100 if nayta_peitto else None,
                gain=(peitto - tied) * 100 if nayta_peitto else None,
                halkaisija_mm=halk, md=md * 100 if md is not None else None, tila=tila))

    def f(v, fmt):
        if v is not None:
            return format(v, fmt)
        leveys = int("".join(ch for ch in fmt.split(".")[0] if ch.isdigit()) or 0)
        return "–".rjust(leveys)

    print(f"\n{'LPI':>4} {'sävy':>4} {'tied.%':>7} {'solu mm':>8} {'odotus':>7} {'kut.%':>6} "
          f"{'peitto%':>8} {'gain':>6} {'Ø mm':>6}"
          + (f" {'MD%':>6}  tila" if md_kaytossa else ""))
    for r in rivit:
        print(f"{r['lpi']:>4} {r['savy']:>4} {r['tiedosto']:7.1f} {f(r['solu_mm'], '8.3f')} "
              f"{r['odotus_mm']:7.3f} {f(r['kutistuma'], '6.1f')} {f(r['peitto'], '8.1f')} "
              f"{f(r['gain'], '+6.1f')} {f(r['halkaisija_mm'], '6.3f')}"
              + (f" {f(r['md'], '6.1f')}  {r['tila']}" if md_kaytossa else ""))
    print("\nsolu '–': pisteväli ei erottunut luotettavasti; Ø lasketaan silloin odotetusta solusta"
          " × ruudukon mittakaava.\nØ '–': pisteet sulautuneet (peitto > 78,5 %) tai ruutu hävinnyt/umpeutunut.")

    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rivit[0].keys()))
            w.writeheader(); w.writerows(rivit)
        print(f"CSV: {a.csv}")

    if a.nayta:
        sk = 1600 / img.shape[1]
        ov = src.convert("RGB").resize((1600, round(img.shape[0] * sk)))
        d = ImageDraw.Draw(ov)
        for (x0, y0, x1, y1) in alueet:
            d.rectangle([x0 * sk, y0 * sk, x1 * sk, y1 * sk], outline=(255, 0, 0), width=2)
        for z in (za, zb):
            d.ellipse([z.real * sk - 6, z.imag * sk - 6, z.real * sk + 6, z.imag * sk + 6],
                      outline=(0, 160, 255), width=3)
        ov.save(a.nayta)
        print(f"Mittausalueet: {a.nayta}")


if __name__ == "__main__":
    main()
