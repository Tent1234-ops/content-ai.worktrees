# Phase 7: ส่งงานและเตรียมพรีเซนต์

## คำสั่ง

อ่าน README, prediction-contract.md และ Handoff ทุก Phase โดยเฉพาะ Phase 6 ทำเฉพาะการส่งมอบ Outcome Prediction รุ่นวันที่ 19 ตุลาคม 2026

ไม่เพิ่มโมเดล/ฟีเจอร์/เปลี่ยนเกณฑ์ ไม่เริ่ม Phase 8 อัตโนมัติ แก้เฉพาะบั๊กที่ขวางส่งพร้อม Retest และเพิ่ม Release revision หากมีการเปลี่ยนไฟล์ที่ผ่านตรวจแล้ว

## งาน

### A. Release manifest ที่เปิดซ้ำได้

สร้างรายการ:
- Source version/commit ถ้า Git ใช้ได้ หรือ file-hash manifest หาก Git pointer ยังเสีย ห้ามซ่อม/reset เอง
- Backend/Flutter/Python/dependency versions และ commands ที่เครื่องนี้รันได้จริง
- DB migration/schema revision, backup path/checksum และ tested restore procedure
- Active classifier/outcome IDs, status, artifact hashes, target/protocol/feature/calibration versions
- Dataset/split/observation cutoff hashes, rights status และ Retention/withdrawal handling
- ขอบเขต Qualified จริง ขอบเขตที่งดทำนาย และ known limitations
- API/Web URLs และการตั้งค่า Environment เฉพาะชื่อ ไม่ใส่ Secret values

สำรองข้อมูลตามสิทธิ์และใช้พื้นที่ที่ผู้ใช้อนุญาต ไม่แพ็ก Private transcripts/User videos/credentials รวมเป็นไฟล์เผยแพร่โดยไม่ยินยอม
Restore test ใช้ DB/Directory แยก ไม่ overwrite ระบบจริง

### B. คู่มือเปิดระบบและ Demo script

เขียนคู่มือภาษาไทยที่ทำตามได้:
1. ตรวจ prerequisite และ environment config
2. เปิด Backend/Frontend โดยไม่มี Terminal เด้งรบกวนเมื่อเป็น Background helper บน Windows
3. ตรวจ health/model readiness โดยไม่ Train ทุกครั้งที่เปิด
4. Login/Upload/อ่านผล/เปิดหลักฐาน/Save/reopen/revision
5. Admin ตรวจ preflight/train run/metrics/qualified status และ Activate/Rollback ด้วย Gate จริง
6. เมื่อ Internet/API/ASR/โมเดลไม่พร้อมให้ดูอะไรและแก้อย่างไร ไม่สร้าง fallback percentage
7. ปิดบริการและสำรองโดยไม่ทำลายข้อมูล

เตรียมตัวอย่าง Demo จากผลจริง:
- กรณีในขอบเขตที่ได้คำแนะนำพร้อมหลักฐาน
- กรณีข้อมูลน้อย/Unknown ที่งดประเมินอย่างถูกต้อง
- กรณีผลเปรียบเทียบไม่ชัด/ลบ หากมีจริง
- ฉบับเดิม/ฉบับแก้ที่แสดงเฉพาะสิ่งตรวจพบจริง
- หน้า Admin เปรียบ Baseline กับ Candidate และเหตุผลที่ผ่าน/ไม่ผ่าน

Offline fallback ใช้ผลที่ Save จริงพร้อมเวลา/Version และบอกว่าเป็นผลบันทึก ไม่แสดงเหมือน API/ASR กำลังวิเคราะห์สด ห้ามคลิป Demo ที่ใช้แก้บั๊กมาเรียก Fresh Test

### C. เอกสารอธิบายให้อาจารย์เข้าใจ

จัด `docs/presentation/outcome-prediction/` อย่างกระชับ:
- `README.md`: ลำดับอ่านและสถานะจริง
- `algorithm-explained.md`: ภาพรวมและตัวอย่างสูตร
- `evaluation-and-limitations.md`: ผลจริง/ข้อจำกัด/สรุปเกณฑ์
- `demo-and-questions.md`: ขั้นตอน Demo และ Q&A

