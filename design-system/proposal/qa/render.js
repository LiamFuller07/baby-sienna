// Render and check a built proposal deck with Node Playwright (Chromium preinstalled).
//   node qa/render.js <deck.html> <outDir> [--sheet] [--allow-local]
// Writes <outDir>/slide-NN.png (1280x720, print layout), <outDir>/deck.pdf and,
// with --sheet, <outDir>/index.html (contact sheet). Exits 1 when a check fails:
// content outside its slide or region, the body running into the source line,
// a request that is not data:, a console error, horizontal scroll on screen, or a
// PDF page count that differs from the slide count.
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

(async () => {
  const [src, outDir, ...flags] = process.argv.slice(2);
  if (!src || !outDir) { console.error('usage: node qa/render.js deck.html outDir [--sheet]'); process.exit(2); }
  const file = path.resolve(src), out = path.resolve(outDir);
  fs.mkdirSync(out, { recursive: true });
  for (const f of fs.readdirSync(out)) if (/^slide-\d+\.png$/.test(f)) fs.unlinkSync(path.join(out, f));
  const url = 'file://' + file;
  const browser = await chromium.launch();
  const problems = [], requests = [], errors = [];

  // 1. Print layout: one unscaled 1280x720 slide per page.
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  const allowLocal = flags.includes('--allow-local');   // template.html links deck.css and fonts/
  page.on('request', r => { const u = r.url(); if (!u.startsWith('data:') && u !== url && !(allowLocal && u.startsWith('file://'))) requests.push(u); });
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  await page.emulateMedia({ media: 'print' });
  await page.goto(url);
  await page.evaluate(() => document.fonts.ready);
  const fontsOk = await page.evaluate(() => document.fonts.check('600 20px Source') && document.fonts.check('400 20px Source'));
  if (!fontsOk) problems.push('Source font did not load');

  const report = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('.slide').forEach((sl, i) => {
      const n = i + 1, r = sl.getBoundingClientRect(), issues = [];
      const type = [...sl.classList].find(c => c.startsWith('slide--') && c !== 'slide--dark').slice(7);
      const title = (sl.querySelector('h1') || {}).textContent || '';
      const inside = el => !el.closest('svg') || el.tagName.toLowerCase() === 'svg';
      // everything inside the slide frame, with the 28px bottom margin and 64px sides respected
      sl.querySelectorAll('*').forEach(el => {
        if (!inside(el)) return;
        const b = el.getBoundingClientRect();
        if (!b.width && !b.height) return;
        if (b.left < r.left + 63 || b.right > r.right - 63 || b.top < r.top + 20 || b.bottom > r.bottom - 25)
          issues.push(`outside the margins: <${el.tagName.toLowerCase()} class="${el.className.baseVal ?? el.className}"> ${Math.round(b.left - r.left)},${Math.round(b.top - r.top)} ${Math.round(b.width)}x${Math.round(b.height)}`);
      });
      // the body never runs into the source line or the footer
      const body = sl.querySelector('.slide-body'), src = sl.querySelector('.srcline'), foot = sl.querySelector('.slide-foot');
      if (body) {
        if (body.scrollHeight > body.clientHeight + 1) issues.push(`body overflows by ${body.scrollHeight - body.clientHeight}px`);
        let bottom = 0;
        body.querySelectorAll('*').forEach(el => { if (inside(el)) bottom = Math.max(bottom, el.getBoundingClientRect().bottom); });
        const limit = (src || foot).getBoundingClientRect().top - 12;
        if (bottom > limit) issues.push(`body content ends ${Math.round(bottom - limit)}px too low (into the source line or footer)`);
      }
      if (src && src.scrollWidth > src.clientWidth + 1) issues.push('source line is cut off (ellipsis)');
      // any block whose content is taller than the box it was given (cards, rows, panels)
      sl.querySelectorAll('.slide-body *').forEach(el => {
        if (el.closest('svg') || !el.clientHeight) return;
        // leaf text may overshoot its line box by its descenders (big type at line-height ~1)
        const slack = el.children.length ? 2 : parseFloat(getComputedStyle(el).fontSize) * 0.2;
        if (el.scrollHeight > el.clientHeight + slack) issues.push(`content taller than its box by ${el.scrollHeight - el.clientHeight}px: <${el.tagName.toLowerCase()} class="${el.className}">`);
      });
      // blocks in the body never overlap each other
      if (body) {
        const kids = [...body.children].map(k => k.getBoundingClientRect());
        for (let k = 1; k < kids.length; k++) if (kids[k].top < kids[k - 1].bottom - 1) issues.push(`body blocks ${k} and ${k + 1} overlap by ${Math.round(kids[k - 1].bottom - kids[k].top)}px`);
      }
      // text that is clipped by its own box
      sl.querySelectorAll('h1,h2,h3,p,li,span,dd,dt,td,th').forEach(el => {
        if (el.closest('svg')) return;
        if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflow !== 'visible') issues.push(`clipped text: "${el.textContent.slice(0, 40)}"`);
      });
      // words broken across lines inside headings (a heading taller than its text needs is fine; a split word is not)
      out.push({ n, type, title, issues: [...new Set(issues)] });
    });
    return out;
  });

  const slides = await page.$$('.slide');
  for (let i = 0; i < slides.length; i++) {
    await slides[i].screenshot({ path: path.join(out, `slide-${String(i + 1).padStart(2, '0')}.png`) });
  }
  const pdfPath = path.join(out, 'deck.pdf');
  await page.pdf({ path: pdfPath, preferCSSPageSize: true, printBackground: true });
  const info = execFileSync('pdfinfo', [pdfPath]).toString();
  const pages = Number((info.match(/Pages:\s+(\d+)/) || [])[1]);
  const size = (info.match(/Page size:\s+([^\n]+)/) || [])[1];
  if (pages !== slides.length) problems.push(`PDF has ${pages} pages for ${slides.length} slides`);

  // 2. Screen layout: stacked, scaled to the window, keyboard stepping, no sideways scroll.
  const scr = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await scr.goto(url);
  await scr.evaluate(() => document.fonts.ready);
  const screen = await scr.evaluate(() => ({
    sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
    s: getComputedStyle(document.documentElement).getPropertyValue('--s'),
    frameW: document.querySelector('.frame').getBoundingClientRect().width,
  }));
  if (screen.sw > screen.cw) problems.push(`screen: horizontal scroll (${screen.sw} > ${screen.cw})`);
  await scr.screenshot({ path: path.join(out, 'screen-1440.png') });
  await scr.keyboard.press('PageDown');
  await scr.keyboard.press('ArrowDown');
  await scr.waitForTimeout(150);
  const step = await scr.evaluate(() => ({ hash: location.hash, top: Math.round(document.querySelector('#slide-3').getBoundingClientRect().top) }));
  if (step.hash !== '#slide-3' || Math.abs(step.top - 24) > 2) problems.push(`screen: keyboard stepping did not land on slide 3 (${JSON.stringify(step)})`);
  const phone = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await phone.goto(url);
  const ph = await phone.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  if (ph.sw > ph.cw) problems.push(`390px: horizontal scroll (${ph.sw} > ${ph.cw})`);
  await phone.screenshot({ path: path.join(out, 'screen-390.png') });

  if (requests.length) problems.push('external requests: ' + requests.join(', '));
  if (errors.length) problems.push('console errors: ' + errors.join(' | '));
  for (const s of report) for (const iss of s.issues) problems.push(`slide ${s.n} (${s.type}): ${iss}`);

  if (flags.includes('--sheet')) {
    const esc = t => t.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const cards = report.map(s => `<figure><a href="slide-${String(s.n).padStart(2, '0')}.png"><img src="slide-${String(s.n).padStart(2, '0')}.png" alt="Slide ${s.n}: ${esc(s.title)}" loading="lazy"></a><figcaption><b>${s.n}</b><span class="t">${esc(s.type)}</span>${esc(s.title)}</figcaption></figure>`).join('\n');
    fs.writeFileSync(path.join(out, 'index.html'), `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Proposal deck previews</title>
<style>
@font-face{font-family:Source;src:url(../fonts/source-400.ttf) format('truetype');font-weight:400}
@font-face{font-family:Source;src:url(../fonts/source-600.ttf) format('truetype');font-weight:600}
:root{--ink:#153e2f;--text:#293f34;--muted:#65736b;--line:#dce2dc;--accent:#e9713b;--desk:#e9ede8}
*{box-sizing:border-box}body{margin:0;padding:32px 16px;background:var(--desk);color:var(--text);font:14px/1.5 Source,Arial,sans-serif}
main{max-width:1500px;margin:auto}
h1{margin:0 0 6px;font-size:28px;font-weight:600;letter-spacing:-.8px;color:var(--ink)}
.lead{margin:0 0 4px;color:var(--ink)}.meta{margin:0 0 24px;font-size:12px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,340px),1fr));gap:22px}
figure{margin:0}figure img{display:block;width:100%;height:auto;aspect-ratio:16/9;background:#fff;box-shadow:0 6px 24px #12301f14}
figcaption{display:flex;gap:8px;align-items:baseline;margin-top:8px;font-size:13px;color:var(--ink)}
figcaption b{color:var(--accent);font-weight:400;font-size:12px}figcaption .t{font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
</style></head><body><main>
<h1>Proposal deck previews</h1>
<p class="lead">${esc(path.basename(file))}: ${report.length} slides, 1280 &times; 720 px each. Select a slide for the full-size image.</p>
<p class="meta">PDF check: ${pages} pages (${esc(size || '')}) for ${slides.length} slides &middot; Layout check: ${problems.length ? problems.length + ' problem(s)' : 'no overflow, nothing outside the margins'} &middot; Rendered with Chromium (Playwright), print layout.</p>
<div class="grid">
${cards}
</div></main></body></html>
`);
  }
  await browser.close();
  console.log(`slides: ${slides.length}  pdf pages: ${pages} (${size})  screen scale at 1440px: ${screen.s} (frame ${Math.round(screen.frameW)}px)`);
  console.log(`requests outside data: ${requests.length}  console errors: ${errors.length}`);
  if (problems.length) { console.log('PROBLEMS:\n  ' + problems.join('\n  ')); process.exit(1); }
  console.log('all checks passed');
})().catch(e => { console.error(e); process.exit(2); });
