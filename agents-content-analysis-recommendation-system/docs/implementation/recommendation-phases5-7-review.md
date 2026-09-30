# Post-Implementation Review: Recommendation Phases 5-7

วันที่ตรวจ: 2026-09-30

ตรวจเทียบกับ Prompt ของทั้งสาม Phase และแก้โค้ดจริง ไม่ได้เริ่ม Phase 8, ฝึก/Activate โมเดล, เก็บข้อมูลจาก Provider หรือสร้างคะแนนผู้ประเมินจริงแทนคน

## Findings ที่แก้แล้ว

### P1: เส้นทางวิเคราะห์ปกติล้มจากตัวแปรของ Revision

`analyze_video_job()` เรียก `update_revision_job(db, comparison_id, ...)` ทั้งที่ไม่มี `comparison_id` ในเส้นทาง `/analyze` จึงล้มหลังถอดเสียง แก้เป็นอัปเดตสถานะ Job ปกติ และเพิ่ม test เรียก Worker นี้ตรง ๆ

โค้ด: `app/routes/analyze.py`, `tests/test_revision_comparisons.py`

### P1: Revision Worker ทำงานซ้ำและการเริ่ม Backend กระทบงานที่ยังรัน

- Worker เดิมเปลี่ยนสถานะเป็น running โดยไม่ยึดสิทธิ์งานแบบ atomic จึงถอดเสียง/สร้างผลลูกซ้ำได้
- เพิ่ม conditional UPDATE จาก queued ไป running, ตรวจรหัส attempt ทุกครั้งที่รับงาน/บันทึก และคืนผลเดิมเมื่อได้รับงาน completed ซ้ำ
- Retry เปลี่ยน attempt แบบ conditional UPDATE; Worker เก่าไม่สามารถใช้ attempt ใหม่ได้
- ตรวจ fingerprint ของแผนก่อน ASR ป้องกันแผนในฐานข้อมูลถูกเปลี่ยนหลังรับงาน
- Startup เดิมเปลี่ยนงาน in-process ทุกตัวเป็น interrupted แม้อีก Backend ยังทำอยู่ เพิ่ม Host/PID/เวลาเริ่ม Process ใน settings snapshot และตรวจเจ้าของด้วย `psutil`
- ผลเก่าที่ไม่มีข้อมูลยืนยันการจำแนกหมวดไม่ถูกถือว่ายอมรับโดยปริยาย
- แก้การเทียบบริบทที่นำ offset ของ Cleaned Transcript ไปใช้กับ Raw Transcript และเก็บเวอร์ชัน Context template/Matcher ที่ใช้จริง

โค้ด: `app/services/revision_comparisons.py`, `app/routes/analyze.py`

### P1: Phase 7 เริ่มประเมินจริงไม่ได้แม้การตั้งค่าเหมือนเดิม

Context lock เดิมรวม `settings.captured_at` ซึ่งเปลี่ยนทุกครั้งที่อ่าน และเปรียบเทียบ tuple กับ list หลัง JSON round trip แก้ให้ตัดเฉพาะเวลาที่อ่านออกและ normalize ผ่าน JSON โดยค่าที่มีผลต่อการวิเคราะห์ยังถูกตรวจครบ

เพิ่ม Cutoff เดียวที่ส่งถึง Recommendation และ fingerprint ประวัติ `reference_video_statistics` ในช่วงที่ใช้งานจริง รวมถึงจำนวน Keyword และหมวดที่พร้อมใช้งาน ตรวจ Context ก่อนและหลัง Prediction หากเปลี่ยนจะไม่สร้าง Packet ที่นำไปให้คะแนนได้

โค้ด: `app/services/recommendation_utility_study.py`, `scripts/evaluate_analysis.py`, `app/services/recommendation.py`

### P1: ผลประเมินอาจดูดีกว่าหลักฐานที่มีจริง

