# Outcome Data Preparation: 12 ตุลาคม 2026

> ผลตรวจล่าสุด: [Handoff รูปแบบและความครอบคลุม 172 คลิป](outcome-format-coverage-20261012-handoff.md) มีหลักฐานสำหรับวางแผนแยกคลิปปกติ 106/Shorts 57 และยังต้องยืนยัน 9 รายการ ไม่มีการแก้ DB หรือย้าย Split ใช้ตารางแยก Format ในเอกสารล่าสุดแทนตัวอย่างสมมุติรวม Format ในรายงานนี้

## สรุปที่นำไปตัดสินใจได้

ตรวจฐานข้อมูลจริงแบบอ่านอย่างเดียวที่ cutoff `2026-10-11T17:46:12Z` หรือ 12 ต.ค. 00:46:12 น. เวลาไทย

อัปเดตภายหลังวันที่ 12 ต.ค.: เจ้าของยืนยันว่า **ชุด NotebookLM เดิมมี Shorts ปนด้วย** แต่ยังไม่ระบุ Video ID จึงยังบอกไม่ได้ว่าอยู่ในผู้สมัคร Train 172 รายการกี่คลิป ตัวอย่างจำนวนที่สมมุติ Format เดียวกันด้านล่างเป็นเพียงการวางแผนแบบมีเงื่อนไข ห้ามใช้ยืนยันความเพียงพอหรือจำนวนที่ต้องเก็บเพิ่มสุดท้าย ดู [Handoff ชุดใหม่](outcome-incoming-batch-20261012-handoff.md) สำหรับบริบทและขั้นตอนตรวจรายคลิป ทั้ง DB และ Snapshot เดิมยังไม่ถูกแก้

**มี 308 คลิป แต่พร้อมฝึก Outcome ครบทุกเงื่อนไขตอนนี้ 0 คลิป ไม่ได้หมายความว่า Transcript เดิมใช้ไม่ได้ทั้งหมด**

| หมวด | มีทั้งหมด | Transcript เต็มใน Train เดิม: ผู้สมัครชุดพัฒนา | Transcript เต็มใน Validation/Test เดิม: ห้ามย้าย | Transcript บางส่วน: ต้องตรวจ/ซ่อมก่อน |
|---|---:|---:|---:|---:|
| Phone | 109 | 60 | 12 | 37 |
| Camera | 101 | 58 | 19 | 24 |
| Laptop | 98 | 54 | 28 | 16 |
| รวม | 308 | **172** | **59** | **77** |

- 308 Video IDs ไม่ซ้ำ จาก 123 ช่อง; จำนวน Observation ไม่ใช่จำนวนคลิปอิสระ
- 172 รายการเป็น **ผู้สมัคร** สำหรับ Fit/Tuning หลังแก้ Metadata และผ่านสิทธิ์/คุณภาพ/การแบ่งชุด ไม่ใช่ Training-ready และไม่ใช่ประชากรคลิปทั่วไป
- 59 รายการยังคงเป็นชุดกันไว้เดิม ไม่ย้ายไป Train หรือคลิปอ้างอิง และไม่เรียกว่า Fresh Outcome Test
- 77 รายการเป็น `first_window` ไม่ใช่ Transcript เต็ม; ในนี้มี Train 37 และ Validation/Test 40 รายการ ต้องรักษาชุดเดิมแม้แก้ข้อความ
- ไม่จำเป็นต้องซ่อมทั้ง 77 รายการทันที หรือไปหาคลิปใหม่ 77 คลิปแทน: ตรวจความคุ้มค่าก่อน หากใช้ต่อให้เก็บข้อความเต็มจากคลิปเดิมและตรวจ hash/ที่มาใหม่

## วิธีคัดเลือกที่เจ้าของยืนยัน

คำตอบผู้ใช้: **“เน้นเลือกคลิปยอดวิวหรือผลตอบรับสูง”** สำหรับ Phone/Camera/Laptop ที่นำ Transcript จาก NotebookLM เข้าโครงการ

