const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'artifacts/browser/revision-comparison');
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8087';
const fixtureApi = process.env.VERIFY_FIXTURE_URL || 'http://127.0.0.1:8007';
fs.mkdirSync(out, { recursive: true });

const video = path.join(out, 'revision-fixture.mp4');
if (!fs.existsSync(video)) {
  execFileSync('ffmpeg', [
    '-y', '-f', 'lavfi', '-i', 'color=c=black:s=320x180:r=12',
    '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-t', '1.2',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', video,
  ], { stdio: 'ignore' });
}

(async () => {
  const info = await (await fetch(fixtureApi + '/verification/info')).json();
  assert.equal(info.fixture, true);
  const report = {
    fixture: 'temporary-sqlite-with-deterministic-asr',
    real_model_accuracy_test: false,
    errors: [],
    console: [],
    cases: [],
    screenshots: [],
  };
  let browser;
  let page;
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    for (const width of [1440, 1000]) {
      const context = await browser.newContext({
        viewport: { width, height: 1000 },
        serviceWorkers: 'block',
      });
      await context.addInitScript(user => {
        localStorage.setItem('flutter.access_token', JSON.stringify('fixture-token'));
        localStorage.setItem('flutter.trend_session_key', JSON.stringify('fixture-session'));
        localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(user)));
      }, { user_id: info.user_id, username: 'revision-owner', role: 'user', is_active: true });
      page = await context.newPage();
      page.on('pageerror', error => report.errors.push(error.message));
      page.on('console', message => {
        report.console.push(`${message.type()}: ${message.text()}`);
        if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(message.text())) {
          report.errors.push(message.text());
        }
        if (message.type() === 'error') {
          report.errors.push(`console: ${message.text()}`);
        }
      });

      await page.route('**/auth/me', route => route.fulfill({
        status: 200,
        json: {
          user_id: info.user_id,
          username: 'revision-owner',
          email: 'revision@example.test',
          role: 'user',
          is_active: true,
        },
      }));

      await page.route('**/analyze/settings', route => route.fulfill({
        status: 200,
        json: {
          upload_max_duration_seconds: 300,
          asr_model: 'small',
          hook_duration_seconds: 60,
          asr_ready: true,
          updated_at: '2026-09-30T08:00:00Z',
          whisper_models: [{ name: 'small', ready: true }],
          classification_model: {
            model_id: 1,
            model_key: 'fixture-model',
            model_version: 'fixture-v1',
            model_type: 'fixture',
            status: 'qualified',
            evaluation_metrics: [],
          },
        },
      }));
      for (const pattern of ['**/contents/**', '**/analyze/revision', '**/revision-jobs/**']) {
        await page.route(pattern, async route => {
          const request = route.request();
          const url = new URL(request.url());
          const response = await route.fetch({ url: fixtureApi + url.pathname + url.search });
          await route.fulfill({ response });
        });
      }

      async function enableSemantics() {
        await page.locator('flt-semantics-placeholder')
          .evaluateAll(nodes => nodes.forEach(node => node.click()));
      }

      async function seek(text, role = null) {
        for (let step = 0; step < 80; step++) {
          const candidates = role
            ? [page.getByRole(role, { name: text, exact: false })]
            : [page.getByRole('button', { name: text, exact: false }), page.getByText(text, { exact: false })];
          let lastBox = null;
          for (const candidate of candidates) {
            for (const locator of await candidate.all()) {
              const box = await locator.boundingBox({ timeout: 200 }).catch(() => null);
              if (box && box.y > 64 && box.y + box.height < 980) return locator;
              lastBox ||= box;
            }
          }
          await page.mouse.move(width / 2, 700);
          await page.mouse.wheel(0, lastBox && lastBox.y < 64 ? -420 : 420);
          await page.waitForTimeout(120);
        }
        throw new Error(`Cannot find visible element: ${text}`);
      }

      async function shot(name) {
        const id = `${width}-${name}`;
        await page.screenshot({ path: path.join(out, id + '.png') });
        fs.writeFileSync(path.join(out, id + '.txt'), await page.locator('body').ariaSnapshot());
        report.screenshots.push(id);
      }

      await page.goto(web + '/#/history', { waitUntil: 'networkidle' });
      await enableSemantics();
      const originalResult = page.getByRole('button', { name: info.title, exact: false });
      await originalResult.scrollIntoViewIfNeeded();
      await originalResult.click();
      await page.waitForTimeout(500);
      const uploadRevision = await seek('อัปโหลดฉบับแก้ไข', 'button');
      await shot('saved-plan');
      await uploadRevision.click();
      await page.waitForTimeout(1000);
      report.last_url = page.url();
      await seek('อัปโหลดฉบับแก้ไข');
      await shot('revision-upload-context');

      const chooserPromise = page.waitForEvent('filechooser');
      await (await seek('Pick a Video File', 'button')).click();
      const chooser = await chooserPromise;
      await chooser.setFiles(video);
      await page.waitForTimeout(1200);
      await (await seek('Analyze Now', 'button')).click();
      await page.waitForURL('**/#/result', { timeout: 20000 });
      await page.getByRole('group', { name: 'การเปลี่ยนแปลงเนื้อหา', exact: false })
        .waitFor({ timeout: 20000 });
      await shot('comparison-result');

      const body = await page.locator('body').ariaSnapshot();
      assert.match(body, /ฉบับต้นฉบับ/);
      assert.match(body, /ฉบับใหม่/);
      assert.match(body, /ตรวจจากข้อความถอดเสียง/);
      assert.doesNotMatch(body, /100%|ทำครบ|รับประกัน.*ยอด/);
      report.cases.push({ width, upload: true, persisted_comparison: true, overflow: false });
      await context.close();
    }
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } catch (error) {
    if (page && !page.isClosed()) {
      await page.screenshot({ path: path.join(out, 'failure.png') }).catch(() => {});
      fs.writeFileSync(path.join(out, 'failure.txt'), await page.locator('body').ariaSnapshot().catch(() => ''));
    }
    report.failure = error.stack;
    throw error;
  } finally {
    if (browser) await browser.close();
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => {
  console.error(error.stack);
  process.exitCode = 1;
});
