# Phase 6: ตรวจรับโมเดล ประโยชน์ และ Workflow

## คำสั่ง

อ่าน README, prediction-contract.md, Frozen Protocol และ Handoff Phase 1-5 ตรวจงานจริงแล้วทำเฉพาะ Phase 6 ไม่เริ่ม Phase 7

Phase นี้คือ Independent evaluation ไม่ใช่รอบค้นโมเดล/ปรับ threshold ให้ Test ผ่าน ห้ามนำ Test กลับไป Tuning หรือ Reference ถ้าแก้เชิงวิธีหลังเปิด Test ต้องประกาศว่าชุดนั้นใช้พัฒนาแล้วและต้องมีการประเมินใหม่ที่อิสระ

## อ่านก่อน

- Outcome dataset/training/inference/registry/API/UI ที่เพิ่มจริง
- `app/services/recommendation_utility_study.py`, `analysis_evaluation.py`
- `app/services/revision_comparisons.py`, `classification_acceptance.py`
- `tests/test_recommendation_utility_evaluation.py`, `test_revision_comparisons.py`
- รายงานก่อนหน้าและ Test access/usage ledger; ตรวจ Candidate hash/Protocol hash ก่อนเปิด Test

## งาน

### A. ตรวจความเป็นอิสระก่อนเปิดผล

- Candidate, feature extraction, preprocessing, Calibration, benchmark และ context selection Freeze แล้ว
- Test IDs/Channels/Transcript identities ไม่ทับ Fit/Tuning/Calibration หรือ Reference
- ตรวจ Sampling frame/สิทธิ์/Outcome observation/provenance ที่ต้องมีครบ โดยไม่ปรับเกณฑ์จากผล Test
- ยืนยันว่าชุดนี้ไม่เคยถูกใช้แก้ Features/ข้อความ/เลือก Candidate; ใช้ดูเพื่อแก้แล้วต้องเป็น Regression
- บันทึกเวลาปลด Test, actor, hashes และ evaluated sample IDs ไว้ใน Artifact
- ถ้าไม่มี Fresh/Independent data ให้รายงานว่าประเมินจริงยังค้าง ไม่ใช้ Fixture/ข้อมูลเดิมแทนแล้วเรียกผ่าน

### B. ประเมิน Candidate ที่เลือกไว้กับ Baselines

เปิด Test หนึ่งรอบด้วย Evaluation CLI:
- ไม่ Fit estimator/calibrator/benchmark ใดจาก Test แม้ Class balance เปลี่ยน
- ใช้ Constant/Metadata-only/Candidate รุ่นที่ตรึงไว้จาก Phase 3
- รายงาน Metrics/Gates/Calibration bins/Channel-bootstrap CI/Coverage ตาม Protocol เดิม
- แยก Phone/Camera/Laptop/format/context; Scope ที่ไม่มีการประเมินรองรับไม่ Qualified
- แสดงตัวอย่างผิด/ถูก/งดทำนายด้วยเกณฑ์เลือกตัวอย่างที่กำหนดก่อน ไม่หยิบเฉพาะเคสสวย
- Dataset selection bias และข้อจำกัดช่อง/เวลาต้องอยู่ใน Model card แม้ Metrics ผ่าน
- Outcome target นี้ไม่ใช่ยอดวิวหลังแก้คลิป อย่าเปลี่ยนชื่อ Report เป็น "พิสูจน์การเพิ่ม Engagement"

หากไม่ผ่าน ห้ามลอง Model ตัวที่สองบน Test แล้วเลือกตัวที่ดีกว่า ให้คงผล failed/experimental และแจ้งผู้ใช้

### C. ประเมินประโยชน์ของเหตุผลที่แสดง