นำคำตอบนี้ผูกกับรายชื่อ 231 รายการปัจจุบันใน `selection-confirmation.json` โดยมี Dataset ID, Video ID และ Transcript SHA256 ครบ ไม่ใช้ครอบข้อมูลใหม่ในอนาคตโดยอัตโนมัติ

- แม้แถวเดิมเขียน `classification_diverse` ก็ไม่ใช่หลักฐานว่าเลือกโดยไม่ดูยอดวิว
- NotebookLM 231 รายการ + legacy ที่ระบุ `recommendation_high_performance` อีก 61 รายการ = 292 รายการที่มีหลักฐานการคัดตามผลตอบรับ
- 16 รายการที่เหลือยังไม่ยืนยันว่าสุ่ม/คัดแบบทั่วไป ห้ามเติม `general_protocol_v1` จากการเดา
- รายการที่ติดข้อห้ามใช้ข้อมูลคัดยอดสูงเป็น Calibration/Test เพิ่มจาก 31 ตาม Metadata เดิม เป็น **90** เมื่อรวมคำยืนยันผู้ใช้
- การคัดเพราะยอดสูงไม่ได้แปลว่าทุกรายการมีผลตอบรับสูงจริงเมื่อเทียบกลุ่มอายุเดียวกัน และไม่ใช่ Label 1 อัตโนมัติ
- คำยืนยันนี้เป็นหลักฐานวิธีคัดเลือก ไม่ใช่หลักฐานสิทธิ์ฝึกโมเดลหรือคำสั่งให้แก้ฐานข้อมูล

## ต้องแก้อะไร

| ประเด็น | ทั้งหมด | เฉพาะ 172 ผู้สมัครชุดพัฒนา | วิธีจัดการ |
|---|---:|---:|---|
| ไม่มี Format ที่ยืนยัน | 308 | 172 | ตรวจจากต้นทางว่า Short/Long พร้อมหลักฐาน ไม่เดาจาก Duration |
| ไม่มี Outcome sampling frame | 308 | 172 | เสนอ `high_response_protocol_v1` ตามคำยืนยัน ไม่เปลี่ยนเป็น General เพื่อให้ผ่าน |
| ไม่มี Observation ที่ใช้ได้ ณ cutoff | 117 | 0 | เก็บสถิติจาก Video ID ผ่าน collector ที่มีสิทธิ์และ Manifest ถูกต้อง |
| Observation เก่ากว่า 24 ชั่วโมง | 13 | 0 | Refresh ก่อน Frozen cutoff สำหรับรอบฝึกจริง |
| Transcript ไม่เต็ม | 77 | 0 | พิจารณาซ่อมจากคลิปเดิม ไม่บังคับเก็บใหม่ทั้งชุด |
| ไม่ผ่าน production transcript contract | 63 | 0 | ทั้ง 63 อยู่ในกลุ่ม Transcript บางส่วน ตรวจรายละเอียดก่อนรับเข้า |
| สิทธิ์ใช้ข้อมูลกับ Outcome ยังไม่ยืนยัน | ทั้งชุด | ทั้งชุด | เจ้าของจัดหลักฐานและยืนยันผ่าน record จริง ไม่ข้าม gate |

สถิติของ 172 รายการใหม่พอ **ณ cutoff นี้** เท่านั้น วันฝึกจริงต้องตรวจซ้ำ ห้ามยกความพร้อมวันนี้ไปใช้ตลอด

หลังอนุมัติ Metadata ให้ใช้ workflow ตรวจความพร้อม/สร้าง Manifest เดิม ไม่ใช้ CSV รอบนี้เป็น Training Manifest โดยตรง และไม่แก้ `collection_strategy` ของงานจำแนกทั้งหมดเพื่อบังคับให้งาน Outcome ผ่าน

## ต้องเก็บเพิ่มเท่าไร

**ยังระบุยอดจบตายตัวไม่ได้โดยไม่เดา** เพราะ Format ยังไม่ยืนยันและกลุ่มอายุ/ช่อง/ผลตอบรับสองระดับยังไม่ผ่านการตรวจครบ

