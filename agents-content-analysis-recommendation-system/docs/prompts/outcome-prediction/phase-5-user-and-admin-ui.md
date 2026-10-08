# Phase 5: Result/Admin ที่อ่านรู้เรื่องและใช้งานจริง

## คำสั่ง

อ่าน README, prediction-contract.md และ Handoff Phase 1-4 ตรวจ Frontend/Backend ปัจจุบัน ทำเฉพาะ Phase 5 ไม่เริ่ม Phase 6 ไม่เปิด Test/Activate โมเดลจริงเอง

เป้าหมายคือแสดงหลักฐาน/ผลประเมินให้เข้าใจถูก ไม่สร้าง Dashboard/Console อีกหน้า หรือ UI ที่มีแต่ปุ่มและไม่ได้บันทึกจริง

## อ่านก่อน

- `frontend_flutter/lib/screens/result_screen.dart`
- `frontend_flutter/lib/screens/admin_training_screen.dart`
- `frontend_flutter/lib/screens/admin_datasets_screen.dart`
- `frontend_flutter/lib/widgets/actionable_advice_panel.dart`
- `frontend_flutter/lib/widgets/recommendation_evidence_panel.dart`
- `frontend_flutter/lib/widgets/clip_revision_planner.dart`
- `frontend_flutter/lib/widgets/revision_comparison_panel.dart`
- `frontend_flutter/lib/models/recommendation_result.dart`, `model_training.dart`, `clip_revision_plan.dart`
- `frontend_flutter/lib/repositories/admin_repository.dart`
- API/Schema/Registry จาก Phase 3-4, Flutter tests และ Theme/Navigation เดิม

## งาน

### A. หน้าผลวิเคราะห์

คงโครงสร้างเดิมและเพิ่มข้อมูลอย่างเป็นลำดับ:
1. สิ่งที่พบจริงในคลิปและหมวดที่ผ่าน Gate
2. คำแนะนำหลัก 2-3 ข้อพร้อมวิธีทำ/ประโยคตัวอย่าง
3. "ทำไมประเด็นนี้จึงน่าลองเพิ่ม" พร้อมหลักฐานสั้น ๆ
4. รายละเอียดหลักฐาน/วิธีประเมิน/Raw keywords เปิดดูเพิ่มเติม

Probability แสดงได้เฉพาะ `available` จาก Server ใช้คำว่า "โอกาสอยู่ในกลุ่มยอดวิวสูงกว่าค่ากลางของชุดอ้างอิง" พร้อมบริบท/ข้อจำกัดใกล้ตัวเลข ไม่ใช้ "เพิ่มยอดวิว X%" หรือใช้สีเขียวเหมือนรับรองผล

- ถ้า status อื่น ใช้ข้อความไทยจำเพาะ ไม่แสดง 0.00/0%/กราฟว่างแทนข้อมูลขาด
- Probability ของ Outcome กับ Classification Confidence ต้องไม่รวมกัน ไม่ใช้แถบชื่อ "ความแม่น AI" เดียว
- ไม่มีค่าจาก Backend ไม่คำนวณเปอร์เซ็นต์เองใน Dart
- หลักฐานไม่มีความต่างหรือพบผลลบต้องแสดงตรง ไม่ทำทุกข้อความเป็นผลบวก
- Scenario ถ้าเปิดได้ให้เป็นส่วนรอง ติดป้ายสถานการณ์สมมุติ แสดง Delta เป็นจุดเปอร์เซ็นต์พร้อม +/0/- ตามจริง
- Scenario ที่ยังไม่มีหลักฐานไม่ให้กดแล้วแจ้งสำเร็จ; แสดงเหตุผลที่ไม่พร้อม
- คง Copy/Save plan/เลือกนำไปปรับ โดย Success หลัง Save สำเร็จ ไม่ถือว่า "เลือก" คือ "ปรับเสร็จ"

### B. ประวัติและฉบับแก้ไข

- เปิดผลเก่าที่ไม่มี Outcome ได้: "ผลนี้ยังไม่มีการประเมินผลตอบรับ" ไม่คำนวณย้อนหลังเอง
- ผลที่มี Outcome ใช้ Snapshot เดิมแม้ Active model เปลี่ยน
- อัปโหลดฉบับแก้แล้วแสดง content changes และ Outcome comparison แยกกัน
- Model/Context/version ต่าง -> "เทียบค่าประเมินโดยตรงไม่ได้" ไม่วาดลูกศรพัฒนาขึ้น
- เก็บ Loading/error/retry/empty/permission denied และ failure ของ Save จริงครบ

