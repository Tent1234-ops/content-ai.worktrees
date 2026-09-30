# ตรวจรับขอบเขตและ Analysis จากระบบจริง

ตรวจคืนวันที่ 30 กันยายน ถึงต้นวันที่ 1 ตุลาคม 2026 (เวลาไทย)

## ข้อสรุป

**เส้นทางเว็บหลักทำงานได้ แต่ยังไม่ผ่านการส่งมอบด้านคำแนะนำของ Analysis**

ใช้เว็บที่ build ใหม่, Backend จริง, MySQL `content_ai`, Whisper small ที่ติดตั้งจริง และ Active Model เดิม ไม่ใช้ mock transcript, ไม่ฝึกหรือ Activate โมเดล และไม่ปิดเกณฑ์ Unknown เพื่อให้การทดสอบผ่าน

สมัครและล็อกอินผ่านเบราว์เซอร์จริง อัปโหลด `videos/Review_Phone.mp4` ยาว 111.85 วินาที ผลถูกบันทึกเป็น Content **#19** ใช้เวลางานประมาณ **69.2 วินาที** รวมการถอดเสียงและบันทึก ได้ Transcript 51 segments

คลิปนี้เคยใช้ตรวจระบบแล้ว จึงเป็น **regression/demo case ไม่ใช่ Test ใหม่** ผลนี้ไม่ใช่รายงานความแม่นของโมเดลหรือหลักฐานว่าคำแนะนำเพิ่ม Engagement

## สิ่งที่ต้องแก้ก่อนเดโม

### P1: Active Model ถูกเกณฑ์รับผลปฏิเสธ ทำให้คำแนะนำหลักไม่ออก

- Active Model **#14**, Complement Naive Bayes รุ่น `20260828T134420Z`, ฝึก 116 ตัวอย่าง
- ผลก่อนตรวจรับ: **Phone, confidence 0.981554** ค่านี้ไม่ใช่ accuracy 98.16%
- Snapshot การตั้งค่าระบุ `scope_validation_required=true` แต่ `scope_validation.status=not_available`, เหตุผล `scope_policy_missing`
- ผลหลังตรวจรับ: `Unknown/Other`, `acceptance.reason=scope_validation_unavailable`
- Recommendation: `status=withheld_unknown`, คำแนะนำหลัก/คำขาด/Hook ว่าง และงดแนะนำความยาว
- ไม่ใช่ปัญหา API ไม่ส่งผลหรือบันทึก MySQL ไม่สำเร็จ แต่เป็นการงดแนะนำตามเงื่อนไขความปลอดภัยที่เพิ่มเข้ามา
- โค้ด `apply_acceptance_policy()` จะงดรับผลทุกหมวดเมื่อไม่มี policy ที่ผ่าน Validation และเปิด `require_validation` อยู่ จึงไม่ใช่ปัญหาเฉพาะคลิป Phone นี้

อ้างอิง: `app/services/classification_acceptance.py:152`, `app/services/classification_acceptance.py:172`, `app/services/classification.py:246`, `artifacts/acceptance/20260930/analysis-detail.json`

**การแก้ที่ควรทำ:** ตรวจโมเดลทั้งหมดว่ามีตัวผ่านเกณฑ์ใหม่จริงหรือไม่ ก่อนคิดจะเปลี่ยนตัวใช้งาน หากยังไม่มี ต้องเติมข้อมูลและประเมินตามเกณฑ์เดิม ไม่ลด threshold จากคลิปนี้ ไม่ให้กฎเก่าทายหมวดทับ และไม่แอบปิด scope validation

หน้า Train ในระบบจริงรายงานข้อมูลใช้ได้: Phone 80, Camera 74, Laptop 85; Out-of-scope ที่ผ่านเงื่อนไขใช้ประเมิน **0** รายการ แผนเก็บเพิ่มตามเกณฑ์เปิดใช้ปัจจุบันคือ Camera อย่างน้อย **6**, Unknown Validation **10**, Unknown Test **30** โดย Unknown แต่ละชุดต้องมีอย่างน้อย 3 ช่อง และไม่ให้ช่อง/คลิปซ้ำข้ามชุด จำนวนครบไม่รับประกันว่าจะผ่าน Metrics

