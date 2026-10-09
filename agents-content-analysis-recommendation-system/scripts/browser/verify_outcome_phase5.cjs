// Outcome Phase 5 browser proof: live admin reads plus explicitly synthetic user-result fixtures.
const { chromium } = require('../../artifacts/browser-tools/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '../..');
const out = path.resolve(process.argv[2]);
const api = process.env.VERIFY_API_URL || 'http://127.0.0.1:8000';
const web = process.env.VERIFY_WEB_URL || 'http://127.0.0.1:8080';
if (fs.existsSync(path.join(out, 'verification.json'))) {
  throw new Error('Use a new Phase 5 evidence directory');
}
fs.mkdirSync(out, { recursive: true });

const report = {
  schemaVersion: 'outcome-prediction-phase5-browser-v1',
  at: new Date().toISOString(),
  liveEvidence: 'real API reads; no train, test-open, dataset change, or model activation',
  fixtureEvidence: 'explicit synthetic UI payload; never written to the application database',
  viewports: ['1440x900', '1000x800', '390x844'],
  apiRequests: [],
  screenshots: [],
  errors: [],
  layout: [],
  fixtureRouteHits: 0,
  passed: false,
};

const assessment = {
  schema_version: 'outcome-assessment-v1',
  status: 'available',
  reason_codes: [],
  target_version: 'reference_relative_views_v1',
  protocol_version: 'reference-relative-views-protocol-v1',
  feature_version: 'outcome-features-v1',
  model_id: 9001,
  model_version: 'SYNTHETIC-BROWSER-ONLY',
  probability: 0.62,
  fixture_only: true,
  context: {
    accepted_category: 'camera',
    confirmed_format: 'long_form',
    frozen_age_context: 'age_7_30_days',
  },
  evaluated_scope: { category: 'camera', confirmed_format: 'long_form' },
  support_summary: { benchmark: { video_count: 30, channel_count: 8 } },
  evidence_topic_ids: ['topic:low-light'],
  limitations: [
    'ค่าประเมินนี้เปรียบเทียบกับกลุ่มอ้างอิง ไม่ใช่การคาดการณ์ยอดวิวจริง',
    'ผลเป็นความสัมพันธ์จากข้อมูลเชิงสังเกต ไม่ได้พิสูจน์เหตุและผล',
  ],
};

const resultFixture = {
  content_id: 24,
  analysis_id: 31,
  recommendation_fingerprint: 'b'.repeat(64),
  outcome_assessment_fingerprint: 'a'.repeat(64),
  title: 'TEST FIXTURE: รีวิวกล้องสำหรับตรวจ UI',
  created_at: '2026-10-09T10:00:00Z',
  transcript: 'รีวิวกล้องและรายละเอียดสีของภาพจากการใช้งานจริง',
  raw_transcript: 'รีวิวกล้องและรายละเอียดสีของภาพจากการใช้งานจริง',
  cleaned_transcript: 'รีวิวกล้องและรายละเอียดสีของภาพจากการใช้งานจริง',
  analysis: { analysis: { title: 'TEST FIXTURE: รีวิวกล้องสำหรับตรวจ UI' } },
  nlp_result: {},
  recommendation: {
    domain: 'camera',
    content_keywords: ['กล้อง', 'สีของภาพ'],
    comparable_keywords: ['camera review'],
    hook_terms: ['รีวิวกล้อง'],
    missing_keywords: [],
    hook_keywords: [],
    recommended_duration: { evidence_status: 'insufficient_evidence', sample_size: 0 },
    dataset_profile: { domain: 'camera', sample_size: 30, source: 'synthetic-browser-only' },
    evidence: {},
    classification: {
      domain: 'camera', taxonomy_leaf_key: 'camera',
      category_level_1: 'Technology', category_level_2: 'Electronics',
      category_level_3: 'Camera', confidence: 0.91, is_unknown: false,
      taxonomy_ready: true, acceptance: { accepted: true },
    },
    actionable_recommendations: {
      status: 'available', method_version: 'fixture-v1', template_version: 'fixture-v1',
      catalog_sha256: 'c'.repeat(64),
      limitation: 'ข้อมูลทดสอบ UI เท่านั้น',
      items: [{
        id: 'advice:low-light', evidence_topic_id: 'topic:low-light',
        title: 'การถ่ายภาพในสภาพแสงน้อย',
        finding: 'ยังไม่พบการทดสอบแสงน้อยในข้อความ',
        proposal: 'ลองเพิ่มขั้นตอนทดสอบในสภาพแสงน้อย',
        condition: 'หากรุ่นนี้รองรับโหมดดังกล่าว',
        steps: ['ถ่ายฉากเดิมในแสงสองระดับ', 'อธิบาย noise และรายละเอียด'],
        example: 'ลองดูว่ารายละเอียดในเงายังเก็บได้แค่ไหน',
        reason: 'พบหัวข้อนี้ในคลิปอ้างอิงที่เทียบได้',
        relevance_reason: 'เกี่ยวข้องกับการรีวิวคุณภาพภาพ', found_topics: [],
      }],
    },
    evidence_bundle: {
      input: {
        availability: 'available', scope: 'full_video', hook_seconds: 60,
        segments: [{ start: 0, end: 8, text: 'รีวิวกล้องและรายละเอียดสีของภาพ' }],
      },
      action_topics: [{
        topic_id: 'topic:low-light', canonical_topic: 'low light', title_th: 'ภาพในสภาพแสงน้อย',
        support_count: 12, sample_size: 30,
        user: { status: 'not_detected', occurrences: [] },
      }],
      topic_comparisons: { items: [] },
    },
    outcome_assessment: assessment,
  },
  outcome_assessment: assessment,
  revision_comparison: null,
};

let browser;
let session;

function save() {
  fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
}

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

async function seek(page, label) {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    const candidates = [
      page.getByText(label, { exact: false }),
      page.getByRole('button', { name: label, exact: false }),
      page.getByRole('heading', { name: label, exact: false }),
      page.getByRole('checkbox', { name: label, exact: false }),
    ];
    for (const candidate of candidates) {
      for (const item of await candidate.all()) {
        const box = await item.boundingBox().catch(() => null);
        if (box && box.y >= 52 && box.y + box.height < page.viewportSize().height - 30) {
          return item;
        }
      }
    }
    await page.mouse.wheel(0, 330);
    await page.waitForTimeout(120);
  }
  throw new Error(`Visible section not found: ${label}`);
}

