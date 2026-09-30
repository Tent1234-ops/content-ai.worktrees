# Recommendation Phase 5 Handoff

## ตรวจทานเพิ่มเติม 2026-09-30

ตรวจแล้วพบช่องว่างเรื่องหลักฐานย้อนหลังและสถิติ จึงเพิ่ม Frozen transcript ของทั้งกลุ่มเปรียบเทียบ ตรวจ Video ID ของ Observation, งด Metric version ที่ไม่รู้จัก/ยอดวิวติดลบ และไม่คำนวณ Growth ข้าม Counter correction หรือการเปลี่ยนนิยามสถิติ ใช้ `topic-comparison-policy-v2` กับผลใหม่เท่านั้น ไม่แก้ผลเก่า

รายละเอียดการแก้และผลทดสอบล่าสุดอยู่ใน [รายงานตรวจ Phase 5-7](recommendation-phases5-7-review.md) ตัวเลข Verification ด้านล่างเป็นบันทึกของรอบพัฒนาเดิม ไม่ใช่หลักฐานว่าข้อมูลจริงเพียงพอแล้ว

## สถานะสองส่วน

- ฟีเจอร์และการทดสอบซอฟต์แวร์: เสร็จสำหรับ Phase 5 และ regression ผ่านทั้งหมด
- ความพร้อมของหลักฐานจริง: ระบบตรวจได้อย่างถูกต้อง แต่ข้อมูลจริงปัจจุบันยังไม่พอให้สรุปเชิงเปรียบเทียบ จึงแสดงเพียง `reference_only` หรือ `not_comparable` ตามหลักฐาน

งานนี้ทำเฉพาะ Phase 5 การเพิ่มน้ำหนักหลักฐาน ยังไม่ได้เริ่ม Phase 6 เรื่องอัปโหลดและเทียบฉบับแก้ไข

## สิ่งที่ทำเสร็จ

1. เพิ่ม comparison cohort จากคลิปอ้างอิงที่ผ่านเกณฑ์ทั้งหมดในหมวดเดียวกัน ก่อนกรองคลิปผลตอบรับสูง จึงไม่ได้ใช้เฉพาะคลิปดังมาสร้างสองกลุ่ม
2. แยก Transcript เป็น `detected`, `not_detected` และ `unassessable` โดยใช้ canonical topic/คำพ้องชุดเดียวกับคำแนะนำ Phase 2/3
3. ตัดคลิป Transcript ไม่ครบ, Transcript hash เปลี่ยน, metadata สำคัญขาด, สถิติไม่ทันเวลา หรือ metric เทียบกันไม่ได้ออกพร้อมเหตุผล ไม่เปลี่ยนเป็นค่าศูนย์
4. ดึงประวัติ `ReferenceVideoStatistic` แบบ batch query และเลือก observation สำเร็จล่าสุดไม่เกิน 24 ชั่วโมงจาก `as_of` เดียวกัน
5. แยก metric เป็นยอดวิว, ไลก์ต่อ 1,000 วิว, ความคิดเห็นต่อ 1,000 วิว และวิวต่อชั่วโมง ไม่รวมเป็น engagement score เดียว
6. เปรียบเทียบภายใน Channel + หมวด + รูปแบบที่ยืนยันได้ + ช่วงความยาว + ช่วงอายุคลิป + metric version ก่อน แล้วให้น้ำหนักแต่ละช่องเท่ากัน
7. เก็บผลบวก ผลลบ ผลไม่ชัด และผลที่เทียบไม่ได้ทั้งหมด ไม่เลือกแสดงเฉพาะผลที่สนับสนุนคำแนะนำ
8. บันทึก comparison snapshot พร้อมผลวิเคราะห์ใหม่ใน `analysis_results.summary` จึงเปิดผลเก่าโดยไม่คำนวณจาก Dataset หรือสถิติล่าสุดอีกครั้ง
9. เพิ่มส่วนเปิดดูหลักฐานในหน้าผลวิเคราะห์ และเพิ่มความพร้อมของ comparison ในหน้า Dataset Quality ของ Admin

## Data Contract

ข้อมูลอยู่ที่ `recommendation.evidence_bundle.topic_comparisons` และผูกกับคำแนะนำผ่าน `evidence_topic_id`

- `schema_version`: `topic-comparison-evidence-v1`
- `method.version`: `channel-stratified-descriptive-v1`
- `policy.version`: `topic-comparison-policy-v1`
- `as_of`: เวลา UTC ที่ตรึงครั้งเดียวต่อการวิเคราะห์
- `items[]`: หัวข้อมาตรฐาน, เวอร์ชัน/Hash, cohort audit, records สองฝั่ง, metric results และข้อจำกัด
- แต่ละ record เก็บ Dataset/Video/Channel ID, Transcript hash/ข้อความ/offset, observation/run ID, เวลาเก็บ, metric ที่ใช้ และเหตุผลคัดออก
- Fingerprint ของ evidence bundle รวม comparison snapshot และ policy ที่ใช้จริง

