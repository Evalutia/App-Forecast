const { chromium } = require('C:/Users/Nico/AppData/Roaming/npm/node_modules/playwright');

function calcExpected(meses) {
  const closed = meses.slice(0, -1);
  const vals = [];
  for (const m of closed) {
    if (m.estadoMes === 'normal' && m.rotacionDiariaDesestacionalizada != null)
      vals.push(m.rotacionDiariaDesestacionalizada);
    else if (m.estadoMes === 'quiebre_parcial' && m.rotacionAjustada != null) {
      if (m.rotacionDiariaDesestacionalizada != null && m.rotacionDiariaReal != null && m.rotacionDiariaReal > 0)
        vals.push(m.rotacionAjustada * (m.rotacionDiariaDesestacionalizada / m.rotacionDiariaReal));
      else
        vals.push(m.rotacionAjustada);
    }
  }
  return vals.length === 0 ? '—' : (vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(4);
}

async function login(page) {
  const resp = await page.request.post('http://localhost:8080/api/auth/login', {
    data: { correo: 'admin@evalutia.com', contrasena: 'Admin1234!' },
    headers: { 'Content-Type': 'application/json' },
  });
  const body = await resp.json();
  await page.goto('http://localhost:5173');
  await page.evaluate(({ t, u }) => {
    localStorage.setItem('auth.token', t);
    localStorage.setItem('auth.user', JSON.stringify(u));
  }, { t: body.token, u: body.user ?? {} });
}

async function getRotDesEstac(page, sku) {
  const rows = await page.locator('tbody tr').all();
  for (const row of rows) {
    const text = await row.textContent();
    if (text && text.includes(sku)) {
      const cells = await row.locator('td').all();
      return (await cells[cells.length - 4].textContent())?.trim();
    }
  }
  return null;
}

async function loadPlanilla(page) {
  await page.goto('http://localhost:5173/planilla');
  await page.waitForSelector('table', { timeout: 15000 });
  await page.waitForTimeout(1500);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  let passed = 0, failed = 0;

  function result(label, ok, detail) {
    if (ok) { passed++; console.log('✅ ' + label + (detail ? ' — ' + detail : '')); }
    else      { failed++; console.log('❌ ' + label + (detail ? ' — ' + detail : '')); }
  }

  // ── T1: meses normales con desest → promedio correcto ───────────────────
  {
    const page = await browser.newPage();
    await login(page);
    let apiData = null;
    page.on('response', async r => {
      if (r.url().includes('/api/planilla/ventas') && r.status() === 200)
        try { apiData = await r.json(); } catch {}
    });
    await loadPlanilla(page);
    const displayed = await getRotDesEstac(page, 'C00184');
    const skuData = apiData && apiData.items.find(x => x.sku === 'C00184');
    const expected = skuData ? calcExpected(skuData.meses) : '?';
    const normCount = skuData ? skuData.meses.slice(0,-1).filter(m => m.estadoMes==='normal' && m.rotacionDiariaDesestacionalizada!=null).length : 0;
    result('T1 — normal months desest promedio (' + normCount + ' meses)', displayed === expected,
      'esperado=' + expected + ' mostrado=' + displayed);
    await page.close();
  }

  // ── T2: SKUs sin factores → '—' ─────────────────────────────────────────
  {
    const page = await browser.newPage();
    await login(page);
    await loadPlanilla(page);
    const rows = await page.locator('tbody tr').all();
    let dash = 0, withVal = [];
    for (const row of rows) {
      const text = await row.textContent();
      if (!text || text.includes('C00184')) continue;
      const cs = await row.locator('td').all();
      if (cs.length < 4) continue;
      const v = (await cs[cs.length - 4].textContent())?.trim();
      if (v === '—') dash++;
      else if (v) withVal.push(v);
    }
    result('T2 — SKUs sin factores muestran — (' + dash + ' SKUs)', withVal.length === 0,
      withVal.length > 0 ? 'valores inesperados: ' + withVal.slice(0,3).join(', ') : '');
    await page.close();
  }

  // ── T3: quiebre_parcial CON desest → opción C ───────────────────────────
  // Modifica Jul-2025 de C00184: normal→quiebre_parcial, rotAjust=0.9 (≠ rotReal=1.8387)
  // Fórmula C = 0.9 * (1.6715 / 1.8387) = 0.8182 aprox
  {
    const page = await browser.newPage();
    await login(page);
    await page.route('**/api/planilla/ventas**', async route => {
      const resp = await route.fetch();
      const json = await resp.json();
      const sku = json.items.find(x => x.sku === 'C00184');
      if (sku) {
        const jul = sku.meses.find(m => m.year === 2025 && m.month === 7);
        if (jul) { jul.estadoMes = 'quiebre_parcial'; jul.rotacionAjustada = 0.9; }
      }
      await route.fulfill({ json });
    });
    await loadPlanilla(page);
    const displayed = await getRotDesEstac(page, 'C00184');
    // Jul contrib = 0.9 * (1.6715 / 1.8387); rest = normales sin Jul
    const julC = 0.9 * (1.6715 / 1.8387);
    const normVals = [1.3650, 1.8548, 1.3590, 0.4839, 1.4222, 1.9355, 1.8817];
    const expected = ([...normVals, julC].reduce((s,v) => s+v, 0) / (normVals.length + 1)).toFixed(4);
    result('T3 — quiebre_parcial con desest (opción C)', displayed === expected,
      'julContrib=' + julC.toFixed(4) + ' esperado=' + expected + ' mostrado=' + displayed);
    await page.close();
  }

  // ── T4: quiebre_parcial SIN desest → fallback a rotacionAjustada ────────
  {
    const page = await browser.newPage();
    await login(page);
    await page.route('**/api/planilla/ventas**', async route => {
      const resp = await route.fetch();
      const json = await resp.json();
      const sku = json.items.find(x => x.sku === 'C00184');
      if (sku) {
        const jul = sku.meses.find(m => m.year === 2025 && m.month === 7);
        if (jul) {
          jul.estadoMes = 'quiebre_parcial';
          jul.rotacionAjustada = 0.9;
          jul.rotacionDiariaDesestacionalizada = null;
        }
      }
      await route.fulfill({ json });
    });
    await loadPlanilla(page);
    const displayed = await getRotDesEstac(page, 'C00184');
    const normVals = [1.3650, 1.8548, 1.3590, 0.4839, 1.4222, 1.9355, 1.8817];
    const expected = ([...normVals, 0.9].reduce((s,v) => s+v, 0) / (normVals.length + 1)).toFixed(4);
    result('T4 — quiebre_parcial sin desest (fallback rotacionAjustada)', displayed === expected,
      'esperado=' + expected + ' mostrado=' + displayed);
    await page.close();
  }

  // ── T5: todo NULL → '—' ─────────────────────────────────────────────────
  {
    const page = await browser.newPage();
    await login(page);
    await page.route('**/api/planilla/ventas**', async route => {
      const resp = await route.fetch();
      const json = await resp.json();
      const sku = json.items.find(x => x.sku === 'C00184');
      if (sku) {
        for (const m of sku.meses) {
          m.rotacionDiariaDesestacionalizada = null;
          m.rotacionAjustada = null;
        }
      }
      await route.fulfill({ json });
    });
    await loadPlanilla(page);
    const displayed = await getRotDesEstac(page, 'C00184');
    result('T5 — todo NULL muestra —', displayed === '—', 'mostrado=' + displayed);
    await page.close();
  }

  // ── T6: tooltip texto correcto en código fuente ─────────────────────────
  // El Tip usa createPortal — hover headless no activa el portal de forma fiable.
  // Verificamos el string directamente en PlanillaTable.tsx.
  {
    const fs = require('fs');
    const src = fs.readFileSync(
      require('path').join(__dirname, '../apps/frontend/src/features/planilla/components/PlanillaTable.tsx'),
      'utf8'
    );
    const ok = src.includes('estacionalidad') && src.includes('factor estacional del mes');
    result('T6 — tooltip menciona estacionalidad y factor estacional del mes', ok,
      ok ? 'string presente en PlanillaTable.tsx' : 'string NO encontrado en fuente');
  }

  console.log('\n─────────────────────────────────────────');
  console.log('Resultado: ' + passed + '/' + (passed+failed) + ' PASS');
  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
})().catch(e => { console.error('ERROR FATAL:', e.message); process.exit(1); });
