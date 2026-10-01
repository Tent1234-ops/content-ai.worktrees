# Handoff: Closeout Phase 1

วันที่ 1 ตุลาคม 2026. ทำเฉพาะตรวจขอบเขต/ความพร้อมและจัดแผนข้อมูล ไม่เริ่ม Phase 2

## เสร็จแล้ว

1. ตรวจ routing/API/ข้อมูลและเทียบ User 1–9, Admin 10–18 ทุกข้อใน [ตารางขอบเขต](project-closeout-scope.md) มีหน้า/บริการ/ที่เก็บข้อมูล/ช่องว่าง/เกณฑ์และผู้ตัดสินใจ
2. ตรวจไฟล์ใหม่ 48 ไฟล์ด้วย parser เดิม, dedup กับ Dataset/collection artifacts และ preview split จาก Channel ID จริงผ่าน metadata API; ไม่แก้ต้นฉบับ ไม่อ่าน heldout เพื่อปรับกฎ
3. ตรวจ registry **34 รุ่น** กับไฟล์และ metrics ไม่เลือกดูแต่ Active: ไฟล์โหลดได้ 34, ใช้สำหรับ production artifact ได้ 28, smoke-only 6; registry qualified 5 / below-threshold 23 / smoke 6; **ไม่มีรุ่นพร้อมตาม scope validation ปัจจุบัน**
4. เพิ่ม `classification_readiness.py` เป็นบริการกลางที่ทั้งหน้า Settings, Training และ settings snapshot ใช้ แยกโหลดไฟล์ได้ / ใช้จริงได้ / scope policy ผ่าน / scope test flag / เกณฑ์บังคับ / เหตุผล; เรียก validator และ loader เดิม ไม่สร้าง classifier หรือ threshold อีกชุด
5. เพิ่มคำเตือนไทยผ่าน widget ร่วมในหน้า `/admin-training`, รายละเอียดโมเดล และ `/admin-analysis-settings`; ไม่ซ่อนชื่อ/รุ่น/ID ของ Active และไม่ใช้คะแนน Test เก่าแทนความพร้อมรับผล
6. ปุ่ม Activate ในรายการไม่เปิดเพียงเพราะ registry บอก qualified: ตรวจไฟล์ใช้งานได้, policy จริงและ scope test flag เพิ่ม ส่วนการกดจริงยังผ่าน metrics/checksum/current-active guard เดิม
7. เพิ่มเครื่องมือตรวจ read-only `scripts/audit_project_closeout.py` และ checklist ที่แยกข้อมูลใน DB ออกจากไฟล์ยังไม่ Review; บันทึก JSON ก่อน/หลังโดยไม่เขียนทับ audit เดิม

## ผลข้อมูลจริง

หลักฐานใหม่สุด: `artifacts/project-closeout/phase1-20261001/readiness-inventory-v2.json`
ผล metadata: `transcript-audit-live.json` ในโฟลเดอร์เดียวกัน

- Dataset ทั้งหมด 423 แถว ไม่เท่ากับ usable training 239 แถว: Phone 80 / Camera 74 / Laptop 85
- Pending Review เดิม 0; Unknown ใช้ประเมินใน DB 0; ไม่พบ partition conflicts หรือ invalid assignments ของข้อมูลที่เลือก
- Camera 6 ใหม่จริง 5: Video ID `pG961MPC7bQ` ซ้ำ Dataset #422
- Unknown 42 แทนจำนวนที่ผู้ใช้เรียก 40: headphone10 / keyboard10 / mouse11 / speaker11
- Unknown ตามช่อง: Train35 (สำรองไม่ fit/evaluate), Validation5 จาก5ช่อง, Test2 จาก2ช่อง
- **หาก Review ผ่านทั้งหมด** ยังขาด Camera1, Unknown Validation5, Unknown Test28 และ Test อย่างน้อยอีก1ช่อง จำนวนขาดนี้ยังไม่ใช่จำนวนหลัง Import จริง
- ขั้นต่อไปใช้ [collection checklist](project-closeout-data-checklist.md) ตรวจ URL/ช่อง/split ก่อนทำ Transcript เพิ่ม
- Manifest utility เดิมมี4regression ไม่ใช่ fresh heldout; ที่มาของคลิป regression ยังไม่ครบ จึงยังรับรอง independence ของไฟล์ใหม่กับกรณีที่เคยแก้ระบบไม่ได้ และยังไม่มีวิดีโอใหม่สามหมวด/คลิปถ่ายเองในรอบนี้