ไม่เพิ่มตารางใหม่ เพราะ `analysis_results.summary` เป็น snapshot แบบคงเดิมที่รองรับข้อมูลนี้อยู่แล้ว ผลเก่าที่ไม่มี snapshot จะไม่ถูกสร้างย้อนหลังจากชื่อคลิปหรือ Dataset ปัจจุบัน

## Policy และสูตร

- สถิติปัจจุบัน: observation สำเร็จล่าสุดที่อายุไม่เกิน 24 ชั่วโมง
- การเติบโต: ใช้ observation จริงสองเวลา โดยตั้งเป้าห่าง 24 ชั่วโมงและยอมรับ 12–36 ชั่วโมง
- `views_per_hour = (views_latest - views_previous) / ชั่วโมงจริงที่ห่างกัน`
- ถ้ายอดลดลง, มี failure คั่น, มี observation เดียว หรือเวลาไม่เข้าเกณฑ์ จะไม่มี growth rate ไม่ปลอมเป็นศูนย์
- `likes_per_1000_views = likes / views * 1000`
- `comments_per_1000_views = comments / views * 1000`
- ช่วงอายุคลิป: 0–<7, 7–<30, 30–<90, 90–<365 และ 365 วันขึ้นไป
- ช่วงความยาว: 1–180 วินาที และมากกว่า 180 วินาที แต่ไม่เรียกคลิปว่า Short จากความยาว ต้องมี metadata ยืนยันรูปแบบ
- ขั้นต่ำสำหรับผลเชิงพรรณนา: อย่างน้อย 10 คลิปต่อฝั่งและ 5 ช่องที่มีทั้งสองฝั่ง
- ขั้นต่ำสำหรับช่วงความไม่แน่นอน: 10 ช่องที่จับคู่ได้
- ช่วงความไม่แน่นอน: BCa bootstrap 2,000 รอบ, 95%, seed `260929`
- ค่าต่างหลัก: median ของค่าต่างภายในช่อง เพื่อไม่ให้ช่องที่มีคลิปมากครอบงำผล

สถานะต่อ metric:

- `not_comparable`: ไม่มีคู่ที่เทียบกันได้ หรือข้อมูล/เวลา/metric ไม่เข้ากัน
- `reference_only`: มีตัวอย่างจับคู่ แต่จำนวนยังต่ำกว่าเกณฑ์
- `comparison_descriptive`: ผ่านขั้นต่ำเชิงพรรณนา แต่ยังประเมินช่วงความไม่แน่นอนไม่ได้
- `comparison_uncertain`: คำนวณช่วงได้แต่ช่วงคร่อมศูนย์
- `comparison_supported`: คำนวณช่วงได้และไม่คร่อมศูนย์ เป็นเพียงความต่างในตัวอย่าง ไม่ใช่เหตุและผลหรือคำรับประกันยอด

## Audit ฐานข้อมูลจริง ณ วันที่พัฒนา

ตัวเลขต่อไปนี้มาจากการอ่านฐานข้อมูลจริงแบบ read-only ไม่ใช่ fixture และไม่ได้รัน collector หรือแก้ข้อมูลเพื่อให้ได้ผล

| หมวด | คลิปอ้างอิงที่ผ่านเกณฑ์ | ช่อง | ผลปัจจุบัน |
| --- | ---: | ---: | --- |
| Phone | 65 | 20 | ทุกหัวข้อยังเป็น `reference_only` ยกเว้น battery เป็น `not_comparable` |
| Camera | 57 | 30 | ทุกหัวข้อยังเป็น `reference_only` |
| Laptop | 65 | 14 | ทุกหัวข้อยังเป็น `reference_only` ยกเว้น display เป็น `not_comparable` |

ตัวอย่างจำนวนคู่ช่องที่พบ:

- Phone: camera 1, chip 1, battery 0, charging 3, display 1, thermal 4
- Camera: image quality 1, autofocus 5, stabilization 3, low light 2, video 3, handling 5
- Laptop: workload 2, thermal 3, battery 2, display 0, ports 3, memory 1, keyboard 1

Phone และ Camera มี Transcript แบบไม่ครบทั้งคลิปหมวดละ 3 รายการซึ่งถูกจัดเป็น `unassessable` ไม่ถูกนับเป็นฝั่ง “ไม่พบหัวข้อ” อย่างผิดความหมาย

