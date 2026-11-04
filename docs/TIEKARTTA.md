# TIEKARTTA — Printgenin kehitysjärjestys

Laadittu 2026-11-04. Pohjana ovat `docs/CODEMAP.md` (commit `31c308f`) ja painotalon koeajon kuvat (Sublistar-kone, max-LPI-haitari ja tiheysporras, filmi ja paita).

Dokumentti kertoo, **missä järjestyksessä** asioita tehdään ja **miksi**. Toteutuksen yksityiskohdat päätetään vaihe kerrallaan ennen koodia. Rivinumerot ovat CODEMAPissa.

Merkinnät:
- **[vahvistettu]**: nähty koodista, selainkokeesta tai tulosteesta.
- **[oletus]**: todennäköinen tulkinta, vahvistettava ennen kuin sen varaan rakennetaan.

---

## 1. Lähtötilanne lyhyesti

CODEMAPin keskeiset löydökset:

1. WebGL-blendaus korottaa alphan toiseen potenssiin jokaisessa passissa, ja pohjan reunat harmaantuvat. [vahvistettu]
2. Rasterin säde on verrannollinen tummuuteen, joten peitto kasvaa neliöllisesti: keskiharmaa peittää noin 15 %. [vahvistettu]
3. Max dot 0,92 on säde, joten täysi sävy peittää noin 66 %. [vahvistettu]
4. Kanavaerottelu ei ole AM-rasteria, koska tiheys koodautuu alphaan. [vahvistettu]
5. Esikatselu ja vienti eroavat useassa kohdassa (mittakaava, choke, logo, clip). [vahvistettu]
6. 600 DPI vaatii muistiratkaisun. [päätelty]

## 2. Koeajon havainnot (2026-11)

| Havainto | Taso | Merkitys |
|---|---|---|
| Tasaiset harmaat tulivat paidalle stokastisena pilkkukohinana, raekoko noin 0,5 mm. | [vahvistettu] tuloste | **RIP rasteroi itse.** Printgenin AM-rasteri rasteroidaan uudelleen. |
| 5 % katosi joka LPI:llä. 15 % katosi noin 50 LPI:stä ylöspäin. | [vahvistettu] tuloste | Vaaleiden sävyjen kynnys on korkea. Pisteet näkyvät filmillä, joten häviö syntyy jauhatuksessa tai siirrossa. |
| Häviön syy: RIPin valkoisen choke syö pienten pisteiden pohjan. | [oletus] | Min dot ja choke ovat profiilin parametripari. |
| 70 % tukkeutuu noin 50 LPI:stä ylöspäin, ja 90 % on umpimusta. | [vahvistettu] tuloste | Dot gain on suuri. Sävykäyrän kompensointi on profiiliasia. |
| Toimiva sävyalue säilyy AM-rasterilla noin 25–40 LPI:llä. | [oletus] | Alustava max LPI. Vahvistetaan korjatulla kartalla. |
| Tiheysporras ajettiin valkoiselle paidalle värikuvana. | [vahvistettu] | Valkoisen peittävyyttä ei mitattu. Testi uusitaan. |
| Kuvien 5 ja 6 filmi on sävyltään käänteinen. | [oletus] pelkkä valkoinen kanava | Ei tulkita ennen kuin asetukset on vahvistettu. |
| Ruudukko aaltoilee. | [vahvistettu] | Johtuu kankaan ja filmin asettumisesta. Kohdistusta ei lueta näistä kuvista. |

**Varaus (ratkaistu vaiheessa 0, ks. alla):** karttageneraattorin pistekaavaa ei ollut tarkistettu. Jos kartta olisi käyttänyt samaa säde ∝ tummuus -kaavaa kuin shader, sarakeotsikot (5–90 %) eivät vastaisi todellista peittoa.

### Vaihe 0: kartan pistekaava (selvitetty 2026-11-04)

**Johtopäätös: koeajon prosenttikynnykset ovat käyttökelpoisia sellaisenaan.** Kartan "5 %" tarkoittaa noin 5 %:n pinta-alapeittoa, ei sädettä. [vahvistettu] tuloste-mittaus

**Miten selvitettiin.** Karttageneraattorin lähdekoodia ei löytynyt repositoriosta, sen historiasta eikä koeajon tiedostoista. Kaava pääteltiin mittaamalla max-LPI-haitarin paitaskannauksesta (600 DPI): pisteväli autokorrelaatiolla, fyysinen piste kynnysarvolla (puoliväli kankaan ja musteen välillä), lisäksi keskitummuudesta Murray–Davies-peitto. Kartan alateksti kertoo, että se on erillinen profiilin `raster.maxLpi`-mittaustyökalu, joka viittaa Printgeniin "työkaluna" (Printgen kvantisoi solun 300 DPI:hin, portaat 25, 30, 33, 38, 43, 50, 60, 75). Kartta ei siis ole Printgenin vientiä. [päätelty]