async function shot(page, name) {
  const dimensions = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  report.layout.push({ name, ...dimensions });
  assert.ok(dimensions.documentWidth <= dimensions.innerWidth + 1, `${name}: horizontal overflow`);
  assert.ok(dimensions.bodyWidth <= dimensions.innerWidth + 16, `${name}: body horizontal overflow`);
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  fs.writeFileSync(path.join(out, `${name}.txt`), await page.locator('body').ariaSnapshot());
  report.screenshots.push(name);
  save();
}

function observe(page, mode) {
  page.on('pageerror', error => report.errors.push(`${mode}: ${error.message}`));
  page.on('console', message => {
    if (/overflowed by|RenderFlex overflow|EXCEPTION CAUGHT/i.test(message.text())) {
      report.errors.push(`${mode}: ${message.text()}`);
    }
  });
  page.on('response', response => {
    if (response.url().startsWith(api)) {
      report.apiRequests.push({ mode, method: response.request().method(), url: response.url(), status: response.status() });
    }
  });
}

function installAuth(context) {
  return context.addInitScript(data => {
    localStorage.setItem('flutter.access_token', JSON.stringify(data.access_token));
    localStorage.setItem('flutter.trend_session_key', JSON.stringify(data.session_key));
    localStorage.setItem('flutter.auth_user', JSON.stringify(JSON.stringify(data.user)));
  }, session);
}

async function fixtureRoutes(page) {
  const escapedApi = api.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  await page.route(new RegExp(`^${escapedApi}/contents/my(?:\\?.*)?$`), route => {
    report.fixtureRouteHits += 1;
    return route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify({
        total: 1,
        items: [{
          content_id: 24, title: resultFixture.title, created_at: resultFixture.created_at,
          transcript_preview: resultFixture.transcript, domain: 'camera',
          recommended_duration: null, recommended_keywords: ['ภาพในสภาพแสงน้อย'],
          hook_keywords: [], outcome_assessment_status: 'available',
        }],
      }),
    });
  });
  await page.route(`${api}/contents/24/revision-plan`, route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({
      content_id: 24, analysis_id: 31, recommendation_fingerprint: 'b'.repeat(64),
      revision: 0, selected_advice_ids: [], notes: '', status: 'planning', saved_at: null,
    }),
  }));
  await page.route(`${api}/contents/24/outcome-scenario`, route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({
      schema_version: 'outcome-scenario-v1', status: 'available', reason_codes: [],
      hypothetical: true, unit: 'percentage_points', probability_before: 0.62,
      probability_after: 0.595, delta_percentage_points: -2.5,
      limitation: 'SYNTHETIC UI FIXTURE: ไม่ใช่ผลเพิ่มยอดวิวหรือหลักฐานเชิงเหตุและผล',
    }),
  }));
  await page.route(`${api}/contents/24`, route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify(resultFixture),
  }));
}

