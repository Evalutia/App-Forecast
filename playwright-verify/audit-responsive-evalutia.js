const { chromium } = require('C:/Users/Nico/AppData/Roaming/npm/node_modules/playwright');
const path = require('path');
const fs = require('fs');

const URL = 'https://evalutia.net';
const OUT_DIR = path.join(__dirname, 'screens');
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

const viewports = [
  { name: '01-iphoneSE',      width: 320,  height: 568 },
  { name: '02-iphone12',      width: 390,  height: 844 },
  { name: '03-android-mid',   width: 412,  height: 915 },
  { name: '04-ipad-portrait', width: 768,  height: 1024 },
  { name: '05-ipad-landscape',width: 1024, height: 768 },
  { name: '06-laptop',        width: 1366, height: 768 },
  { name: '07-fhd-monitor',   width: 1920, height: 1080 },
  { name: '08-qhd-monitor',   width: 2560, height: 1440 },
  { name: '09-4k-tv',         width: 3840, height: 2160 },
];

(async () => {
  const browser = await chromium.launch();
  const results = [];

  for (const vp of viewports) {
    const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
    const consoleErrors = [];
    page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
    page.on('pageerror', err => consoleErrors.push(String(err)));

    let status = null;
    try {
      const resp = await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });
      status = resp ? resp.status() : null;
    } catch (e) {
      results.push({ ...vp, error: String(e) });
      await page.close();
      continue;
    }

    // Simulate a real user scroll so IntersectionObserver-based .reveal sections fire
    const totalHeight = await page.evaluate(() => document.body.scrollHeight);
    for (let y = 0; y < totalHeight; y += Math.round(vp.height * 0.8)) {
      await page.evaluate(yy => window.scrollTo({ top: yy, behavior: 'auto' }), y);
      await page.waitForTimeout(250);
    }
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'auto' }));
    await page.waitForTimeout(800); // let reveal/canvas animations settle

    const metrics = await page.evaluate(() => {
      const de = document.documentElement;
      const scrollW = de.scrollWidth;
      const clientW = de.clientWidth;
      const overflowing = [];
      if (scrollW > clientW + 1) {
        document.querySelectorAll('body *').forEach(el => {
          const r = el.getBoundingClientRect();
          if (r.right > clientW + 1 || r.left < -1) {
            overflowing.push({
              tag: el.tagName,
              cls: el.className && typeof el.className === 'string' ? el.className.slice(0, 60) : '',
              right: Math.round(r.right),
              left: Math.round(r.left),
            });
          }
        });
      }
      const navLinksVisible = Array.from(document.querySelectorAll('.nav-links a:not(.nav-cta)'))
        .map(a => getComputedStyle(a).display !== 'none');
      const revealEls = document.querySelectorAll('.reveal');
      const revealVisibleCount = document.querySelectorAll('.reveal.visible').length;
      return {
        revealTotal: revealEls.length,
        revealVisibleCount,
        scrollW, clientW,
        horizontalOverflow: scrollW > clientW + 1,
        overflowingTop: overflowing.slice(0, 8),
        navLinksVisibleCount: navLinksVisible.filter(Boolean).length,
        hasHamburger: !!document.querySelector('[class*="hamburger"],[class*="menu-toggle"],[aria-label*="menu" i]'),
        bodyWidth: document.body.scrollWidth,
      };
    });

    await page.screenshot({ path: path.join(OUT_DIR, `${vp.name}.png`), fullPage: true });

    results.push({ ...vp, status, ...metrics, consoleErrors: consoleErrors.slice(0, 5) });
    await page.close();
  }

  await browser.close();
  console.log(JSON.stringify(results, null, 2));
})();