Fingerprint ข้อมูลฝึกก่อน/หลังคงเดิม:

`b2fe9687c3509d0e3f70908ad4a882d5a89f0dd7f473e35f5481219b0ae4bfa5`

Identity hash (รวม ID/label/split/video/channel/transcript hash/flags ของ Dataset ทุกแถว) ใน inventory:

`60ad7b2f4e049231aeeca352d610d23e538aa677f2cd8b108fd90911983ab0c2`

Active ก่อน/หลังยังเป็น **#14** Complement Naive Bayes `20260828T134420Z`, training116, artifact checksum `f77e26d1ccf940ef7e8c520397fe808521bb485b39fcc9c2b619789e1cd98cd2`
Validation Accuracy85.7143% / MacroF180.4511% บน21ตัวอย่าง, Test Accuracy/F1100% บน17ตัวอย่าง เป็นผลประเมินเก่าจริง แต่ไม่มี scope policy จึงถูกงดคำแนะนำเฉพาะหมวดใน runtime ปัจจุบัน ไม่ใช่คุณภาพคำแนะนำ100%

## สิ่งที่ไม่ได้เปลี่ยน

- ไม่ Import หรือ Approve ไฟล์ใหม่ ไม่แก้ Transcript ต้นฉบับ ไม่ย้าย split/สมาชิกชุด ไม่ Train ไม่ Activate และไม่ลด threshold/ปิด `classification_require_scope_validation`
- ไม่เปลี่ยนการตัดสินหมวดหรือกฎ keyword/recommendation, ไม่แอบแนะนำให้ผล Phone กลับมาผ่านจาก confidence อย่างเดียว
- ไม่เพิ่ม Guest readiness endpoint และไม่เปลี่ยนความหมาย `/health`; สุขภาพบริการกับความพร้อมโมเดลยังแยกกัน
- ผลเก่าไม่ถูกคำนวณใหม่ การเพิ่ม readiness ใน settings snapshot เป็นข้อมูลเพิ่มสำหรับงานใหม่
- ไม่มี DB migration; การ Train ที่เกิดใน unit tests ใช้ฐานข้อมูล/ไฟล์ชั่วคราวของ test ไม่ใช่ MySQL จริง

## Verification

- Backend focused suite **41 tests ผ่าน**: readiness, analysis settings, model management, collection plan, NotebookLM batch. ครอบคลุม policy หาย/ไม่ผ่าน/ผ่าน/คนละรุ่น, corrupt/smoke/registry mismatch, disabled enforcement, API permissions, ทั้งสองหน้าได้ readiness เดียวกัน, registry gate ไม่หลอกว่า artifact ไม่มี policy ใช้ได้
- Flutter focused suite **15 tests ผ่าน**, รวมข้อความเตือนที่จอ desktop1000/1440, legacy response, Settings/Train/collection panel
- Dart analyze ไฟล์ UI ที่แตะผ่าน ไม่มี issue
- Flutter web build ผ่าน; มี warning เดิมเรื่อง Cupertino icon font และข้อความแนะนำ Wasm ไม่ได้เปลี่ยน SDK/แพ็กเกจ
- Browser verification ใช้ **payload ที่อ่านจาก service/DB จริง + authentication fixture เฉพาะ browser** เพื่อไม่สร้าง/เปิดใช้บัญชี Admin ทดสอบใน DB ไม่ใช่การรับรอง Login ใหม่ หลักฐาน `browser-readiness.json` และรูป `admin-*-1000/1440.png`; อ่านสถานะล่าสุดจากไฟล์ผล ไม่ใช้ภาพรอบที่ล้มเหลวเป็นหลักฐานผ่าน
- Browser รอบสุดท้าย **ผ่าน4checks**: Training/Settings ที่1440และ1000px, ไม่มี JS error/Flutter overflow; เปิดดูภาพตรวจข้อความ รุ่นและIDของ Active ยังคงแสดงอยู่ ทดสอบก่อนหน้าที่ล้มเหลวเกิดจาก selector ของข้อความที่ Flutter รวมใน accessibility และ SelectableText ที่ ariaSnapshot ไม่ส่งค่าออกมา ไม่ใช่การแก้ข้อมูลให้ผ่าน
- Live service ตรวจ `/health`200 และ Admin Settings ไม่มี session ได้401; ไม่ได้อัปโหลดคลิปซ้ำหรือประเมินความแม่นโมเดลใน Phase1