(async () => {
  try {
    session = JSON.parse(execFileSync(
      'C:/Users/tent9/AppData/Local/Programs/Python/Python311/python.exe',
      ['artifacts/settings_browser_session.py'],
      { cwd: root, encoding: 'utf8', windowsHide: true },
    ).trim());
    const headers = {
      Authorization: `Bearer ${session.access_token}`,
      'X-Trend-Session-Key': session.session_key,
      'Content-Type': 'application/json',
    };
    const live = await fetch(`${api}/admin/outcome-training`, { headers });
    assert.equal(live.status, 200);
    const livePayload = await live.json();
    fs.writeFileSync(path.join(out, 'live-outcome-overview.json'), JSON.stringify(livePayload, null, 2));
    assert.equal(livePayload.preflight.ready, false);
    assert.equal(livePayload.independent_test_opened, false);
    assert.equal(livePayload.active_model, null);
    const rejected = await fetch(`${api}/admin/outcome-training/models/999999/activate`, {
      method: 'POST', headers, body: JSON.stringify({ expected_active_model_id: null }),
    });
    report.activationRejectionStatus = rejected.status;
    assert.equal(rejected.status, 404);

    browser = await chromium.launch({ channel: 'msedge', headless: true });
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 1000, height: 800 },
      { width: 390, height: 844 },
    ]) {
      const suffix = `${viewport.width}x${viewport.height}`;
      const liveContext = await browser.newContext({ viewport, serviceWorkers: 'block' });
      await installAuth(liveContext);
      const admin = await liveContext.newPage();
      observe(admin, `live-${suffix}`);
      await open(admin, '/admin-training');
      await admin.getByText('ประเมินผลตอบรับ', { exact: true }).click();
      await admin.getByText('ยังเริ่มเทรนไม่ได้', { exact: true }).waitFor();
      const liveText = await admin.locator('body').ariaSnapshot();
      assert.ok(liveText.includes('ยังไม่มี Frozen manifest'));
      assert.ok(liveText.includes('สิทธิ์ใช้ข้อมูล'));
      assert.equal(await admin.getByRole('button', { name: 'เริ่มเทรน Outcome' }).isDisabled(), true);
      await shot(admin, `live-admin-blocked-${suffix}`);
      await liveContext.close();

      const fixtureContext = await browser.newContext({ viewport, serviceWorkers: 'block' });
      await installAuth(fixtureContext);
      const page = await fixtureContext.newPage();
      observe(page, `fixture-${suffix}`);
      await fixtureRoutes(page);
      await open(page, '/history');
      await shot(page, `fixture-history-${suffix}`);
      assert.ok(report.fixtureRouteHits > 0, 'Fixture history route was not used');
      await page.getByRole('button', { name: resultFixture.title, exact: false }).click();
      await page.getByText('1. พบอะไรในคลิป', { exact: true }).waitFor();
      await seek(page, 'ทำไมประเด็นนี้จึงน่าลองเพิ่ม');
      const fixtureText = await page.locator('body').ariaSnapshot();
      assert.ok(fixtureText.includes('ข้อมูลทดสอบระบบเท่านั้น'));
      assert.ok(fixtureText.includes('โอกาสอยู่ในกลุ่มยอดวิวสูงกว่าค่ากลางของชุดอ้างอิง 62.0%'));
      assert.ok(!fixtureText.includes('เพิ่มยอดวิว 62.0%'));
      await shot(page, `fixture-result-available-${suffix}`);
      await seek(page, 'การถ่ายภาพในสภาพแสงน้อย');
      const checkbox = page.getByRole('checkbox', { name: 'การถ่ายภาพในสภาพแสงน้อย' });
      await checkbox.click();
      const simulate = page.getByRole('button', { name: 'ประเมินสถานการณ์สมมุติ' });
      for (let attempt = 0; attempt < 20 && await simulate.isDisabled(); attempt += 1) {
        await page.waitForTimeout(100);
      }
      assert.equal(await simulate.isEnabled(), true, 'Scenario button did not enable after topic selection');
      await simulate.click();
      await page.getByText('ส่วนต่างค่าประเมิน -2.5 จุดเปอร์เซ็นต์', { exact: true }).waitFor();
      await shot(page, `fixture-scenario-negative-${suffix}`);
      await fixtureContext.close();
    }
    assert.deepEqual(report.errors, []);
    const unexpectedFailures = report.apiRequests.filter(item => item.status >= 400);
    assert.deepEqual(unexpectedFailures, []);
    report.passed = true;
  } catch (error) {
    report.failure = error.stack || error.message;
    process.exitCode = 1;
  } finally {
    if (session) {
      await fetch(`${api}/auth/logout`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          'X-Trend-Session-Key': session.session_key,
          'Content-Type': 'application/json',
        },
        body: '{}',
      }).catch(() => {});
    }
    if (browser) await browser.close();
    save();
    console.log(JSON.stringify({ passed: report.passed, screenshots: report.screenshots.length, errors: report.errors.length }));
  }
})();
