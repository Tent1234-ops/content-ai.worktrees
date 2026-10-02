# รายงานตรวจรับรุ่นส่งจริง

วันที่ตรวจ: 2 ตุลาคม 2026 (Asia/Bangkok)

ขอบเขต: Closeout Phase 5 เท่านั้น โดยใช้เกณฑ์เดิมจาก `project-closeout-scope.md` และ protocol ประเมิน Recommendation Phase 7 ไม่ได้ลดเกณฑ์ Unknown, ไม่ Train/Activate, ไม่อนุมัติ Pending Review และไม่เริ่ม Phase ถัดไป

## สถานะรวม

**ผ่านเฉพาะส่วนที่ระบุ และยังไม่ผ่านการตรวจรับทั้งโครงการ**

- Software ของ Dashboard, Auth, Follow, Dataset CRUD, User Management, Settings/Logs และหน้า Web หลักทำงานตามหลักฐานรอบปัจจุบัน
- เส้นทาง AI เชิงบวกยังเป็น **Release blocker**: Active Model #14 โหลดได้แต่ไม่มี validated scope policy จึง `can_accept_predictions=false` และระบบงดคำแนะนำตามการออกแบบ
- Model evaluation รอบส่งยังไม่มี fresh heldout และ Unknown rejection ที่ครบ protocol
- Recommendation utility ยังไม่มีคลิปใหม่ 12 เคสและผู้ประเมินจริง 3 คน จึงเป็น `not_evaluated` ไม่ใช่ผลไม่ดีหรือผลผ่าน

## รุ่นที่ตรวจ

| รายการ | ค่าที่ตรวจจริง |
|---|---|
| เวลา inventory | `2026-10-02T09:01:46Z` จากรอบ `inventory-v4` |
| Python | 3.11.9 |
| Backend packages หลัก | FastAPI 0.135.1, SQLAlchemy 2.0.48, scikit-learn 1.8.0, PyThaiNLP 5.3.2, faster-whisper 1.2.1, NumPy 2.4.3 |
| Web build | `frontend_flutter/build/web` สร้างใหม่ด้วย `flutter build web --release` |
| Web main hash | `9608cd192d9fdaed26bb99717835ca8de78ac81a5999de1e7945b4dbf1c7c6e4` |
| Flutter lock hash | `fa4abcaea7b653658b572b3847bb0eea2275411637dd979b4424b4b4556eff87` |
| Active Model | #14 `taxonomy-tfidf-complement-nb`, version `20260828T134420Z` |
| Model artifact hash | `f77e26d1ccf940ef7e8c520397fe808521bb485b39fcc9c2b619789e1cd98cd2` |
| Analysis settings | Upload 300 วินาที, Whisper `small`, Hook 60 วินาที, ASR ready |
| Reference versions | `youtube-cc-th-v1` 88 แถว, `youtube-public-research-th-v1` 230 แถว |
| Reference statistics cutoff | `2026-10-02 09:00:12Z` |
| Pending Review | 42 candidates ยังไม่ได้อนุมัติ |
| Git identity | ใช้ไม่ได้ เพราะ worktree metadata ชี้ปลายทางที่หาย จึงใช้ source/build hashes แทนและไม่ได้ซ่อม Git |

Source tree hashes และค่าครบอยู่ใน `artifacts/project-closeout/phase5-20261002T152216+0700/inventory-v4.json` โดย inventory ยืนยัน `database_unchanged=true`

## วิธีและสถานะ

คำสถานะ:

- `PASS`: มีหลักฐาน live รอบปัจจุบันและ automated regression รองรับตามความเสี่ยง
- `PARTIAL`: ส่วนหนึ่งผ่าน แต่ยังขาด live proof, การยืนยันขอบเขต หรือเหตุการณ์ภายนอก
- `BLOCKED`: flow สำคัญถูก gate ที่ถูกต้องหรือขาดข้อมูลที่ห้ามจำลอง
- `NOT TESTED`: ไม่มีหลักฐานรอบนี้และไม่ควรอนุมานจาก fixture

