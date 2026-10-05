# โมเดลสาธิตสำหรับพรีเซนต์ 5 ตุลาคม 2026

## สถานะที่เปิดใช้

ผู้ใช้ขอเปิดรุ่นที่เหมาะสมที่สุดก่อน แม้ยังไม่ผ่านเกณฑ์ 80% จึงเปิด **Model #43**
แบบ `presentation_only` แทน #14 โดยไม่ได้เปลี่ยนผลประเมินให้เป็นผ่าน

- รุ่น: `presentation-20261004T164253915985Z`
- วิธี: Thai word/character TF-IDF + multilingual MiniLM embeddings + Logistic Regression C=16
- ฝึกจาก known Train178; เลือก C ด้วย grouped CV; เลือกจุดตรวจรับจาก Validation เท่านั้น
- ใช้ผลฝึกที่เก็บไว้จริงจาก `artifacts/laptop-scope-20261004/hybrid-v1`
  ไม่ได้ฝึกซ้ำ ไม่ใช้ Test มาเลือกโมเดล ไม่เปลี่ยน label/split
- เปิดชั่วคราวถึง **6 ตุลาคม 2026 เวลา 23:42 น. ประเทศไทย** (48 ชั่วโมงจากเปิด)
- หมดอายุแล้วงดคำแนะนำเฉพาะหมวด ไม่ต่ออายุเอง และไม่ยกระดับเป็น qualified
- ยังตรวจ confidence >=0.6 และเปรียบเทียบความคล้ายกับหมวดอื่น ไม่ปล่อยผ่านทุกคลิป
- คำเตือนติดในผลวิเคราะห์และถูกบันทึกพร้อมผลเดิม เปิดผลเก่าแล้วไม่เปลี่ยนเงียบ ๆ

เหตุผลเลือก: เหมาะกับโจทย์ Laptop/Unknown มากกว่ารุ่นก่อนในชุดพัฒนาที่ตรวจ
ไม่ได้หมายความว่าเป็นโมเดลดีที่สุดกับคลิปทุกประเภท หรือผ่านการประเมินอิสระแล้ว

## ตัวเลขที่พูดได้

จุดใช้งานสาธิต: scope v2, similarity >=0, predicted-class contrast >=0,
confidence >=0.6 ตัวเลขต่อไปนี้เป็น **Validation ที่ใช้พัฒนา** ไม่ใช่ Test ใหม่:

| หมวด | รับถูก / จำนวน | Recall |
| --- | --- | --- |
| Phone | 9/12 | 75% |
| Camera | 11/13 | 84.62% |
| Laptop | 3/5 | 60% |
| Unknown | ปฏิเสธ 8/10 | 80% |

สามหมวดรวมรับถูก23/30 (76.67%), Macro F1=82.90%; ไม่ผ่านเกณฑ์รายหมวด
แม้ Macro F1 เกิน80% ก็ตาม Grouped CV ที่เลือก C ได้ Accuracy96.07% และ
Macro F1=98.04% แต่เป็นผลพัฒนา ไม่ใช้แทนความแม่นของคลิปใหม่
ยังไม่ได้ตรวจ Test รอบใหม่กับรุ่นนี้

ประโยคพรีเซนต์: "รุ่นนี้เปิดชั่วคราวเพื่อสาธิตกระบวนการ ตั้งแต่ถอดเสียงจนถึง
คำแนะนำและหลักฐาน แต่การจำแนกบางหมวดยังไม่ผ่านเกณฑ์ที่ตั้งไว้ จึงมีคำเตือน
และยังปฏิเสธคลิปที่ไม่มั่นใจ ไม่อ้างว่าคำแนะนำจะเพิ่มยอดวิวแน่นอนครับ"

## การเปลี่ยนแปลง

- เพิ่มสิทธิ์สาธิตที่มีผู้อนุมัติ เหตุผล รุ่นโมเดล เวลาที่เริ่ม/หมดอายุ
  และรหัสโมเดลเดิมใน artifact สำเนาใหม่ ไม่แก้ไฟล์ทดลองต้นฉบับ
- `classification_models`: แถวใหม่ #43, status=presentation_only, active=true;
  #14 คงสถานะเดิม แต่ inactive
- `model_evaluation_metrics`: เก็บผล Train CV/Validation และ promotion_gate=0
  ไม่มีแถว Test ปลอม และไม่มี ModelTrainingRun ปลอมเพราะรอบนี้ไม่ได้ฝึกใหม่
