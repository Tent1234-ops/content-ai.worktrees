const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const out = path.resolve(process.argv[2] || path.join(root, 'artifacts/browser/utility-review-audit'));
execFileSync('python', ['scripts/verification/utility_review_fixture.py', '--out', out], { cwd: root, stdio: 'inherit' });
execFileSync('ffmpeg', ['-f', 'lavfi', '-i', 'testsrc2=s=640x360:r=12', '-t', '1.2', '-c:v', 'libx264',
  '-pix_fmt', 'yuv420p', path.join(out, 'fixture.mp4')], { stdio: 'ignore' });
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const checks = [];
  try {
    for (const width of [1440, 1000]) {
      const context = await browser.newContext({ viewport: { width, height: 1050 }, acceptDownloads: true });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto(pathToFileURL(path.join(out, 'review.html')).href);
      await page.locator('#next').click();
      assert.match(await page.locator('#error').innerText(), /ยืนยัน/);
      await page.locator('#consent').check();
      await page.locator('#next').click();
      for (let caseIndex = 0; caseIndex < 2; caseIndex++) {
        await page.locator('video').waitFor();
        await page.waitForFunction(() => document.querySelector('video').readyState >= 2);
        await page.locator('video').evaluate(video => video.play());
        await page.waitForFunction(() => document.querySelector('video').currentTime > 0.1);
        await page.locator('#watched').check();
        await page.selectOption('#opp', 'yes');
        await page.fill('#preNote', 'Synthetic browser test, not a human judgement');
        await page.locator('#next').click();
        for (let position = 0; position < 3; position++) {
          if (caseIndex === 0) {
            if (await page.locator('.references').count()) {
              await page.locator('.references summary').click();
              await page.locator('.comparisons summary').click();
              assert.match(await page.locator('.references').innerText(), /ชาร์จได้เร็ว/);
              assert.match(await page.locator('.references').innerText(), /2026-09-29/);
              assert.match(await page.locator('.comparisons').innerText(), /-300/);
              assert.match(await page.locator('#root').innerText(), /หากรุ่นนี้รองรับ/);
              await page.screenshot({ path: path.join(out, `evidence-${width}.png`), fullPage: true });
            }
            for (const select of await page.locator('#scores select').all()) await select.selectOption('4');
          } else {
            await page.locator('#missed').check();
            await page.selectOption('#actionability', '4');
            await page.locator('#next').click();
            assert.match(await page.locator('#error').innerText(), /ให้คะแนนนำไปทำต่อได้ 1/);
            await page.selectOption('#actionability', '1');
            await page.fill('#lowReason', 'Synthetic missed opportunity fixture');
          }
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
          await page.locator('#next').click();
          if (position === 0) {
            await page.reload();
            assert.match(await page.locator('#root').innerText(), /ชุดคำแนะนำ 2/);
          }
        }
      }
      assert.match(await page.locator('#root').innerText(), /ประเมินครบแล้ว/);
      const downloadPromise = page.waitForEvent('download');
      await page.locator('#export').click();
      const download = await downloadPromise;
      await download.saveAs(path.join(out, 'synthetic-responses.json'));
      assert.equal(JSON.parse(fs.readFileSync(path.join(out, 'synthetic-responses.json'), 'utf8')).ratings.length, 6);
      assert.deepEqual(errors, []);
      checks.push({ width, videoPlayed: true, evidenceVisible: true, restoredDraft: true, overflow: false });
      await context.close();
    }
    execFileSync('python', ['scripts/verification/utility_review_fixture.py', '--out', out, '--validate'], { cwd: root, stdio: 'inherit' });
    fs.writeFileSync(path.join(out, 'browser-checks.json'), JSON.stringify({ syntheticOnly: true, checks }, null, 2));
    console.log(JSON.stringify({ passed: true, out, checks }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