แผนผังที่ต้องมี:
```text
วิดีโอผู้ใช้ -> ASR -> Classifier/Unknown gate -> Transcript concepts
                                                   |
ชุดอ้างอิง + Observations -> Frozen cohort/labels -> Outcome model
                                                   |
              คำแนะนำลงมือทำ + หลักฐาน + ผลประเมินที่ผ่าน Gate
                                                   |
                           บันทึก -> ปรับคลิป -> ตรวจเนื้อหาอีกครั้ง
```

อธิบายชัด:
- Training class label กับ Outcome label ต่างกันอย่างไร
- Dataset แต่ละบทบาทใช้/ห้ามใช้อะไร
- Views ณ เวลาเก็บ, Median, Features, Logistic Regression, Calibration, Baseline, Test คืออะไร
- เลข Probability หมายถึงเหตุการณ์ไหน Population ไหน และไม่หมายถึงอะไร
- ทำไมไม่ใช้ยอดสะสมแทนความเร็วเติบโต หรืออ้างว่าเป็นยอด 7 วัน
- ทำไมเมื่อข้อมูลไม่พอระบบเลือกไม่ทำนาย
- การพบคำซ้ำไม่ได้แปลว่าเนื้อหาดีขึ้น
- UI/Endpoint/DB table/Artifact จริงที่รองรับแต่ละขั้น พร้อมลิงก์ไฟล์จริง ไม่อธิบายสถาปัตยกรรมที่ยังไม่ได้ทำ

Q&A ต้องตอบคำถามสำคัญ:
"รู้ได้อย่างไรว่าทำตามแล้ววิวเพิ่ม?"
คำตอบต้องตรงว่า รุ่นนี้ประเมินความสัมพันธ์/โอกาสอยู่กลุ่มเป้าหมายจากข้อมูลอ้างอิงและตรวจประสิทธิภาพการทำนาย ไม่ได้พิสูจน์ผลเชิงเหตุและผลของคำแนะนำ ต้องทดลองกับผู้ใช้/ติดตาม Outcome ที่ออกแบบเหมาะสมต่อไป

ห้ามพูดว่า Accuracy/Confidence 80% หมายถึง 80% ที่ผู้ใช้จะดังขึ้น

### D. ซ้อมและตรวจส่ง

- วันที่ 18 ซ้อมเปิดตั้งแต่ระบบปิดจนจบ Workflow อย่างน้อยหนึ่งรอบ
- ตรวจ Logs/Network/Quota ที่ต้องใช้จริงและไฟล์ Demo อ่านได้
- เวลา/model status ไม่หมดอายุระหว่าง Demo โดยใช้ Workflow อนุมัติที่ถูกต้อง ไม่ต่อเวลา Presentation bypass เงียบ ๆ
- ตรวจว่าเอกสาร/ภาพตรงกับรุ่นที่จะส่ง ไม่เอารูป Fixture qualified มาแทน Live experimental
- เปิดผลเก่าและรีสตาร์ตแล้วข้อมูลยังอยู่ตามสิทธิ์
- วันที่ 19 ตรวจ Release hash/health/URLs/readiness ครั้งสุดท้าย ไม่ Retrain นาทีสุดท้าย

## เกณฑ์จบ

- ส่งแพ็กเกจ/Manifest/Backup ที่ตรวจได้และคู่มือที่ทำตามบนเครื่องจริงแล้ว
- มีผล Acceptance และคำตัดสินแยก Software, Data rights, Prediction, Utility, Live workflow
- ผู้ใช้เข้าใจอัลกอริทึมและตอบข้อจำกัดได้ มีผลจริงให้ตรวจไม่ใช่แค่กราฟสวย
- ไม่มี Secrets/Private data ที่ไม่อนุญาตในเอกสารส่ง
- งานที่ไม่ผ่านยังอยู่ในรายการค้าง ไม่ถูกลบเพื่อให้ดูจบ

ส่ง `docs/implementation/outcome-prediction-phase-7-handoff.md` พร้อม Release paths, URLs, commands, rollback และสรุป Ready to submit / Ready with explicitly agreed limitations / Not ready พร้อมเหตุผล

การส่งเอกสารครบไม่เปลี่ยนสถานะ Prediction ที่ไม่ผ่านให้เป็นผ่าน หากยังไม่ผ่านต้องให้ผู้ใช้รับทราบและตกลงขอบเขตการนำเสนออย่างตรงไปตรงมา

