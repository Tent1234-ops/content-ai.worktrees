# Closeout Phase 3: เก็บ Workflow ผู้ใช้และ Admin

อ่าน README, scope matrix จาก Phase 1, Handoff ล่าสุด และ acceptance report ก่อนแก้ ทำส่วนที่ยังตรวจไม่ครบหรือมีบั๊ก ไม่เขียน CRUD/Scheduler/Notification ใหม่ทั้งระบบ งานนี้ทำได้ระหว่าง Phase 2 รอข้อมูล แต่ต้องได้รับการมอบหมายแยก

## 1. Follow และ Notification

- ทดสอบผ่าน UI: เลือก YouTube category -> ติดตาม -> reload/relogin -> ยังติดตาม -> เลิกติดตาม; ซ้ำต้องไม่สร้างแถวซ้ำ และผู้ใช้แต่ละคนไม่เห็นรายการของกัน
- ทดสอบโหมดแจ้งเตือนทั้งหมด/เฉพาะที่ติดตาม/ปิด ตาม semantics ที่กำหนดใน service ปัจจุบัน ไม่เพิ่ม keyword extraction จาก transcript ของ Top 50
- ใช้ snapshot ของ platform/scope/category เดียวกัน ตรวจรายการเข้าใหม่หลัง baseline/session; ไม่แจ้งรายการเดิมซ้ำทุก poll ไม่แสดง google update เป็น youtube และไม่แจ้งย้อนหลังจากช่วงปิดแจ้งเตือนโดยไม่ตั้งใจ
- ตรวจ unread/read/badge เปิดอ่านแล้วกลับหน้าเดิม รีสตาร์ต ไม่ซ้ำข้าม browser tab และสิทธิ์ของเจ้าของ
- มี deterministic integration tests ด้วย snapshot ที่ระบุว่า fixture ใน DB แยก และ live test จาก provider เมื่อเกิดเหตุการณ์จริง ห้ามใส่คลิปสมมุติลงฐาน trend จริงเพื่อให้ notification ผ่าน
- ถ้าไม่มี live change ระหว่างตรวจ ให้แยกว่าตรรกะผ่าน fixture แต่ delivery จากเหตุการณ์ใหม่จริงยังไม่ได้ตรวจ ห้ามลดเงื่อนไขเพื่อให้เกิดการแจ้งเตือน

## 2. Scheduler และการเก็บข้อมูล

- ตรวจหน้า Settings ผูกกับ `trend_schedule`/worker จริง; เปลี่ยนตารางใน test environment แล้วพิสูจน์ due/not-due จากเวลา ไม่ใช่เพียง PUT/GET สำเร็จ
- ตรวจ process เก็บข้อมูลแยกและ Backend ไม่ชนกัน ไม่เก็บซ้ำ slot, เคารพ enabled/window/timezone, error/backoff และ daily request estimate
- ตรวจรัน Windows Task Scheduler แบบไม่มี terminal เด้ง และแสดงเวลาล่าสุด/รอบถัดไป/สำเร็จ/ล้มเหลวตามงานจริง ไม่สร้างเวลารวบย้อนหลังเมื่อเครื่องปิด
- Browser poll 60 วินาทีต้องอ่าน DB ไม่กระตุ้น provider ทุก poll; รักษา cache categories และ scope ranks
- ตรวจจริงแบบจำกัดรอบ provider/quota พร้อมผู้ใช้รับรู้และคืนค่าหลังทดสอบ ห้ามเปลี่ยนทุก 60 วินาทีถาวรเพื่อเดโม; baseline ปัจจุบัน 14:00-23:00 วันละ 10 รอบ
- คง history/gap/counter correction ตาม Phase 2/5 เดิม ไม่เชื่อมเส้นผ่านข้อมูลขาดหรือเอายอดสะสมเป็นการเติบโต

## 3. Admin และข้อมูลส่วนตัว