### P2: หน้า Admin ยังบอกเหตุผลที่ Analysis ถูกงดไม่ครบ

หน้า Settings แสดงโมเดล #14 และคะแนน Test 100% บน 17 ตัวอย่าง แต่ยังไม่แสดงคำเตือนเด่นว่ารุ่นนี้ไม่มี scope validation จึงไม่สามารถสร้างคำแนะนำเฉพาะหมวดใน runtime ปัจจุบันได้ หน้า Train แสดงแผนเก็บข้อมูลที่ขาดแล้ว แต่ป้ายโมเดลที่ใช้งานอยู่ยังอ่านได้เหมือนพร้อมใช้

ควรเพิ่มสถานะความพร้อมสำหรับ **สร้างคำแนะนำจริง** โดยแยกจากการโหลดไฟล์โมเดลได้/ผลประเมินเก่า ไม่ใช้ `/health=ok` เป็นหลักฐานว่าโมเดลผ่านเกณฑ์รับผลแล้ว

อ้างอิง: `frontend_flutter/lib/screens/admin_analysis_settings_screen.dart`, `frontend_flutter/lib/screens/admin_training_screen.dart`, `app/main.py:188`, ภาพ `14-admin-analysis-settings.png`

### P2: Transcript และชื่อผลที่สร้างจาก Transcript ยังอ่านยาก

ข้อความจริงเริ่มด้วย `มือเที่ยวระบบภัยดโฟล์ลิกฟิตคูลิง...` และถูกนำไปเป็นชื่อผลใน History ด้วย พบทั้งคำแตกและวลีอ่านไม่สมบูรณ์ รอบนี้ยังไม่ได้ทำ human transcription เพื่อคำนวณ WER จึงไม่รายงานตัวเลขความแม่น ASR

ควรตรวจการถอดเสียงแยกจาก Classification และปรับชื่อผลให้ผู้ใช้จำคลิปได้ง่าย ไม่แก้ Transcript ทั้งก้อนโดยเดาสเปกหรือเปลี่ยนข้อความเพื่อให้โมเดลทายถูก

## ตารางเทียบขอบเขต

“ผ่าน” ในตารางหมายถึงเส้นทางที่ระบุได้ทดสอบแล้ว ไม่ได้หมายถึงทุกกรณีขอบหรือทุกคุณภาพโมเดล

