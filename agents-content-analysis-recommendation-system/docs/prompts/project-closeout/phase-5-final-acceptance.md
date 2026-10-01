# Closeout Phase 5: ตรวจรับรุ่นส่งจริง

อ่าน README, scope matrix และ Handoff 1-4 รวม protocol ประเมินใน `docs/prompts/recommendation-roadmap/phase-7-utility-evaluation.md` งานนี้พิสูจน์สิ่งที่ทำ ไม่เปลี่ยนเกณฑ์ตามผลและไม่เริ่มรอบวิจัยใหม่

## 1. เตรียมรุ่นตรวจ

- ระบุรุ่นโค้ด/build, dependency, Active Model/Artifact hash, settings, cutoff/reference versions และเวลาตรวจ
- สำรองข้อมูล/config ที่จะกระทบก่อนทดสอบ ใช้ test accounts/rows แยกและ cleanup แบบมี identity guard
- อ่านสคริปต์ acceptance เก่าก่อน reuse เพราะเป็น one-off ที่มี paths/date/IDs เฉพาะรอบ มี private credentials และ admin ที่ retire แล้ว ปรับเป็น run directory/IDs ของรอบใหม่ ไม่รัน cleanup เก่าทับข้อมูลใหม่
- สร้าง checklist expected outcome ก่อนดูผลจริง แยก mandatory/approved optional/pending scope ไม่มีการลบข้อที่ไม่ผ่านออกจากรายงาน

## 2. Software Acceptance

- Guest Dashboard, YouTube/Google/category/detail/history charts/more, Auth gate
- Register/Login/Logout, wrong credentials, protected pages และไม่เห็นข้อมูลของคนอื่น
- Upload valid/over-limit/corrupt, ASR/job loading/error, retry/double submission ตาม flow ที่มี
- Accepted classification -> recommendations/evidence/hook/duration -> copy/select/plan/save/reopen/restart
- Unknown/ASR fail/no reference/no gap แสดงสาเหตุแยกและไม่ให้ข้อแนะนำข้ามหมวด
- Revision จากไฟล์ที่แก้จริงถ้ามี พร้อมอ้าง parent/plan/version ที่ถูกต้อง; fixture แยกเป็น fixture
- User statistics รายวัน/เดือน, Follow category, Notification modes/unread/read, Scheduler due/failed/restore
- Admin Dataset import/review/edit/trash/restore, Users role/status/delete, Logs, Settings, Model status; Train/Activate ตรวจตามงานควบคุมใน Phase 2 ไม่ฝึกซ้ำเพียงเพื่อเพิ่มจำนวน test
- Save/DB/network failure ต้องไม่แสดง success; ผลเก่าไม่เปลี่ยนตาม Dataset/config ปัจจุบัน; privacy ไม่มี SQL/secret ในหน้าเว็บ

ใช้ backend unittest และ Flutter tests ของ repo ตามที่ติดตั้งจริง แล้ว build เว็บใหม่/รัน browser กับ backend จริง เก็บ failure ที่แก้พร้อม retest อย่าอ้าง test suite ที่รันในอดีตเป็นรอบปัจจุบัน

## 3. Model และ Recommendation Evaluation แยกกัน

- ใช้ fresh heldout clips ที่กำหนดก่อนดูผลตาม protocol เดิม ทั้ง Phone/Camera/Laptop, คลิปถ่ายเองและนอกขอบเขต หากไม่มี ให้ระบุยังไม่ประเมิน ไม่ย้าย regression clips เป็น fresh test
- Classification: รายงาน n, confusion matrix/Accuracy/Macro F1/Recall แต่ละหมวด และ Unknown rejection แยก ไม่อ้าง confidence ของคลิปหนึ่งเป็น accuracy ระบบ
- Recommendation: ตรวจ relevance, redundancy, evidence correctness, clarity/actionability ตาม rubric เดิม แยกผล A/B/C และจำนวนผู้ประเมินที่มีจริง ไม่ให้ agent กรอกคะแนนแทนมนุษย์
- ตรวจ provenance ของทุก quote/สถิติ/เวลาและการกัน reference/test; missing evidence ต้องถูกนับตาม protocol ไม่ตัดเคสล้มออกเงียบ ๆ
- Test ที่เปิดผลแล้วถูกใช้แก้ระบบไม่ถือเป็น fresh test ซ้ำ รายงานว่าเป็น retest/regression และต้องมีชุดใหม่หากจะสรุป generalization
- ถ้ายังไม่มีผู้ประเมิน/จำนวนคลิปครบ ให้รายงาน software acceptance ที่ตรวจได้กับ model/utility evaluation ที่ยังค้างแยกกัน ไม่ประกาศทุกอย่างผ่าน

## 4. Deliverable

สร้าง `docs/implementation/project-closeout-final-acceptance.md` มีตารางทุกข้อใน scope, method, expected/actual, pass/fail/not tested/blocked, artifact path และผู้รับผิดชอบงานค้าง

แยกอย่างน้อย:

- Release blockers: วิเคราะห์หลักไม่ทำงาน, ข้อมูลสูญหาย/รั่ว, false save success, แนะนำผิดหมวด, ไม่มีหลักฐานแต่แต่งคำอธิบาย
- Non-blocking polish: สิ่งตกแต่งที่ไม่ขวาง flow และผู้ใช้ยอมรับให้ค้าง
- Research limitations: จำนวนคลิป/ช่อง/ผู้ประเมินและเวลาสถิติไม่พอ ไม่ใช่บั๊กที่แก้ด้วยเปลี่ยนป้าย

## เกณฑ์ผ่าน

1. Mandatory flows ที่ยืนยันมี live evidence ไม่ใช่แค่ fixtures/endpoint 200; feature ใดไม่มี live proof ต้องบอกตรง ๆ
2. ไม่มี release blocker ที่ถูกปิดด้วยการลดเกณฑ์หรือซ่อน UI และ Test/Reference ไม่ปะปน
3. รายงาน software/model/utility แยกกัน นับจำนวนตัวอย่าง/ช่อง/ผู้ประเมินจริง
4. ผลตรวจย้อนกลับถึงรุ่น/config/artifacts ได้ cleanup เสร็จและระบบเปิดให้ผู้ใช้ลองได้

หากผ่านเพียง software แต่ model/utility ยังไม่ครบ ให้สถานะส่งมอบเป็นบางส่วนพร้อมข้อจำกัดและการยอมรับจากผู้ใช้ ไม่ตั้งชื่อว่า completed ทั้งโครงการ

เสร็จแล้วได้: หลักฐานว่ารุ่นส่งทำอะไรได้จริงและยังทำอะไรไม่ได้ บันทึก `project-closeout-phase-5-handoff.md` แล้วหยุด