```powershell
python -m unittest tests.test_classification_readiness tests.test_analysis_settings tests.test_model_management tests.test_classification_collection_plan tests.test_notebooklm_batch
C:\flutter\bin\flutter.bat test test/classification_readiness_panel_test.dart test/admin_training_test.dart test/analysis_settings_test.dart test/training_collection_panel_test.dart
C:\flutter\bin\cache\dart-sdk\bin\dart.exe analyze lib/widgets/classification_readiness_panel.dart lib/models/model_training.dart lib/screens/admin_analysis_settings_screen.dart lib/screens/admin_training_screen.dart
node scripts/browser/verify_closeout_readiness.cjs
```

คำสั่ง Flutter/Dart ใช้ cwd `frontend_flutter`; Python/Node ใช้ repo root

## ค้างและเจ้าของงาน

| สถานะ | งาน | ผู้รับผิดชอบ/ข้อจำกัด |
|---|---|---|
| pending | ยืนยันข้อความรายงานข้อ11/13/15/17/18 | เจ้าของโครงการ/อาจารย์, ไม่มีคำยืนยันเปลี่ยนรายงานในรอบนี้ |
| pending | นำเข้าไฟล์ใหม่เป็นคิว Review แล้วตรวจ Transcript/หมวด/ที่มา/สิทธิ์ | เจ้าของโครงการ, ยังไม่ถือว่า47รายการมีคุณภาพผ่านโดยอัตโนมัติ |
| blocked by data | ข้อมูลตาม split ให้ครบเกณฑ์ปัจจุบัน | ตาม checklist, ตรวจช่องก่อนเก็บเพิ่ม; ห้ามย้ายชุดเพื่อให้ครบ |
| blocked by evaluation | ใช้โมเดลพร้อม scope validation จริง | ขั้นตอน Analysis ใน Phase2 หลังยืนยันข้อมูล, train/evaluate แล้วเลือกตามหลักฐาน ไม่รับประกันผ่านจากจำนวนครบ |
| pending | วิดีโอใหม่สามหมวด/ถ่ายเอง, ยืนยัน independence และผลประเมินมนุษย์ | Transcriptอย่างเดียวไม่ทดสอบ ASR/UI, ไม่เอา regression นับเป็น Testใหม่ |
| later closeout | ตรวจ Notification/Scheduler/Dataset UI, เก็บ UI, final acceptance | ตามลำดับ phase closeout เดิม ไม่เริ่มเองในงานนี้ |

## รันเว็บ/ข้อจำกัดเครื่องมือ

เปิดแบบซ่อนหน้าต่าง `http://127.0.0.1:8080/#/dashboard` และ API `http://127.0.0.1:8000`; ใช้บัญชี Admin ของเจ้าของโครงการดูสองหน้าที่แก้ เซิร์ฟเวอร์ที่เริ่มรอบนี้ API PID17568, web PID14780 (PID อาจเปลี่ยนเมื่อเริ่มใหม่)

Git status ยังใช้ไม่ได้เพราะ `.git` worktree ชี้ไป `Z:/content-ai/.git/worktrees/agents-content-analysis-recommendation-system` ที่หาไม่พบ ไม่แก้ Git metadata และไม่ revert งานเดิม

Sandbox network/Flutter SDK/เปิด browser มีข้อจำกัด จึงขอสิทธิ์ก่อนรันที่จำเป็นและเก็บ audit ที่ล้มเหลวแยกจากผลสำเร็จ ต้องไม่เผยแพร่ไฟล์ private credentials จากรอบ acceptance เดิม