ต่อยอดเครื่องมือ Utility study เดิม ไม่สร้างระบบคะแนนอีกชุดที่ตรวจย้อนกลับไม่ได้
ใช้ Utility protocol ที่ Freeze ไว้ใน Phase 1/5 ภายในวันที่ 15 ก่อนดูคะแนน หากยังไม่มีต้องบันทึกก่อนเริ่มประเมิน ห้ามลงวันที่ย้อนหลัง:
- ชุดกรณีอย่างน้อย 12 คลิปในขอบเขต หมวดละ 4 และ 3 คลิปนอกขอบเขต/Transcript ใช้ไม่ได้สำหรับตรวจ refusal แยก
- ผู้ประเมินจริงอย่างน้อย 3 คน เกณฑ์นี้เป็น Pilot โครงการ ไม่อ้างเป็นตัวแทนผู้ใช้ทั่วไป
- ใช้ผล Frozen เดียวกันเปรียบเทียบ 3 รูปแบบ: A Keywords เดิม, B คำแนะนำลงมือทำพร้อมหลักฐาน, C แบบ B พร้อมผลประเมิน Outcome/ข้อจำกัด
- สลับลำดับแบบกำหนด seed ไม่บอกว่ารูปแบบใด "ใหม่กว่า/ฉลาดกว่า"; ใช้ pseudonymous reviewer ID
- คะแนน 1-5: เกี่ยวข้อง, ไม่ซ้ำสิ่งที่พูดแล้ว, หลักฐานถูกต้อง, เข้าใจง่าย, นำไปทำได้; เพิ่มคำถามว่าตัวเลขหมายถึงอะไร/รับประกันยอดหรือไม่
- เกณฑ์ Pilot เริ่มต้น: Median ความเข้าใจง่ายและนำไปทำได้ >=4/5; อย่างน้อย 80% ของคำตอบตีความได้ว่าไม่รับประกันยอด และข้ออ้างหลักฐานแต่งขึ้นต้องเป็น 0
- เทียบ B กับ C แบบ Paired แสดงคะแนน/จำนวน/ความไม่แน่นอน ถ้า C ไม่ช่วยหรือทำให้เข้าใจผิดให้รายงาน ไม่อ้างชนะเพียงเพราะคะแนนเฉลี่ยต่างนิดเดียว
- รักษา Transcript/หลักฐาน/คำแนะนำให้ตรงกันระหว่าง Variants เพื่อไม่ให้ผลดีเกิดจากคนละคลิป

หากยังไม่มี Qualified Outcome model ให้ C เป็น Internal research prototype ที่บอกสถานะตรง และผล Utility ไม่นับเป็นหลักฐานว่าโมเดลพร้อม Production ห้ามใช้ค่าจำลองเป็นผลจากโมเดลจริง หรือให้อีก AI ทำคะแนนแทนผู้ประเมินแล้วเรียก Human evaluation

ถ้าผู้ประเมิน/คลิปไม่ครบให้รายงานจำนวนจริง งานเครื่องมือเสร็จได้แต่การประเมินประโยชน์ยังค้าง

### D. Acceptance แบบใช้งานจริง

ทดสอบบนบัญชี/ผลทดสอบที่แยก ไม่ปะปน Dataset:
1. Login -> Upload -> ASR -> accepted classification/Unknown gate -> recommendation -> assessment หรือเหตุผล abstain
2. Copy example -> เลือกแผน -> Save -> Ideas/history -> reopen
3. เปลี่ยน Dataset/Active outcome ใน Environment ทดสอบ -> reopen ผลเดิมยังคงเดิม
4. Upload revision -> content evidence -> version-compatible assessment หรือ cannot_compare ตามจริง
5. Admin preflight/train/status/model details -> reject unqualified activation
6. หาก Qualified จริงและผู้ใช้อนุมัติ: Activate ผ่าน Route จริง -> new analysis ใช้รุ่นใหม่ -> rollback ใช้งานได้
7. Restart -> jobs ไม่ค้าง, model/settings/snapshots ยังคงอยู่
8. API unavailable/timeout, save failure, ASR failure, missing metadata, artifact corrupt, rights withdrawn และ expired classifier
9. User A เปิด/แก้/จำลองผล User B ไม่ได้; Public ไม่สั่ง Train/Activate ได้
10. Browser 1440/1000/390 ไม่มี overflow/console error ในหน้าที่เปลี่ยน

ไม่มีคลิปใหม่จริงหรือ Active Classifier block ต้องรายงาน Live acceptance ค้าง ไม่ใช้ fixture ASR/forced category แทนแล้วบอกครบ

### E. ตัดสินรุ่นส่ง

ส่งตาราง PASS/FAIL/NOT RUN พร้อม Artifact link ต่อข้อ:
- Software/Regression
- Data rights/Retention
- Data independence/readiness
- Prediction qualification และแต่ละ Scope
- Human utility
- Live end-to-end
- Performance/Latency บนเครื่องจริงตามงบที่ Freeze ใน Protocol

แยก Qualification จาก Activation ต้องได้รับอนุมัติผู้ใช้จริงก่อนเปิด หากมีส่วนใดไม่ผ่านแจ้งผลกระทบและทางเลือกภายใน 17 ต.ค. อย่าปล่อยให้ Deadline เป็นเหตุให้ bypass

## Tests และส่งมอบ

รัน focused tests + relevant backend/Flutter regression + Web build + Browser acceptance บันทึก command/exit code/environment/hash จริง
อย่าใช้งานโปรแกรมที่ยังรัน Test ค้างแล้วจบเทิร์นโดยไม่รายงานผล

ส่ง Independent evaluation report, model card รุ่นรับตรวจ, utility raw ratings ที่ไม่เผยตัวตน/summary, Browser evidence, qualification decision และ `docs/implementation/outcome-prediction-phase-6-handoff.md`

Freeze release 17 ต.ค. รายงานข้อจำกัดจริง ไม่เริ่ม Phase 7 อัตโนมัติ