สิ่งที่ต้องเก็บเพิ่มไม่ใช่เพียงเพิ่มจำนวนคลิปสุ่ม แต่ต้องมีคลิป `detected` และ `not_detected` จากช่องเดียวกัน อยู่ในช่วงอายุ/ความยาว/รูปแบบ/metric version ที่เทียบกันได้ โดยไม่ใช้ Validation/Test หรือรายการที่ซ้ำกับ Holdout

## ไฟล์สำคัญ

- `app/services/topic_comparisons.py`: policy, cohort audit, topic detection, observation/growth, stratification, comparison และ bootstrap
- `app/services/recommendation.py`: ส่ง comparison cohort ทั้งหมดและตรึงผลไว้ใน evidence bundle ของการวิเคราะห์ใหม่
- `app/services/recommendation_evidence.py`: cache การตัดตำแหน่งคำใน Transcript ที่ใช้ซ้ำหลายหัวข้อ
- `app/services/dataset_readiness.py`: audit ความพร้อมจริงรายหมวด/หัวข้อสำหรับ Admin
- `frontend_flutter/lib/widgets/recommendation_evidence_panel.dart`: แสดงสองกลุ่ม metric สถานะ ช่วงความไม่แน่นอน และข้อจำกัด
- `frontend_flutter/lib/widgets/dataset_readiness_panel.dart`: แสดงจำนวนคู่และช่องว่างข้อมูลใน Admin
- `tests/test_topic_comparisons.py`: unit/integration tests ของ policy และสูตร
- `scripts/browser/verify_topic_comparisons.cjs`: browser fixture แบบแยกฐาน ทดสอบผลบวก/ลบ/ข้อมูลไม่พอที่ 1,000 และ 1,440 พิกเซล

เพิ่ม `scipy` ใน `requirements.txt` เพื่อใช้ BCa bootstrap โดยตรง

## การตรวจสอบ

- Backend ทั้งระบบ: `python -m unittest discover -s tests -p "test_*.py"` ผ่าน 417 tests
- Regression ที่ Phase 5 กำหนดและ tests ใหม่: ผ่าน 71 tests
- Flutter ทั้งระบบ: `flutter test --no-pub` ผ่าน 115 tests
- Flutter analyze: `flutter analyze --no-pub` ผ่านโดยไม่พบปัญหา
- Python compile: `python -m compileall -q app tests/test_topic_comparisons.py` ผ่าน
- Browser verification: ผ่าน ไม่มี console error หรือ mutation request
- Screenshot: `artifacts/browser/topic-comparisons-phase5/`

Browser verification ใช้ข้อมูลจำลองที่ประกาศชัดและไม่เขียนฐานข้อมูลจริง มีไว้พิสูจน์ UI เท่านั้น ไม่ใช่หลักฐานว่าข้อมูลจริงผ่านเกณฑ์เปรียบเทียบ

## ประสิทธิภาพและข้อจำกัด

- ใช้ batch query ประวัติสถิติ ไม่มี query ต่อหัวข้อต่อคลิป
- เพิ่ม LRU cache ของตำแหน่งคำจาก 64 เป็น 512 เพื่อไม่ให้ cohort 65 คลิปล้าง cache ระหว่างหัวข้อ
- การวิเคราะห์จริงหมวด Phone บนเครื่องพัฒนาหลัง cache ใช้ประมาณ 10.6–13.0 วินาที โดยส่วนใหญ่เป็น pipeline วิเคราะห์ Dataset เดิม ไม่ใช่ query แบบ N+1
- ยังไม่มี cross-analysis result cache เพราะสถิติอ้างอิงเปลี่ยนตามเวลา ผลแต่ละครั้งจึงตรึง snapshot และ fingerprint ที่ใช้จริงแทน
- กลุ่มข้อมูลอ้างอิงเป็นชุดที่คัดมา ไม่ใช่ตัวแทน YouTube ทั้งหมด และ comparison นี้ไม่ควรถูกอธิบายว่าเป็น causal effect
- Web build มี warning ว่าไม่มี CupertinoIcons font แต่ Material icons ที่หน้านี้ใช้ถูก build และ browser verification ผ่าน

## งานค้างและสิ่งที่ Phase 6 ต้องรู้

งานโค้ดตามข้อกำหนด Phase 5 ไม่มีค้าง งานด้านข้อมูลที่ค้างคือเพิ่มคู่เปรียบเทียบที่สมดุลตาม audit ข้างต้นก่อนจะได้สถานะสูงกว่า `reference_only`

หากเริ่ม Phase 6 ภายหลัง ต้องอ้าง comparison snapshot และ recommendation fingerprint ที่บันทึกกับผลเดิม ห้ามคำนวณผลเก่าจาก Dataset/policy ปัจจุบัน และต้องแยก “เนื้อหาเปลี่ยน” ออกจากคำกล่าวอ้างว่า engagement จะดีขึ้น งาน Phase 6 ยังไม่ได้เริ่มในงานนี้
