// alpha_selainkoe.js — WebGL-moottorin (_GL) alpha-käsittelyn selainkoe (tiekartan vaihe A1)
//
// Käyttö: avaa index.html selaimessa, avaa kehittäjäkonsoli ja liitä tämän tiedoston
// koko sisältö konsoliin. Koe ajetaan heti, ja tulos tulostuu taulukkona.
// Uudelleenajo: await alphaSelainkoe()
//
// Koe ei muuta sovelluksen tilaa. Kohta 8 (kontekstin menetys) näyttää toastin.
// Toleranssi ±2 johtuu siitä, että 2D-canvas säilyttää pikselit premultiplied-muodossa
// 8-bittisinä, joten puoliläpinäkyvän pikselin väri pyöristyy luettaessa.

async function alphaSelainkoe() {
  const TOL = 2;
  const tulokset = [];
  const kirjaa = (id, koe, odotettu, saatu, ok) =>
    tulokset.push({ id, koe, odotettu, saatu, tulos: ok === null ? 'PUUTTUU' : (ok ? 'PASS' : 'FAIL') });

  function pohja(w, h, piirra) {
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    const ctx = c.getContext('2d');
    piirra(ctx, w, h);
    return c;
  }
  function tasainen(w, h, r, g, b, a) {
    return pohja(w, h, (ctx) => { ctx.fillStyle = `rgba(${r},${g},${b},${a / 255})`; ctx.fillRect(0, 0, w, h); });
  }
  function data(c) { return c.getContext('2d').getImageData(0, 0, c.width, c.height).data; }
  function px(c, x, y) { const d = c.getContext('2d').getImageData(x, y, 1, 1).data; return [d[0], d[1], d[2], d[3]]; }
  const lahella = (a, b, t = TOL) => a.every((v, i) => Math.abs(v - b[i]) <= t);
  const fmt = (p) => '(' + p.join(',') + ')';

  // 1. Erode, puoliläpinäkyvä: pikselin pitää kulkea läpi muuttumattomana.
  {
    const src = tasainen(40, 40, 200, 100, 50, 128);
    const odot = px(src, 20, 20);
    const saatu = px(_GL.erode(src, 1), 20, 20);
    kirjaa('1', 'erode, (200,100,50) alpha 128, keskus', fmt(odot), fmt(saatu), lahella(saatu, odot));
  }

  // 2. Erode, läpinäkymätön (regressio): koko sisäosa bitintarkasti ennallaan.
  {
    const src = tasainen(40, 40, 200, 100, 50, 255);
    const s = data(src), o = data(_GL.erode(src, 1));
    let erot = 0;
    for (let y = 1; y < 39; y++) for (let x = 1; x < 39; x++) {
      const i = (y * 40 + x) * 4;
      for (let k = 0; k < 4; k++) if (s[i + k] !== o[i + k]) { erot++; break; }
    }
    kirjaa('2', 'erode, alpha 255, sisäosa bitintarkka', '0 eroa', erot + ' eroa', erot === 0);
  }

  // 3. Värihalftone, musta eri alphoilla: solun keskuksen alpha = syötteen alpha.
  for (const a of [64, 128, 255]) {
    const src = tasainen(40, 40, 0, 0, 0, a);
    const odot = px(src, 10, 10)[3];
    const saatu = px(_GL.colorHalftone(src, 20, 0, 0.92, 0), 10, 10)[3];
    kirjaa('3', `colorHalftone, musta alpha ${a}, solun keskus`, 'alpha ' + odot, 'alpha ' + saatu, Math.abs(saatu - odot) <= TOL);
  }

  // 4. Värihalftone, läpinäkymätön värikuva: pisteiden antialias-reunojen väri ei saa tummua.
  {
    const src = tasainen(96, 96, 200, 100, 50, 255);
    const o = data(_GL.colorHalftone(src, 12, 22.5, 0.92, 0));
    let n = 0, vaarin = 0, pahin = 0;
    for (let i = 0; i < o.length; i += 4) {
      if (o[i + 3] < 64) continue;
      n++;
      const ero = Math.max(Math.abs(o[i] - 200), Math.abs(o[i + 1] - 100), Math.abs(o[i + 2] - 50));
      if (ero > 3) vaarin++;
      pahin = Math.max(pahin, ero);
    }
    kirjaa('4', 'colorHalftone, (200,100,50) alpha 255, värisävy kaikissa pikseleissä (alpha ≥ 64)',
      '0 väärää, ero ≤ 3', `${vaarin}/${n} väärää, suurin ero ${pahin}`, vaarin === 0);
  }

  // 5. Pohjahalftone, alpha 128: solun keskus valkoinen ja alpha säilyy.
  {
    const src = tasainen(40, 40, 255, 255, 255, 128);
    const odot = [255, 255, 255, px(src, 10, 10)[3]];
    const saatu = px(_GL.baseHalftone(src, 20, 0, 0.8, 0.88, 0), 10, 10);
    kirjaa('5', 'baseHalftone, alpha 128, solun keskus', fmt(odot), fmt(saatu), lahella(saatu, odot));
  }

  // 6. Pohjahalftone: jokainen näkyvä pikseli on valkoinen (ei harmaita reunoja).
  {
    const src = tasainen(40, 40, 255, 255, 255, 128);
    const o = data(_GL.baseHalftone(src, 20, 0, 0.8, 0.88, 0));
    let n = 0, harmaat = 0, tummin = 255;
    for (let i = 0; i < o.length; i += 4) {
      if (o[i + 3] < 8) continue;
      n++;
      const m = Math.min(o[i], o[i + 1], o[i + 2]);
      if (m < 250) harmaat++;
      tummin = Math.min(tummin, m);
    }
    kirjaa('6', 'baseHalftone, alpha 128, kaikki pikselit valkoisia (alpha ≥ 8)',
      '0 harmaata', `${harmaat}/${n} harmaata, tummin ${tummin}`, harmaat === 0);
  }

  // 7. Reunus: värillinen kiekko läpinäkyvällä pohjalla. Kuvan reunalla solun keskipisteen
  //    näyte ei saa sekoittua läpinäkyvän (0,0,0,0) naapurin kanssa tummemmaksi.
  //    (Valkoinen ei kelpaa koekuvaksi, koska valkoinen ei piirrä halftone-pistettä.)
  {
    const src = pohja(96, 96, (ctx) => {
      ctx.fillStyle = 'rgb(200,100,50)'; ctx.beginPath(); ctx.arc(48, 48, 33.3, 0, Math.PI * 2); ctx.fill();
    });
    const o = data(_GL.colorHalftone(src, 12, 22.5, 0.92, 0));
    let n = 0, vaarin = 0, pahin = 0;
    for (let i = 0; i < o.length; i += 4) {
      if (o[i + 3] < 64) continue;
      n++;
      const ero = Math.max(Math.abs(o[i] - 200), Math.abs(o[i + 1] - 100), Math.abs(o[i + 2] - 50));
      if (ero > 3) vaarin++;
      pahin = Math.max(pahin, ero);
    }
    kirjaa('7', 'colorHalftone, (200,100,50)-kiekko, kuvan reunan pisteiden värisävy (alpha ≥ 64)',
      '0 väärää, ero ≤ 3', `${vaarin}/${n} väärää, suurin ero ${pahin}`, vaarin === 0);
  }

  // 8. Kontekstin menetys (vaatii testikoukun _GL._testLoseContext).
  if (typeof _GL._testLoseContext !== 'function') {
    kirjaa('8', 'kontekstin menetys', 'testikoukku _GL._testLoseContext', 'ei olemassa', null);
  } else {
    const src = tasainen(40, 40, 255, 255, 255, 128);
    const keskus = () => px(_GL.baseHalftone(src, 20, 0, 0.8, 0.88, 0), 10, 10);
    const odot = [255, 255, 255, px(src, 10, 10)[3]];

    // 8a: konteksti menetetään kutsujen välissä → seuraava kutsu luo uuden ja toimii.
    {
      const ok = _GL._testLoseContext();
      await new Promise(r => setTimeout(r, 50));
      let saatu, virhe = null;
      try { saatu = keskus(); } catch (e) { virhe = e.message; }
      kirjaa('8a', 'menetys kutsujen välissä → seuraava baseHalftone toimii',
        fmt(odot), virhe ? 'virhe: ' + virhe : fmt(saatu), ok && !virhe && lahella(saatu, odot));
    }
    // 8b: konteksti menetetään kesken passin → colorHalftone palauttaa CPU-tuloksen.
    {
      _GL._testLoseContext({ kesken: true });
      let tulos, virhe = null;
      try { tulos = _GL.colorHalftone(tasainen(40, 40, 0, 0, 0, 255), 20, 0, 0.92, 0); } catch (e) { virhe = e.message; }
      const a = tulos ? px(tulos, 10, 10)[3] : null;
      kirjaa('8b', 'menetys kesken colorHalftonen → CPU-fallback, ei virhettä',
        'canvas, keskus alpha 255', virhe ? 'virhe: ' + virhe : 'canvas, keskus alpha ' + a, !virhe && a === 255);
    }
    // 8c: konteksti menetetään kesken pohjan → selkeä virhe (pohjalla ei ole fallbackia).
    {
      await new Promise(r => setTimeout(r, 50));
      _GL._testLoseContext({ kesken: true });
      let virhe = null;
      try { keskus(); } catch (e) { virhe = e.message; }
      kirjaa('8c', 'menetys kesken baseHalftonen → heittää virheen',
        'Error, viesti mainitsee WebGL:n', virhe ? 'Error: ' + virhe : 'ei virhettä', !!virhe && /WebGL/.test(virhe));
    }
    // 8d: menetyksen jälkeen moottori toipuu.
    {
      await new Promise(r => setTimeout(r, 50));
      let saatu, virhe = null;
      try { saatu = keskus(); } catch (e) { virhe = e.message; }
      kirjaa('8d', 'menetyksen jälkeen baseHalftone toimii taas',
        fmt(odot), virhe ? 'virhe: ' + virhe : fmt(saatu), !virhe && lahella(saatu, odot));
    }
  }

  const fail = tulokset.filter(t => t.tulos === 'FAIL').length;
  const puuttuu = tulokset.filter(t => t.tulos === 'PUUTTUU').length;
  console.table(tulokset);
  console.log(`alpha_selainkoe: ${tulokset.length - fail - puuttuu} PASS, ${fail} FAIL, ${puuttuu} PUUTTUU — ${navigator.userAgent}`);
  return tulokset;
}

alphaSelainkoe();
