# Closeout Phase 2: ปิด Analysis ให้สร้างคำแนะนำได้จริง

อ่าน README, Phase 1 Handoff, acceptance report และ Handoff/review ของ Recommendation Phases 5-7 ก่อนแก้ ห้ามเขียนระบบคำแนะนำใหม่ทับของเดิม

## Gate ก่อนเริ่ม

หากยังไม่มีโมเดลที่ผ่าน scope policy และไม่มีข้อมูลสำหรับประเมิน ให้ทำ diagnostics/readiness/tests/UX ส่วนที่ไม่ติด และรายงานว่า positive recommendation ยัง blocked ห้ามสลับไปรับผลดิบ/ใช้กฎเก่า/ลด threshold/แต่ง Unknown data

งานแบ่งเป็น 2A ข้อมูลและโมเดล, 2B Transcript/คำแนะนำ, 2C flow จริง ทำครบจึงเรียก Phase นี้ว่าผ่าน

## 2A ข้อมูลและโมเดล

1. ตรวจ candidate models จาก Phase 1 ก่อนฝึกใหม่ ถ้ามีตัวผ่านทุกเกณฑ์จริงเสนอให้ผู้ใช้ Activate ผ่าน workflow เดิมพร้อมก่อน/หลังและวิธีย้อนกลับ ห้ามเลือกด้วย Test accuracy ที่สูงที่สุด
2. ถ้าต้องเก็บเพิ่ม ใช้ข้อมูลจริงที่ผู้ใช้ส่งและ workflow import/review เดิม ตรวจ taxonomy, provenance, transcript duplicate, channel split และคลิปที่สงวนไว้ ไม่ auto-approve โดยไม่ตรวจ
3. เก็บ Unknown Validation แยกจาก Unknown Test และ Train/Reference ใช้ Validation เลือกเกณฑ์ตาม protocol เดิม ไม่ค่อย ๆ ปรับจากผล Test
4. รัน Train/benchmark ผ่าน workflow เดิมหลังประกาศขอบเขตทรัพยากรและพร้อมข้อมูล เก็บ artifact/checksum/params/versions/metrics ของทุกโมเดล ไม่เพิ่มการทดลอง embedding/โมเดลใหญ่รอบใหม่เพื่อไล่คะแนนก่อนส่ง
5. รายงาน classification ต่อหมวด, confusion matrix, recall/F1, Unknown rejection แยกกัน รวม n และจำนวนช่อง หากไม่ผ่านให้คงว่าไม่ผ่าน ไม่แก้ qualification record
6. Activate เฉพาะรุ่นผ่านเกณฑ์และได้รับการยืนยัน ยืนยันงานใหม่ใช้รุ่นนั้นจริง งาน/ผลเก่าคง snapshot รุ่นเดิม

## 2B ถอดเสียงและสร้างคำแนะนำ

1. ตรวจเสียง/Raw Transcript เทียบข้อความที่คนตรวจในคลิปตัวอย่าง แยก ASR error ออกจาก classifier/matcher error ไม่รายงาน WER โดยไม่มี reference transcript ที่คนตรวจ
2. ใช้เฉพาะ Whisper รุ่นติดตั้งพร้อมตาม setting; อย่าดาวน์โหลดรุ่นใหญ่หรือสลับ global default โดยไม่ยืนยัน เก็บค่าที่ใช้จริงกับทุกผล
3. รักษา raw/cleaned/segments และ offset/Timestamp จริง Normalize เฉพาะ alias ที่มีหลักฐาน ไม่แก้ Transcript ทั้งก้อนให้เข้าหมวด
4. เปลี่ยนชื่อผลใหม่จากข้อความ ASR อ่านยากเป็นชื่อไฟล์ที่ sanitize/ชื่อผู้ใช้ตาม pattern เดิม ไม่ใช้ชื่อไฟล์เป็น feature ทายหมวดหรือหลักฐานคำแนะนำ และไม่เขียนผลเก่าทับ
5. ตรวจ output ที่มีอยู่ให้แยกชัด: สิ่งที่พบทั้งคลิป / สิ่งที่พบช่วงต้น / หัวข้อมาตรฐาน / ประเด็นควรเพิ่ม / ตัวอย่างเปิดคลิป / ความยาวอ้างอิง
6. คำแนะนำหลัก 2-3 ข้อที่เกี่ยวข้องจริง: สิ่งที่พบ, สิ่งที่เสนอ, วิธีทำ, ตัวอย่างประโยค, เหตุผล/แหล่งอ้างอิง ไม่เพิ่มจำนวนครั้งที่พูด keyword เป็นเป้าหมาย
7. ไม่แนะนำซ้ำแนวคิดที่พูดแล้วแม้คำพ้องต่างกัน ไม่แต่งสเปก/ผลทดสอบ/ความสัมพันธ์เป็นเหตุเป็นผล หากไม่มีข้อที่เหมาะสมให้ empty state ที่ถูกต้อง ไม่บังคับมี 3 ข้อ
8. Hook recommendation เป็นข้อเสนอ ไม่ใช่อ้างว่าคลิปอ้างอิงพูดใน 60 วินาทีถ้าไม่มี timestamp; ข้อเสนอไม่ซ้ำแนวคิดที่พบใน hook ผู้ใช้ และไม่กล่าวอ้างว่าเปิดคลิปแบบนี้จะเพิ่มยอดแน่นอน
9. Duration ต้องผ่าน metadata/sample/comparability contract เดิม (baseline ขั้นต่ำ 10); แสดง median/percentile/n/ข้อจำกัด หรือ insufficient evidence ไม่เอาความยาว upload สูงสุดมาเป็นความยาวแนะนำ
10. แยก Unknown ที่รับผลไม่ได้, เสียงถอดไม่ได้, reference ไม่พอ, และไม่มีประเด็นเพิ่ม ไม่รวมเป็นข้อความว่างเดียว