**Laskelma 25 LPI:llä** (solu 25,4 / 25 = 1,016 mm):

| Sarake | Säde ∝ tummuus (Printgenin shader, max 0,92) | Pinta-ala ∝ tummuus | Mitattu paidalta |
|---|---|---|---|
| 5 % | Ø 0,047 mm, peitto 0,17 % | Ø 0,256 mm, peitto 5 % | Ø ≈ 0,27 mm (epätarkka, kankaan rakenne häiritsee) |
| 15 % | Ø 0,140 mm, peitto 1,5 % | Ø 0,444 mm, peitto 15 % | Ø ≈ 0,46 mm, peitto ≈ 17 % |

Kaavat: säde-tulkinnassa Ø = t × 0,92 × solu, pinta-alatulkinnassa Ø = solu × √(4t / π).

Muut mittaukset tukevat samaa:
- 25 LPI:n 30 %:n ja 50 %:n sarakkeiden fyysinen peitto oli 33 % ja 55 %. Pinta-alamalli antaa 30 % ja 50 %, säde-malli 6 % ja 17 %.
- 15 %:n pisteen halkaisija suhteessa soluun oli 0,45 / 0,44 / 0,45 riveillä 25 / 30 / 35 LPI. Pinta-alamalli antaa 0,437, säde-malli 0,138.
- Ero mallien välillä on peitossa noin kymmenkertainen, joten johtopäätös ei riipu mittaustarkkuudesta. Fyysisessä peitossa näkyy painon dot gain (+2–5 %-yksikköä). Murray–Davies-peitto on suurempi (15 % → noin 29 %, 50 % → 73–79 %), koska siihen sisältyy myös kankaan optinen dot gain.

**Seuraukset:**
- Kynnykset luetaan pinta-alapeittona. Pisteen halkaisija pinta-alamallilla:

  | LPI | 25 | 30 | 35 | 40 | 45 | 50 | 55 | 60 |
  |---|---|---|---|---|---|---|---|---|
  | 5 % | 0,26 | 0,21 | 0,18 | 0,16 | 0,14 | 0,13 | 0,12 | 0,11 mm |
  | 15 % | 0,44 | 0,37 | 0,32 | 0,28 | 0,25 | 0,22 | 0,20 | 0,19 mm |

- Häviörajat osuvat samaan pistekokoon. 5 % katosi lähes kokonaan, mutta 25 ja 30 LPI:llä (Ø 0,26 / 0,21 mm) jäi hajanaisia pisteitä. 15 % katosi noin 50 LPI:stä ylöspäin (Ø 0,22 mm). Raja on noin 0,22–0,25 mm:n pisteessä, mikä vastaa kumppanin min dotia 0,25 mm. [päätelty]
- Luvun 3 lause "kalibrointikartat on tehty samalla moottorilla kuin tuotanto" ei pidä tämän kartan osalta. Printgenin oma vienti piirtäisi samalla 15 %:n syötteellä 25 LPI:llä 0,14 mm:n pisteen, eli selvästi häviörajan alle. 5 %:n piste (Ø 0,047 mm ≈ 0,55 px 300 DPI:llä) ei piirry lainkaan.
- Vaihe A2 on edelleen tarpeen tuotantorasterin vuoksi, mutta koeajon datan tulkinta ei odota sitä.
- Generaattorin lähdekoodi kannattaa tallentaa, jotta seuraavan kartan kaava voidaan tarkistaa koodista eikä tulosteesta.

## 3. Periaatteet, jotka ohjaavat järjestystä

- **Mittalaitteen on oltava oikein ennen mittausta.** Kalibrointikartat on tehty samalla moottorilla kuin tuotanto. Jos moottori piirtää väärän peiton, jokainen profiiliin luettu arvo on väärä.
- **Contone on oletettu tuotantoreitti, AM-rasteri ilmaisullinen valinta.** Tämä on voimassa, kunnes vertailukoe (luku 6) osoittaa muuta.
- **Kriittisellä polulla on vain se, mikä koskee kaikkea vientiä.** Erikoisreitit (kanavaerottelu, värikerrokset) korjataan tai piilotetaan myöhemmin.
- **Fyysiset suureet millimetreinä, ei pikseleinä.** Pikseli on resoluution sivutuote.

