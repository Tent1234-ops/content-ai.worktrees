// Current release-browser acceptance for Closeout Phase 5. Read-only workflows only.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '../..');
const runId = process.argv[2] || process.env.PHASE5_RUN_ID || `phase5-${new Date().toISOString().replace(/[:.]/g, '-')}`;
const out = path.join(root, 'artifacts/project-closeout', runId, 'browser');
const reportPath = path.join(out, 'verification.json');
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8000';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8080';
if (fs.existsSync(reportPath)) throw new Error(`Refusing to overwrite ${reportPath}`);
fs.mkdirSync(out, { recursive: true });

(async () => {
  const session = JSON.parse(execFileSync(
    'C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
    ['artifacts/settings_browser_session.py'],
    { cwd: root, encoding: 'utf8' },
  ).trim());
  const report = {
    schemaVersion: 'project-closeout-phase5-browser-v1',
    runId,
    capturedAt: new Date().toISOString(),
    releaseBuild: 'frontend_flutter/build/web',
    evidenceType: 'live backend/database reads through current release web build',
    constraints: ['no provider fetch', 'no valid upload', 'no business-data mutation'],
    checks: [], screenshots: [], apiRequests: [], errors: [], layout: [],
  };
  let browser;

  function pass(name, details = {}) { report.checks.push({ name, status: 'passed', ...details }); }
  function blocked(name, reason) { report.checks.push({ name, status: 'blocked', reason }); }
  function observe(page) {
    page.on('pageerror', error => report.errors.push(error.message));
    page.on('console', message => {
      if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/i.test(message.text())) report.errors.push(message.text());
    });
    page.on('response', response => {
      if (response.url().startsWith(api)) report.apiRequests.push({ url: response.url(), status: response.status() });
    });
  }
  async function semantics(page) {
    await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(node => node.click()));
  }
  async function open(page, route) {
    await page.goto(`${web}/#${route}`, { waitUntil: 'networkidle' });
    await semantics(page);
    await page.waitForTimeout(800);
  }
  async function shot(page, name) {
    const dimensions = await page.evaluate(() => ({
      viewport: window.innerWidth,
      document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
    }));
    report.layout.push({ name, ...dimensions });
    assert.ok(dimensions.document <= dimensions.viewport + 1, `${name}: horizontal document overflow`);
    await page.screenshot({ path: path.join(out, `${name}.png`) });
    fs.writeFileSync(path.join(out, `${name}.txt`), await page.locator('body').ariaSnapshot());
    report.screenshots.push(name);
  }
  async function seek(page, text) {
    for (let attempt = 0; attempt < 45; attempt += 1) {
      const candidates = [
        page.getByText(text, { exact: false }),
        page.getByRole('group', { name: text, exact: false }),
        page.getByRole('heading', { name: text, exact: false }),
        page.getByRole('button', { name: text, exact: false }),
      ];
      for (const candidate of candidates) {
        for (const locator of await candidate.all()) {
          const box = await locator.boundingBox().catch(() => null);
          if (box && box.y >= 60 && box.y < page.viewportSize().height - 50) return locator;
        }
      }
      await page.mouse.move(page.viewportSize().width - 50, page.viewportSize().height - 80);
      await page.mouse.wheel(0, attempt % 12 === 11 ? -1800 : 520);
      await page.waitForTimeout(150);
    }
    throw new Error(`Cannot reach text: ${text}`);
  }
  async function scrollToTop(page) {
    for (let attempt = 0; attempt < 10; attempt += 1) {
      await page.mouse.move(page.viewportSize().width - 50, 100);
      await page.mouse.wheel(0, -2200);
      await page.waitForTimeout(80);
    }
  }

  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    for (const viewport of [{ width: 1440, height: 900 }, { width: 1000, height: 800 }]) {
      const suffix = `${viewport.width}x${viewport.height}`;
      const guestContext = await browser.newContext({ viewport, serviceWorkers: 'block' });
      const guest = await guestContext.newPage();
      observe(guest);
      await open(guest, '/dashboard');
      await (await seek(guest, 'อันดับวิดีโอบน YouTube ตอนนี้')).waitFor();
      await shot(guest, `guest-youtube-${suffix}`);
      await guest.getByRole('button', { name: 'ดูรายละเอียด' }).first().click();
      await guest.getByText('รายละเอียดเทรนด์', { exact: true }).waitFor();
      await shot(guest, `guest-youtube-detail-${suffix}`);
      await guest.getByRole('button', { name: 'ปิด' }).click();

      await (await seek(guest, 'ดูเพิ่มเติม')).click();
      await (await seek(guest, 'แสดง 24 จาก 50 รายการ')).waitFor();
      await shot(guest, `guest-youtube-more-${suffix}`);
      await (await seek(guest, 'อันดับย้อนหลัง')).waitFor();
      await shot(guest, `guest-youtube-history-${suffix}`);
      const evidenceButton = await seek(guest, 'ดูตารางข้อมูลกราฟ');
      await evidenceButton.click();
      await guest.getByText('ข้อมูลที่ใช้วาดกราฟ', { exact: true }).waitFor();
      await shot(guest, `guest-youtube-history-evidence-${suffix}`);
      await guest.getByRole('button', { name: 'ปิด', exact: true }).click();

      await scrollToTop(guest);
      const categorySelector = guest.getByRole('button', {
        name: 'เลือกแพลตฟอร์ม หมวดหมู่ ทั้งหมด', exact: true,
      });
      const categoryBox = await categorySelector.boundingBox();
      assert.ok(categoryBox, 'YouTube category selector is not visible');
      await categorySelector.click({ position: { x: 180, y: categoryBox.height - 20 } });
      const categoryHistory = guest.waitForResponse(response =>
        response.url().includes('/dashboard/public/history?') &&
        response.url().includes('video_category_id=20'),
      );
      await guest.getByRole('menuitem', { name: /เกม \(/ }).click();
      assert.equal((await categoryHistory).status(), 200);
      await (await seek(guest, 'อันดับวิดีโอ YouTube หมวดเกม')).waitFor();
      await shot(guest, `guest-youtube-category-${suffix}`);

      await guest.getByRole('tab', { name: 'Google' }).click();
      await (await seek(guest, 'อันดับคำค้นบน Google ตอนนี้')).waitFor();
      await shot(guest, `guest-google-${suffix}`);
      await guest.getByRole('tab', { name: 'TikTok' }).click();
      await (await seek(guest, 'TikTok ยังไม่พร้อมใช้งาน')).waitFor();
      await shot(guest, `guest-tiktok-${suffix}`);
      await open(guest, '/upload');
      assert.ok((await guest.locator('body').ariaSnapshot()).includes('เข้าสู่ระบบ'));
      await shot(guest, `guest-auth-gate-${suffix}`);
      pass(`Guest dashboard, platform separation, detail, and auth gate ${suffix}`);
      await guestContext.close();

      const context = await browser.newContext({ viewport, serviceWorkers: 'block' });
      await context.addInitScript(data => {
        localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
        localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
        localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
      }, session);
      const page = await context.newPage();
      observe(page);

      await open(page, '/upload');
      await shot(page, `private-upload-${suffix}`);
      await open(page, '/history');
      await shot(page, `private-history-${suffix}`);
      const headers = { Authorization: `Bearer ${session.access_token}`, 'X-Trend-Session-Key': session.session_key };
      const historyResponse = await fetch(`${api}/contents/my?limit=50`, { headers });
      assert.equal(historyResponse.status, 200);
      const history = await historyResponse.json();
      const result = history.items?.find(item => item.domain === 'phone') || history.items?.[0];
      if (result) {
        await (await seek(page, result.title)).click();
        await page.getByText('1. พบอะไรในคลิป', { exact: true }).waitFor();
        await shot(page, `private-result-${suffix}`);
        pass(`Saved result reopens from history ${suffix}`, { contentId: result.content_id });
      } else {
        blocked(`Saved result reopens from history ${suffix}`, 'No saved result belongs to the verification admin');
      }

      const adminRoutes = [
        ['/admin-users', 'users', 'button', 'เพิ่มผู้ใช้'],
        ['/admin-training', 'training', 'text', 'โมเดลที่ใช้งานอยู่'],
        ['/admin-analysis-settings', 'settings', 'text', 'วิดีโอและการถอดเสียง'],
        ['/admin-transcript-import', 'import', 'button', 'ไฟล์ Markdown'],
        ['/admin-dataset-review', 'review', 'group', 'ความครอบคลุมที่ตรวจสอบแล้ว'],
        ['/admin-datasets', 'datasets', 'tab', 'รายการข้อมูล'],
        ['/admin-logs', 'logs', 'button', 'สถานะ'],
      ];
      for (const [route, name, readyRole, readyName] of adminRoutes) {
        await open(page, route);
        assert.ok(page.url().includes(`#${route}`), `${route}: route did not open`);
        const ready = readyRole === 'text'
          ? page.getByText(readyName, { exact: false }).first()
          : page.getByRole(readyRole, { name: readyName, exact: false }).first();
        await ready.waitFor({ state: 'visible', timeout: 30000 });
        await page.waitForTimeout(300);
        const snapshot = await page.locator('body').ariaSnapshot();
        assert.ok(snapshot.length > 80, `${route}: empty accessibility tree`);
        await shot(page, `admin-${name}-${suffix}`);
      }
      pass(`Private and seven Admin surfaces load ${suffix}`);
      await context.close();
    }

    const unexpectedHttp = report.apiRequests.filter(row => row.status >= 400);
    assert.deepEqual(unexpectedHttp, []);
    assert.deepEqual(report.errors, []);
    report.passed = report.checks.every(row => row.status === 'passed');
  } catch (error) {
    report.failure = error.stack || error.message;
    report.passed = false;
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
    report.finishedAt = new Date().toISOString();
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    process.stdout.write(JSON.stringify({ reportPath, passed: report.passed, checks: report.checks.length, screenshots: report.screenshots.length }));
  }
})().catch(error => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
