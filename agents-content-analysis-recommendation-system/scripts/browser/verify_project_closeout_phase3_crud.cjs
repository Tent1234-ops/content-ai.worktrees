// Live UI proof on one isolated, non-training dataset row. Leaves the row archived.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'artifacts/browser/project-closeout-phase3');
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8000';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8082';
fs.mkdirSync(out, { recursive: true });

(async () => {
  const suffix = `${Date.now()}`;
  const requestedId = Number(process.argv[2] || process.env.VERIFY_DATASET_ID || 0);
  const title = process.argv[3] || process.env.VERIFY_DATASET_TITLE || `PHASE3 UI TEST ${suffix}`;
  const transcript = `ข้อความทดสอบ Phase 3 ${suffix} สำหรับยืนยันการสร้าง hash และหมวดโทรศัพท์`;
  const session = JSON.parse(execFileSync(
    'C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
    ['artifacts/settings_browser_session.py'],
    { cwd: root, encoding: 'utf8' },
  ).trim());
  const headers = {
    Authorization: `Bearer ${session.access_token}`,
    'X-Trend-Session-Key': session.session_key,
  };
  const report = { at: new Date().toISOString(), title, errors: [] };
  let browser;
  let datasetId = requestedId || undefined;
  try {
    async function rows(trashed) {
      const response = await fetch(
        `${api}/admin/datasets?trashed=${trashed}&limit=10&search=${encodeURIComponent(title)}`,
        { headers },
      );
      assert.equal(response.status, 200);
      return (await response.json()).items;
    }

    async function waitForState(trashed) {
      for (let attempt = 0; attempt < 30; attempt++) {
        const matching = (await rows(trashed)).find(
          row => !datasetId || row.dataset_id === datasetId,
        );
        if (matching) return matching;
        await new Promise(resolve => setTimeout(resolve, 250));
      }
      throw new Error(`Dataset #${datasetId} did not reach trashed=${trashed}`);
    }

    if (datasetId) {
      const archived = (await rows(true)).find(row => row.dataset_id === datasetId);
      if (archived) {
        const response = await fetch(
          `${api}/admin/datasets/${datasetId}/restore?confirmation_id=${datasetId}`,
          { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: '{}' },
        );
        assert.equal(response.status, 200);
      }
    }

    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 950 },
      serviceWorkers: 'block',
    });
    await context.addInitScript(data => {
      localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
      localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
      localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
    }, session);
    const page = await context.newPage();
    page.on('pageerror', error => report.errors.push(error.message));
    page.on('console', message => {
      if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/.test(message.text())) {
        report.errors.push(message.text());
      }
    });
    async function openDatasets() {
      await page.goto(`${web}/#/admin-datasets`, { waitUntil: 'networkidle' });
      await page.locator('flt-semantics-placeholder').evaluateAll(
        nodes => nodes.forEach(node => node.click()),
      );
      await page.waitForTimeout(500);
    }

    await openDatasets();
    if (!datasetId) {
      await page.getByRole('button', { name: 'เพิ่ม Dataset สำหรับตรวจสอบ' }).click();
      const category = page.getByRole('button', { name: /หมวดหมู่มาตรฐาน/ });
      await category.click();
      await page.getByRole('menuitem', {
        name: 'Technology > Electronics > Phone',
        exact: true,
      }).click();
      await page.getByRole('textbox', { name: 'ชื่อรายการ' }).fill(title);
      await page.getByRole('textbox', { name: 'Transcript' }).fill(transcript);
      await page.getByRole('button', { name: 'บันทึกเป็นรายการรอตรวจ' }).click();
      await page.getByRole('alertdialog').waitFor({ state: 'hidden' });
      const createdRow = await waitForState(false);
      datasetId = createdRow.dataset_id;
    }

    const created = await waitForState(false);
    assert.equal(created.data_split, 'unassigned');
    assert.equal(created.is_training_eligible, false);
    assert.equal(created.taxonomy_leaf_key, 'phone');
    assert.equal(created.transcript_sha256.length, 64);
    report.dataset_id = datasetId;
    report.created = {
      data_split: created.data_split,
      is_training_eligible: created.is_training_eligible,
      taxonomy_leaf_key: created.taxonomy_leaf_key,
      transcript_hash_length: created.transcript_sha256.length,
    };
    await page.screenshot({ path: path.join(out, 'dataset-crud-created.png') });

    await page.getByRole('button', { name: `ลบ Dataset #${datasetId}` }).click();
    await page.getByRole('button', { name: 'ยืนยันลบ Dataset' }).click();
    await waitForState(true);
    await openDatasets();
    await page.getByRole('tab', { name: /ถังขยะ/ }).click();
    await page.waitForTimeout(1200);
    fs.writeFileSync(
      path.join(out, 'crud-trash.txt'),
      await page.locator('body').ariaSnapshot(),
    );
    await page.screenshot({ path: path.join(out, 'crud-trash.png') });
    const restoreButton = page.getByRole('button', {
      name: `กู้คืน Dataset #${datasetId}`,
    });
    await restoreButton.waitFor();
    await restoreButton.click();
    await page.getByRole('button', { name: 'ยืนยันกู้คืน' }).click();
    await waitForState(false);
    await openDatasets();
    const deleteButton = page.getByRole('button', {
      name: `ลบ Dataset #${datasetId}`,
    });
    await deleteButton.waitFor();
    await deleteButton.click();
    await page.getByRole('button', { name: 'ยืนยันลบ Dataset' }).click();
    const archived = await waitForState(true);
    assert.equal(archived.dataset_id, datasetId);
    assert.equal(archived.is_training_eligible, false);
    assert.ok(archived.deleted_at);
    report.final_state = 'archived_non_training';
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } finally {
    if (datasetId) {
      const activeResponse = await fetch(
        `${api}/admin/datasets?limit=10&search=${encodeURIComponent(title)}`,
        { headers },
      ).catch(() => null);
      if (activeResponse && activeResponse.ok) {
        const rows = (await activeResponse.json()).items;
        if (rows.some(row => row.dataset_id === datasetId)) {
          await fetch(`${api}/admin/datasets/${datasetId}?confirmation_id=${datasetId}`, {
            method: 'DELETE', headers,
          }).catch(() => {});
        }
      }
    }
    await fetch(api + '/auth/logout', {
      method: 'POST',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: '{}',
    }).catch(() => {});
    if (browser) await browser.close();
    fs.writeFileSync(
      path.join(out, 'crud-verification.json'),
      JSON.stringify(report, null, 2),
    );
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