### C. หน้า Admin เดิม

เพิ่ม Section/Tab แยก **โมเดลจำแนกหมวด** และ **โมเดลประเมินผลตอบรับ** ในหน้าฝึกเดิม:
- แสดงความพร้อมข้อมูล/สิทธิ์/จำนวนคลิปและช่องต่อ Split จาก API ไม่ Hard-code
- Train job, progress/status/error, run history, model detail/target/scope/versions
- แสดง Baseline vs Candidate, Validation vs Independent Test, Calibration และ Coverage เป็นข้อมูลคนละประเภท
- คลิก Train ใช้ Background job จริง; ปุ่ม Disable/Reason เมื่อ Preflight ไม่ผ่าน
- Activate/Rollback มี Confirmation และตรวจ Server gate; Model ที่ยังไม่ Qualified กดเปิดใช้จริงไม่ได้
- Status และผลลัพธ์ต้องคงอยู่เมื่อ Refresh/Restart ไม่ใช้ state ใน Browser เป็นความจริง
- ไม่สร้างปุ่ม Force qualify, Override accuracy หรือใส่เปอร์เซ็นต์เอง
- หน้า Dataset เดิมเพิ่มสถานะพร้อมสำหรับ Outcome/ขาดอะไร/role ตามจำเป็น ไม่ให้แก้ Protected split โดยตรง
- แยกจำนวน Observation ออกจาก Independent videos/channels ให้ Admin ไม่เข้าใจผิด

ไม่มี Console ใหม่ ไม่เอา Tab/ช่องที่ผู้ใช้ขอเอาออกก่อนหน้ากลับมา ไม่แก้ Dashboard/TikTok/Sorting ที่ปิดงานแล้ว

### D. การออกแบบและ Browser verification

ใช้ Theme/Typography/Icon library เดิม ไม่ใส่ Hero/Marketing cards ในหน้าเครื่องมือ ไม่ซ้อน Card หลายชั้น
- หัวข้อกระชับ สีแยก Neutral/Warning/Error/Success ตามความหมาย
- วันที่/หน่วย/เปอร์เซ็นต์/ข้อความไทยอ่านตรง ไม่ตัดเลขหรือคำสำคัญ
- ข้อความยาว/ชื่อคลิปยาว/สถิติ null ไม่ทำ Layout overflow
- ตรวจ Desktop 1440x900, 1000x800 และ Web แคบ 390x844 เพื่อป้องกันข้อความล้น ไม่ใช่เพิ่ม Mobile app
- ใช้ Browser/Playwright จริงหลัง build ตามวิธี repo Capture screenshots และ Browser console
- States แบบ Qualified ที่ใช้ Fixture ต้องแยกจาก Live ที่ยังไม่ Qualified ไม่เปลี่ยน Production DB ให้ผ่านเพื่อถ่ายรูป
- Start dev server หากต้องใช้และไม่มี instance ที่เหมาะสม แจ้ง URL; อย่าแย่ง Port/ปิด Server ของผู้ใช้

## Tests และเกณฑ์จบ

- Flutter parser backward compatibility และ Unknown field/status tolerance
- Widget tests ทุก Status, null probability, negative/zero delta, long Thai text, no generated default 0%
- Role guard/disabled actions และ Server failure ไม่แสดง Success
- Save -> History -> Reopen -> Model/Dataset changed -> Reopen แสดงผลเดิม
- Browser admin train/status path ใช้ Endpoint จริงได้; Activation rejection ทำงานจริง
- Regression Analyze/Ideas/Revision/Classifier Admin เดิมยังทำงาน
- flutter analyze, focused/full relevant tests, Web build พร้อม Exit codes
- Screenshots แต่ละ viewport และ error log; หากตรวจ Browser ไม่ได้ต้องรายงาน ไม่ใช้ build ผ่านแทน

## ส่งมอบ

UI/API integration, Tests, screenshots/console evidence, running URL และ `docs/implementation/outcome-prediction-phase-5-handoff.md`

Freeze Candidate/Protocol/UI contract และ Utility study protocol จาก Phase 1/6 ภายใน 15 ต.ค. รวมข้อความคำถาม เกณฑ์คะแนนและการสลับลำดับก่อนมี Human ratings โดยยังไม่เริ่มประเมินหรือเปิด Test ใน Phase นี้ แจ้งความสามารถใดเป็น Live, Fixture only, Blocked แยกกันอย่างชัดเจน