ส่วนที่นับได้แน่นอนคือ “จำนวนช่องว่างของชุดประเมิน” ตาม Protocol เดิม:

| บทบาท | จำนวนที่ใช้ประเมินได้ขั้นต่ำ | มีที่ยืนยันพร้อมในข้อมูลเดิม | ช่องว่าง |
|---|---:|---:|---:|
| Calibration: ปรับความน่าเชื่อถือของเปอร์เซ็นต์ | 30 | 0 | 30 |
| Independent Test: ตรวจรุ่นที่ Freeze แล้ว | 30 | 0 | 30 |

Calibration ระบุขั้นต่ำ partition 20 แต่มีเกณฑ์กราฟ 3 bins อย่างน้อย bin ละ 10 จึงต้องมี **อย่างน้อย 30 ตัวอย่างที่ประเมินได้จริง** ส่วน Test ต้องมีอย่างน้อย 10 ต่อหมวด และรวมอย่างน้อย 10 ช่อง/หมวดละ 3 ช่อง ทั้งสองชุดต้องมีอย่างน้อย 10 ตัวอย่างต่อ Label ตาม Protocol; ห้ามคัดจากยอดจริงเพื่อจัดสัดส่วน Label ให้ผ่าน

**แผนเริ่มต้นที่แนะนำ: จองคลิปใหม่หมวดละ 20 รวม 60** แยกหมวดละ 10 Calibration + 10 Test ตั้งแต่ต้น โดยยังต้องตรวจ Format/อายุที่ชุด Fit รองรับก่อนเลือกจริง การแบ่ง Calibration 10 ต่อหมวดเป็นแผนกระจายข้อมูล ไม่ใช่เพิ่ม/เปลี่ยนเกณฑ์ Protocol

- 60 คือแผนทดแทนชุดประเมินที่ยังไม่พร้อม ไม่ใช่จำนวนทั้งหมดที่รับประกันว่าฝึกผ่าน
- Legacy 9 รายการที่ไม่ได้ระบุคัดยอดสูงยังมี Transcript บางส่วนและที่มาไม่ครบ: 4 Validation และ 5 Test ไม่ให้เครดิตเป็นข้อมูลพร้อมล่วงหน้า หากภายหลังซ่อมและพิสูจน์ความเหมาะสม/ความเป็นอิสระได้จริง จำนวนที่ต้องเก็บใหม่อาจลดลง ต้อง Audit ใหม่ก่อนนับ
- ต้องจองช่อง/Creator/วิดีโอ/Transcript ไม่ให้ซ้ำข้าม Fit, Tuning, Calibration, Test หรือข้อมูลเก่าที่ใช้พัฒนา ห้ามใช้การย้าย Split เก่าแก้จำนวน
- Probability ties, บางหัวข้อไม่มีทั้งพบ/ไม่พบ, ผลตอบรับเหลือเพียง Label เดียว หรือระบบงดทำนาย อาจทำให้เก็บ 30 แล้วเหลือที่ประเมินได้ไม่ถึง 30
- ห้ามเปิดผล Test แล้วเลือก Model/Threshold หรือเติมคลิปตาม Label ที่ต้องการ; Freeze นโยบายเก็บ/ขอบเขตจาก Train/Tuning ก่อนเปิด Test หากใช้ Test ปรับระบบแล้วต้องถือว่าชุดนั้นถูกใช้พัฒนา

### เหตุใด Fit/Tuning ยังอาจต้องเก็บเพิ่ม

การแบ่งตามช่องของโค้ดเดิมให้ผู้สมัคร Fit 141 และ Tuning 31 จาก 172 รายการ แต่จำนวนรวมอย่างเดียวไม่พอ ต้องมี Fit อย่างน้อย **20 คลิป/5 ช่องในแต่ละ category + format + age + metric** และมี Label ทั้งสองระดับ

