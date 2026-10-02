// Phase 4 UI proof against the latest release build. Data workflows stay read-only.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'artifacts/browser/project-closeout-phase4');
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8000';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8080';
fs.mkdirSync(out, { recursive: true });

(async () => {
  const session = JSON.parse(execFileSync(
    'C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
    ['artifacts/settings_browser_session.py'],
    { cwd: root, encoding: 'utf8' },
  ).trim());
  const report = {
    at: new Date().toISOString(),
    build: 'frontend_flutter/build/web',
    evidenceType: 'live database reads; no provider fetch or application data mutation',
    viewports: ['1440x900', '1000x800'],
    screenshots: [],
    apiRequests: [],
    errors: [],
    layoutChecks: [],
  };
  let browser;

  async function activateSemantics(page) {
    await page.locator('flt-semantics-placeholder').evaluateAll(
      nodes => nodes.forEach(node => node.click()),
    );
  }

  async function open(page, route) {
    await page.goto(`${web}/#${route}`, { waitUntil: 'networkidle' });
    await activateSemantics(page);
    await page.waitForTimeout(900);
  }

  async function checkLayout(page, name) {
    const dimensions = await page.evaluate(() => ({
      width: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
    }));
    report.layoutChecks.push({ name, ...dimensions });
    assert.ok(
      dimensions.documentWidth <= dimensions.width + 1,
      `${name}: document has horizontal overflow`,
    );
  }

  async function shot(page, name) {
    await checkLayout(page, name);
    await page.screenshot({ path: path.join(out, `${name}.png`) });
    fs.writeFileSync(
      path.join(out, `${name}.txt`),
      await page.locator('body').ariaSnapshot(),
    );
    report.screenshots.push(name);
  }

  async function seek(page, label) {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      let position = null;
      const candidates = [
        page.getByText(label, { exact: true }),
        page.getByText(label, { exact: false }),
        page.getByRole('group', { name: label, exact: false }),
        page.getByRole('button', { name: label, exact: false }),
        page.getByRole('tab', { name: label, exact: false }),
        page.getByRole('heading', { name: label, exact: false }),
      ];
      for (const candidate of candidates) {
        for (const item of await candidate.all()) {
          const box = await item.boundingBox({ timeout: 250 }).catch(() => null);
          if (box && box.y >= 64 && box.y < page.viewportSize().height - 64) {
            return item;
          }
          position ||= box;
        }
      }
      await page.mouse.move(page.viewportSize().width - 60, page.viewportSize().height - 100);
      const delta = position?.y < 64 || attempt % 10 === 9 ? -1600 : 420;
      await page.mouse.wheel(0, delta);
      await page.waitForTimeout(180);
    }
    throw new Error(`Visible section not found: ${label}`);
  }

  function observe(page) {
    page.on('pageerror', error => report.errors.push(error.message));
    page.on('console', message => {
      if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/i.test(message.text())) {
        report.errors.push(message.text());
      }
    });
    page.on('response', response => {
      if (response.url().startsWith(api)) {
        report.apiRequests.push({ url: response.url(), status: response.status() });
      }
    });
  }

  try {
    const headers = {
      Authorization: `Bearer ${session.access_token}`,
      'X-Trend-Session-Key': session.session_key,
    };
    const historyResponse = await fetch(`${api}/contents/my?limit=50`, { headers });
    assert.equal(historyResponse.status, 200);
    const history = await historyResponse.json();
    const selected = history.items?.find(item => item.domain === 'phone') || history.items?.[0];
    assert.ok(selected, 'A saved result is required for result-page UI proof');

    browser = await chromium.launch({ channel: 'msedge', headless: true });
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 1000, height: 800 },
    ]) {
      const suffix = `${viewport.width}x${viewport.height}`;

      const guestContext = await browser.newContext({ viewport, serviceWorkers: 'block' });
      const guest = await guestContext.newPage();
      observe(guest);
      await open(guest, '/dashboard');
      await shot(guest, `dashboard-initial-${suffix}`);
      await seek(guest, 'อันดับวิดีโอบน YouTube ตอนนี้');
      await shot(guest, `dashboard-youtube-${suffix}`);
      const detail = guest.getByRole('button', { name: 'ดูรายละเอียด' }).first();
      await detail.click();
      await guest.getByText('รายละเอียดเทรนด์', { exact: true }).waitFor();
      await shot(guest, `dashboard-detail-${suffix}`);
      await guest.getByRole('button', { name: 'ปิด' }).click();
      await guest.getByRole('tab', { name: 'Google' }).click();
      await seek(guest, 'อันดับคำค้นบน Google ตอนนี้');
      await shot(guest, `dashboard-google-${suffix}`);
      await guest.getByRole('tab', { name: 'TikTok' }).click();
      await seek(guest, 'TikTok ยังไม่พร้อมใช้งาน');
      await shot(guest, `dashboard-tiktok-${suffix}`);
      await open(guest, '/login');
      await guest.getByLabel('อีเมล').focus();
      await guest.keyboard.press('Tab');
      const passwordFocused = await guest.getByLabel('รหัสผ่าน').evaluate(
        element => element === document.activeElement,
      );
      assert.equal(passwordFocused, true, 'Login keyboard order must reach password');
      await shot(guest, `login-${suffix}`);
      await open(guest, '/register');
      await shot(guest, `register-${suffix}`);
      await guestContext.close();

      const adminContext = await browser.newContext({ viewport, serviceWorkers: 'block' });
      await adminContext.addInitScript(data => {
        localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
        localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
        localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
      }, session);
      const page = await adminContext.newPage();
      observe(page);

      await open(page, '/upload');
      await seek(page, 'วิเคราะห์คลิปของคุณ');
      await shot(page, `upload-${suffix}`);
      await open(page, '/history');
      await seek(page, 'ผลวิเคราะห์');
      await shot(page, `history-${suffix}`);
      await page.goto(`${web}/#/result`, { waitUntil: 'networkidle' });
      await activateSemantics(page);
      await page.evaluate(contentId => {
        sessionStorage.setItem('phase4_result_content_id', String(contentId));
      }, selected.content_id);
      // Flutter route arguments cannot be injected through a hash URL; open from History.
      await open(page, '/history');
      await (await seek(page, selected.title)).click();
      await page.getByText('1. พบอะไรในคลิป', { exact: true }).waitFor();
      await shot(page, `result-found-${suffix}`);
      await seek(page, '2. ควรเพิ่มอะไร');
      await shot(page, `result-advice-${suffix}`);

      const adminRoutes = [
        ['/admin-users', 'users', 'เพิ่มผู้ใช้'],
        ['/admin-training', 'training', 'โมเดลที่ใช้งานอยู่'],
        ['/admin-analysis-settings', 'settings', 'วิดีโอและการถอดเสียง'],
        ['/admin-transcript-import', 'transcript-import', 'ไฟล์ Markdown'],
        ['/admin-dataset-review', 'dataset-review', 'ความครอบคลุมที่ตรวจสอบแล้ว'],
        ['/admin-datasets', 'datasets', 'รายการข้อมูล'],
        ['/admin-logs', 'logs', 'สถานะ'],
      ];
      for (const [route, name, readyLabel] of adminRoutes) {
        await open(page, route);
        await seek(page, readyLabel);
        await shot(page, `${name}-${suffix}`);
      }
      await open(page, '/admin-datasets');
      await page.getByRole('button', { name: 'เพิ่ม Dataset สำหรับตรวจสอบ' }).click();
      await page.getByText('เพิ่ม Dataset สำหรับตรวจสอบ', { exact: true }).last().waitFor();
      await shot(page, `dataset-create-form-${suffix}`);
      await page.getByRole('button', { name: 'ยกเลิก' }).click();
      await adminContext.close();
    }

    assert.deepEqual(report.errors, []);
    const failedApi = report.apiRequests.filter(item => item.status >= 400);
    assert.deepEqual(failedApi, []);
    report.passed = true;
  } catch (error) {
    report.failure = error.stack || error.message;
    throw error;
  } finally {
    await fetch(`${api}/auth/logout`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        'X-Trend-Session-Key': session.session_key,
        'Content-Type': 'application/json',
      },
      body: '{}',
    }).catch(() => {});
    if (browser) await browser.close();
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
