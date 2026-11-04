# CODEMAP — index.html:n kartoitus

Laadittu 2026-11-03 commitin `31c308f` pohjalta (`index.html`, 4616 riviä). Rivinumerot viittaavat tähän versioon, ja ne vanhenevat koodin muuttuessa. Etsi tällöin funktion nimellä.

Dokumentti kuvaa nykytilan. Korjausehdotuksia siinä ei ole: suunnitelma tehdään erikseen tämän pohjalta.

Myöhemmin korjatut kohdat on merkitty tunnuksella **[korjattu: commit]**. Alkuperäinen havainto jätetään näkyviin, jotta selainkokeiden lähtötaso on luettavissa.

Merkinnät:
- **[koe]**: varmistettu selainkokeella (Chromium 152, WebGL päällä, 2026-11-03).
- **[päätelty]**: päätelty koodia lukemalla, ei ajettu.
- Muut väitteet ovat suoraan koodista luettuja.

---

## Sisältö

1. [Datavirta lähteestä vientiin](#1-datavirta-lähteestä-vientiin)
2. [Tila: state ja DOM](#2-tila-state-ja-dom)
3. [Osioiden ja funktioiden rivialueet](#3-osioiden-ja-funktioiden-rivialueet)
4. [Kuollut tai käyttämätön koodi](#4-kuollut-tai-käyttämätön-koodi)
5. [Ristiriidat CLAUDE.md:n ja koodin välillä](#5-ristiriidat-claudemdn-ja-koodin-välillä)
6. [Avoimiin teknisiin kysymyksiin liittyvät kohdat](#6-avoimiin-teknisiin-kysymyksiin-liittyvät-kohdat)
7. [Arvio: PDF-vienti omalla valkoisella kanavalla](#7-arvio-pdf-vienti-omalla-valkoisella-kanavalla)
8. [Riskit ja hauraat kohdat](#8-riskit-ja-hauraat-kohdat)

---

## 1. Datavirta lähteestä vientiin

### 1.1 Lähteet → `state.mainImage`

Kuvan voi tuoda neljää reittiä. Jokainen asettaa `state.mainImage`n (HTMLImageElement), nollaa `wandMask`in ja `wandHistory`n ja kutsuu sitten `updateUpscaleInfo()`, `updateCanvas()` ja `updateExportBtn()`.

| Reitti | Funktio | Rivi | Erityistä |
|---|---|---|---|
| AI-generointi | `generateImage` | 2766 | POST Workerille `{inputs, parameters:{1024×1024, 4 steps}}`. Prompt = käyttäjän teksti + `PROMPT_STYLES` + `PROMPT_BACKGROUNDS`. 503: odotetaan 22 s, sitten pyydetään painamaan uudelleen. **Nollaa myös `bgColors`.** |
| Tiedostovalinta | `handleFileUpload` | 2510 | `FileReader` → dataURL. Ei nollaa `bgColors`ia. |
| Drag & drop | nimetön käsittelijä | 2535 | Kopio `handleFileUpload`in logiikasta. Ei nollaa `bgColors`ia. |
| Upscale | `doUpscale` | 2583 | 2D-canvas `imageSmoothingQuality='high'` ×2/3/4 → PNG-blob → uusi Image. |

Logo kulkee omaa reittiään: `handleLogoUpload` (2654) asettaa `state.logoImage`n. `removeLogoBg` (2682) poistaa vasemman yläkulman värin kiinteällä toleranssilla 40×2 ja korvaa `state.logoImage`n uudella kuvalla.

### 1.2 Yhteinen ydin: `getProcessedImage(img, targetW, targetH)` (3036–3110)

Jokainen esikatselu ja vienti kutsuu tätä **omassa kohderesoluutiossaan**:

```
mainImage
  └─ drawImage → off-canvas (targetW × targetH, selaimen skaalaus)
       └─ applyColorAdjustments(off)            (2098)  ← lukee sliderit DOMista
            └─ [jos bgColors tai wandMask]
                 ├─ wand-maski: nearest-neighbor lähderesoluutiosta → alpha 0
                 ├─ eyedropper: RGB-etäisyys < tolerance×2.2 → alpha 0
                 └─ [jos haloRemoval > 0] applyErosion(adjusted, haloRemoval)   (_GL.erode)
```

Jos `bgColors` on tyhjä eikä wand-maskia ole, palautetaan pelkkä värisäädetty kuva (3048), eikä halo-poistoa tehdä.

### 1.3 Kutsugraafi

```
oninput / onclick (inline-HTML)
  └─ updateCanvas()                              (2874)  pääesikatselu 500×600
       ├─ applyShapeClip()        [vain jos shapePreview]
       ├─ getProcessedImage(imgW, imgH)
       ├─ logo (keskitetty, ei rotaatiota)
       ├─ [halftonePreview] applyHalftoneAlphaSafe(KOKO canvas) → _GL.colorHalftone
       │     └─ logo piirretään uudelleen päälle rasteroimattomana
       ├─ updateDPI()
       ├─ updateShirtPreview()                   (3153)  paita 256×300
       │     ├─ applyShapeClipCtx()   [vain jos shapePreview]
       │     ├─ getProcessedImage(imgW, imgH)    (sizeCm × paita-px/cm)
       │     └─ logo (rotaatio)
       └─ [baseHalftoneOn] updateBasePreview()   (3235)  pohja 512×512
             ├─ getProcessedImage(pw, ph)
             ├─ applyShapeClipCtx()   [vain jos shapePreview]
             └─ _GL.baseHalftone(state.baseHalftoneCell, ...)     (ei logoa, ei erosionia)

exportFiles()                                    (3529)  DTF-paketti
  ├─ outW×outH = adminW/H × 300/2.54
  ├─ getProcessedImage(imgW, imgH)               (sizeCm × 300/2.54)
  ├─ 1. colorCanvas: applyShapeClipCtx [aina jos shape≠none], translate/rotate, logo
  ├─ 2. combinedCanvas = halftonePreview ? colorHalftone(colorCanvas, 300/LPI) : colorCanvas
  ├─ 3. erodedSource = applyErosion(colorCanvas, erosion)
  │     baseCanvas = baseHalftoneOn ? _GL.baseHalftone(erodedSource) : valkoinen kun alpha>10
  ├─ 4. per kanava: extractChannel(colorCanvas, ch) → colorHalftone(CHANNEL_ANGLES[ch])  [AINA]
  ├─ 5. computeUnionBBox(combinedCanvas, baseCanvas)
  ├─ 6. trimCanvas(kaikki, bbox)
  └─ 7. JSZip: kuva_rgb, pohja, R/G/B tai C/M/Y/K, paitaohje (renderShirtPreviewForExport(800))

analyzeColors()                                  (4332)
  └─ getProcessedImage(300 px leveä) → kMeansClustering(k = sepColors) → state.colorLayers

exportColorLayers()                              (4424)
  ├─ getProcessedImage(imgW, imgH) (sama koko kuin exportFiles)
  ├─ per kerros: drawProcessedAtPosition → luokittelu lähimpään centroidiin → tasaväri
  │     └─ [halftonePreview] colorHalftone
  ├─ composite + bbox (yhdistetty kaikista kerroksista)
  └─ JSZip: varikerrokset/L01_…png, _yhdistetty_referenssi.png, _paitaohje.png
```

### 1.4 Esikatselu ja vienti rinnakkain

| Vaihe | Pääesikatselu `updateCanvas` | Paita `updateShirtPreview` | Pohja `updateBasePreview` | `exportFiles` | `exportColorLayers` | Paitaohje `renderShirtPreviewForExport` |
|---|---|---|---|---|---|---|
| Kuvan koko | Sovitettu 86 %:n alueelle, ei riipu `sizeSlider`ista | `sizeCm × (0.55·256 / adminW)` | Sovitettu 512 px:iin | `sizeCm × 300/2.54` px | sama kuin export | `sizeCm × (0.55·800 / adminW)` |
| `getProcessedImage`-resoluutio | ~430 px | ~70 px (15 cm) | ≤512 px | ~1772 px (15 cm) | ~1772 px | ~220 px |
| Clip-muoto | vain `shapePreview` | vain `shapePreview` | vain `shapePreview` | **aina** kun `shape≠none` | aina | aina |
| Rotaatio | ei | kyllä | ei | kyllä | kyllä | kyllä |
| Sijainti | keskitetty | `posX/posY` paita-alueella (0.55w × 0.60h) | keskitetty | `posX·outW`, `posY·outH` | sama kuin export | kuten paita |
| Logo | keskellä, ei rotaatiota | kyllä, rotaatio | **puuttuu** | kyllä, ei clipiä | kyllä | kyllä |
| Logo rasteroidaan | ei (piirretään halftonen päälle) | – | – | **kyllä**, jos halftone päällä | kyllä | – |
| Värikerroksen halftone | koko canvakselle (myös `#1a1a1a`-tausta); solu `areaW/adminW·2.54/LPI` | ei | – | solu `round(300/LPI)` | per kerros, tasavärinä | ei |
| Halo-poisto (`haloRemoval`) | px @ ~430 px | px @ ~70 px | px @ 512 px | px @ ~1772 px | px @ ~1772 px | px @ ~220 px |
| Pohjan erosion (`erosion`) | ei | ei | **ei** | kyllä | ei pohjaa lainkaan | ei |
| Pohjan halftone | – | – | kyllä, viennin px-solulla 512 px:n kuvaan | kyllä | – | – |
| Kanavaerottelu | ei | – | – | aina rasteroitu | – | – |

**Keskeiset erot:**

1. **Clip-muoto** näkyy esikatseluissa vain, kun "Esikatselu muodossa" on päällä. Vienti leikkaa aina.
2. **Pääesikatselu ei näytä kokoa, rotaatiota eikä sijaintia.** Kuva täyttää aina 86 %:n alueen.
3. **Halftonen mittakaava:** esikatselun solu lasketaan ikään kuin kuva olisi `adminW` leveä, vienti käyttää `sizeCm`ä. Esikatselu näyttää siksi pisteet kuvaan nähden `adminW/sizeCm`-kertaa pienempinä. Oletuksilla (30 cm / 15 cm) ero on 2×, ja jos kuva on korkea eikä täytä alueen leveyttä, vielä enemmän.
4. **Esikatselun halftone ajetaan koko canvakseen**, myös läpinäkymättömään `#1a1a1a`-taustaan (taustan pisteet ovat taustan värisiä, joten ne eivät näy). Viennin `colorCanvas` on läpinäkyvä.
5. **Logo:** esikatselussa logo jää rasteroimattomaksi, mutta viennin `combinedCanvas`issa se rasteroidaan. Pohjaesikatselussa logoa ei ole lainkaan, mutta viennin pohjassa on.
6. **Pikseliyksiköt:** `haloRemoval` ja `erosion` annetaan pikseleinä, ja ne sovelletaan kunkin polun omassa resoluutiossa. Sama arvo on fyysisesti eri suuruinen eri poluissa (ks. 6.2).
7. **Choke (`erosion`) ei näy missään esikatselussa.**
8. **Pohjaesikatselu** käyttää viennin pikselisolua (`state.baseHalftoneCell`, esim. 7 px) 512 px:n kuvaan, joten pistetiheys ei vastaa vientiä.
9. **Kanavaerottelu rasteroidaan aina**, vaikka värikerroksen halftone olisi pois päältä (3645).
10. **Paitaesikatselun pystyakseli:** paita-alueen kuvasuhde (0.55·256 : 0.60·300 ≈ 0.78) ei ole sama kuin tulostusalueen (30:36 ≈ 0.83), ja `posY` lasketaan paita-alueen korkeudesta eikä `adminH`:sta. Pystysijainti on siksi likimääräinen.

---

## 2. Tila: state ja DOM

### 2.1 `state`-objekti (1841–1878)

| Kenttä | Alku | Kirjoittaa | Lukee |
|---|---|---|---|
| `mainImage` | null | 2517, 2544, 2627, 2839 | lähes kaikki renderöinti- ja vientifunktiot |
| `logoImage` | null | `handleLogoUpload` 2661, `removeLogo` 2674, `removeLogoBg` 2732 | `updateCanvas`, `updateShirtPreview`, `renderShirtPreviewForExport`, `exportFiles`, `exportColorLayers` |
| `logoBgRemovedCanvas` | null | 2662, 2675, 2725, 2733 (nollataan heti async-vaiheessa) | 2934, 2962, 3214, 3432, 4474 (ei `exportFiles`) |
| `bgColors` | [] | eyedropper-klikkaus 2275, `clearColors` 2260, `generateImage` 2844 | `getProcessedImage` 3048/3058, `renderSwatches` |
| `eyedropperActive` | false | `toggleEyedropper` 2247, `toggleMagicWand` 2320 | klikkauskäsittelijä 2266 |
| `shirtBg` | 'light' | `setShirtBg` 2238 | `updateShirtPreview`, `renderShirtPreviewForExport` |
| `shape` | 'none' | `setShape` 2219 | `applyShapeClip(Ctx)`, kaikki renderöinnit ja viennit |
| `shapePreview` | false | `toggleShapePreview` 2228 | `updateCanvas`, `updateShirtPreview`, `updateBasePreview` (ei vientejä) |
| `logoStrength` | 0 | `toggleLogoEnabled` 2750 | `< 20`-tarkistukset: 2932, 2960, 3212, 3428, 3587, 4470 |
| `processedImageData` | null | – | – (**käyttämätön**) |
| `hasImage` | false | 2521, 2548, 2843 (ei koskaan takaisin false) | `updateExportBtn` |
| `halftonePreview` | false | `toggleHalftone` 4185 | `updateCanvas` 2946, `exportFiles` 3602, `exportColorLayers` 4528, `updateHalftoneVals`, `setHtShape` |
| `halftoneMaxSize` | 0.92 | `updateHalftoneVals` 4161 (DOM `halftoneSize`/100) | `updateCanvas`, `exportFiles`, `exportColorLayers` |
| `halftoneShape` | 0 | `setHtShape('color')` 4212 | samat |
| `baseHalftoneOn` | false | `toggleBaseHalftone` 4193 | `updateCanvas` 2981, `updateBasePreview`, `exportFiles` 3613 |
| `baseHalftoneCell` | **10** (px) | `updateHalftoneVals` 4162: `round(300/LPI)` | `updateBasePreview`, `exportFiles` |
| `baseHalftoneAngle` | 75 | 4163 | samat |
| `baseHalftoneDensity` | 0.80 | 4164 | samat |
| `baseHalftoneDotScale` | 0.88 | 4165 | samat |
| `baseHalftoneShape` | 0 | `setHtShape('base')` 4216 | samat |
| `halftoneMask` | false | `toggleHalftoneMask` 4203 (ei kutsuta) | – (**käyttämätön**) |
| `upscaleMultiplier` | 2 | `setUpscaleMultiplier` 2561 | `updateUpscaleInfo`, `doUpscale` |
| `currentView` | 'editor' | vain kommentoidussa koodissa 1885 | – (**käyttämätön**) |
| `tritoneActive` | false | `applyPreset` 2048/2057, `toggleTritone` 2074 | `applyColorAdjustments` |
| `cmykMode` | false | `toggleColorspace` 3311 | `exportFiles` 3639, 3678 |
| `colorLayers` | null | `analyzeColors` 4339, 4382 | `renderColorPreview`, `exportColorLayers` |
| `wandActive` | false | `toggleMagicWand` 2317, `toggleEyedropper` 2250 | klikkauskäsittelijä 2461 |
| `wandTolerance` | 30 | `onWandToleranceChange` 2299 | `magicWandFloodFill` 2429 |
| `wandMask` | null | `ensureWandMask`, `magicWandFloodFill` (muokkaa), `wandUndo`, `wandClear`, kuvan latausreitit | `getProcessedImage`, `updateWandHistoryUI` |
| `wandHistory` | [] | `pushWandSnapshot`, `wandUndo`, kuvan latausreitit | keydown 2393, `updateWandHistoryUI` |
| `haloRemoval` | 0 | `onHaloRemovalChange` 2304 | `getProcessedImage` 3106 |
| `promptStyle` | null | `setPromptStyle` 2009 | `generateImage` 2796 |
| `promptBackground` | 'white' | `setPromptBackground` 2017 | `generateImage` 2797 |

Vakiot `state`-objektin ulkopuolella: `WAND_HISTORY_MAX` (1880), `FEATURE_SECTIONS` (1906), `PROMPT_STYLES` / `PROMPT_BACKGROUNDS` (1995/2002), `PRESETS` (2024), `CHANNEL_ANGLES` (3514).

### 2.2 DOM-kentissä asuvat asetukset

Nämä luetaan suoraan `document.getElementById(...).value`-kutsulla, eikä niitä ole `state`ssa.

| id | Tyyppi, alue, oletus | Lukijat |
|---|---|---|
| `adminW` | text, oletus 30 (cm), fallback 30 | `updateCanvas` 2893, `updateShirtPreview` 3189, `renderShirtPreviewForExport` 3404, `exportFiles` 3538, `analyzeColors` 4347 (käyttämätön), `exportColorLayers` 4435 |
| `adminH` | text, oletus 36, fallback 36 | `updateCanvas` 2894 (käyttämätön), `exportFiles` 3539, `exportColorLayers` 4436 |
| `promptInput` | textarea | `generateImage` |
| `logoSize` | range 10–100, 40 (% kuvan leveydestä) | kaikki logoa piirtävät funktiot |
| `tolerance` | range 5–80, 30 | `getProcessedImage` 3054 |
| `erosion` | range 0–20, 2 (px) | **vain** `exportFiles` 3554 |
| `brightnessSlider`, `contrastSlider`, `saturationSlider`, `temperatureSlider` | range −100…100, 0 | `applyColorAdjustments`; kirjoittaa `applyPreset` |
| `posterizeSlider` | range 0–32, 0 | samat |
| `tritoneShadow` / `tritoneMid` / `tritoneHighlight` | color | samat |
| `tritoneStrength` | range 0–100, 100 | samat |
| `halftoneCell` | range 15–120, 45 (**LPI**, vaikka id sanoo cell) | `updateCanvas` 2947, `exportFiles` 3599, `exportColorLayers` 4529 |
| `halftoneAngle` | range 0–90, 45 | samat |
| `sizeSlider` | range 2–30, 15, step 0.5 (cm, kuvan leveys) | `updateCanvas` (DPI), `updateShirtPreview`, `exportFiles`, `exportColorLayers`, `renderShirtPreviewForExport` |
| `rotSlider` | range −180…180, 0 | paita, viennit |
| `posX` / `posY` | range 0–100, 50 / 45 (% tulostusalueesta, kuvan keskipiste) | paita, viennit |
| `maskScale` | range 10–200, 100 | kaikki clip-kohdat (`updateBasePreview` lukee `parseInt`illä, muut `parseFloat`illa) |
| `sepColors` | range 2–12, 6 | `analyzeColors` |
| `featureUpscale` … `featureClipmask` | checkbox | `applyFeatureToggles`, `saveFeatureStates` → `localStorage['printgen_features']` |

**DOM → state -peilit** (DOM on syöte, `state` välimuisti):

| DOM | → state | Missä | Huom. |
|---|---|---|---|
| `halftoneSize` (10–100, 92) | `halftoneMaxSize` = /100 | `updateHalftoneVals` 4161 | |
| `baseHalftoneCell` (15–120 LPI, 45) | `baseHalftoneCell` = round(300/LPI) px | 4162 | alkuarvo 10 px ≠ slider 45 LPI (ks. 6.3) |
| `baseHalftoneAngle` (0–90, 75) | `baseHalftoneAngle` | 4163 | |
| `baseHalftoneDensity` (10–100, 80) | `baseHalftoneDensity` = /100 | 4164 | |
| `baseHalftoneDotScale` (50–100, 88) | `baseHalftoneDotScale` = /100 | 4165 | |
| `wandTolerance` (5–80, 30) | `wandTolerance` | 2299 | |
| `haloRemoval` (0–10, 0) | `haloRemoval` | 2304 | |
| `*N`-numerokentät | synkronoidaan slidereihin | `htSyncNR` / `htSyncNRf` | |

**Recipe-valmiuden kannalta:** yhden viennin asetukset ovat kolmessa paikassa: `state` (esim. `shape`, `bgColors`, `wandMask`, halftone-muoto), DOM (koko, sijainti, rotaatio, LPI, kulma, erosion, värisäädöt, tritone) ja `localStorage` (feature-togglet). Lisäksi `halftonePreview` on samaan aikaan esikatselun kytkin ja viennin intentti.

---

## 3. Osioiden ja funktioiden rivialueet

### 3.1 Tiedoston rakenne

| Alue | Rivit |
|---|---|
| `<head>`, JSZip CDN (8), Google Fonts `@import` (10) | 1–8 |
| CSS | 9–1060 |
| Topbar (kommentoitu view-toggle 1069–1074) | 1065–1080 |
| Admin-modaali (tulostusala, feature-togglet) | 1083–~1185 |
| Vasen paneeli: VAIHE 1 lähde (1193), 2 upscale (1253), 3 logo (1283), 4 taustanpoisto (1336), 4.5 värisäädöt (1417), 5 rasterointi (1533), Laatu/DPI (1633) | 1189–1645 |
| Keskialue: välilehdet Värikerros/Pohjakerros, `mainCanvas` 500×600 (1662), `basePreviewCanvasCenter` 512×512 (1670) | 1647–1674 |
| Oikea paneeli: `shirtCanvas` 256×300 (1686), VAIHE 7 sijoittelu (1697), 7b clip-maski (1733), 8 vienti ja värikerrokset (1783) | 1676–1833 |
| `<script>` | 1837–4614 |

Vaihenumerot ovat 1, 2, 3, 4, 4.5, 5, 7, 7b ja 8. Vaihetta 6 ei ole.

### 3.2 Skriptin osiot

| Banneri | Rivit | Sisältö |
|---|---|---|
| (alku) | 1838–1880 | `canvas`, `ctx`, `state`, `WAND_HISTORY_MAX` |
| VIEW TOGGLE | 1882–1893 | kommentoitu `setView` + stub |
| ADMIN MODAL | 1894–1966 | `openAdmin` 1895, `closeAdmin` 1898, `closeAdminOnOverlay` 1901, `FEATURE_SECTIONS` 1906, `saveFeatureStates` 1917–1923, `loadFeatureStates` 1925–1934, `applyFeatureToggles` 1936–1951, `initCollapsibleSections` 1954–1965 |
| CANVAS SETUP | 1967–1982 | `resizeCanvas` 1968–1979 + resize-kuuntelija |
| TAB SWITCH | 1983–1990 | `switchTab` |
| CATEGORY TAGS | 1991–2022 | `PROMPT_STYLES`, `PROMPT_BACKGROUNDS`, `setPromptStyle` 2007, `setPromptBackground` 2015 |
| COLOR ADJUSTMENTS | 2023–2216 | `PRESETS` 2024, `applyPreset` 2038–2067, `resetColorAdj` 2069, `toggleTritone` 2073–2080, `updateColorAdj` 2082–2095, **`applyColorAdjustments` 2098–2206**, `clamp` 2208, `lerp` 2209, `hexToRgb` 2210–2215 |
| SHAPE | 2217–2235 | `setShape` 2218–2225, `toggleShapePreview` 2227–2234 |
| SHIRT BG | 2236–2244 | `setShirtBg` |
| EYEDROPPER | 2245–2292 | `toggleEyedropper` 2246–2257, `clearColors` 2259, klikkauskäsittelijä 2265–2280, `rgbToHex` 2282, `renderSwatches` 2286–2291 |
| MAGIC WAND | 2293–2508 | `onWandToleranceChange` 2298, `onHaloRemovalChange` 2303, `updateMagicWandBtn` 2309, `toggleMagicWand` 2316–2326, `ensureWandMask` 2329–2338, `pushWandSnapshot` 2342–2350, `wandUndo` 2352–2359, `wandClear` 2361–2368, `updateWandHistoryUI` 2370–2378, Cmd/Ctrl+Z-kuuntelija 2385–2394, **`magicWandFloodFill` 2399–2458**, wand-klikkaus (86 %:n muunnos) 2460–2507 |
| FILE UPLOAD | 2509–2558 | `handleFileUpload` 2510–2529, drag & drop 2532–2557 |
| UPSCALE | 2559–2652 | `setUpscaleMultiplier` 2560, `updateUpscaleInfo` 2568–2581, `doUpscale` 2583–2651 |
| LOGO | 2653–2764 | `handleLogoUpload` 2654–2671, `removeLogo` 2673–2680, `removeLogoBg` 2682–2740, `toggleLogoEnabled` 2748–2763 |
| AI GENERATION | 2765–2872 | **`generateImage` 2766–2871** |
| CANVAS RENDER | 2873–2983 | **`updateCanvas` 2874–2982** |
| SHAPE CLIP | 2984–3034 | `applyShapeClip` 2985–3033 |
| PROCESSED IMAGE | 3035–3111 | **`getProcessedImage` 3036–3110** |
| SHIRT SILHOUETTE | 3112–3136 | `drawShirtSilhouette` |
| DPI | 3137–3151 | `updateDPI` 3138–3150 |
| SHIRT PREVIEW | 3152–3233 | **`updateShirtPreview` 3153–3232** |
| BASE LAYER PREVIEW | 3234–3296 | **`updateBasePreview` 3235–3295** |
| CANVAS TAB SWITCH | 3297–3308 | `switchCanvasTab` |
| CMYK | 3309–3364 | `toggleColorspace` 3310–3318, `setColorspace` 3320–3323, `applyCMYKApprox` 3327–3363 |
| SHIRT PREVIEW EXPORT HELPER | 3365–3456 | `renderShirtPreviewForExport` 3368–3455 |
| CHANNEL SEPARATION | 3457–3520 | **`extractChannel` 3466–3511**, `CHANNEL_ANGLES` 3514–3519 |
| EXPORT | 3521–3715 | `updateExportBtn` 3522–3527, **`exportFiles` 3529–3714** |
| BBOX & TRIM HELPERS | 3716–3811 | `computeUnionBBox` 3720–3746, `trimCanvas` 3750–3758, *`applyShapeClipCtx` 3762–3810 (väärän bannerin alla)* |
| WebGL moottori | 3812–4231 | `_GL`-IIFE 3814–4133 (ks. alla), `applyHalftoneAlphaSafe` 4136, `applyErosion` 4139, *halftone-UI (väärän bannerin alla):* `updateHalftoneVals` 4143–4167, `htSyncNR` 4170, `htSyncNRf` 4177, `toggleHalftone` 4184, `toggleBaseHalftone` 4192, `toggleHalftoneMask` 4200, `setHtShape` 4210–4221, *`downloadCanvas` 4223–4230* |
| UTILS | 4232–4248 | `setApiStatus` 4233, `showToast` 4241 |
| COLOR SEPARATION | 4249–4608 | `kMeansClustering` 4253–4309, `colorName` 4312–4326, `rgbToHex2` 4328, `analyzeColors` 4332–4400, `renderColorPreview` 4402–4422, **`exportColorLayers` 4424–4607** |
| (init) | 4609–4613 | `loadFeatureStates`, `applyFeatureToggles`, `initCollapsibleSections`, `updateCanvas` |

### 3.3 `_GL`-IIFE:n sisältö (3814–4133)

| Osa | Rivit |
|---|---|
| `VS` (vertex shader) | 3815–3818 |
| `SHAPE_FN`: `shapeDist`, `cellUV`, `cellLocal` | 3819–3837 |
| `FS_COLOR` (värihalftone) | 3839–3856 |
| `FS_BASE` (pohjahalftone) | 3858–3880 |
| `FS_ERODE` (erosion, maks. 8 px) | 3882–3900 |
| Moduulin tila `_gl`, `_glCanvas`, `_progs`, `_buf`, `_fbo` | 3902 |
| `getGL` (yksi jaettu konteksti; `BLEND` päällä, pois 261104_010) | 3904–3927 |
| `getProg` | 3929–3938 |
| `makeTex` (FLIP_Y) | 3940–3954 |
| `setupQuad` | 3956–3963 |
| `setUni` | 3965–3971 |
| `to2D` | 3973–3978 |
| `ensureFBO` | 3980–3997 |
| `colorHalftone` (julkinen) | 4000–4017 |
| `baseHalftone` (julkinen) | 4019–4065 |
| `erode` (julkinen) | 4067–4082 |
| `fallback` (CPU-värihalftone) | 4085–4109 |
| `erodeCanvas` (CPU-erosion) | 4112–4130 |
| Julkiset funktiot `{ colorHalftone, baseHalftone, erode }` | 4132 |

---

## 4. Kuollut tai käyttämätön koodi

### 4.1 Funktiot, joita ei kutsuta mistään

| Funktio | Rivi | Huom. |
|---|---|---|
| `setView` (stub) | 1892 | Ainoat kutsut ovat kommentoidussa HTML:ssä (1071–1072). Alkuperäinen on kommentoitu 1883–1891. |
| `setColorspace` | 3320 | Kommentin mukaan "yhteensopivuuden vuoksi". Viittauksia ei ole. |
| `applyCMYKApprox` | 3327–3363 | CMYK-gamutin esikatselu, jota ei käytetä. CMYK-kytkin vaikuttaa vain kanavaerotteluun. |
| `downloadCanvas` | 4223–4230 | |
| `toggleHalftoneMask` | 4200–4208 | Nappia `halftoneMaskToggle` ei ole HTML:ssä. |

### 4.2 Kuolleet polut ja parametrit

- `_GL.baseHalftone`n `maskSrc`-haara (4025–4044) ja `ensureFBO` (3980–3997): ainoat kutsut (3281, 3614) välittävät `null`in.
- `FS_BASE`: uniformit `u_colorTex` ja `u_useMask` on määritelty (3860–3861) ja asetettu (4053, 4061), mutta shaderin runko ei käytä niitä.
- `baseHalftone`n `maskTex`-sidonta tekstuuriyksikköön 1 (4051–4054) ei käynnisty koskaan.

### 4.3 Käyttämättömät muuttujat ja kentät

- `state.processedImageData`, `state.currentView`, `state.halftoneMask`.
- `updateCanvas`: `const DPI = 300` (2895), `ph` (2894), `areaX`/`areaY` (2901–2902).
- `analyzeColors`: `pw` (4347).
- `removeLogoBg`: `cornerColors[1..3]` lasketaan, mutta vain `[0]` käytetään. Kommentti "most common corner color" ei vastaa toteutusta.
- `state.colorLayers[].positions`, `analysisW`, `analysisH` (4389–4391): tallennetaan, mutta `exportColorLayers` luokittelee pikselit uudelleen centroidien perusteella.
- `state.logoBgRemovedCanvas`: asetetaan 2725 ja nollataan heti blob-latauksen jälkeen 2733, joten se on käytännössä aina `null`. Lukukohdat (`|| state.logoImage`) ovat jäänteitä.
- `state.hasImage` ei palaa koskaan arvoon `false`.

### 4.4 CSS ja HTML

- View-toggle: `.view-toggle`, `.view-btn`, `.view-btn.active` (83–107), `body.view-editor` / `body.view-layout` (154–162). `<body>`ssa ei ole näitä luokkia.
- Kommentoitu view-toggle-HTML (1069–1074).

### 4.5 Duplikaatit (ei kuollutta, mutta kahdennettua)

| Mitä | Missä |
|---|---|
| `applyShapeClip` ja `applyShapeClipCtx` ovat identtiset | 2985–3033 / 3762–3810 |
| `rgbToHex` ja `rgbToHex2` ovat identtiset | 2282 / 4328 |
| Kuvan latauslogiikka | `handleFileUpload` 2514–2528 / drop 2540–2555 |
| 86 %:n sovituslaskenta | `updateCanvas` 2899–2911 / wand-klikkaus 2472–2482 |
| Paidan sijoittelulaskenta | `updateShirtPreview` 3172–3199 / `renderShirtPreviewForExport` 3393–3414 |
| Viennin `outW/outH` ja sijoittelu | `exportFiles` 3538–3557 / `exportColorLayers` 4435–4454 |
| Logon piirto | 2932, 2960, 3212, 3428, 3587, 4470 (kuusi kopiota, osin eri lähteellä: `exportFiles` käyttää `logoImage`a, muut `logoBgRemovedCanvas || logoImage`) |
| Halftone-solun laskenta `max(2, round(300/LPI))` | 3601, 4162, 4531 |

---

## 5. Ristiriidat CLAUDE.md:n ja koodin välillä

| # | CLAUDE.md sanoo | Koodi tekee |
|---|---|---|
| 5.1 | "WebGL engine … with CPU canvas fallbacks (`fallback`, `erodeCanvas`)" ja "WebGL-funktiot palauttavat AINA 2D-canvaksen" | `baseHalftone` palauttaa `null`, jos WebGL puuttuu (4021). Fallbackia ei ole. `exportFiles` antaa `null`in `computeUnionBBox`ille, ja `getContext` kaatuu. Seurauksena on toast "Vienti epäonnistui". `colorHalftone` ja `erode` noudattavat sääntöä. |
| 5.2 | Cmd/Ctrl+Z: `preventDefault()` aina, "kun fokus ei ole tekstikentässä" | Koodi ohittaa kaikki `INPUT`-elementit (2389): range, color, checkbox ja file. Kun slideria on juuri liikutettu, fokus on siinä, ja Cmd+Z menee selaimelle eikä wand-undoon. |
| 5.3 | Magic wand: toleranssi "sama metriikka kuin eyedropperilla" | Metriikka on sama (euklidinen × 2.2, `<`), mutta **syöte eroaa**. Wand vertaa alkuperäisen kuvan pikseleihin (2410), eyedropper avaintaa värisäädetystä kuvasta (3051), ja sen näyte otetaan renderöidystä esikatselusta (2272). |
| 5.4 | Sävysäädöt: "kanavakohtainen gamma laskee saturaatiota" | Gammasäätöä ei ole koodissa. Kanavittain tehdään lämpötila (+30/+5/−20), kirkkaus (additiivinen), kontrasti (keskipiste 128) ja posterize. Luminanssia (Rec.601, gamma-koodatusta sRGB:stä) käytetään vain saturaatiossa ja tritonessa (ks. 6.4). |
| 5.5 | "Max dot: 90 %" | `halftoneMaxSize` (oletus 0.92) on pisteen **säde** puolisolun yksikössä, ei pinta-ala. Ympyrän suurin peitto on π·0.46² ≈ 66 % solusta. **[koe]** Musta täysi sävy peitti 256/400 px (64 %). |
| 5.6 | "`FEATURE_SECTIONS` maps admin checkboxes to panel sections that get hidden/collapsed" | Osio saa luokat `disabled-step` + `collapsed`, eli UI lukittuu. **Asetukset jäävät voimaan:** esim. pois kytketyn halftone- tai taustanpoisto-osion arvot vaikuttavat edelleen esikatseluun ja vientiin. |
| 5.7 | "Preview vs export … e.g. `applyShapeClip` vs `applyShapeClipCtx`" | `applyShapeClipCtx` ei ole vientikohtainen: sitä käyttävät myös `updateShirtPreview` ja `updateBasePreview`. `applyShapeClip` on käytössä vain `updateCanvas`issa. Funktiot ovat identtiset. |
| 5.8 | "Reset the mask/history whenever a new main image is loaded" | Toteutuu kaikilla neljällä reitillä. Muu kuvakohtainen tila jää kuitenkin voimaan: `bgColors` (paitsi generoinnissa), `colorLayers` (värikerrosvienti jää aktiiviseksi vanhoilla kerroksilla) ja logo. |
| 5.9 | "Vanha view-toggle hylättiin, eikä sitä palauteta" | Hylätyn togglen jäänteet ovat edelleen koodissa (ks. 4.1, 4.4). |
| 5.10 | Päätökset: vaiheistettu työnkulku, Tallenna/Avaa projekti | Ei vielä toteutettu: kaikki vaiheet näkyvät samanaikaisesti, eikä tallennusta ole. (Tila, ei ristiriita.) |
| 5.11 | "`updateCanvas()` … also triggers `updateShirtPreview()` / `updateBasePreview()`" | `updateBasePreview` ajetaan vain, kun `baseHalftoneOn` on päällä. `rotSlider` ja `posX/Y` kutsuvat pelkkää `updateShirtPreview`ia, ja `logoSize` kutsuu sekä `updateCanvas`ia että `updateShirtPreview`ia (paita piirretään kahdesti). |

---

## 6. Avoimiin teknisiin kysymyksiin liittyvät kohdat

### 6.1 DPI-oletukset

Kovakoodatut 300 DPI:n kohdat:

| Rivi | Mitä |
|---|---|
| 2895 | `const DPI = 300` (`updateCanvas`, käyttämätön) |
| 3540–3541 | `exportFiles`: `outW/outH = cm × 300 / 2.54` |
| 3601 | `exportFiles`: `halftoneCellPx = max(2, round(300 / LPI))` |
| 4162 | `updateHalftoneVals`: `baseHalftoneCell = max(2, round(300 / LPI))` |
| 4437–4438 | `exportColorLayers`: `outW/outH` |
| 4531 | `exportColorLayers`: halftone-solu |
| 1804 | UI-teksti "· 300 DPI" |
| 3148–3149 | `updateDPI`: laaturajat 250 / 150 (efektiivinen DPI = lähdekuvan px / `sizeSlider`-tuumat) |

Havainnot:
- **Solukoko pyöristetään kokonaisiin pikseleihin**, joten todellinen LPI on `300 / round(300/LPI)`. Esimerkkejä: 45 → 7 px → 42,9 LPI; 20 → 15 px (tarkka); 25 → 12 px (tarkka); 30 → 10 px (tarkka); 120 → 3 px → 100 LPI. Kun yli 75 LPI, porrastus on karkea.
- **PNG-tiedostoissa ei ole DPI-metatietoa** (`canvas.toBlob` ei kirjoita pHYs-chunkia). RIP ei siis saa fyysistä kokoa tiedostosta.
- `analyzeColors`in `analysisSize = 300` (4348) on pikselileveys, ei DPI.

### 6.2 Erosion ja choke

Kaksi erillistä mekanismia, molemmat `_GL.erode`n kautta:

| | `haloRemoval` (värikerros) | `erosion` (pohjan choke) |
|---|---|---|
| UI | 0–10 px, oletus 0 | 0–20 px, oletus 2 |
| Sovelletaan | `getProcessedImage`issa jokaisessa polussa, vain jos taustaa on poistettu | vain `exportFiles` 3611, `colorCanvas`ille ennen pohjan rakentamista |
| Resoluutio | kunkin polun oma (~70…~1772 px) | 300 DPI → 1 px = 0,0847 mm; oletus 2 px ≈ 0,17 mm |

Toteutus (`FS_ERODE` 3882–3900):
- **Neliökernel** (Chebyshev-etäisyys `|dx| ≤ px` ja `|dy| ≤ px`), ei pyöreä. Kulmissa choke on √2-kertainen.
- **Binäärinen kynnys:** pikseli poistetaan, jos yksikin naapuri ikkunassa on alpha < 0,05. Puoliläpinäkyvät pikselit jäävät muuten koskematta.
- **Silmukka on rajattu ±8 px:iin**, joten slider-arvot 9–20 tuottavat WebGL:llä saman tuloksen kuin 8. CPU-fallback `erodeCanvas` (4112) noudattaa koko arvoa ja vertaa ehtoon `alpha === 0` (ei `< 0,05`), joten tulos eroaa WebGL-polusta.
- Kokonaispikselitarkkuus: viitteen 0,10 mm on 300 DPI:llä 1,18 px ja 600 DPI:llä 2,36 px.
- **Kiinteä pohja** (kun `baseHalftoneOn` ei ole päällä, 3624–3632): RGB asetetaan valkoiseksi, jos alpha > 10, mutta **alpha säilyy** (reunat ovat puoliläpinäkyviä). Pikselit, joiden alpha ≤ 10, jäävät alkuperäisen värisiksi pohjatiedostoon.
- Värikerrosta (`combinedCanvas`) ei kutisteta. Choke kohdistuu vain pohjaan, mikä on DTF:n oikea suunta.
- Myös erosion-passi kulkee blendauksen läpi (ks. 8.1). **[koe]** Puoliläpinäkyvä pikseli RGBA (199,100,50,128) muuttui arvoon (100,52,24,64). Läpinäkymättömät pikselit säilyvät ennallaan. **[korjattu: 261104_010]** Pikseli säilyy arvossa (199,100,50,128).

### 6.3 Pohjan halftone: ruudukko ja kulma suhteessa värikerrokseen

- **Sama ruudukkofunktio:** sekä `FS_COLOR` että `FS_BASE` käyttävät `cellUV`- ja `cellLocal`-funktioita (`SHAPE_FN` 3826–3836). Pikselikoordinaatit ovat `v_uv × u_res`, ja origo on canvaksen **vasen alakulma** (`UNPACK_FLIP_Y`, 3949). Kierto tehdään origon ympäri.
- **Sama canvas-koko viennissä:** molemmat rasteroidaan `outW × outH`-kokoisina ennen trimmausta, joten ruudukot ovat samassa vaiheessa (phase). **Ne osuvat kohdalleen vain, jos solu (LPI) ja kulma ovat samat.**
- **Oletukset eroavat:** värikerroksella 45 LPI / 45°, pohjalla 45 LPI / **75°**. Viitestandardissa molemmilla on sama kulma.
- **Pohjan solun alkuarvo ei vastaa slideria:** `state.baseHalftoneCell = 10` px (= 30 LPI), slider näyttää 45 LPI (→ 7 px). Arvo korjautuu vasta, kun mitä tahansa halftone-slideria liikutetaan (`updateHalftoneVals`).
- Pisteen koko lasketaan solun keskipisteestä otetusta näytteestä (`texture2D(u_img, sUV)`), ja solu ilman väriä (alpha < 0,05 keskellä) jää tyhjäksi. Logiikka on sama molemmissa kerroksissa.
- Pohjan pisteen säde = `density × dotScale × cellAlpha` (oletus 0,80 × 0,88 = 0,704 puolisoluyksikköä → ympyrä peittää noin 39 % solusta). Säde ei riipu luminanssista.
- **CPU-fallback** (`fallback`, 4085) kiertää canvaksen **keskipisteen** ympäri, ohittaa `maxSize`- ja `shape`-asetukset (kovakoodattu 0,92 ja ympyrä) eikä vastaa shaderin ruudukkoa. Pohjalle fallbackia ei ole lainkaan.
- **Kanavaerottelun kulmat** (`CHANNEL_ANGLES`: R15/G75/B45, C15/M75/Y0/K45) ovat kiinteät eivätkä riipu käyttäjän kulmasta. Yhdistetty värikuva käyttää `halftoneAngle`a.
- Esikatselussa origo on 500×600-pääcanvaksen vasen alakulma, eikä ruudukko vastaa viennin ruudukkoa.

### 6.4 Sävysäätöjen laskentatapa

`applyColorAdjustments` (2098–2206). Säädöt tehdään pikseleittäin tässä järjestyksessä, 8-bittisinä ja gamma-koodatussa sRGB:ssä (ei linearisointia), ja jokainen vaihe pyöristetään ja leikataan välille 0–255 (`clamp`):

| # | Säätö | Kaava | Kanavittain vai luminanssi |
|---|---|---|---|
| 1 | Lämpötila | R += t·30, G += t·5, B −= t·20 | kanavittain |
| 2 | Kirkkaus | kaikki += b·2,55 | kanavittain (additiivinen) |
| 3 | Kontrasti | `f·(c−128)+128`, `f = 259(C+255)/(255(259−C))` | kanavittain |
| 4 | Saturaatio | `lum + s·(c−lum)`, lum = Rec.601 (0,299/0,587/0,114) | luminanssiin ankkuroitu |
| 5 | Posterize | `round(c/255·(n−1))/(n−1)·255` | kanavittain |
| 6 | Tritone | Rec.601-luminanssi → 3-värigradientti, lerp voimakkuudella | luminanssi |

- Kanavittainen leikkaus kirkkaudessa ja kontrastissa muuttaa sävyä (hue) ja saturaatiota lähellä ääripäitä. Mitään säätöä ei tehdä havaintopohjaisessa avaruudessa (esim. OKLab).
- Halftone käyttää myös Rec.601-luminanssia gamma-koodatusta RGB:stä (`FS_COLOR` 3851).
- **Sävyvaste rasterissa:** säde on `(1 − br) × maxSize`, joten peitto kasvaa neliöllisesti. **[koe]** Solusta 20×20 px harmaa 191 peitti 16 px (4 %), harmaa 128 peitti 60 px (15 %) ja musta 256 px (64 %). Blendauksen poiston jälkeen (261104_010) samalla mittarilla (alpha > 127) 16 / 68 / 268 px, koska pisteen antialias-reunan alpha ei enää korotu toiseen potenssiin. Neliöllinen sävyvaste ei muuttunut. Dot gain -kompensaatiota tai tonaalista linearisointia ei ole.
- **Väripisteet ovat solun keskipisteen värisiä** (`gl_FragColor = col.rgb`), eli värikerroksen halftone ei ole kanavaerottelu vaan "värillinen AM". Valkoiset ja hyvin vaaleat alueet (br → 1) tuottavat pisteen nollakoolla, eli ne katoavat rasteroidusta yhdistetystä kuvasta.

### 6.5 Max dot

- **Värikerros:** `halftoneMaxSize` (UI 10–100 → 0,10–1,00, oletus 0,92) on säde suhteessa puoleen solusta. Ympyrämuoto koskettaa naapuria arvolla 1,0 ja peittää solun kokonaan vasta noin arvolla 1,41, jota UI ei salli. Täysi sävy jättää siis aina aukkoja, oletuksella noin 34 %.
- Muodot (`shapeDist`): 0 = ympyrä, 1 = ellipsi (y × 1,6), 2 = timantti (L1), 3 = viiva (|y| × 2,5). Sama `maxSize` tuottaa eri muodoilla eri peiton.
- **Kanavaerottelu ei ole AM-rasteria.** `extractChannel` kirjoittaa mustan pikselin, jonka alpha on tiheys. Koska br = 0, `FS_COLOR` piirtää **joka soluun maksimikokoisen pisteen**, ja tiheys koodautuu pisteen läpinäkyvyyteen. **[koe]** Tiheyksillä 0,25 / 0,5 / 1,0 piste peitti aina 276/400 px. Keskipisteen alpha oli 16 / 64 / 255 eli tiheys², blendauksen vuoksi (8.1). **[korjattu: 261104_010]** Keskipisteen alpha on nyt 64 / 128 / 255 eli tiheys. Kanavaerottelu ei silti ole AM-rasteria.
- **Pohja:** max dot = `density × dotScale` (oletus 0,704).

---

## 7. Arvio: PDF-vienti omalla valkoisella kanavalla

Vain arvio. Viitetiedoston rakenne CLAUDE.md:n mukaan: RGB + SMask, valkoinen omana `/Separation White` -kanavana + SMask, overprint, valkoinen ensin, 600 DPI, PDF 1.4.

### 7.1 Mitä nykyisestä polusta on käytettävissä

- `exportFiles`in vaiheen 6 jälkeen (3669–3670) on kaksi samaan bboxiin trimmattua, samankokoista canvasta: `trimmedCombined` (RGB + alpha) ja `trimmedBase` (valkoinen + alpha). **Kohdistus on siis jo valmis**, ja molemmat voidaan sijoittaa PDF-sivulle samaan paikkaan.
- Choke (`erosion`) ja pohjan rakentaminen on erotettu värikerroksesta.
- JSZip on käytössä, joten PDF voidaan liittää samaan ZIPiin.

### 7.2 Mitä puuttuu

| Osa | Nykytila | Mitä vaaditaan |
|---|---|---|
| PDF-kirjoitin | ei ole | Objektit, `xref`, trailer, streamit. Käsin kirjoitettuna tämä on rajattu ongelma, koska sivulla on vain kaksi kuvaa. Valmis kirjasto olisi uusi riippuvuus ja vaatii erillisen päätöksen. Ei tiedossa, tukeeko kevyt kirjasto Separation-väriavaruutta ja SMaskia suoraan, vaatii selvityksen. |
| Pakkaus (FlateDecode) | JSZip ei tarjoa raakaa deflatea julkisesti | Natiivi `CompressionStream('deflate')` tuottaa zlib-muotoa, joka käy suoraan FlateDecodeen (Chrome 80+, Safari 16.4+). Uutta riippuvuutta ei tarvita. |
| RGB + SMask | RGBA-canvas | `getImageData` → erottelu 3-kanavaiseksi DeviceRGB-streamiksi ja 1-kanavaiseksi DeviceGray-SMaskiksi. Huom: canvas säilyttää datan premultiplied-muodossa, joten matalan alphan pikseleiden värit ovat jo valmiiksi epätarkkoja. |
| Valkoinen kanava | RGBA, valkoinen + alpha (tai harmaa reunoilla blendauksen vuoksi) | Muunto yksikanavaiseksi tinttiarvoksi (todennäköisesti alpha, puhtaimmin ennen blendausvirheitä) `/Separation /White /DeviceCMYK <tint transform>` -väriavaruudessa, SMaskin kanssa tai ilman. Tint transform -funktio (Type 2) vaihtoehtoisen näyttövärin tuottamiseen. |
| Overprint | ei ole | `ExtGState` `/OP true /op true /OPM 1` valkoiselle. |
| Piirtojärjestys | – | Sisältöstream: ensin valkoinen kuva, sitten RGB-kuva, molemmat samalla `cm`-matriisilla. |
| Sivukoko | px | `MediaBox` = bbox_px / DPI × 72 pt. |
| DPI | kovakoodattu 300 (6.1) | Parametrisointi kaikkiin kohtiin. Lisäksi solukoko, choke ja halo-poisto pikseleinä muuttuvat DPI:n mukana. |
| Värinhallinta | ei ole | DeviceRGB vai ICCBased sRGB / OutputIntent: riippuu RIPistä. |
| Kanavaerottelut (R/G/B, CMYK) | aina mukana ZIPissä | Viite-PDF:ssä niitä ei ole: RIP erottelee itse. |

### 7.3 Isoimmat epävarmuudet

1. **Rasteroiko RIP itse?** Viitteen min dot 0,25 mm, max dot 90 % ja kulma 22,5° voivat olla RIPin rasteriasetuksia. Jos RIP rasteroi, PDF:ään viedään contone-RGB ja contone-valkoinen, eikä sovelluksen halftone-polkua käytetä PDF:ssä lainkaan. Jos taas tiedoston pitää olla valmiiksi rasteroitu, rasterin laatuongelmat (6.4, 6.5, 8.1) tulevat PDF:n mukana. **Tämä kysymys ratkaisee suurimman osan työmäärästä.**
2. **Muisti 600 DPI:llä.** Tulostusala 30 × 36 cm on 7087 × 8504 px ≈ 60 Mpx ≈ 240 Mt RGBA-dataa canvasta kohden. `exportFiles` pitää samanaikaisesti muistissa noin 10 täysikokoista canvasta (`colorCanvas`, `shapeCanvas`, `combinedCanvas`, `erodedSource`, `baseCanvas`, 3–4 kanavaa ja jokaisen `to2D`-kopio), mikä tekee yli 2 Gt. Lisäksi WebGL:n `MAX_TEXTURE_SIZE` on monella GPU:lla 8192 (< 8504), ja Safarilla on omat canvas-muistirajansa. 300 DPI:llä sama on noin 15 Mpx (~60 Mt / canvas).
3. **Tulkitseeko RIP valkoisen kanavan harmaat suhteellisena peittona?** (CLAUDE.md:n porraskiilatesti.)

### 7.4 Karkea työmääräarvio

- PDF-kirjoitin (objektit, Separation, SMask, ExtGState, deflate): noin 150–250 riviä.
- Integraatio `exportFiles`iin (datan erottelu, ZIP tai erillinen lataus): noin 50 riviä.
- DPI-parametrisointi: noin 8 kohtaa (6.1).
- Muistin hallinta 600 DPI:llä (työskentely bboxin kokoisena, canvasten vapautus, mahdollinen paloittelu): laajuus on epävarma ja riippuu kohdasta 7.3.1.
- Verifiointi: Acrobatin Output Preview (separaatiot ja overprint) sekä koeajo RIPissä (CADlink vahvistamatta).

---

## 8. Riskit ja hauraat kohdat

### 8.1 WebGL-renderöinti

- **Blendaus tuplaa alphan [koe]. [korjattu: 261104_010]** `getGL` kytkee blendauksen pois (`gl.disable(gl.BLEND)`), ja shaderin tulos kirjoitetaan puskuriin sellaisenaan. Alkuperäinen havainto: `getGL` kytkee `gl.BLEND`in (`SRC_ALPHA, ONE_MINUS_SRC_ALPHA`) pysyvästi päälle (3924–3925), ja jokainen passi piirtää tyhjään (0,0,0,0) puskuriin. Tämän seurauksena jokaisessa WebGL-passissa puoliläpinäkyvän pikselin väri kerrotaan alphalla ja alpha korotetaan toiseen potenssiin. Kokeessa:
  - erode: (199,100,50,128) → (100,52,24,64)
  - colorHalftone, musta alpha 128 → alpha 64
  - baseHalftone: valkoinen alpha 128 → (128,128,128,64), eli pohjatiedostoon tulee harmaata eikä valkoista

  Vaikutus kohdistuu pisteiden antialias-reunoihin, kuvan reunoihin, halo-poistoon ja choke-passiin. Läpinäkymättömät pikselit eivät muutu.
- **Tekstuurin `LINEAR`-suodatus sekoittaa suoraa alphaa [koe].** `FS_COLOR` ottaa näytteen solun keskipisteestä, joka osuu yleensä pikselien väliin. Kuvan reunalla näyte sekoittuu läpinäkyvän (0,0,0,0) naapurin kanssa, jolloin reunan pisteen väri tummuu ja piste kasvaa. Koe 7 (`tools/alpha_selainkoe.js`): (200,100,50)-kiekon reunapisteistä 104/702 pikseliä poikkesi värisävyltään, enimmillään 55 yksikköä.
- **Kontekstin menetystä ei käsitellä** (`webglcontextlost`). `_gl` jää viittaamaan kuolleeseen kontekstiin, eikä tuloksesta saa virhettä. Riski kasvaa suurissa vienneissä.
- **`precision mediump float`** kaikissa fragment shadereissa. Pikselikoordinaatit ovat viennissä tuhansia (esim. 4252). Jos GPU toteuttaa mediumpin oikeana fp16:na (mobiili, mahdollisesti osa Safari/Metal-poluista), ruudukon tarkkuus on suurilla koordinaateilla luokkaa 2–4 px. Työpöytä-Chromessa mediump on yleensä käytännössä highp. **[päätelty]**
- **Yksi jaettu GL-canvas ja -konteksti** muuttaa kokoaan jokaisen kutsun mukana (esikatselu ↔ vienti). Turvallisuus nojaa siihen, että jokainen julkinen funktio palauttaa `to2D`-kopion.
- **Fallbackien erot:** `fallback` ja `erodeCanvas` tuottavat eri tuloksen kuin shaderit (ks. 6.2 ja 6.3). Pohjalle fallbackia ei ole (5.1).

### 8.2 Vienti

- **Asetuksia luetaan kesken viennin.** `exportFiles` antaa selaimelle vuoron (`await setTimeout 30`) vaiheiden välissä (3608, 3635, 3653) ja lukee tilaa uudelleen myöhemmissä vaiheissa (esim. `state.halftoneMaxSize`, `state.halftoneShape`, `state.cmykMode`). Vain vientinappi lukitaan, joten käyttäjä voi muuttaa slidereita kesken viennin, ja yhteen ZIPiin voi päätyä sekaisin asetuksia. **[päätelty]**
- **Hiljainen leikkaus:** kuva sijoitetaan `posX·outW, posY·outH`-pisteeseen. Sisältö, joka menee tulostusalueen yli, leikkautuu ilman varoitusta. Näin käy esim. kun `sizeSlider` (maks. 30 cm) > `adminW`, kun korkea kuva ylittää `adminH`:n (koko määrää vain leveyden) tai kun kuva sijoitetaan reunalle tai kierretään. Paitaesikatselu ei leikkaa.
- **Bbox ja alpha:** `computeUnionBBox` laskee mukaan kaikki pikselit, joiden alpha > 0, myös yksittäiset alpha 1 -jäänteet.
- **`exportColorLayers`:**
  - Jokaiselle kerrokselle piirretään koko kuva uudelleen, ja jokainen pikseli luokitellaan uudelleen. Työ on O(kerrokset × pikselit × k).
  - Kerrokset ovat tasavärisiä, joten halftone saa pisteen koon kerroksen värin kirkkaudesta, ei pikselin sävystä.
  - Pohjakerrosta ei synny.
  - Bboxin yhdistämissilmukka (4549–4558) käyttää `bbox`ia ennen null-tarkistusta (4559).

### 8.3 Tila ja syötteet

- **Vanhentunut tila uuden kuvan jälkeen:** `bgColors` säilyy uploadin, dropin ja upscalen jälkeen. `colorLayers` säilyy aina, joten "Vie värikerrokset" jää aktiiviseksi edellisen kuvan kerroksilla. Myös logo säilyy.
- **Eyedropper** ottaa näytteen renderöidystä pääcanvaksesta (2272). Näyte voi osua halftone-pisteisiin, logoon tai `#1a1a1a`-taustaan. Koska avainnus tehdään värisäätöjen jälkeen, säätöjen muuttaminen jälkikäteen mitätöi valitut värit.
- **Feature-togglet** eivät kytke asetuksia pois (5.6).
- **Desimaalipilkku:** `adminW`/`adminH` ovat tekstikenttiä, ja `parseFloat("30,5")` = 30.
- **Cmd/Ctrl+Z ja fokus** (5.2).
- **Upscale:** 10 s:n turvatimeri (2596) voi laueta kesken hitaan mutta onnistuvan `toBlob`in. Käyttäjä saa virheilmoituksen ja nappi vapautuu, minkä jälkeen onnistuminen ajetaan vielä erikseen. 4× suurelle lähdekuvalle voi ylittää selaimen canvas-rajat.
- **Kuvan lataus ilman `onerror`ia** (`generateImage` 2837, upload, drop, logo): jos vastaus ei ole kuva, mitään ei tapahdu eikä virhettä näytetä.
- `setHtShape('base', …)` päivittää näkymän vain, jos värikerroksen halftone on päällä (4220). Pohjaesikatselu ei siis päivity muodon vaihtuessa.
- `generateImage`n virheteksti "tarkista token" on vanhentunut, koska token on Workerissa.

### 8.4 Suorituskyky

- Jokainen slider-`input` ajaa `updateCanvas`in ilman debouncea tai `requestAnimationFrame`a: `getProcessedImage` 1–3 kertaa (pää, paita, pohja), uudet canvakset joka kerta ja mahdollisesti WebGL-passit.
- `magicWandFloodFill` piirtää ja lukee koko lähdekuvan joka klikkauksella (`getImageData` + `visited` w×h). 4096²-kuvalla se tarkoittaa noin 64 Mt + 16 Mt klikkausta kohden, ja JS-taulukkopino voi kasvaa suureksi.
- `getImageData`-kutsuja tehdään ilman `willReadFrequently`-vihjettä.

### 8.5 Ylläpidettävyys

- **Duplikaatit** (4.5): kun yhtä kopiota muutetaan, muut jäävät jälkeen. Esikatselun ja viennin erot (1.4) ovat osin tällaista ajautumista.
- **Inline-handlerit globaaleihin nimiin:** funktion uudelleennimeäminen rikkoo HTML:n hiljaa, eikä virhettä näy ennen klikkausta.
- **Koordinaattimuunnos** (86 %:n sovitus) on kahdessa paikassa. Jos esikatselun asettelu muuttuu, wand-klikkaus osuu väärään kohtaan.
- **Väärän bannerin alla olevat funktiot** (3.2) vaikeuttavat grep-navigointia.
- **Nimet:** `halftoneCell` ja `baseHalftoneCell` ovat UI:ssa LPI-arvoja, mutta `state.baseHalftoneCell` on pikseleitä.

### 8.6 Ulkoiset riippuvuudet

- JSZip ladataan ajon aikana cdnjs:stä, joten vienti ei toimi ilman verkkoyhteyttä.
- Worker-URL (2802) on julkinen eikä vaadi tunnistusta (todetaan vain).

---

## Liite: selainkokeet (2026-11-03)

Ajettu selainpaneelissa (`file://…/index.html`, Chromium 152, WebGL käytössä) konsolista kutsumalla `_GL`-funktioita 40×40 px:n testicanvaksille. Koodia ei muutettu.

| Koe | Syöte | Tulos |
|---|---|---|
| `_GL.erode(c, 1)` | tasainen (200,100,50), alpha 128 | keskipikseli (100,52,24,**64**) |
| `_GL.erode(c, 1)` | tasainen (200,100,50), alpha 255 | (200,100,50,255), ei muutosta |
| `_GL.colorHalftone(c, 20, 0, 0.92, 0)` | musta, alpha 128 | solun keskus alpha **64** |
| `_GL.baseHalftone(c, 20, 0, 0.8, 0.88, 0)` | alpha 128 | solun keskus (128,128,128,**64**) |
| `colorHalftone`, musta alpha 64/128/255 | tiheys 0,25/0,5/1,0 | peitto aina 276/400 px; keskus-alpha 16/64/255 |
| `colorHalftone`, harmaa 191/128/0, alpha 255 | sävy | peitto (alpha > 127) 16/60/256 px / 400 |

Safarilla kokeita ei ajettu.

### Vaihe A1: toistettava koe `tools/alpha_selainkoe.js` (2026-11-04)

Koe liitetään index.html:n konsoliin (ohje tiedoston alussa). Se tulostaa jokaisesta kohdasta PASS / FAIL / PUUTTUU. Toleranssi ±2 johtuu 2D-canvaksen premultiplied-tallennuksesta.

| # | Koe | Lähtötaso (`ca3c6a9`) | Blendaus pois (`261104_010`) |
|---|---|---|---|
| 1 | `erode`, (200,100,50) alpha 128 | FAIL (100,52,24,64) | PASS (199,100,50,128) |
| 2 | `erode`, alpha 255, sisäosa bitintarkka | PASS | PASS |
| 3 | `colorHalftone`, musta alpha 64 / 128 / 255, keskus | FAIL 16 / 64 / 255 | PASS 64 / 128 / 255 |
| 4 | `colorHalftone`, läpinäkymätön (200,100,50), sävy pisteiden reunoilla | FAIL 140/1582, ero ≤ 100 | PASS 0/1641, ero ≤ 2 |
| 5 | `baseHalftone`, alpha 128, keskus | FAIL (128,128,128,64) | PASS (255,255,255,128) |
| 6 | `baseHalftone`, kaikki pikselit valkoisia | FAIL 176/176 harmaata | PASS 0/176 |
| 7 | reunus: (200,100,50)-kiekon reunapisteiden sävy | FAIL 112/638, ero ≤ 118 | FAIL 104/702, ero ≤ 55 (`LINEAR`-suodatus, 8.1) |
| 8 | kontekstin menetys | PUUTTUU | PUUTTUU |

Ajettu: Chromium 152. Safari: ei vielä ajettu.