ตัวอย่างช่องว่างจากวันเผยแพร่ หาก Refresh ที่ cutoff นี้ โดย **ยังสมมุติว่า Format/Metric เหมือนกันทั้งหมด**:

| หมวด/ช่วงอายุ | Fit เดิม | ช่อง Fit | Tuning เดิม | ช่องว่าง Fit อย่างน้อย |
|---|---:|---:|---:|---:|
| Phone / 90-365 วัน | 18 | 8 | 5 | 2 คลิป |
| Camera / 365 วันขึ้นไป | 25 | 16 | 6 | 0 ในเชิงจำนวนเท่านั้น |
| Laptop / 90-365 วัน | 20 | 3 | 4 | 2 คลิปจาก 2 ช่อง Fit เพิ่ม |

หากเลือกแค่สามบริบทตัวอย่างนี้จะมี Tuning ที่ตรงบริบทเพียง 15 ไม่ใช่ 31 จึงขาด Tuning อย่างน้อยอีก 15 รวม Fit/Tuning เพิ่มเชิงจำนวนอย่างน้อย 19 ในสถานการณ์นี้ หรือ 79 เมื่อรวมแผนชุดประเมิน 60

**79 เป็นเพียงตัวอย่างคำนวณแบบมีเงื่อนไข ไม่ใช่ใบสั่งให้ไปหา 79 คลิปหรือยอดรับประกันจบ** ไม่ได้อนุมัติขอบเขตโมเดลใหม่ และไม่ถือว่ากลุ่มเหล่านี้ผ่านแล้ว หาก Format แยกกัน, อยู่ใกล้ขอบช่วงอายุ, แบ่งช่องไม่ได้, สอง Label/Topic support ไม่พอ ต้องคำนวณใหม่ รายงานทุกช่วงอายุอยู่ใน `projected-age-coverage.csv`

อีกประเด็นคือ Fit/Tuning เก่ายังคัดยอดสูง การเติมคลิปทั่วไปตามแผนเก็บที่ไม่ดูผลตอบรับช่วยลดการพึ่งพากลุ่มดัง แต่ไม่มีจำนวนเสริมใดรับประกันลบ Selection bias ได้ และค่ากลางจาก Fit ที่คัดยอดสูงอาจทำให้คลิปทั่วไปใน Calibration/Test เป็น Label ต่ำเกือบทั้งหมด ห้ามแก้ด้วยการคัดเฉพาะยอดสูงเข้า Holdout

## วิธีเก็บที่ไม่ต้องทำงานซ้ำ

1. ตรวจ Format ของ 172 ผู้สมัครเดิมก่อน พร้อมแหล่งหลักฐาน แยก Short/Long จริงและรัน Coverage ใหม่
2. ตรวจสิทธิ์ฝึก/เสิร์ฟผล และยืนยันการแก้ Outcome Metadata ที่เสนอ ก่อนเขียน DB จริง
3. วางกรอบเก็บใหม่จากหมวด รูปแบบ ช่วงเผยแพร่และช่องที่ไม่ทับชุดอื่น **ก่อนดูยอดวิว/ไลก์** เก็บทั้งรายการที่ดังและไม่ดังตามกติกาเดียวกัน ไม่เลือกเฉพาะคลิปยอดต่ำมา “ถ่วง” คลิปดัง
4. จอง Calibration/Test แยกช่องแต่ต้น และกันจาก Reference eligibility; เก็บ Transcript เต็ม URL, Video/Channel ID, วันที่เผยแพร่, Duration, Format พร้อมหลักฐานและกติกาที่เลือก
5. เติม Fit/Tuning เฉพาะกลุ่มที่ Coverage ขาดด้วยกติกาคลิปทั่วไปเดียวกัน ใช้ channel hash/identity checks เดิม ไม่ย้ายชุดเก่าเพื่อให้ครบ
6. เมื่อสิทธิ์และ Metadata ผ่าน จึงใช้ collector เดิมเก็บ Observation ใหม่, Freeze Manifest, สร้าง benchmark จาก Fit, Train/Validation และเปิด Test ตามขั้นตอน ไม่สร้างยอดย้อนหลังหรือข้อมูลเทียม

