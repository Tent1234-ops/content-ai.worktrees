// Real browser acceptance: no API interception, fixture transcripts, or model changes.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'artifacts/acceptance/20260930');
const web = 'http://127.0.0.1:8080';
const api = 'http://127.0.0.1:8000';
fs.mkdirSync(out, { recursive: true });
const credentialsPath = path.join(out, 'private-session.json');
const account = fs.existsSync(credentialsPath) ? JSON.parse(fs.readFileSync(credentialsPath)) : {
  username: `acceptance_${Date.now()}`, password: crypto.randomBytes(18).toString('hex'),
};
account.email ||= `${account.username}@example.com`;
fs.writeFileSync(credentialsPath, JSON.stringify(account));
const reportPath = path.join(out, 'browser.json');
const report = fs.existsSync(reportPath) ? JSON.parse(fs.readFileSync(reportPath)) : {
  started_at: new Date().toISOString(), real_backend: true, real_asr: true,
  novel_test_clip: false, checks: [], errors: [], http_errors: [], screenshots: [] };
delete report.failure;
function persist() { fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify(report, null, 2)); }
function pass(name, details = {}) {
  report.checks = report.checks.filter(c => c.name !== name);
  report.checks.push({ name, status: 'passed', ...details }); persist(); console.log(name);
}
let browser, page, context;
async function open(route) {
  await page.goto(web + '/#' + route, { waitUntil: 'networkidle' });
  await page.locator('flt-semantics-placeholder').evaluateAll(nodes => nodes.forEach(n => n.click()));
  await page.waitForTimeout(1200);
}
async function shot(name) {
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  fs.writeFileSync(path.join(out, `${name}.txt`), await page.locator('body').ariaSnapshot());
  report.screenshots.push(name); persist();
}
async function seek(name, role = 'button') {
  for (let n = 0; n < 55; n++) {
    let pos;
    for (const locator of await page.getByRole(role, { name, exact: false }).all()) {
      const box = await locator.boundingBox().catch(() => null);
      if (box && box.y > 65 && box.y + box.height / 2 < 955) return locator;
      pos ||= box;
    }
    await page.mouse.move(1150, 600);
    await page.mouse.wheel(0, pos && pos.y < 65 ? -340 : 340);
    await page.waitForTimeout(160);
  }
  throw new Error(`Cannot reach ${role} ${name}`);
}
async function input(name, value) {
  await (await seek(name, 'textbox')).click();
  await page.keyboard.press('ControlOrMeta+A');
  await page.keyboard.insertText(value);
}
async function read(url) {
  const response = await fetch(api + url, { headers: { Authorization: `Bearer ${account.session.access_token}`,
    'X-Trend-Session-Key': account.session.session_key } });
  assert.equal(response.status, 200, url);
  return response.json();
}
(async () => {
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block',
      permissions: ['clipboard-read', 'clipboard-write'] });
    page = await context.newPage();
    page.on('pageerror', e => report.errors.push(e.message));
    page.on('console', m => { if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(m.text())) report.errors.push(m.text()); });
    page.on('response', r => { if (r.url().startsWith(api) && r.status() >= 400) report.http_errors.push({ url: r.url(), status: r.status() }); });
    await open('/dashboard'); await shot('01-public-dashboard');
    assert.ok((await page.locator('body').ariaSnapshot()).includes('YouTube'));
    pass('Public dashboard loads without login');
    await open('/upload');
    assert.ok((await page.locator('body').ariaSnapshot()).includes('Welcome back'));
    pass('Guest upload requires login');
    if (!account.registered) {
      await open('/register');
      await input('Username', account.username); await input('Email', account.email); await input('Password', account.password);
      const registration = page.waitForResponse(r => r.url().endsWith('/auth/register') && r.request().method() === 'POST');
      await page.getByRole('button', { name: 'Register', exact: true }).click();
      assert.equal((await registration).status(), 201);
      account.registered = true; fs.writeFileSync(credentialsPath, JSON.stringify(account));
      pass('Register through UI');
    }
    await open('/login'); await input('Email', account.email); await input('Password', account.password);
    const login = page.waitForResponse(r => r.url().endsWith('/auth/login') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Login', exact: true }).click();
    const lr = await login; assert.equal(lr.status(), 200);
    account.session = await lr.json(); fs.writeFileSync(credentialsPath, JSON.stringify(account));
    pass('Login through UI', { user_id: account.session.user.user_id });
    await page.waitForTimeout(1500);
    await open('/upload'); await shot('02-upload');
    const settings = await read('/analyze/settings');
    fs.writeFileSync(path.join(out, 'analysis-settings.json'), JSON.stringify(settings, null, 2));
    if (!account.content_id) {
      const chooser = page.waitForEvent('filechooser');
      await (await seek('Pick a Video File')).click();
      await (await chooser).setFiles(path.join(root, 'videos/Review_Phone.mp4'));
      await page.waitForTimeout(2000); await shot('03-file-selected');
      const upload = page.waitForResponse(r => r.url().endsWith('/analyze/save') && r.request().method() === 'POST', { timeout: 90000 });
      await (await seek('Analyze Now')).click();
      const ur = await upload; assert.equal(ur.status(), 200, await ur.text());
      const job = await ur.json(); account.job_id = job.job_id;
      fs.writeFileSync(credentialsPath, JSON.stringify(account));
      pass('Real MP4 uploaded through UI', { job_id: job.job_id });
      const deadline = Date.now() + 15 * 60 * 1000;
      let result;
      while (Date.now() < deadline) {
        result = await read(`/jobs/${job.job_id}`);
        fs.writeFileSync(path.join(out, 'analysis-job.json'), JSON.stringify(result, null, 2));
        if (['failed', 'error'].includes(result.status)) throw new Error(`Analysis failed: ${JSON.stringify(result)}`);
        if (['completed', 'done', 'finished'].includes(result.status)) break;
        await page.waitForTimeout(4000);
      }
      assert.ok(['completed', 'done', 'finished'].includes(result.status), 'Analysis deadline exceeded');
      const history = await read('/contents/my');
      account.content_id = history.items[0]?.content_id;
      assert.ok(account.content_id, 'Analysis must be saved in My Ideas');
      fs.writeFileSync(credentialsPath, JSON.stringify(account));
      pass('Real ASR/classification/recommendation saved', { content_id: account.content_id });
      await page.waitForTimeout(3000);
      await shot('04-analysis-result');
    }
    const detail = await read(`/contents/${account.content_id}`);
    fs.writeFileSync(path.join(out, 'analysis-detail.json'), JSON.stringify(detail, null, 2));
    await open('/history'); await shot('05-history');
    await (await seek(detail.title.slice(0, 50))).click(); await page.waitForTimeout(1200);
    await shot('06-reopened-result');
    const reopened = await read(`/contents/${account.content_id}`);
    assert.deepEqual(reopened, detail);
    pass('Saved result reopened without changes');
    for (let n = 0; n < 5; n++) {
      await page.mouse.move(1150, 640); await page.mouse.wheel(0, 660); await page.waitForTimeout(350);
      await shot(`07-result-section-${n}`);
    }
    const plan = await read(`/contents/${account.content_id}/revision-plan`);
    fs.writeFileSync(path.join(out, 'plan-before.json'), JSON.stringify(plan, null, 2));
    await input('รายละเอียดแผนปรับคลิป', 'ตรวจรับระบบ 30/09/2026: ทบทวนหลักฐานก่อนถ่ายฉากเพิ่มเติม');
    await (await seek('บันทึกแผนปรับคลิป')).click(); await page.waitForTimeout(800);
    const after = await read(`/contents/${account.content_id}/revision-plan`);
    assert.ok(after.notes.includes('30/09/2026'));
    pass('Clip plan saved through UI and API readback', { revision: after.revision });
    await shot('08-plan-saved');
    await open('/history');
    await (await seek(detail.title.slice(0, 50))).click(); await page.waitForTimeout(1000);
    await (await seek('รายละเอียดแผนปรับคลิป', 'textbox')).click();
    const values = await page.locator('input, textarea').evaluateAll(nodes => nodes.map(n => n.value));
    assert.ok(values.some(v => v.includes('30/09/2026')));
    pass('Saved plan restored in UI');
    await shot('09-plan-reopened');
    await open('/admin-users');
    assert.ok(!page.url().includes('/admin-users'));
    pass('Normal user blocked from admin UI');
  } catch (error) {
    report.failure = error.message; console.error(error.message);
    if (page) await shot('failure').catch(() => {});
    process.exitCode = 1;
  } finally {
    report.finished_at = new Date().toISOString(); persist();
    if (browser) await browser.close();
    console.log(JSON.stringify({ checks: report.checks, errors: report.errors, failure: report.failure }, null, 2));
  }
})();