---

## 4. Vaiheet

### Vaihe 0 — Karttageneraattorin pistekaava (selvitys)

**Tehtävä:** Selvitä, millä kaavalla kalibrointikartat piirtävät pisteen koon ja mitä "5 %" tarkoittaa todellisena peittona. Laske kummallakin tulkinnalla pisteen halkaisija millimetreinä 5 %:n ja 15 %:n sarakkeille 25 LPI:llä.

**Valmis kun:** Tiedetään, ovatko koeajon prosenttikynnykset käyttökelpoisia sellaisenaan. Tulos kirjataan tähän dokumenttiin lukuun 2.

**Koodimuutoksia ei tehdä.**

### Vaihe A1 — Alpha ja blendaus

**Miksi ensin:** Pieni muutos, joka koskee kaikkea vientiä. PDF-reitti kuljettaa contone-alphan SMaskeina, joten se ei voi olla oikein ennen tätä.

**Sisältö:**
- `gl.BLEND` pois passeista, jotka piirtävät tyhjään puskuriin, tai vastaava premultiplied-oikea ratkaisu. Ratkaisu valitaan ennen toteutusta.
- `FS_ERODE`, `FS_COLOR` ja `FS_BASE` tarkistetaan alpha-käsittelyn osalta.
- `webglcontextlost`-käsittely (vähintään selkeä virhe, ei hiljaista rikkoutumista).

**Valmis kun:** CODEMAPin liitteen selainkokeet antavat odotetut tulokset: alpha 128 pysyy arvossa 128 eikä putoa arvoon 64, ja pohjatiedoston puoliläpinäkyvät reunat ovat valkoisia eivätkä harmaita. Kokeet ajetaan Chromessa **ja Safarissa**.

### Vaihe A2 — Rasterin sävyvaste ja rehelliset kartat

**Miksi nyt:** Seuraavan koeajon data on käyttökelpoista vain, jos kartat piirtävät sen peiton, jonka ne ilmoittavat.

**Sisältö:**
- Pinta-alakorjattu piste: peitto on lineaarinen tummuuteen nähden.
- Max dot pinta-alana (esim. 90 % = kumppanin arvo), ei säteenä.
- LPI-kvantisointi näkyviin: UI ja kartat näyttävät todellisen LPI:n (`300 / round(300/LPI)`), ei pyydettyä.
- Pohjan solun alkuarvo korjataan vastaamaan slideria (`baseHalftoneCell` 10 px vs. 45 LPI).
- Värikerroksen ja pohjan oletuskulma yhtenäistetään, tai ero perustellaan.

**Valmis kun:** Selainkokeessa harmaa 128 peittää noin 50 % solusta, ja kartan jokaisen sarakkeen mitattu peitto vastaa otsikkoaan ±2 %-yksikön tarkkuudella.

### Selvitys (rinnakkain, ei koodia)

Kysytään painotalon yhteyshenkilöiltä:

1. RIP-ohjelmiston nimi ja versio (CADlink?)
2. Rasterointitila (stokastinen tai error diffusion vai AM) ja tulostusresoluutio
3. Valkoisen generointitapa (automaattinen vai tiedostosta) ja choke-asetus
4. Millä asetuksilla kukin koeajon filmi ajettiin, erityisesti kuvien 5 ja 6 filmi
5. Hyväksyykö RIP PDF:n `/Separation White` -kanavan suoraan

Vastaukset kirjataan lukuun 7. Kohdat 1–3 ratkaisevat vaiheen C laajuuden ja 600 DPI:n tarpeen.

### Vaihe B — Yksi totuuden lähde

**Miksi ennen C:tä:** PDF tarvitsee oikean fyysisen koon, ja tällä hetkellä DPI on kovakoodattu kahdeksaan kohtaan.

**Sisältö:**
- DPI yhdeksi parametriksi (CODEMAP 6.1).
- Choke ja halo-poisto millimetreinä. Pikseliarvo lasketaan DPI:stä kussakin polussa, jolloin sama asetus on fyysisesti sama esikatselussa ja viennissä.
- Esikatselun ja viennin erot (CODEMAP 1.4) pienennetään yhteisellä renderöintipolulla. Vähintään mittakaava, choke ja clip näkyvät esikatselussa samoin kuin viennissä.
- Vienti lukee asetukset kerran alussa (snapshot) eikä kesken viennin (CODEMAP 8.2).
- Recipe-valmius: asetukset kootaan yhteen objektiin, joka voidaan myöhemmin sarjallistaa (Tallenna / Avaa projekti).