| ข้อ | ขอบเขต | ผลรอบนี้ | หน้า/หลักฐาน |
|---|---|---|---|
| 1 | สมัครสมาชิก | ผ่าน: กรอกและส่งผ่าน UI จริง | `/register`, บัญชีทดสอบ #13 |
| 2 | เข้าสู่ระบบ | ผ่าน: User และ Admin ผ่าน UI; บุคคลทั่วไปถูกกันจากข้อมูลส่วนตัว | `/login`, HTTP 401/403 |
| 3 | อัปโหลดวิดีโอ | ผ่าน: MP4 จริง; ไฟล์เสียถูกปฏิเสธ HTTP 422 | `/upload`, `/analyze/save` |
| 4.1 | คำแนะนำปรับคอนเทนต์ | **ยังไม่ผ่านเชิงใช้งาน**: วิเคราะห์จบ แต่งดคำแนะนำเพราะ policy ไม่พร้อม | `/result`, ผล #19 |
| 4.2 | ความยาวที่แนะนำ | **ยังรับรองไม่ได้**: งดแนะนำตามหมวดที่ยังไม่ยืนยัน ไม่สร้างตัวเลขแทน | `/result` |
| 4.3 | Hook Keywords Recommendation | **ยังรับรองไม่ได้**: มี Hook Terms ที่ตรวจพบ แต่คำแนะนำถูกงด ต้องไม่สับสนสองอย่างนี้ | `/result` |
| 5 | Dashboard แนวโน้ม | ผ่านเส้นทางที่ตรวจ: สาธารณะ, YouTube/Google, กราฟและรายละเอียดต้นทาง | `/dashboard`, จอ 1440/1000 px |
| 6 | บันทึก My Ideas | ผ่าน: บันทึกอัตโนมัติ เปิดกลับได้ แผนบันทึกและเปิดคืนได้ รีสตาร์ตแล้วยังอยู่ | `/history`, `/result`, Content #19 |
| 7 | สถิติย้อนหลังรายคน | ผ่าน: Daily UI และ API รายวัน/รายเดือน; ผลใหม่ถูกนับ 1 รายการ | `/history`, `/contents/statistics` |
| 8 | ติดตามกลุ่มคอนเทนต์ | ผ่าน API: ติดตามหมวด YouTube, กันซ้ำ, เลิกติดตาม; ยังไม่ได้กด workflow นี้ผ่าน UI รอบนี้ | Dashboard, `/follows/*` |
| 9 | แจ้งเตือนตามความสนใจ | **ตรวจได้บางส่วน**: ตั้ง/อ่านความสนใจและอ่านแจ้งเตือนได้; ไม่ได้เกิดเทรนด์ใหม่จริงระหว่างตรวจเพื่อยืนยัน delivery | Dashboard/Notifications |
| 10 | Admin Login | ผ่าน: Login จริง, User เข้า Admin ไม่ได้ | `/login`, หน้า Admin ทั้ง 7 |
| 11 | จัดการแหล่งข้อมูล/คลิปต้นแบบ | ผ่าน CRUD API บนแถวทดสอบ: เพิ่ม แก้ Transcript/หมวด ลบ กู้คืน; **Transcript ยังนำเข้าเอง** ไม่ใช่ auto import | `/admin-datasets`, `/admin-transcript-import`, `/admin-dataset-review` |
| 12 | ตั้งรอบเก็บข้อมูลอัตโนมัติ | พบหน้าจอและงานจริง 10 รอบวันนี้สำเร็จ; **ไม่ได้เปลี่ยนตารางแล้วรอรอบใหม่** ในการตรวจนี้ | Settings แท็บอัปเดตเทรนด์, scheduled slots |
| 13 | ดูผลโมเดลจัดกลุ่ม | **ยังไม่ตรงรายงาน**: หน้า Train ปัจจุบันเป็น Classification; API มี KMeans เก่า 1 run แต่ไม่มีหน้า Clustering ใน routing ปัจจุบัน | `/admin-training`, `/admin/clusters/runs` |
| 14 | Logs ดึงสำเร็จ/ล้มเหลว | ผ่านการเปิด/อ่าน: มีชื่อเหตุการณ์ภาษาไทย เวลา ผู้กระทำ และสถานะ | `/admin-logs`, `/admin/logs` |
| 15 | ตั้งพารามิเตอร์ | ผ่าน API เปลี่ยน Hook 60 → 59 → 60, endpoint อัปโหลดอ่านค่าจริง ผลเก่าไม่เปลี่ยน; รุ่น Whisper ไม่พร้อมถูกปฏิเสธ; **ตัวตั้งจำนวน Keywords ยังไม่ตรงขอบเขตรายงาน** | `/admin-analysis-settings` |
| 16 | สถิติรวมของผู้ใช้ | ผ่านหน้า Users และ API สถิติรวม; แยกจากสถิติส่วนตัวได้ | `/admin-users`, `/admin/usage-statistics` |
| 17 | รายงานสรุปเทรนด์ | **บางส่วน**: Dashboard มีกราฟย้อนหลังจริง; ไม่พบหน้ารายงาน Admin โดยเฉพาะ และ `/admin/reports/overview` เก่าเป็นยอด Dataset/Logs ไม่ใช่รายงานเทรนด์ย้อนหลัง | `/dashboard` |
| 18 | เปรียบเทียบ Top/Emerging ข้ามแพลตฟอร์ม | **ยังไม่ครบตามข้อความเดิม**: มี YouTube/Google แยกแท็บ; TikTok ยังว่าง และไม่มีรายงานเปรียบเทียบข้ามแพลตฟอร์ม | `/dashboard` |