Checklist expected outcome ใช้ตาราง `project-closeout-scope.md` ซึ่งถูกสร้างก่อนรอบนี้ ไม่มีการลบข้อที่ไม่ผ่านหลังเห็นผล

## ตารางตรวจรับขอบเขต

| ข้อ | ขอบเขต/Expected | วิธีตรวจรอบนี้ | Actual | สถานะ | หลักฐาน/ผู้รับผิดชอบงานค้าง |
|---|---|---|---|---|---|
| 1 | สมัครสมาชิก, กันชื่อ/อีเมลซ้ำ, ห้ามสมัคร Admin เอง | Live API สร้าง 2 บัญชีและลองซ้ำ | สมัครสำเร็จและ duplicate ได้ 409; บัญชีชั่วคราวถูกลบครบ | PASS | `live-api-v2.json`; เจ้าของโครงการไม่มีงานค้าง |
| 2 | Login/Logout, wrong credentials, protected route, แยกบัญชี | Live API + Browser auth gate | รหัสผิด 401, Guest/User ถูกกันตามสิทธิ์, ประวัติแยกบัญชี, session ตรวจรับถูก logout | PASS | `live-api-v2.json`, browser r10 |
| 3 | Upload valid/เกินกำหนด/ไฟล์เสีย, loading/error/retry | ไฟล์เสียผ่าน Live API; valid/over-limit/ASR/retry ผ่าน automated tests | ไฟล์เสีย 422 และไม่แจ้งสำเร็จ; **ไม่ได้อัปโหลด valid clip ใหม่รอบนี้** และ accepted result ถูก Model gate ขวาง | PARTIAL | Backend 480 tests, Flutter 125 tests; Positive live เป็น blocker ของข้อ 4 |
| 4.1 | คำแนะนำปรับปรุงจากหมวดที่รับได้ พร้อมหลักฐาน ไม่ผิดหมวด | ตรวจ Active Model/readiness + recommendation regressions | Model #14 `scope_policy_missing`; ระบบ fail closed และไม่ใช้ Dataset ผิดหมวด แต่ไม่มี positive live advice | BLOCKED | `inventory-v4.json`; ต้องมีข้อมูล Unknown ผ่าน review, train/evaluate และ activate หลังเจ้าของยืนยัน |
| 4.2 | Median/percentile/n หรือ insufficient evidence | Automated duration tests + ตรวจ Result เก่า | สูตรและสถานะ fallback ผ่าน tests; ไม่มี accepted live result ใหม่ให้ตรวจตัวเลข | BLOCKED | Tests `test_phase21_recommended_duration`; dependency เดียวกับ 4.1 |
| 4.3 | Hook ที่เสนอแยกจากคำที่พบ และไม่สร้างเวลา | Automated evidence/UI tests | Contract ผ่าน tests; ไม่มี accepted live result ใหม่ | BLOCKED | Evidence/keyword/actionable tests; dependency เดียวกับ 4.1 |
| 5 | Public Dashboard แยก YouTube/Google/category/detail/history/more และ auth gate | Release browser 1440x900 และ 1000x800 | YouTube 50, Google 12, โหลดเพิ่มได้ 24/50, กรองหมวด, เปิดรายละเอียด/ประวัติ/ตารางหลักฐาน และแสดง TikTok unavailable ชัด; API 39 requests ไม่มี failure, ไม่มี layout/page error | PASS | browser r10 38 screenshots |
| 6 | บันทึกผลในรายการไอเดีย, เปิดผลเก่าไม่เปลี่ยน, save fail ไม่ success | Live Browser เปิด Content #4 จาก History + current tests ของ plan/save | เปิดผลเดิมได้; persistence/failure contract ผ่าน tests แต่ไม่ได้บันทึกแผนจาก positive advice รอบนี้ | PARTIAL | browser r10, clip revision tests; รอ positive model flow |
| 7 | สถิติย้อนหลังรายวัน/เดือนและแยกบัญชี | Live API/Browser + tests | หน้า History/API เปิดได้และบัญชีทดสอบไม่เห็นข้อมูลกัน | PASS | live API + browser + scope completion tests |
| 8 | Follow category, dedup, reopen, unfollow | Live API บัญชีแยก | Follow ซ้ำได้ ID เดิม, preferences จำค่า, บัญชีอื่นไม่เห็น, unfollow สำเร็จ | PASS | `live-api-v2.json` |
| 9 | แจ้งเตือนตามโหมด/ความสนใจ, unread/read, provider event ครั้งเดียว | Current deterministic tests; รอบนี้ไม่มี provider event ใหม่ที่ควบคุมได้ | Logic/ownership/dedup ผ่าน fixtures แต่ยังไม่มี live delivery จากเทรนด์ใหม่จริง | PARTIAL | Notification/scope tests; ผู้รับผิดชอบคือเหตุการณ์ provider รอบใหม่ + เจ้าของตรวจ |
| 10 | Admin login และ authorization ทุกหน้า | Live API + browser 7 หน้า | Guest/User เข้า Admin ไม่ได้; Admin surfaces โหลดครบสอง viewport | PASS | live API + browser r10 |
| 11 | จัดการข้อมูลต้นแบบ เพิ่ม/แก้/ลบ/กู้/Review/Import | Live Dataset isolated CRUD + current tests | Create/edit/hash/taxonomy/trash/restore ผ่าน, แถวทดสอบไม่เคย eligible และ cleanup 0; Review/Import เป็น tests ไม่แตะ 42 แถวจริง | PASS เฉพาะ workflow ที่ยืนยัน | `live-api-v2.json`; ข้อความ “อัตโนมัติ” ในรายงานยังรออาจารย์ยืนยัน |
| 12 | ตั้งรอบเก็บจริง, Restart จำค่า, งานซ่อนหน้าต่าง | Tests + read Windows Task จริง | Task `ContentAI-Trends-D33AFF90B7` Ready, `pythonw.exe`, last result 0 เวลา 15:00, next 16:00 | PASS | `automated-tests.json` |
| 13 | ดูผลโมเดลจัดกลุ่ม | Browser/Admin Training + inventory | หน้าแสดง Classification/readiness จริง ไม่ใช่ Clustering; โมเดลยัง blocked | PARTIAL | ต้องให้อาจารย์ยืนยันเปลี่ยนคำว่า Clustering เป็น Classification |
| 14 | Log ดึงข้อมูลสำเร็จ/ล้มเหลว อ่านได้และไม่เผย secret/SQL | Live Admin read + sanitization tests | หน้า/API เปิดได้, sanitizer tests ผ่าน; Log ไม่ใช่ตัวจับ Browser/OS error ทุกชนิด | PASS ตามขอบเขตที่ทำจริง | live API/browser + Phase3 log tests |
| 15 | ตั้งค่าพารามิเตอร์รวมจำนวน keyword และช่วงวิดีโอ | Live read + settings tests | Upload/Whisper/Hook ใช้ Server settings จริง; UI จำนวน keyword ถูกยกเลิกตามคำสั่งเดิม | PARTIAL | ต้องแก้ข้อความรายงานข้อ 6.1 หรืออนุมัติขอบเขตใหม่ |
| 16 | สถิติรวมผู้ใช้และจำนวนวิเคราะห์ | Live Admin usage read + browser | API และหน้า Users เปิดได้, authorization tests ผ่าน | PASS | live API/browser + user management tests |
| 17 | รายงานสรุปเทรนด์ | Public Dashboard/browser + trend tests | Dashboard มีรายการและกราฟย้อนหลังจากข้อมูลจริง; ยังไม่มี Admin report แยก | PARTIAL | เจ้าของ/อาจารย์ต้องยืนยันว่า Dashboard คือรายงานตามขอบเขต |
| 18 | เปรียบเทียบแพลตฟอร์ม Top/Emerging เช่น YouTube/TikTok | Browser platform tabs | YouTube/Google แยกหน่วยและไม่รวมอันดับ; TikTok ไม่มี provider ที่ยืนยันได้ และไม่มี cross-platform ranking | PARTIAL | ต้องแก้ขอบเขตเป็น YouTube/Google แยกกัน หรือจัดหา provider ที่อนุญาตในอนาคต |

