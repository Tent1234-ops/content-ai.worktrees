# การประเมินและข้อจำกัด

## คำตัดสินจาก Phase 6

คำตัดสิน Outcome Prediction ปัจจุบันคือ `NO_GO` สำหรับการแสดง Probability จริงและการ Activate โมเดล คำตัดสินนี้ไม่ทำให้ Recommendation เดิมหยุดทำงาน แต่ป้องกันไม่ให้ระบบอ้างตัวเลขที่ยังไม่มีหลักฐานรับรอง

| ด้าน | ผลจริง ณ 9 ต.ค. 2026 | ความหมาย |
|---|---|---|
| Software regression | ผ่าน | Backend 562 tests, Flutter 164 tests, Analyze/Web build และ Browser acceptance ผ่านใน Phase 6 |
| Data rights/retention | ไม่ผ่าน | ยังไม่มีหลักฐานยืนยันสิทธิ์ Training/Serving และนโยบายเก็บ/ถอนข้อมูล |
| Outcome data readiness | ไม่ผ่าน | 308 แถวเป้าหมาย แต่ Structurally ready 0 และ Training allowed 0 |
| Fresh Independent Test | ยังไม่เปิด | มี 0 ตัวอย่าง จึงไม่มี Metric จริงให้รายงาน |
| Outcome model | ไม่มี | Registered 0, Active 0, Qualified 0 |
| Human utility | ยังไม่ทำ | Reviewer จริง 0 คน Rating 0 ค่า Missing ยังคงเป็น `null` |
| Live Outcome workflow | ยังไม่ทำ | ไม่มี Qualified model จึงห้ามสร้าง Positive live result |

ไม่ได้นำ Synthetic fixture 62% มาเป็นผลโมเดล ไม่ได้สร้าง Human rating แทนคน ไม่ลดขั้นต่ำข้อมูล และไม่ได้เปิด Independent Test ก่อน Gate พร้อม

## เกณฑ์ที่ต้องผ่านก่อนเปิดใช้งาน

1. ยืนยันสิทธิ์ใช้ Transcript และสถิติ YouTube สำหรับ Training และ Serving พร้อม Retention/Withdrawal policy
2. เติมข้อมูลโครงสร้างที่ขาด เช่น รูปแบบคลิป แหล่งที่มาของ Sampling frame และ Snapshot ตาม Cutoff
3. แยก Fit/Tuning/Calibration/Fresh Test ตาม Channel group และผ่านขั้นต่ำใน Protocol
4. Freeze Dataset manifest, Split manifest, Feature schema, Model, Calibrator, Baseline และ Qualified scope
5. เลือก Candidate ด้วย Validation โดยไม่ดู Test
6. เปิด Independent Test หนึ่งครั้ง ตรวจ Brier/Calibration/Coverage/Scope และช่วงความไม่แน่นอน
7. Activate ได้เฉพาะรุ่น `qualified` ที่ Backend ตรวจ Hash และสิทธิ์ครบ
8. ทำ Utility study ด้วยคนจริงอย่างน้อย 3 คนตาม Protocol

## ข้อจำกัดที่ต้องพูดตรง ๆ

- ข้อมูลอ้างอิงเป็น Convenience sample ของโครงการ จึงไม่แทน YouTube ทั้งแพลตฟอร์ม
- Target เป็นการเทียบยอดวิวสะสมกับค่ากลาง ไม่ใช่การทำนายยอดวิว 7 วันและไม่ใช่ Growth
- ความสัมพันธ์ระหว่าง Topic กับกลุ่มยอดวิวสูงไม่พิสูจน์ว่า Topic เป็นสาเหตุ เพราะคุณภาพการถ่าย ช่อง เวลาโพสต์ Thumbnail และปัจจัยอื่นอาจเกี่ยวข้อง
- โมเดลจำแนกหมวดรุ่น 43 เป็น `presentation_only`, หมดช่วงรับรอง และไม่ผ่าน Gate สำหรับผลที่ยอมรับได้
- หน้าเว็บรองรับ YouTube และ Google แต่ `/health` อาจเป็น `degraded` เพราะ Provider TikTok เก่าที่ยังถูกตรวจหลังบ้านผิดพลาด ไม่ควรอ้าง TikTok เป็นความสามารถของรุ่นส่งมอบ
- ผล Recommendation ที่ใช้สาธิตเป็นผลบันทึกในอดีต ไม่ใช่ผลทดสอบใหม่และไม่มี Outcome Probability
- มี Revision plan 1 รายการ แต่ยังไม่มี Revision comparison จึงห้ามอ้างว่าวงจรเทียบคลิปแก้ไขสำเร็จจากข้อมูลจริง
- การซ้อมวันที่ 18 และตรวจวันส่งวันที่ 19 ตุลาคมยังเกิดขึ้นไม่ได้ ณ วันที่จัดทำ 9 ตุลาคม จึงบันทึกเป็นงานค้าง ไม่ลงวันที่ย้อนหลัง

## สถานะส่งมอบ

ตัว Software และเอกสารส่งมอบพร้อมสำหรับซ้อมโดยเปิดเผยข้อจำกัด แต่ Outcome Prediction ยังไม่พร้อมในฐานะโมเดลที่ผ่านการรับรอง หากเจ้าของโครงการยอมรับการนำเสนอแบบ "ความสามารถถูกสร้างครบแต่ Fail-closed เพราะข้อมูลจริงยังไม่ผ่าน" ให้บันทึกการยอมรับนั้นแยกต่างหาก ห้ามแก้สถานะข้อมูลหรือ Metric เพื่อให้ดูว่าผ่าน

หลักฐานตัวเลขอยู่ใน `artifacts/outcome-prediction/phase-6/20261009T123558Z-final-evaluation` และ Release manifest ล่าสุดตาม `artifacts/outcome-prediction/phase-7/latest-release.txt`