สำหรับ Outcome ที่ใช้ Transcript ไม่จำเป็นต้องหา MP4 ใหม่ทุกตัวอย่าง; MP4 สำหรับทดสอบอัปโหลด/ถอดเสียงจริงเป็นงานตรวจ Workflow อีกส่วนหนึ่ง

## งานที่เสร็จและหลักฐาน

- เพิ่ม CLI `scripts/prepare_outcome_data_review.py` ใช้ source records, validation, prior-use scan และ SQL write guard ของระบบเดิม ไม่เพิ่ม sampler/โมเดล/collector ซ้ำ
- เพิ่ม 12 Tests ครอบคำยืนยันเลือกยอดสูง, ไม่อนุมาน General, ห้ามย้าย Holdout, ไม่ยกข้อความบางส่วนเป็นเต็ม, ไม่ใช้ projected age เป็น Observation, ไม่ส่งค่า Views/Transcript/Label ไปในไฟล์ตรวจ และ Spreadsheet formula escaping
- Audit เดิม + Phase 2 preflight + preparation CLI อ่าน DB จริงสำเร็จและ `database_unchanged=true`
- ข้อมูล Snapshot: dataset_contents ทั้งฐาน 472 แถว, statistics 25,134 แถว, runs 164, classification_models 43; ทั้งฐานไม่เท่ากับ 308 คลิปเป้าหมายที่ active
- Identity ก่อน/หลัง: `d5344d594cffe4892b1564a91ab910c34c87365040bd09b9961cdf2d631b9f70`
- Protocol SHA: `ef3a7475e2a005b5dda4f9311eec6740570277b82204847a32114d6bdae6e12b` ไม่เปลี่ยน
- Owner selection confirmation SHA: `71b3a2a9063d680bb7e651c80a169d5fe955941f53f281c1d5f12dc76543aa4d`

หลักฐานทั้งหมด: `artifacts/outcome-prediction/data-preparation/20261011T174612Z/`

| ไฟล์ | ใช้ทำอะไร |
|---|---|
| `audit/readiness.json` | Audit เดิมพร้อมสถานะสิทธิ์/โมเดล/ที่มา |
| `dataset-preflight/build-report.json` | Phase 2 preflight ที่ถูก Block จริง ไม่สร้าง Manifest |
| `review/selection-confirmation.json` | คำยืนยันเจ้าของและรายชื่อ 231 คลิปที่ผูกกับคำยืนยัน |
| `review/01-development_review.csv` | 172 ผู้สมัครพัฒนาที่ควรตรวจ Format ก่อน |
| `review/02-protected_do_not_train.csv` | 59 Transcript เต็มที่ห้ามย้ายเข้า Train/Reference |
| `review/03-transcript_repair.csv` | 77 Transcript บางส่วน พร้อมสถานะ protected รายคลิป |
| `review/all-review-rows.csv` | ทั้ง 308 รายการ พร้อม URL ช่อง วันที่ Metadata ที่ขาด และช่องกรอกการตรวจ |
| `review/projected-age-coverage.csv` | การนับตามอายุสมมุติหลัง Refresh ไม่ใช่ Cell ที่ผ่านแล้ว |
| `review/preparation-report.json`, `summary.json` | ตัวเลขแยกกลุ่มและช่องว่างทั้งหมด ไม่เปิด Labels/Test metrics |
| `tests-stdout.log` | ผลทดสอบ 32/32 ข้อจาก unittest; ไม่มี NativeCommandError จากการรวม stderr ของ PowerShell |

### คำสั่งที่รันสำเร็จ

ทุกคำสั่งรันใน Project root และตั้ง `$env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'` ก่อน ไม่มี migration/DB bootstrap