- เคส ASR/Analysis ล้มเหลวเดิมถูกสร้างเป็น Variant ว่างให้ผู้ประเมินให้คะแนนงดแนะนำ แก้ให้เก็บ Failure ในรายงานโดยไม่มี Variant สำเร็จและไม่ส่งให้ให้คะแนน Utility
- Utility เดิมมีผู้ประเมินรวมสามคนก็พอ แม้แต่ละคลิปได้คะแนนคนเดียว แก้เป็นอย่างน้อยสามชุด A/B/C ที่ครบต่อคลิป พร้อมรายงานคลิปที่ขาด
- Unknown ที่วิเคราะห์ล้มเหลวทั้งหมดไม่สามารถทำให้ Classification ผ่านเพียงเพราะ false acceptance เป็นศูนย์
- รับคะแนนได้ต่อเมื่อมี Pre-review, ยืนยันดูคลิป, เหตุผล, และคะแนนตรงประเภท ไม่รับ boolean เป็นคะแนน 1
- ตรวจ payload hash จริง ไม่เพียงเทียบช่อง hash ที่ผู้ส่งกรอกมา
- Critical flag ต้องมีผู้ตัดสินและเหตุผลก่อนปิดเรื่อง; เพิ่ม `test_data_leakage`
- `evaluation_complete` ต้องมีคะแนนครบตาม Allocation รวมเคส Unknown และไม่มีแถวปฏิเสธค้าง

โค้ด: `app/services/analysis_evaluation.py`, `scripts/evaluate_analysis.py`

### P2: การกระจายลำดับและแบบประเมินยังไม่ตรงการทดลอง

- เปลี่ยนจากสมดุลรวมอย่างเดียวเป็น Latin rotations: Pilot 12 คลิป/3 คน ได้หกลำดับอย่างละสองครั้งต่อผู้ประเมิน และตำแหน่งแรกกระจาย A/B/C ต่อคลิป
- B/C แสดงเงื่อนไขสินค้าเหมือนกัน C เปิดดูข้อความอ้างอิง Source URL/Video ID/แถวข้อมูล/วันเก็บสถิติ และกลุ่มเปรียบเทียบได้ รวมผลต่างติดลบ
- เพิ่ม Rubric ภาษาไทย 1/3/5 และระดับ 2/4, เตือนข้อจำกัด Carryover/การปกปิดที่ไม่สมบูรณ์
- เก็บฉบับร่างหลังส่งแต่ละขั้น กู้คืนหลังรีเฟรชได้ และตรวจคะแนน Missed opportunity ก่อนดาวน์โหลด
- Clip คนละไฟล์จาก Creator ใหม่คนเดียวกันไม่ถูกตีเป็นวิดีโอซ้ำ แต่ยังห้าม Creator/Channel ที่ใช้พัฒนารั่วเข้าชุดทดสอบ

โค้ด: `app/services/utility_review.html`, `app/services/analysis_evaluation.py`

### P2: ประวัติหลักฐานและ Artifact ตรวจย้อนหลังไม่พอ

- Phase 5 เก็บ Transcript ของทั้งกลุ่มพูดถึงและไม่พูดถึงไว้ใน Snapshot เดียวครั้งละชุด ไม่พึ่ง Dataset ปัจจุบันเมื่อต้องย้อนตรวจ
- ไม่ใช้สถิติของ Video ID เก่า หลัง Dataset row ถูกเปลี่ยนเป็นคลิปอื่น
- ไม่ใช้ Metric version ที่ไม่รู้จัก หรือยอดวิวติดลบเป็นข้อมูลเปรียบเทียบ
- Growth ไม่เชื่อมผ่านจุดเปลี่ยนนิยามยอดวิวหรือ Counter correction ที่ภายหลังฟื้นกลับมา
- Evidence audit ตรวจ Timestamp กับ Segment จริง ไม่ยอมรับเพียงเพราะข้อมูลมีชนิด dict/list
- จอง Output directory ก่อน ASR, เก็บความคืบหน้ารายคลิป และรักษาเคสที่ถูกตัดออกไว้ในรายงาน
- ตรวจ Artifact integrity ทั้ง Prepared/Run ก่อนใช้ต่อ และตรวจประวัติ Transcript จาก Evaluation เดิมด้วย

โค้ด: `app/services/topic_comparisons.py`, `scripts/evaluate_analysis.py`, `app/services/recommendation_utility_study.py`

## Verification