**Valmis kun:** DPI:n vaihto 300 → 600 muuttaa viennin pikselikoon, mutta ei fyysistä kokoa, chokea tai LPI:tä. Esikatselu ja vienti näyttävät saman rasterin mittakaavan.

### Vaihe C — PDF-vienti omalla valkoisella kanavalla

**Miksi:** Kumppani pyytää tätä aktiivisesti, ja koeajon perusteella se on oikea tuotantoreitti.

**Sisältö (ensisijainen muoto):**
- Contone-RGB + SMask.
- Valkoinen `/Separation /White` -kanavana + SMask, overprint (`/OP /op /OPM 1`). Valkoinen piirretään ensin.
- `CompressionStream('deflate')` → FlateDecode, ei uutta riippuvuutta.
- `MediaBox` fyysisestä koosta (vaihe B).

**Valmis kun:** Acrobatin Output Preview näyttää White-separaation ja overprintin oikein, ja koeajo RIPissä tuottaa odotetun tuloksen.

**Laajuus riippuu selvityksestä:** jos RIP vaatii valmiiksi rasteroidun tiedoston, A2:n laatu tulee mukaan PDF:ään, ja vaihe laajenee.

### Vaihe D — Rasteri ilmaisullisena valintana, profiilirajoilla

**Edellyttää:** A2 valmiina ja korjatulla kartalla ajettua koeajon dataa.

**Sisältö:**
- Profiilin rasteriosa: max LPI, min dot (mm), max dot, sävykäyrä (dot gain -kompensaatio).
- UI varoittaa, kun valinta ylittää profiilin rajat.
- Kanavaerottelu (CODEMAP 6.5) korjataan oikeaksi AM-rasteriksi **tai** piilotetaan oletuksena. Päätös tehdään, kun tiedetään, tarvitseeko sitä kukaan.

### Vaihe E — 600 DPI:n muisti

**Edellyttää:** selvityksen vastauksen siitä, tarvitaanko 600 DPI:tä.

**Sisältö:** työskentely bboxin kokoisena, canvasten vapautus vaiheiden välissä, `MAX_TEXTURE_SIZE`-tarkistus ja tarvittaessa paloittelu. Safarin canvas-rajat testataan erikseen.

---

## 5. Riippuvuudet

```
Vaihe 0 ──► A2 ──► (koeajo 2) ──► D
A1 ──────────────────────────────► C
Selvitys ──► C:n laajuus, E:n tarve
B ───────────────────────────────► C
```

A1 ja vaihe 0 voidaan tehdä heti ja rinnakkain. Selvitys kulkee koko ajan taustalla.

## 6. Seuraava koeajo

Ajetaan, kun A2 on valmis.

1. **Max-LPI-haitari uudelleen** korjatulla pistekaavalla. Lisätään 10 %:n ja 20 %:n sarakkeet, koska kynnys osuu niiden väliin.
2. **Tiheysporras** tummalle paidalle **pelkällä valkoisella kanavalla**.
3. **Contone vs. AM -vertailu:** sama harmaaliuku kahdesti samalla arkilla, kerran contonena (RIP rasteroi) ja kerran Printgenin AM-rasterina 30 LPI:llä. Tämä ratkaisee, tuoko Printgenin oma rasteri DTF:ssä lisäarvoa vai onko se puhtaasti tyylikeino.
4. **Min dot × choke -matriisi** (jos RIPin choke on säädettävissä): pienet erilliset pisteet (0,2 / 0,3 / 0,4 / 0,5 mm) kahdella choke-arvolla.

Jokaisesta filmistä kirjataan RIPin asetukset ennen ajoa.

## 7. Avoimet kysymykset

| Kysymys | Vaikuttaa | Tila |
|---|---|---|
| RIPin nimi ja rasterointitila | C, E | avoin |
| Valkoisen generointi ja choke | D (min dot) | avoin |
| Hyväksyykö RIP `/Separation White` | C | avoin |
| Kuvien 5 ja 6 filmin asetukset | koeajon tulkinta | avoin |
| Karttageneraattorin pistekaava | koeajon tulkinta | vaihe 0 |
| Tehtiinkö painotalon "your file" -testit Printgenillä | viitearvojen tulkinta | avoin |

## 8. CLAUDE.md:n korjaukset

- Gamma-ongelma koski toisen tahon presetiä, ei Printgeniä.
- Max dot 90 % on kumppanin **pinta-ala**arvo, ei säde.

Korjataan vaiheen A1 yhteydessä.