## 2C ทดสอบวงจรจริง

- อัปโหลดคลิปที่ยอมรับหมวด -> สร้างข้อแนะนำ -> เปิดหลักฐาน -> คัดลอกประโยค -> เลือกนำไปปรับ -> บันทึก -> เปิดกลับ -> restart แล้วตรวจค่าคงเดิม
- เมื่อมีฉบับแก้ไขจริง: อัปโหลดเชื่อม parent/plan -> ดูข้อความและเวลาที่เปลี่ยน -> เปิดต้นฉบับ; ไม่ใช้การอัปโหลดไฟล์เดิมซ้ำเป็นหลักฐานว่าปรับเนื้อหาสำเร็จ
- ถ้าไม่มีคลิปฉบับใหม่ ตรวจ software contract ด้วย fixture แยกแล้วระบุ live revision flow ยังตรวจไม่ได้
- ทดสอบ Unknown/ASR fail/ข้อมูลไม่พอ, double submit, retry, save fail, ไม่ใช่เจ้าของ; ไม่แจ้งสำเร็จเมื่อบันทึกล้มเหลว
- คลิป Phone เดิมเป็น regression เท่านั้น จัด fresh evaluation ตาม protocol เดิม ไม่ตั้งเกณฑ์ 3 คลิปว่าพิสูจน์ความแม่นแล้ว

## โค้ดเริ่มอ่าน

- `app/routes/analyze.py`, `app/services/ai_pipeline.py`, `app/services/classification*.py` (ใช้การค้นไฟล์ ไม่ส่ง wildcard เป็น path บน Windows)
- `app/services/recommendation.py`, `recommendation_evidence.py`, `actionable_recommendations.py`, `saved_recommendations.py`, `topic_comparisons.py`
- `app/services/persistence.py`, `contents.py`, `clip_revision_plans.py`, `revision_comparisons.py`
- `frontend_flutter/lib/screens/upload_screen.dart`, `result_screen.dart`, `history_screen.dart` และ widgets/models/repositories ที่เกี่ยวข้อง
- tests ของ full clip/classification acceptance/evidence/actionable/plan/revision/settings และ Flutter tests ที่ตรงงาน

## เกณฑ์ผ่าน

- มีผลคลิปในขอบเขตที่ผ่าน Active Model + acceptance จริง และให้ข้อแนะนำที่ตรวจกลับถึง Dataset/ข้อความจริงได้ ไม่ใช่แค่ `job=completed`
- Unknown ยังคง fail closed; ผลเก่าไม่เปลี่ยน; ไม่มีการรั่วข้อมูลส่วนตัวหรือข้อมูล Test เข้า reference
- คำแนะนำ/Hook/Duration แสดงได้ตามหลักฐาน และแยกเคสที่ต้องงดอย่างถูกต้อง
- Positive flow, persistence และ failure path มีหลักฐานแยก live/fixture พร้อมรุ่นที่ใช้
- ถ้าขาดข้อมูลหรือโมเดลไม่ผ่าน ให้ Handoff เป็นบางส่วน/ไม่ผ่านพร้อม blocker ไม่ประกาศเสร็จ

เสร็จแล้วได้: แกน AI ที่ใช้ช่วยปรับคลิปได้จริงและอธิบายเหตุผลได้ บันทึก `project-closeout-phase-2-handoff.md` แล้วหยุด ไม่เริ่มเก็บแพลตฟอร์มใหม่