```powershell
py -X utf8 scripts/audit_outcome_prediction_readiness.py --cutoff 2026-10-11T17:46:12Z --output-dir artifacts/outcome-prediction/data-preparation/20261011T174612Z/audit
py -X utf8 scripts/build_outcome_dataset.py --cutoff 2026-10-11T17:46:12Z --output-dir artifacts/outcome-prediction/data-preparation/20261011T174612Z/dataset-preflight
py -X utf8 scripts/prepare_outcome_data_review.py --cutoff 2026-10-11T17:46:12Z --output-dir artifacts/outcome-prediction/data-preparation/20261011T174612Z/review --owner-confirmed-notebooklm-high-response --owner-statement 'เน้นเลือกคลิปยอดวิวหรือผลตอบรับสูง'
py -X utf8 -m unittest tests.test_outcome_data_preparation tests.test_outcome_dataset tests.test_outcome_prediction_readiness -v
```

Exit code 0 ทุกคำสั่ง; 32/32 Tests ผ่าน ทั้ง Fixture/SQLite และ read-only audit ของจริงแยกกัน ไม่ใช่ผลประเมินโมเดลจริง คำสั่ง preflight ออก `blocked_data_use` ตามคาด แม้ Exit 0 เพื่อเขียนรายงานได้

`git diff --check` ผ่าน มีเพียงคำเตือน LF/CRLF ของไฟล์ค้างเดิม รันจาก workspace parent

ตรวจไฟล์ใหม่ทั้งสามด้วย `git diff --no-index --check -- NUL <path>` เพิ่มด้วย ไม่มี whitespace error; Exit 1 เป็นความต่างจาก NUL ไม่ใช่ผล Tests ล้มเหลว

## งานค้างและขอบเขต

| งาน | ผู้รับผิดชอบ | สถานะ |
|---|---|---|
| ยืนยัน Format/หลักฐานของผู้สมัครเดิม | เจ้าของ/ผู้ตรวจข้อมูล | ยืนยันว่าชุดเดิมมี Shorts ปนแล้ว; ยังรอระบุรายคลิปใน CSV |
| ยืนยันสิทธิ์ใช้ข้อมูลฝึก/ให้บริการ | เจ้าของโครงการ | `unverified`; ห้าม Agent ยืนยันแทน |
| อนุมัติบันทึก Metadata ที่ตรวจจริง | เจ้าของ แล้ว Agent ดำเนินการ | ยังไม่แก้ DB รอบนี้ |
| ล็อกกรอบเก็บใหม่/Identity/Split/Scope | เจ้าของร่วมกับ Agent | ต้องทำก่อนเก็บ/เปิดผล ไม่ใช่ลดเกณฑ์ |
| เก็บและทบทวนชุดใหม่ | เจ้าของ/ผู้ตรวจข้อมูล | ยังไม่มีชุดใหม่ที่รับรองพร้อม |
| ฝึก/Validation/Calibration/Test Outcome จริง | Agent หลัง Dependency ผ่าน | ยังไม่ได้ฝึก ไม่มี Probability จริง |
| Active Classifier สำหรับ Live analysis | เจ้าของผ่าน workflow เดิม | Audit ยังพบ presentation-only หมดอายุ; ไม่ต่ออายุหรือ Activate อัตโนมัติ |

ไม่มี Production DB/API/scheduler/model activation เปลี่ยน ไม่มีการเรียก YouTube API หรือเปิดหน้าเว็บใหม่ ไม่มี Test label/ผลประเมินอิสระถูกใช้เลือกวิธีในรอบนี้ งาน dirty เดิมไม่ถูกย้อนทับ ไม่ต้อง Rollback ฐานข้อมูลเพราะไม่มีการเขียน

ก่อนส่ง 19 ต.ค. ให้ตัดสินจากหลักฐานจริง: ซอฟต์แวร์และการเตรียมข้อมูลพร้อมตรวจไม่ได้เท่ากับโมเดลผ่าน หากข้อมูลไม่ทันให้รายงานข้อจำกัดและความไม่พร้อมตรง ๆ ไม่ใช้จำนวนคลิปหรือ Classification Confidence แทนผลตรวจ Outcome