- `system_logs`: `classification_presentation_activate` พร้อมผู้อนุมัติAdmin#2
- งาน Analyze ใหม่บันทึกรุ่นโมเดล/สิทธิ์สาธิตไว้ใน analysis_settings snapshot
- หน้า Admin แสดงสถานะสาธิต/คำเตือน/วันหมดอายุ และแปลชื่อ Log ใหม่เป็นไทย
- ปุ่ม Activate ปกติยังคงเกณฑ์เดิม ไม่สามารถนำรุ่นนี้ไป Activate เป็น qualified
- ไม่แก้ `CLASSIFICATION_REQUIRE_SCOPE_VALIDATION` เป็น false
- แก้การบันทึกคำแนะนำที่มีหลักฐานขนาดใหญ่: `recommendations.recommended_keywords`
  เปลี่ยนจาก TEXT เป็น LONGTEXT บน MySQL และขยายด้วย startup migration ที่รันซ้ำได้
  ไม่ตัดข้อความ/หลักฐาน ผลเดิม8รายการตรวจ hash ก่อนและหลังแล้วเหมือนเดิม
- แก้หน้าผลวิเคราะห์ที่นำเปอร์เซ็นไทล์25/75มาแสดงเป็นวินาที ให้ใช้
  `percentile_low_seconds` / `percentile_high_seconds` จริง ถ้าผลเก่าไม่มีช่วงจะบอกตามจริง

โค้ด: `classification_presentation.py`, `classification_acceptance.py`,
`classification_training.py`, `classification.py`, `classification_readiness.py`,
`scripts/presentation_classification_model.py` และข้อความใน Flutter

## เปิดเว็บและย้อนกลับ

เว็บ: http://127.0.0.1:8080/#/dashboard
API: http://127.0.0.1:8000

