# Handoff: ชุด Prompt Outcome Prediction วันที่ 8 ตุลาคม 2026

## สถานะ

เสร็จเฉพาะการจัดทำ Prompt/ข้อตกลง/แผนส่งวันที่ 19 ตุลาคม 2026 ยังไม่ได้เริ่มพัฒนา Phase 1-7 ในรอบงานนี้ ไม่แก้ Application code, Database, Scheduler หรือ Active models และยังไม่ได้ Train/Activate Outcome model

ชุดเอกสาร: [README](../prompts/outcome-prediction/README.md), [ข้อตกลงกลาง](../prompts/outcome-prediction/prediction-contract.md) และ Prompt Phase 1-7 ใน Directory เดียวกัน

## สิ่งที่ออกแบบ

- เป้าหมาย reference_relative_views_v1: ประเมินการอยู่ในกลุ่มยอดวิวเหนือค่ากลางของชุดอ้างอิงตามบริบท ไม่ใช่รับประกันการเพิ่มยอดวิวหลังทำตามคำแนะนำหรือทำนายยอด 7 วัน
- แยก Classification, Transcript evidence, Descriptive comparison และ Outcome model
- Label จากสถิติจริง/Benchmark เฉพาะ Fit; Split ตาม Channel/Identity; Calibration อิสระ; Baselines และ Independent evaluation
- แสดงผลผ่าน Gate เท่านั้น รักษาผลเก่า/Unknown/ข้อมูลที่ประเมินไม่ได้ และไม่ใช้ Scenario เป็นข้อพิสูจน์เชิงเหตุและผล
- ผูกงานกับบริการ FastAPI/SQLAlchemy/Flutter/Recommendation/Revision/Admin เดิม ไม่เพิ่ม Console/แพลตฟอร์ม/โมเดลเสียเงิน
- กำหนด Handoff/Tests/Artifact ต่อ Phase และไม่ให้เริ่ม Phase ต่อไปอัตโนมัติ
- หยุดเพิ่มฟีเจอร์ 17 ต.ค., ซ้อม 18 ต.ค., ส่ง 19 ต.ค. พร้อมจุด No-go ที่ต้องแจ้งล่วงหน้า

## การตรวจที่ทำในงานเอกสารนี้

- อ่านโค้ดบริการและโครงสร้างที่เกี่ยวข้อง รวม Prompt/รายงานเดิมเพื่อไม่สั่งสร้างสิ่งที่มีแล้วซ้ำ
- ตรวจ Path จริงที่อ้างถึง 39 รายการ: พบครบ, คำสั่ง PowerShell exit 0
- ตรวจเอกสาร Prompt 9 ไฟล์: UTF-8 อ่านได้, fenced code blocks สมดุล, local Markdown links 8 จุดไม่ขาด, แต่ละ Phase มี Handoff ของตน; exit 0
- ทบทวน Scope/Probability semantics/Guardrails/วัน Freeze/การแยก Calibration กับ Test ให้สอดคล้องกัน
- ตรวจเอกสารทางการ scikit-learn ด้าน Calibration/Leakage และ YouTube ด้าน Derived metrics; ใส่แหล่งอ้างอิงใน README
- ไม่รัน Backend/Flutter tests หรือ Browser เพราะไม่มีการแก้โปรแกรมในงานนี้ การตรวจเอกสารไม่ใช่การตรวจรับ Software/Model

ตัวเลข DB ใน README เป็น Baseline ที่บันทึกไว้ก่อนจัด Prompt ไม่ใช่การ Audit DB ใหม่ในขั้นตรวจเอกสาร ต้องรัน Read-only audit อีกครั้งใน Phase 1

## Dependency ที่ต้องตามต่อ

1. ยืนยันสิทธิ์และเงื่อนไขการใช้ API Data ทำ Derived metrics/ML/การเก็บข้อมูลก่อนฝึกหรือให้บริการจริง ไม่มีการยืนยันแทนเจ้าของโครงการในงานนี้
2. จำนวนคลิป/ช่อง/รูปแบบ/Observation ที่พร้อมจริงอาจต่ำกว่าจำนวน Dataset rows ต้องตรวจตาม Protocol
3. Collector เดิมอาจไม่เก็บสถิติ Holdout ต้องตรวจและใช้ Manifest-driven collection ที่ไม่เปิด Holdout เป็น Reference
4. สถานะ Classifier แบบ presentation_only ที่ตรวจรอบก่อนหมดอายุเป็นความเสี่ยงต่อ Live Analyze ต้องตรวจซ้ำ ไม่ต่ออายุหรือข้าม Gate อัตโนมัติ
5. ต้องมี Independent evaluation และผู้ประเมินจริง ไม่สามารถรับรองว่าผ่านเพียงเพราะส่ง Code ทัน
6. Worktree Git pointer ที่รายงานเดิมระบุว่าเสียต้องตรวจใหม่ก่อนอ้าง Commit; ห้ามซ่อม/Reset โดยพลการ

## ขั้นตอนถัดไป

ผู้ใช้มอบหมาย Outcome Prediction Phase 1 ด้วยข้อความใน README ให้ Agent อ่านข้อตกลงกลางและไฟล์ Phase 1 แล้วตรวจความพร้อมก่อน ไม่ Train จากจำนวน Dataset rows ที่เห็นทันที