## Software Verification

| การตรวจ | ผล |
|---|---|
| Backend unittest | 480/480 ผ่าน, 130.237 วินาที |
| Flutter test | 125/125 ผ่าน |
| Flutter analyze | ผ่าน, no issues |
| Release build | ผ่าน, `build/web` |
| Live isolated API | 8/8 กลุ่มผ่าน; temporary users 0, temporary datasets 0 หลัง cleanup |
| Live release browser | 6/6 กลุ่มผ่าน, 38 screenshots, 39 API calls, API failure 0, page/console error 0, layout failure 0 |

รอบ browser r1-r3 ถูกเก็บไว้และไม่ซ่อน: acceptance harness ค้น Flutter semantics ด้วย locator แคบเกินไป รอบ r4 ผ่านเชิงอัตโนมัติแต่ visual audit พบว่าภาพ Training ถูกถ่ายระหว่าง loading จึงเพิ่ม data-ready anchors และรัน r5 ใหม่ รอบ r6-r9 เพิ่มหลักฐาน load-more/history/evidence/category แต่พบปัญหาการ scroll และ locator ใน harness ก่อนที่รอบ r10 จะผ่านครบพร้อมภาพที่โหลดเสร็จ โดยไม่เปลี่ยน application code

## Model Evaluation

### ผล registry เดิม ไม่ใช่ fresh Phase 5 test