ไม่ควรเรียก Classification ว่า Clustering หรือทำอันดับรวม YouTube/Google กลับมาเพียงเพื่อให้ข้อความรายงานดูครบ ควรตกลงแก้ขอบเขตกับอาจารย์อย่างชัดเจน

## รายละเอียดผลจริง

- Raw Transcript 1,520 ตัวอักษร และ Cleaned Transcript 1,519 ตัวอักษรถูกเก็บแยก
- Settings ที่ผูกกับผล: อัปโหลดสูงสุด 300 วินาที, Whisper `small`, Hook 60 วินาที, Model #14 พร้อมรุ่นและ checksum
- พบ Content Keywords และ Hook Terms แต่ Comparable/คำแนะนำถูกงดหลังผลรับหมวดเป็น Unknown ไม่รายงานว่าเป็นการแนะนำสำเร็จ
- บันทึกโน้ตแผนผ่าน UI ได้แม้ไม่มีข้อแนะนำให้เลือก; สถานะยังเป็น planning ไม่ใช่ปรับเสร็จ
- เปิดผลเดิมหลังแก้การตั้งค่าและหลังรีสตาร์ตแล้ว JSON ผลวิเคราะห์ไม่เปลี่ยน แผน revision 1 คืนกลับได้
- บัญชีอื่นอ่าน Content/แผนของบัญชีทดสอบไม่ได้ (404)
- เปลี่ยน Role/ระงับ/ลบบัญชีทดสอบอีกบัญชีผ่าน API ได้ และบัญชีที่ระงับ Login ไม่ได้
- ไม่มี JavaScript error, Flutter overflow หรือ HTTP error ในการเปิดหน้า 7 Admin และ Dashboard ที่ตรวจ ไม่ได้หมายถึงตรวจ interaction ทุกปุ่มครบแล้ว
- Latest snapshot ที่อ่าน: 30/9/2026 23:00 เวลาไทย, YouTube รวม 48 คลิป, Google 11 คำค้น; ไม่บังคับเติมให้ครบ 50
- กราฟ YouTube 5 วันแสดงข้อมูล 43/121 ช่องชั่วโมง พร้อมช่องว่าง 78 ช่องและสถานะเก็บไม่สำเร็จ ไม่ถือช่วงไม่มีข้อมูลเป็นศูนย์
- Scheduler ปัจจุบันเป็น 10 รอบต่อวัน 14:00–23:00; Browser poll ทุก 60 วินาที ไม่ใช่ API provider ทุก 60 วินาที

## ข้อที่รอบนี้ยังรับรองไม่ได้

- คุณภาพคำแนะนำเชิงบวก การเลือกคำแนะนำ/คัดลอกตัวอย่างในผลใหม่ และความยาวอ้างอิงหลังผ่านหมวด เพราะถูก policy กั้นก่อน
- Accuracy/Macro F1 บนคลิปใหม่สามหมวด, การปฏิเสธคลิปนอกขอบเขตจริง, และประโยชน์ต่อผู้ใช้โดยผู้ประเมิน
- Notification ใหม่จาก provider หลังติดตามหมวด, Scheduler หลังเปลี่ยนตาราง และการ Train/Activate ผ่าน UI จริง
- Revision upload ฉบับที่ปรับเนื้อหาจริง ไม่มีคลิปฉบับแก้ไขในรอบนี้
- การอนุมัติ/นำเข้า Transcript ชุดใหม่ ไม่ได้ทำเพื่อเลี่ยงเปลี่ยนชุดฝึกระหว่างตรวจ
- ไม่ทดสอบ Mobile app; จอที่ตรวจเป็น Desktop กว้าง 1,000 และ 1,440 px

## Handoff

**เสร็จแล้ว:** ตรวจระบบจริง, build เว็บใหม่, อัปโหลดคลิปจริงหนึ่งครั้ง, เปิดผล/แผนกลับ, ตรวจสิทธิ์, Dataset CRUD บนข้อมูลแยก, Admin account lifecycle, Settings round trip, รีสตาร์ตตรวจ persistence, เก็บภาพ/JSON และตารางเทียบขอบเขต

