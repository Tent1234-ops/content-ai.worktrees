# Closeout Phase 6: เตรียมส่งและพรีเซนต์

อ่าน README, final acceptance report และ Handoff ล่าสุด งานนี้จัดรุ่นส่งและทำให้เจ้าของโปรเจคอธิบายได้ ไม่เพิ่มโมเดล/ฟีเจอร์หรือแก้ผลทดสอบย้อนหลัง

## 1. รุ่นส่งและการเปิดระบบ

- ระบุ release version/เวลา, commit ถ้ามี Git ที่ใช้งานจริง หรือ file manifest/checksum หาก Git เสีย ห้ามแก้ worktree pointer/reset/init เพื่อให้มี commit โดยไม่ยืนยันกับผู้ใช้
- ตรวจ README/run scripts ปัจจุบันให้ตรงเครื่อง: MySQL, env keys โดยไม่ใส่ค่า secret, dependencies, model assets ที่ต้องมี, API/Web URLs และวิธีตรวจ readiness
- ปรับหรือใช้ launcher เดิมให้เปิด backend/web แบบไม่เด้ง terminal ตามความต้องการผู้ใช้ ตรวจพอร์ตชนและ readiness ไม่ยึด PID/port เดิมแล้ว kill งานอื่น
- ทดลอง stop/start ใหม่ เปิดเว็บ/ผลเก่า/แผน/settings ได้ บันทึกว่าทดสอบอะไร ไม่ต้องส่ง public deployment ถ้าไม่ได้อยู่ในขอบเขต
- ทำ checklist สำรอง DB + evaluated model artifacts + taxonomy/template/method versions + env ส่วนตัว ให้กู้คืนในฐานแยกได้ตามที่ทดสอบ ห้ามลอง restore ทับ production เพื่อพิสูจน์
- เก็บสิ่งจำเป็นของสถิติย้อนหลัง/ผลเก่า ไม่ลบ artifacts/ไฟล์โมเดล/สื่อทั้งหมดด้วย wildcard เพื่อให้โฟลเดอร์ดูเรียบร้อย

## 2. ชุดพรีเซนต์ที่ไม่มีข้อมูลลับ

- คัดภาพจริงจากรุ่นตรวจพร้อมวันที่/สภาวะ ไม่ใส่ภาพ fixture แบบไม่ติดป้าย
- มีเดโมที่เสนอหัวข้อได้จริง, เดโม Unknown/หลักฐานไม่พอ, และตัวอย่าง Dashboard ที่มีช่วงข้อมูลขาดอย่างซื่อสัตย์ หาก positive Analysis ยัง blocked ต้องระบุ ไม่ใช้ภาพเก่าหรือผลที่แต่งให้เหมือนรุ่นปัจจุบัน
- เตรียมผลบันทึก/ภาพ/วิดีโอเดโมสำรองกรณีเน็ต/API ไม่พร้อม โดยติดป้ายข้อมูลย้อนหลังตามเวลาจริง ไม่เปลี่ยน cache เก่าให้ดู live
- ห้ามแนบ `.env`, `private-*.json`, token, password, session หรือข้อมูลส่วนตัวที่ผู้ใช้ไม่อนุญาตใน bundle/เอกสาร

## 3. คู่มือเข้าใจระบบภาษาไทย

สร้าง `docs/presentation/system-walkthrough-th.md` และ `docs/presentation/demo-checklist-th.md` ตามรูปแบบเอกสารเดิมถ้ามีแล้ว ให้ใช้ชื่อไฟล์จริง/ฟังก์ชัน/ตาราง/endpoint อ้างอิงในทุกหัวข้อสำคัญ

เนื้อหาที่ต้องมี:

1. ภาพรวมโจทย์: ผู้ใช้ได้อะไรจาก Dashboard และจากการวิเคราะห์คลิป ต่างจากการดู YouTube อย่างไร
2. Dashboard: provider -> normalize schema (ไม่ใช่ทำหน่วยเหมือนกัน) -> snapshot -> history -> graph -> notification; แยก browser poll/collection schedule และอันดับรวม/หมวด/platform
3. Analysis: upload validation -> audio/ASR -> raw/clean/segments -> feature/classification -> acceptance -> reference selection -> topic gap -> advice/evidence/duration -> save/plan/revision
4. Classification training: ข้อมูล/Label -> grouped split -> features -> fit -> Validation เลือกวิธี/เกณฑ์ -> Test ประเมิน -> artifact/metrics -> manual Activate; อธิบาย Accuracy/F1/Recall/Confidence ต่างกันด้วยตัวอย่างเล็ก
5. Recommendation ไม่ใช่โมเดลจำแนก: อ้างอิงอะไร เทียบอย่างไร สิ่งที่พบ/ไม่พบ/ตรวจไม่ได้ และทำไมสถิติสัมพันธ์ไม่รับประกันเพิ่ม Engagement
6. ตาราง DB ที่เกี่ยวข้องจริงกับทุก flow: มาจากไหน เก็บอะไร ใช้ต่อไหน ใครเป็นเจ้าของ ไม่อธิบาย legacy table ว่ายังใช้งานจริงโดยไม่ตรวจ
7. Admin: หน้าที่แต่ละหน้า Settings ที่มีผลจริง Logs ไม่ใช่เครื่องจับทุก bug และแก้ dataset แล้วไม่ใช่ retrain model อัตโนมัติ
8. ข้อจำกัด/ผลตรวจ/ขอบเขตที่แก้และรออาจารย์อนุมัติ รวมถึงข้อมูลน้อย กระแสไม่ realtime ทุกวินาที ASR error และช่วงข้อมูลขาด

จัด flow เดโมประมาณ 8-10 นาที (ปรับตามเวลาที่ผู้ใช้กำหนด), คำถามอาจารย์ที่คาดว่าจะเจอ และคำตอบสั้นพร้อมอ้างโค้ด ไม่ให้ผู้ใช้จำสูตรอังกฤษอย่างเดียว อธิบายตัวแปรเป็นภาษาไทย

## 4. Freeze

- อัปเดต scope matrix/final handoff ให้ตรง release สุดท้าย ทุก blocker ต้องแก้หรือระบุยังไม่ผ่านพร้อมการยอมรับข้อจำกัด ไม่ลบทิ้งจากรายการ
- บันทึกค่าก่อนเดโมและเช็กลิสต์ห้ามแตะ Train/Activate/collection interval/random seeds ระหว่างซ้อมโดยไม่ตั้งใจ
- หลัง freeze แก้เฉพาะข้อผิดพลาดขวางการเดโม พร้อม retest และอัปเดตรุ่น/ภาพที่เปลี่ยน งานทดลองใหม่ย้ายเป็น backlog หลังส่ง
- เว้นเสาร์-อาทิตย์ให้เจ้าของโปรเจคเรียนและซ้อมจากรุ่นเดียวกัน ไม่ตั้ง task background ให้เปลี่ยนโมเดล/ข้อมูลผลวิเคราะห์เก่าโดยเงียบ ๆ

## เกณฑ์ผ่าน

- เปิดระบบตามคู่มือได้จริงจากสถานะที่ปิดอยู่; account/secret ไม่รั่วและไม่มี admin ทดสอบที่เปิดค้างโดยไม่จำเป็น
- รุ่นส่ง/ฐานข้อมูล/โมเดล/ผลตรวจจับคู่กัน ตรวจย้อนกลับได้
- คู่มือ/เดโมอธิบายจากโค้ดและผลจริง ไม่มีข้อความที่ขัด final acceptance หรือขอบเขตที่ยัง pending
- ระบุ backup/restore ที่ทดสอบจริงและที่ยังไม่ได้ทดสอบ ไม่อ้างรองรับเครื่องใหม่ทั้งหมดเพียงเพราะเครื่องนี้รันได้

เสร็จแล้วได้: รุ่นส่งพร้อมเอกสารให้ผู้ใช้ทำความเข้าใจและซ้อม บันทึก `project-closeout-phase-6-handoff.md` และรายการค้างสุดท้าย หยุดพัฒนาอัตโนมัติ