คืนสถานะก่อนเปิดสาธิต (คืน #14 ซึ่งยังงดคำแนะนำเมื่อไม่ผ่าน scope validation):

```powershell
python scripts/presentation_classification_model.py disable --admin-id 2 --expected-active-model-id 43
```

ใช้ช่องทางพิเศษผ่าน CLI ที่ตรวจ active admin/รุ่นปัจจุบัน/งานเทรนที่ค้าง/
fingerprint ของข้อมูล ไม่เพิ่มปุ่มกดข้ามเกณฑ์แบบทั่วไปในเว็บ

## หลักฐานตรวจ

- Backend **513 tests passed** รวมเปิด/ปิดสาธิต, ย้อนกลับ, สิทธิ์admin,
  ไม่แก้ผลประเมินเป็นผ่าน, ไม่รับ artifact ที่ข้อมูลเปลี่ยน,
  หมดอายุ/สิทธิ์ผิดต้องงดรับผล, ยังปฏิเสธ Unknown, warning ในผลและsnapshot
- รวม6testsสำหรับชนิดคอลัมน์/การขยาย/รันซ้ำ/ข้อมูลขนาดเกิน64KiB/ผลเก่า
- Flutter **17 focused tests passed**, analyze ไม่พบปัญหา, release web build ผ่าน
- Build มีคำเตือนเดิมเกี่ยวกับ CupertinoIcons และข้อเสนอ Wasm ไม่มี build error
- รีสตาร์ตด้วย hidden demo launcher แล้ว API อ่าน Active#43 ได้จริง
- Browserรอบแรกหยุดเพราะตรวจหน้าขณะยังโหลด; รอบสองใช้ชื่อปุ่มอังกฤษเก่า
  ทั้งสองรอบยังไม่ส่งคลิป จึงไม่ใช่ความล้มเหลวของ ASR/โมเดล เก็บหลักฐานไว้ครบ
- รอบสามพบข้อผิดพลาดจริง: ถอดเสียง/จำแนก/แนะนำสำเร็จ แต่บันทึกลง TEXT ไม่ได้
  แก้คอลัมน์เป็น LONGTEXT แล้ว ไม่ซ่อนข้อผิดพลาดหรือทำเครื่องหมายงานนั้นว่าสำเร็จ
- รอบสี่อัปโหลด `videos/Review_Phone.mp4` ผ่านเว็บ ถอดเสียงด้วยWhisper small จริง
  บันทึกสำเร็จเป็น **content#23 / analysis#22 / Model#43** ของAdmin#2
  รับหมวดPhone ความมั่นใจ67.0962% พร้อมคำเตือนสาธิต และคลิปอ้างอิง26รายการ
  ตัวเลขความมั่นใจไม่ใช่คะแนนความถูกต้องของคำแนะนำหรือโอกาสที่คลิปจะดัง
- รอบสี่หยุดภายหลังตอนสคริปต์ค้น History ด้วยชื่อไฟล์ดิบ แต่เว็บใช้ชื่อที่จัดรูปแบบแล้ว
  แก้สคริปต์ให้อ่านชื่อที่บันทึกจริง ไม่แก้ข้อมูลผลเพื่อให้การทดสอบผ่าน
- รอบห้าตรวจต่อจากผล#23โดยไม่อัปโหลด/ถอดเสียงใหม่ เปิดผ่านHistoryที่1440และ1000pxได้
  คำแนะนำและsettingsที่อ่านกลับมาเท่ากับผลตอนงานเสร็จทุกค่า ไม่มีBrowser/API error
- ระหว่างตรวจภาพพบการแสดงช่วงความยาวผิดตามที่กล่าวข้างต้น
  ค่าจริงของผล#23: ค่ากลาง112วินาที ช่วง77-136วินาที มีข้อมูลความยาว12คลิป
- Databaseจริงเก็บJSONได้: analysis6,746,580bytes; recommendation229,314bytes
  ตรวจอ่านJSONกลับมาได้ ไม่ใช่ผลสำเร็จเฉพาะในหน้าจอ
- รอบหกพบเซิร์ฟเวอร์หยุดหลังเปลี่ยนเซสชัน จึงเปิดhidden launcherใหม่
  ยกเลิกสิทธิ์sessionทดสอบที่ค้าง และปรับสคริปต์ไม่ให้เผยtokenเมื่อเชื่อมต่อไม่ได้
- **รอบเจ็ดผ่านหลังรีสตาร์ตจริง**: APIยังใช้#43 ผล#23และsettingsตรงกับผลรอบสี่
  เปิดผ่านHistoryที่1440และ1000px คำเตือน/คำแนะนำ/ช่วง77-136วินาทีถูกต้อง
  ไม่มีBrowser/API error และปิดsessionทดสอบเรียบร้อย ไม่วิเคราะห์MP4ซ้ำในรอบนี้

หลักฐานอยู่ที่ `artifacts/laptop-scope-20261004/`:

- `presentation-final-tests.stderr.log`: Backend513tests
- `presentation-payload-migration.json`: ชนิดคอลัมน์/hashเดิม/รันmigrationซ้ำ
- `presentation-saved-result-proof.json`: แถวผล#23และรุ่นโมเดลที่บันทึกจริง
- `presentation-browser-r4/analysis-job.json`: งานMP4จริงที่completed
- `presentation-browser-r5/verification.json`, `saved-result.json`, รูปdesktopทั้งสองขนาด
- `presentation-browser-r7/verification.json`: ผลตรวจเว็บสุดท้ายผ่าน7checks
  พร้อม `saved-result.json`, `training-*.png`, `reopened-*.png`, `advice-*.png`

คำสั่งตรวจซ้ำจากผลที่บันทึกแล้ว (เปลี่ยนoutput directoryทุกครั้ง):

```powershell
node scripts/browser/verify_presentation_model.cjs artifacts/presentation-recheck artifacts/laptop-scope-20261004/presentation-browser-r4/analysis-job.json
```

สคริปต์นี้ใช้admin#2ชั่วคราวและlogoutเมื่อจบ ไม่ได้ทดสอบแบบฟอร์มLogin
ถ้าไม่ใส่argumentสุดท้ายจะอัปโหลดMP4และสร้างผลใหม่จริง ไม่ใช่เพียงเปิดผลเก่า

## ข้อจำกัดที่ยังค้าง

- Whisper small ถอดชื่อสินค้าและคำเทคนิคบางคำคลาดเคลื่อนในคลิปตรวจซ้ำนี้
  จึงมีโอกาสพลาดประเด็นที่ผู้ใช้พูดแล้ว เช่นเรื่องชาร์จ ไม่อ้างว่าคำแนะนำแม่นครบทุกข้อ
- หน้าผลอ่านหลักฐานJSONประมาณหลายMB จึงมีช่วงโหลดข้อมูล
  ยังไม่ได้ลดข้อมูลซ้ำหรือทำlazy-loading เป็นงานประสิทธิภาพแยกต่างหาก
- ไม่ได้ทำTestอิสระรอบใหม่ ไม่ได้นำคลิปเดิมมานับเป็นTestใหม่
- ไม่ได้เปลี่ยนlabel/splitหรืออ้างว่าการเปิดสาธิตแก้ข้อจำกัดLaptop/Unknownแล้ว

ยังค้างเรื่องข้อมูล/ความแม่นตาม [Handoff Train/Validation](laptop-scope-20261004-handoff.md)
การเปิดสาธิตไม่ได้ถือว่าปัญหาเหล่านั้นแก้เสร็จ ไม่ใช้คลิปตรวจซ้ำครั้งนี้เป็น Test ใหม่
