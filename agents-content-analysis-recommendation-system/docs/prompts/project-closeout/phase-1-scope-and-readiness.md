# Closeout Phase 1: ล็อกขอบเขตและตรวจความพร้อม

อ่าน `README.md` ในโฟลเดอร์นี้และ `docs/implementation/acceptance-20260930.md` ก่อนทำ งานนี้คือปิดความไม่ชัดเจน ไม่เริ่ม Train/Activate หรือสร้างระบบใหม่

## งานที่ต้องทำ

1. ตรวจ routing/frontend/API ที่ใช้อยู่ เทียบขอบเขตผู้ใช้ 1-9 และ Admin 10-18 ทำตาราง `ข้อ / หน้าจอ / API / ข้อมูล / ทำแล้ว / ขาด / เกณฑ์ตรวจรับ / ผู้ตัดสินใจ` เก็บใน `docs/implementation/project-closeout-scope.md`
2. แยกข้อเสนอแก้รายงานออกจากข้อที่ผู้ใช้/อาจารย์ยอมรับแล้ว ต้องมี `pending/approved/rejected` และข้อความยืนยันอ้างอิง ห้ามประกาศว่าขอบเขตเปลี่ยนแล้วเพราะ agent เห็นด้วยเอง
3. ตรวจ Active Model และโมเดลที่มีอยู่ทั้งหมดจาก registry + artifact + ผลประเมิน แยกสถานะไฟล์พร้อม, classification evaluation, scope policy validated, activation eligibility และ runtime recommendation readiness ไม่ใช้เพียง `status=qualified`
4. ตรวจข้อมูลใช้ได้และข้อมูลที่ยัง review ค้างด้วย contract จริง ออกรายการขาดตามหมวด/split/channel รวม Unknown; ตรวจ reservation/คลิปที่เคยใช้แก้ระบบก่อนเสนอชุด Test ใช้ `plan_classification_collection.py` และ API preview เดิมหลังอ่านวิธีใช้ ไม่สร้างกฎ split อีกชุด
5. เพิ่ม/แก้สถานะ readiness ที่หน้า Admin Training/Analysis Settings ให้บอกตรงกับ Backend พร้อมเหตุผล เช่น มีโมเดลแต่ยังงดคำแนะนำเพราะไม่ผ่าน scope validation ใช้ service กลางที่มี ไม่ซ่อนรุ่นที่กำลัง Active
6. ถ้าขยาย health endpoint ให้เป็น field/additive semantics แยกความพร้อมบริการกับความพร้อมคำแนะนำ ไม่ทำให้ฐานข้อมูลที่ทำงานอยู่กลายเป็นล่มเพียงเพราะ policy ขาด และไม่เปิดรายละเอียดลับแก่ Guest
7. จัดลำดับ must-fix ก่อนศุกร์กับงานที่เลื่อนได้ ระบุ dependency ผู้ใช้/ข้อมูลให้ชัดเจน

## ข้อเสนอขอบเขตที่ให้ผู้ใช้ยืนยัน

| ข้อเดิม | ข้อเสนอสำหรับรุ่นส่ง | หากยังไม่ยืนยัน |
|---|---|---|
| 11 คลิปต้นแบบอัตโนมัติ | นำเข้า/ตรวจ/แก้ Transcript เอง; อัปเดต metadata และสถิติจาก Video ID อัตโนมัติ | ระบุไม่ตรงข้อความเดิม ไม่อ้าง auto transcript |
| 13 โมเดลจัดกลุ่ม | ดูผลประเมินโมเดลจำแนกหมวดและ Unknown ในหน้า Train เดิม | ยังเป็น gap ไม่สร้าง clustering เพื่อให้มีหน้าเฉย ๆ |
| 15 จำนวน Keywords | ถ้าต้องคงไว้ ทำเป็นจำนวนคำดิบที่แสดงในส่วนรายละเอียด ไม่ตัดการสกัด/หลักฐาน/ข้อแนะนำ | ไม่คืน setting ที่เคยถอดออกโดยอัตโนมัติ |
| 17 รายงานเทรนด์ | ใช้ Dashboard/ข้อมูลประวัติเดิม หรือรายงานอ่านอย่างเดียวที่ reuse service เดิมหากต้องมีหน้าเฉพาะ | ห้ามนับ Dataset ฝึกเป็นความนิยม |
| 18 ข้ามแพลตฟอร์ม | เทียบภาพรวม YouTube กับ Google ในเวลาเดียวกัน แยกหน่วย/อันดับ/coverage; งด TikTok รุ่นนี้ | ยังไม่ครบตามรายงาน ไม่สร้างข้อมูล TikTok ปลอม |

## โค้ดเริ่มอ่าน

- `frontend_flutter/lib/routing/app_router.dart`
- `app/services/classification.py`, `classification_acceptance.py`, `classification_training.py`, `classification_collection_plan.py`, `analysis_settings.py`, `model_management.py`
- `app/routes/model_management.py`, `app/routes/admin.py`, `app/main.py`
- `frontend_flutter/lib/screens/admin_training_screen.dart`, `admin_analysis_settings_screen.dart`
- `tests/test_classification_acceptance.py`, `tests/test_classification_collection_plan.py`, `tests/test_analysis_settings.py`

## เกณฑ์ผ่าน

- ตารางขอบเขตทุกข้อมีสถานะและเกณฑ์ ไม่หายไปเพราะไม่ได้ทำ
- Admin เห็นสาเหตุเดียวกับ runtime ว่าทำไมคำแนะนำพร้อม/ไม่พร้อม; ทดสอบ policy ขาด, ไม่ผ่าน, ผ่าน และ artifact ใช้ไม่ได้
- มี collection checklist จากข้อมูลปัจจุบัน ไม่คัดลอกตัวเลขเดิมโดยไม่ตรวจ
- ไม่มีการเปลี่ยน Active Model, threshold หรือ Train/Validation/Test membership
- ข้อที่รอยืนยันยังเป็น pending ส่วนการพร้อมวิเคราะห์ต้องไม่ใช้ป้ายผ่านแทนข้อมูลที่ยังขาด

เสร็จแล้วได้: รายการงานที่ตัดสินใจได้จริงและไม่มีความเข้าใจผิดว่าโมเดลพร้อมเพียงเพราะโหลดได้ บันทึก `project-closeout-phase-1-handoff.md` แล้วหยุด