**ค้างก่อนส่ง:** แก้ P1 ด้าน readiness/acceptance ของโมเดลก่อนตกแต่งหน้า Analysis, ยืนยันขอบเขตข้อ 11/13/15/17/18 กับรายงาน, ทดสอบ Notification ตามเหตุการณ์จริง, จากนั้นเก็บ UI และซ้อมเดโม ไม่เพิ่มแพลตฟอร์มหรือโมเดลใหญ่ในงานตรวจรับนี้

**ไม่ได้แก้โค้ดแอป:** เพิ่มเฉพาะเครื่องมือตรวจและรายงาน ไม่เปลี่ยน Model/Threshold/กฎแนะนำ และคืน Hook เป็น 60 วินาทีแล้ว

**ข้อมูลทดสอบที่คงไว้:** User #13 กับผล #19/แผน สำหรับหลักฐาน; Dataset #428/#429 เป็น `acceptance_test`, `is_training_eligible=false`, ปิดใช้งานและอยู่ถังขยะ ไม่เป็นหลักฐานแนะนำ; บัญชี lifecycle #15 ลบแล้ว; Admin ทดสอบ #14 ปิดใช้งานและเพิกถอน session แล้ว ไม่มีการเปลี่ยนบัญชีเดิม

**เว็บที่เปิดไว้:** `http://127.0.0.1:8080/#/dashboard`, Backend `http://127.0.0.1:8000` เปิดแบบซ่อนหน้าต่าง ตัว Backend ถูกรีสตาร์ตหนึ่งครั้งหลังงานวิเคราะห์เสร็จ

## หลักฐานและคำสั่ง

Artifacts: `artifacts/acceptance/20260930/` (ignored โดย Git)

- `browser.json`: 10 checks ของเส้นทาง User; `analysis-detail.json`, `analysis-job.json`, `04-analysis-result.png`, `09-plan-reopened.png`
- `screens.json`: 16 checks เปิด Dashboard/รายละเอียด/Admin/Compact desktop ไม่ใช่การรับรองทุกปุ่ม
- `api.json`: 33 checks รวม expected 401/403/404/422 และ mutation บนข้อมูลทดสอบ
- `final-checks.json`: 5 checks รวม Settings และ persistence หลังรีสตาร์ต
- ตัวเลขเหล่านี้เป็น **software checks ไม่ใช่จำนวนคลิปประเมิน** และไม่ได้ลบล้าง P1 ที่คำแนะนำยังใช้งานไม่ได้
- ไฟล์ `private-*.json` มี session/รหัสผ่านบัญชีทดสอบ ห้ามนำไปใส่รายงานหรือแชร์กับภาพพรีเซนต์

```powershell
C:\flutter\bin\flutter.bat build web --dart-define=API_BASE_URL=http://127.0.0.1:8000
node scripts/browser/acceptance_live.cjs
python scripts/verification/acceptance_live_api.py
node scripts/browser/acceptance_screens.cjs
python scripts/verification/acceptance_final_checks.py
python scripts/verification/acceptance_final_checks.py --after-restart
python scripts/verification/acceptance_cleanup.py
```

สคริปต์เหล่านี้เป็นเครื่องมือของการตรวจรอบนี้ อ่าน/เขียนฐานข้อมูลจริงและมีข้อมูลทดสอบ ต้องตรวจ artifacts และสถานะบัญชีก่อนรันซ้ำ ไม่ใช่ test fixture แบบปลอดผลข้างเคียง ส่วน cleanup มี identity guard และออกแบบสำหรับรอบนี้โดยเฉพาะ

`git status` ตรวจไม่ได้เพราะ `.git` ของ worktree ชี้ไป `Z:/content-ai/.git/worktrees/agents-content-analysis-recommendation-system` ที่หาไม่พบ จึงไม่ได้แก้ metadata Git หรือยืนยัน clean diff; โค้ดและข้อมูลเดิมไม่ได้ถูก revert