- Dataset create/update/delete/restore ผ่าน UI จริงบนแถวทดสอบที่ไม่ใช้ Train/Reference; ตรวจ transcript hash, taxonomy label, confirmation, train/test reservation และ audit log ตามระบบเดิม
- Review/import: ทดสอบรายการถูก/ผิด/ซ้ำ/approve all โดยไม่อนุมัติสิ่งที่ตรวจไม่ได้ ทดสอบ fixture ที่แยกหรือแถวทดสอบเท่านั้น ไม่ mass approve ข้อมูลจริงที่ค้าง
- Users: role/active/delete/session revoke, ห้ามทำลาย admin คนสุดท้าย/ตัวเอง, stale revision/conflict, private history และ save ที่ล้มเหลวไม่แสดง success
- Settings: เปลี่ยน upload max/Hook/Whisper ที่พร้อมผ่าน UI ใหม่ใช้จริง ผลเก่าไม่เปลี่ยน; unavailable model เลือกหรือบันทึกไม่ได้
- Logs: เวลา/ผู้กระทำ/status/ชื่อไทย, failure แสดงเหตุผลสั้นที่ทำตามได้ ไม่รั่ว SQL stack trace, session หรือ API key

## 4. เติมเฉพาะช่องว่างที่ได้รับอนุมัติจาก Phase 1

- ถ้าคงข้อ max Keywords: จำนวนคำดิบที่แสดงเป็น display preference กลางเท่านั้น ไม่เปลี่ยนข้อมูลสกัด/ข้อสรุป/หลักฐานที่แช่แข็ง และไม่เปลี่ยนจำนวนคำแนะนำหลัก 2-3 ข้อโดยไม่เกี่ยวข้อง
- ถ้าต้องมีหน้ารายงาน Admin: reuse trend history service และ components เดิม พร้อมช่วงเวลา/platform/scope/coverage; ห้ามทำ Console ใหม่หรือใช้จำนวน training rows วัดกระแส
- ถ้าอนุมัติการเทียบ YouTube/Google: แสดงขนานกันในช่วงเวลาเดียวกันพร้อมหน่วย/coverage ของแต่ละฝั่ง ไม่รวมคะแนน/ลำดับ ไม่อ้าง Google search count คือจำนวนคนไม่ซ้ำ และไม่บังคับจับชื่อคลิปเป็นหัวข้อเดียวกับคำค้น
- หากเรื่องยัง pending ให้ส่งรายการถามและทำงานที่ไม่ติดก่อน ไม่ถือว่ายกเลิก scope เดิมแล้ว

## โค้ดเริ่มอ่าน

- `app/services/follows.py`, `live_trend_notifications.py`, `category_interest_notifications.py`, `trend_watch_sessions.py`, `notifications.py`
- `app/services/trend_scheduler.py`, `trend_settings.py`, `trending_fetcher.py`, `live_trend_snapshots.py`, `trend_history.py`
- `scripts/run_trend_scheduler.py`, `scripts/run_trend_scheduler.ps1`, `scripts/install_trend_scheduler.ps1`
- `app/routes/admin.py`, `user_management.py`, `dataset_review.py`, `contents.py`, services/schemas ที่ตรงกัน
- Dashboard/Admin widgets และ repositories ที่เรียก endpoints จริง รวม tests ของแต่ละ workflow

## เกณฑ์ผ่าน

1. ทุก flow ที่ระบุมี assertion ต่อค่าที่บันทึกและสิทธิ์ ไม่ใช่เพียงหน้าโหลด HTTP 200
2. Notification และ Scheduler มี tests ครอบคลุมเวลา/ความซ้ำ/platform/scope และรายงาน live evidence แยกจาก fixture
3. ข้อใน scope matrix เปลี่ยนสถานะได้เพราะมีหลักฐานหรือการอนุมัติจริงเท่านั้น
4. คืนค่าตาราง/model settings, ปิดสิทธิ์บัญชีทดสอบ และเก็บแถวทดสอบนอกแหล่งฝึก/แนะนำ พร้อมรายการ cleanup

เสร็จแล้วได้: เว็บทำงานต่อเนื่องตั้งแต่ตั้งความสนใจไปถึงดูผลและให้ Admin จัดการได้จริง บันทึก `project-closeout-phase-3-handoff.md` แล้วหยุด