- Backend ทั้งระบบ: `python -m unittest discover -s tests -p "test_*.py" -q` ผ่าน **465 tests** รอบสุดท้าย ก่อนหน้านี้พบ assertion เวอร์ชัน Policy เก่าใน `test_dataset_readiness.py` และแก้เป็น v2 แล้ว
- Flutter ที่เกี่ยวข้อง: 21 tests ผ่าน (`revision_comparison`, `recommendation_evidence`, `clip_revision_planner`, `actionable_advice`)
- Browser: ผ่านที่ 1,000 และ 1,440 px ทั้งเล่นวิดีโอ, Pre-review, แสดงเงื่อนไข/หลักฐาน/ผลต่างติดลบ, กู้ฉบับร่าง, ส่งออก JSON และตรวจรับกลับด้วย Python; ไม่มี horizontal overflow หรือ JavaScript error
- Browser artifacts: `artifacts/browser/utility-review-audit-20260930-v2/`
- คะแนนใน Browser artifacts และ Tests เป็น **Synthetic software fixtures** ไม่ใช่คนหรือคลิปทดสอบจริง และไม่อยู่ใน `artifacts/evaluation/`

คำสั่งตรวจซ้ำเฉพาะส่วน:

```powershell
python -m unittest tests.test_dataset_readiness tests.test_revision_comparisons tests.test_topic_comparisons tests.test_recommendation_utility_evaluation tests.test_recommendation_phase_review -q
```

จาก `frontend_flutter/`:

```powershell
flutter test --no-pub --concurrency=1 test/revision_comparison_test.dart test/recommendation_evidence_test.dart test/clip_revision_planner_test.dart test/actionable_advice_test.dart
```

Browser ต้องเลือก Output directory ใหม่เสมอ:

```powershell
node scripts/browser/verify_utility_review.cjs artifacts/browser/utility-review-next-run
```

มี warning เดิมของ SWIG/น้ำหนัก Sentence Transformer และข้อความ failed จาก Negative test ที่ตั้งใจจำลองข้อผิดพลาด ไม่ใช่ test failure ผลลัพธ์สุดท้ายเป็น `OK`

## ข้อจำกัด / งานค้าง

1. ยังไม่มีหลักฐานใหม่ว่าคำแนะนำช่วยผู้ใช้หรือเพิ่ม Engagement ต้องเก็บ Pilot ใหม่ Phone/Camera/Laptop/Unknown อย่างละ 3 คลิป และผู้ประเมินจริงอย่างน้อย 3 คนตาม Protocol
2. ยังต้องตรวจ ASR/Revision กับคู่คลิปจริงที่ไม่เคยใช้พัฒนา ไม่ใช้ Tests ซอฟต์แวร์แทนความแม่นของโมเดล
3. Protocol/Review schema ใหม่เป็น v2 ต้องสร้าง Prepared/Run ใหม่ ไม่แก้ Hash ทับ Artifact เดิมเพื่อให้ผ่านการตรวจ
4. ช่วงทำ Study ควรหยุดการแก้ Dataset/Model/settings และงานอัปเดตสถิติไว้ก่อน ถ้า Context เปลี่ยนต้องสร้าง Protocol ใหม่ เครื่องมือจะไม่แช่แข็งฐาน Production ให้เอง
5. Hash เป็นการตรวจความเปลี่ยนแปลง ไม่ใช่ลายเซ็นดิจิทัลและไม่พิสูจน์ตัวตนผู้ประเมิน ต้องเก็บ Artifact/Mapping ไว้ในพื้นที่ที่ควบคุมสิทธิ์ และแจกเฉพาะ Packet พร้อมสิทธิ์ดูวิดีโอ
6. แบบประเมินใช้ `video_uri` ของไฟล์จริง ผู้ประเมินต้องเข้าถึงไฟล์นั้นได้; ถ้าวิดีโอเปิดไม่ได้ ห้ามให้คะแนนจากข้อความแนะนำเพียงอย่างเดียว
7. ไม่แก้ผลวิเคราะห์เก่าหรือผลประเมินเก่าย้อนหลัง ตัวเลข/ข้อความเดิมยังคงเป็น Snapshot เดิม
