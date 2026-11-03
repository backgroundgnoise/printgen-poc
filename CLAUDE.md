# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Printgen v3 is a proof-of-concept DTF (direct-to-film) print preparation tool: generate an image with AI (or upload one), clean up its background, adjust colors/halftone, preview it on a shirt, and export print-ready layered PNGs in a ZIP.

The entire app is a single self-contained file, `index.html` (~4600 lines: CSS, markup, and one inline `<script>`). There is no build system, package manager, linter, or test suite. To run it, open `index.html` in a browser (or serve the directory with any static server, e.g. `python3 -m http.server`). External dependencies are loaded from CDNs only: JSZip 3.10.1 (cdnjs) and Google Fonts.

The UI text and most code comments are in **Finnish** — keep new UI strings and comments in Finnish to match.

## Architecture (inside `index.html`)

The script is organized into sections marked with `// ===== SECTION NAME =====` banners; grep for these to navigate.

- **Global `state` object** (top of the script) holds all app state: the source image (`mainImage`), logo, bg-removal colors, halftone settings, magic-wand mask and undo history, prompt presets, CMYK mode, color layers, etc. Many settings are *not* in `state` but read directly from DOM inputs by id (`adminW`/`adminH` print area in cm, `sizeSlider`, `posX`/`posY`, `rotSlider`, `erosion`, `maskScale`, `halftoneCell`, …). Functions are global and wired via inline `onclick`/`oninput` attributes.
- **AI generation** (`generateImage`): POSTs `{inputs, parameters}` to a Cloudflare Worker proxy (`https://hf-proxy-poc.bgnoiseandthecubicles.workers.dev`) in front of a Hugging Face FLUX model; the response is an image blob. The prompt is assembled from the user text + optional `PROMPT_STYLES[state.promptStyle]` + `PROMPT_BACKGROUNDS[state.promptBackground]` (solid white/black backgrounds are deliberate so background removal doesn't leave halos). A 503 means model cold start.
- **Background removal**: color-key removal against eyedropper-picked `bgColors` with tolerance (`getProcessedImage`), plus a region-based magic wand (`magicWandFloodFill`) that writes into `state.wandMask` (Uint8Array, source-image sized) with snapshot undo (Cmd/Ctrl+Z, max `WAND_HISTORY_MAX`). Reset the mask/history whenever a new main image is loaded.
- **Rendering**: `updateCanvas()` is the central redraw for the preview canvas and also triggers `updateShirtPreview()` / `updateBasePreview()`. Call it after any state change.
- **Preview vs export are separate code paths.** The preview fits the image centered in the canvas; `exportFiles()` and `exportColorLayers()` re-render at full print resolution (300 DPI from the admin print-area cm size) using size/position/rotation inputs, and `renderShirtPreviewForExport()` re-implements the shirt mockup. A change to the image pipeline (bg removal, clip shapes, logo, halftone, erosion) usually needs to be made in both preview and export paths — e.g. `applyShapeClip` vs `applyShapeClipCtx`.
- **Export**: `exportFiles()` builds a base color image, combined color image (with optional halftone), white underbase layer, and RGB/CMYK channel separations, computes a union bounding box, trims all layers to it, and zips them with JSZip. `exportColorLayers()` does k-means color separation (`analyzeColors`/`kMeansClustering`) into per-color layers.
- **WebGL engine** (`_GL` IIFE): shader-based color halftone, base (underbase) halftone, and alpha erosion, with CPU canvas fallbacks (`fallback`, `erodeCanvas`) when WebGL is unavailable.
- **Admin modal / feature toggles**: `FEATURE_SECTIONS` maps admin checkboxes to panel sections that get hidden/collapsed; state persists in `localStorage` under `printgen_features`.

---

# Projektin päätökset ja työtavat

Alla oleva osa on kirjoitettu keskusteluissa tehtyjen päätösten pohjalta. Koodista sitä ei näe. Lue se ennen kuin ehdotat muutoksia.

## Työtavat

- **Kieli:** vastaa käyttäjälle suomeksi. Tekniset termit englanniksi sulkeissa, kun ne ovat työkalun valikoissa tai koodissa.
- **Käyttäjä ei ole JavaScript-ekspertti**, mutta ymmärtää logiikkaa ja arkkitehtuuria hyvin (tausta node-pohjaisissa ympäristöissä). Selitä *miksi* ennen *mitä*.
- **Suunnittelu ennen koodia.** Trade-offit, vaihtoehdot, liukusäätimien asteikot ja parametrien yksiköt päätetään yhdessä ennen toteutusta. Esitä suunnitelma ja odota hyväksyntää ennen kuin muokkaat koodia.
- **Askel kerrallaan.** Pienet, erikseen testattavat muutokset. Yksi asiakokonaisuus per commit.
- **Testaus:** käyttäjä testaa Safarilla ja Chromella. Kerro jokaisen muutoksen jälkeen, mitä ja miten testataan. Syntaksivirheisiin puututaan heti.
- **Ei uusia riippuvuuksia, frameworkeja tai build-vaihetta** ilman erillistä päätöstä.
- **Session lopussa:** jos koodi muuttui, päivitä `docs/`-kansion dokumentit (kun ne ovat olemassa) samassa commitissa.

## Git-säännöt

- Kaikki työ tehdään `dev`-haarassa. GitHub Pages julkaisee `main`-haaran, ja sitä katsovat kumppanit.
- **Älä koskaan pushaa `main`iin, mergeä `main`iin tai käytä `--force`a** ilman käyttäjän nimenomaista pyyntöä.
- Commit-viestit suomeksi. Muoto jatkaa vanhaa versiointikonventiota: `YYMMDD_NNN lyhytKuvaus: mitä muuttui`.
- **Repo on julkinen.** Älä commitoi salaisuuksia (HF-token on vain Cloudflaren ympäristömuuttujana), rahoitustietoja, kumppanien nimiä tai kumppanien materiaalia.

## Kriittiset arkkitehtuurisäännöt

- **WebGL-funktiot palauttavat AINA 2D-canvaksen** (`to2D`-kopio ennen returnia). Downstream (`getImageData`, CMYK, kanavaerottelu) olettaa 2D-canvaksen.
- **Cmd/Ctrl+Z:** `preventDefault()` kutsutaan aina, kun fokus ei ole tekstikentässä, vaikka undo-pino olisi tyhjä. Muuten selain saa pikanäppäimen ja voi nollata sivun tilan.
- **Magic wand** vertaa aina lähtöpikseliin (ennustettavuus). Toleranssi = RGB-euklidinen etäisyys × 2.2, sama metriikka kuin eyedropperilla. Klikkauksen koordinaattimuunnos huomioi, että kuva piirretään keskitettynä 86 %:n alueelle, ei koko canvakselle.
- **Pohjakerros** on alpha-pohjainen: pisteen koko = density × dotScale × alpha, jotta valkoinen ei vuoda reunoilla.
- **Logo:** `state.logoStrength` on 0 (päällä) tai 100 (pois). img2img-toimintoa ei ole toteutettu, eikä vanha slider-käyttöliittymä palaa.
- **Esikatselu ja vienti:** kuvaketjun muutos tehdään aina molempiin polkuihin. Mainitse suunnitelmassa erikseen, miten molemmat katetaan.

## Suunta: intent/execution-datamalli (lukittu 8/2026)

| Kerros | Muoto | Rooli |
|---|---|---|
| Lähde | PNG | Aito lähde. Recipe viittaa nimellä + sisältö-hashilla, ei upoteta. |
| Recipe (intent) | JSON | Laiteriippumaton järjestetty askellista: upscale, taustanpoisto, värisäädöt, posterize/tritone, clip, asemointi, halftone-intentti (LPI-tavoite, kulma, muoto), separaatiovalinta. |
| Profiili | JSON | Mitattu per (printteri × muste × filmi × jauhe × kangas): dot gain, pohjan tiheys, max LPI, musteraja, choke, kohdistustoleranssi, kutistuma, värimuunnos. |
| Execution | ZIP/PDF | Johdettu: recipe × profiili. Uudelleenluotava, ei aito lähde. |

Rajatapaus: halftone-kulma ja -muoto ovat intentiä, suurin toimiva LPI ja choke ovat profiilia.
Uusia ominaisuuksia suunniteltaessa kysy: kuuluuko tämä parametri recipeen vai profiiliin?

## Päätökset

- **Vaiheistettu työnkulku** Lähde → Käsittely → Asemointi → Vienti, state-ohjattu näytä/piilota yhdessä tiedostossa. Vanha view-toggle hylättiin sekavana, eikä sitä palauteta.
- **Tallenna/Avaa projekti** (JSZip, client-side): recipe + lähde (+ maski). Tekee recipe-kerroksesta todellisen.
- **Modulaarinen pilkkominen (Vite/esbuild) on LYKÄTTY.** Laukaisin: ominaisuudet lukittuvat TAI uusi kehittäjä tulee mukaan. Älä pilko tiedostoa omasta aloitteestasi.
- **Selvitettävänä, ei päätetty:** erotetaanko loppukäyttäjän näkymä painotalon kalibrointityökalusta.

## Avoimet tekniset kysymykset (DTF-testipainatukset 11/2026)

Kohdeympäristö: Sublistar DTF -tulostin. RIP todennäköisesti CADlink, vahvistamatta.

Kumppanin tuotannossa toimiva viitetiedostorakenne: RGB + SMask, valkoinen omana `/Separation White` -kanavana + SMask, overprint, valkoinen ensin, 600 DPI, PDF 1.4, choke 0.10 mm, min dot 0.25 mm, max dot 90 %, kulma 22.5°.

- **DPI:** vienti on kovakoodattu 300 DPI:hin (`cellPx = Math.round(300 / LPI)`). Viitestandardi on 600 DPI. 300 DPI:ssä 0.25 mm:n min dot on ~3 px ja 0.05 mm:n choke alle pikselin.
- **Choke:** nykyinen erosion toimii kokonaisina pikseleinä. Vaihtoehto: laske choke halftone-shaderissa analyyttisesti (valkoisen pisteen säde = värisäde − choke), jolloin se on alipikselitarkka. Vakiochoke syö pieniä pisteitä suhteessa enemmän (50 %:n sävyssä valkoisen peitto 64 % / 57 % / 50 % LPI:llä 20 / 25 / 30).
- **Pohjan rekisteröinti:** tarkista, käyttääkö pohjan halftone samaa ruudukkoa ja kulmaa kuin värikerros. Viitestandardissa molemmilla on sama kulma.
- **Sävysäädöt:** kanavakohtainen gamma laskee saturaatiota. Sävysäädöt pitäisi tehdä luminanssille (esim. OKLab), jolloin sävy ja kroma säilyvät.
- **Max dot:** 90 % jättää täysiin sävyihin tummat reiät. Kuuluu intentiin (rasteri-ilme).
- **LPI-tasot:** ehdotus 20 (tyyli) ja 25 (detalji), 30 pois. Ei vielä vahvistettu samalla aineistolla.
- **Kompaktit alueet** (logot, tasaiset värit): contone + epätasainen valkoinen pohja (esim. 85–100 %, kohinamoduloitu, kiinteä siemen toistettavuutta varten). Riippuu siitä, tulkitseeko RIP valkoisen kanavan harmaat suhteellisena peittona. Selvitetään porraskiilatestillä.
- **Recipe-valmius:** osa asetuksista asuu DOM-kentissä eikä `state`-objektissa. Ennen recipe-sarjallistamista tarvitaan yksi totuuden lähde.
- **PDF-vienti omalla valkoisella kanavalla** on kumppanien toivoma suunta.