| ชุด | n | Accuracy | Macro F1 | หมายเหตุ |
|---|---:|---:|---:|---|
| Validation เดิม | 21 | 0.857143 | 0.804511 | Laptop recall 0.40 |
| Test เดิม | 17 | 1.00 | 1.00 | Phone 3, Camera 5, Laptop 9; เคยถูกใช้ตรวจระบบแล้ว ไม่ใช่ fresh heldout รอบส่ง |

- Fresh heldout รอบ Phase 5: Phone 0, Camera 0, Laptop 0, Unknown 0
- Fresh confusion matrix: NOT TESTED
- Unknown rejection/false acceptance: NOT TESTED เพราะไม่มี validated Unknown policy และไม่มี fresh eligible run
- Classification confidence ของคลิปใดคลิปหนึ่งไม่ถูกใช้แทน accuracy

## Recommendation Utility

| รายการ | ผลจริง |
|---|---|
| Fresh cases | 0/12 |
| Phone/Camera/Laptop/Unknown | 0/3 ต่อกลุ่ม |
| คลิปถ่ายเองตาม protocol | 0 |
| ผู้ประเมินจริง | 0/3 |
| A/B/C scores | NOT EVALUATED |
| Critical flags adjudicated | ไม่มีข้อมูลให้ตัดสิน |

สถานะ tooling จาก Phase 7 คือพร้อมสร้าง packet และตรวจคะแนน แต่ `evaluation_complete=false` จึงไม่มีข้อสรุปว่าคำแนะนำช่วยผู้ใช้หรือเพิ่ม Engagement

## Release Blockers

1. Active Model #14 ไม่มี validated scope policy (`scope_policy_missing`) ทำให้ accepted classification และคำแนะนำเชิงบวกใช้งานไม่ได้ นี่เป็น blocker ของฟังก์ชันหลัก ไม่ใช่งานตกแต่ง
2. ไม่มี fresh heldout ที่กำหนดก่อนดูผลสำหรับ Phone/Camera/Laptop/Unknown จึงยังรับรอง generalization และ Unknown rejection ไม่ได้
3. ไม่มีผู้ประเมินจริงและคะแนน A/B/C จึงยังรับรองคุณภาพคำแนะนำเชิงผู้ใช้ไม่ได้

ไม่พบหลักฐาน data loss, cross-account leak, false save success หรือคำแนะนำผิดหมวดในรอบนี้ แต่ข้อแรกป้องกันผิดหมวดด้วยการงดคำแนะนำ ไม่ใช่หลักฐานว่าโมเดลพร้อมใช้

## Non-blocking / Scope Decisions

- ข้อ 11, 13, 15, 17 และ 18 ยังมีข้อความขอบเขตไม่ตรงระบบจริงตามตาราง และต้องให้อาจารย์/เจ้าของโครงการยืนยัน ไม่ควรแก้ชื่อใน UI เพื่อทำเหมือนผ่าน
- Git worktree metadata ยังเสีย จึงไม่มี commit hash; source/build hashes ใน inventory ใช้ระบุรุ่นแทนชั่วคราว
- Notification live delivery รอ provider event จริง แต่ logic และสิทธิ์ผ่าน tests

## Cleanup และ Runtime

- รอบตรวจนี้ไม่เปลี่ยน config, Active Model หรือแถวข้อมูลเดิม จึงไม่มี state เดิมที่ต้อง restore จาก backup; mutation จำกัดอยู่ในบัญชี/แถวที่มี run marker และ identity guard เท่านั้น ส่วน inventory บันทึก identity ก่อน-หลังและยืนยัน `database_unchanged=true`
- Temporary users เหลือ 0; temporary datasets เหลือ 0; invalid upload file ไม่เหลือใน `videos/`
- Audit logs ของการตรวจรับคงไว้ตามหน้าที่ของระบบ แต่ไม่มี password/token ใน artifact
- ไม่มี Train/Activate/Approve/Reject/provider fetch ใน Phase 5
- ระบบเปิดให้ลองที่ `http://127.0.0.1:8080/#/dashboard`; Backend health ที่ `http://127.0.0.1:8000/health`

## Artifact หลัก

- `artifacts/project-closeout/phase5-20261002T152216+0700/inventory-v4.json`
- `artifacts/project-closeout/phase5-20261002T152216+0700/live-api-v2.json`
- `artifacts/project-closeout/phase5-20261002T152216+0700/automated-tests.json`
- `artifacts/project-closeout/phase5-20261002T152216+0700-r10/browser/verification.json`
- `artifacts/project-closeout/phase5-20261002T152216+0700-r10/browser/*.png`

ข้อสรุปการส่งมอบ: **Software workflows ส่วนใหญ่พร้อมสาธิต แต่โครงการยังไม่ completed เพราะ AI positive flow, fresh model evaluation และ human utility ถูก blocked/not evaluated ตามหลักฐานจริง**

## Phase 6 Delivery Freeze

- Release version: `content-ai-closeout-20261002-phase6`
- Release manifest: `artifacts/project-closeout/phase6-20261002T181200+0700/release-manifest.json`
- เปิดระบบจากสถานะปิดผ่าน launcher แบบหน้าต่างซ่อนบนพอร์ตแยก และยืนยัน History, ผลเก่า, revision plan, settings และ model readiness หลัง restart
- Private backup รุ่นสุดท้ายครบ 41 ตาราง 279,351 แถว และ restore ลง SQLite แยกผ่าน ไม่ได้ restore ทับ MySQL ต้นทางและไม่รวม `.env`
- คู่มือพรีเซนต์อยู่ที่ `docs/presentation/system-walkthrough-th.md` และ `docs/presentation/demo-checklist-th.md`
- Blocker และ Scope Decisions ด้านบนยังคงเดิม การ freeze ไม่ได้เปลี่ยนสถานะโครงการเป็น completed

