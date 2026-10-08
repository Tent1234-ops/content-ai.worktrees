# Outcome Prediction Protocol v1

สถานะ: **ล็อกก่อน Train** วันที่ 8 ตุลาคม 2026 สำหรับ Phase 1 แหล่งข้อมูลจริงยังต้องผ่าน Data-use gate และ Manifest ใน Phase 2

ไฟล์ที่โปรแกรมตรวจ: [outcome-prediction-protocol-v1.json](outcome-prediction-protocol-v1.json)

## คำถามที่ตอบ

โมเดลรุ่นแรกตอบว่า ภายใต้หมวด รูปแบบ และช่วงอายุอ้างอิงที่ระบุ เนื้อหาแบบนี้มีโอกาสอยู่ในกลุ่มที่มียอดวิวสะสม ณ เวลาสังเกตสูงกว่าค่ากลางของชุด Fit เท่าไร

หนึ่งตัวอย่างคือหนึ่ง YouTube Video ID ไม่ใช่หนึ่ง Snapshot ค่ากลางให้น้ำหนักแต่ละช่องเท่ากัน แล้วแบ่งน้ำหนักเท่ากันระหว่างคลิปภายในช่องเดียวกัน Label เป็น 1 เฉพาะเมื่อ Views มากกว่าค่ากลางอย่างเคร่งครัด; เท่ากันเป็น 0

ผลนี้เป็นความสัมพันธ์ในชุดอ้างอิง ไม่ใช่:

- ยอดวิวใน 7 วันหรือจำนวนวิวที่จะได้
- ความน่าจะเป็นที่ทำตามคำแนะนำแล้ววิวเพิ่ม
- หลักฐานเชิงเหตุและผล
- Confidence ของโมเดลจำแนก Phone/Camera/Laptop

## ข้อมูลและเวลา

ใช้ Transcript ทั้งคลิปที่ตรวจ Hash ได้, หมวดที่ยืนยัน, Format ที่มีหลักฐาน, Duration, Published time และ Observation จริงก่อน Cutoff ไม่เกิน 24 ชั่วโมง Missing ไม่เท่ากับศูนย์ และไม่อนุมาน Shorts จากความยาว

Benchmark cell คือหมวด + Confirmed format + Age bucket + View metric version ช่วงอายุ 0-<7, 7-<30, 30-<90, 90-<365 และ 365 วันขึ้นไป หาก Fit ไม่มี Cell ที่รองรับ ระบบงดทำนาย ไม่ยืม Median จาก Validation/Test

Collection strategy บอกเหตุผลการเก็บ ไม่ใช่ Outcome label คลิปที่ถูกเลือกเข้ามาเพราะรู้ว่ายอดสูงห้ามเป็น Calibration/Test แต่คลิปยอดสูงที่ได้มาตาม Sampling protocol ปกติยังคงอยู่ ไม่ตัดตามผลเพื่อแต่ง Class balance

## การแบ่งข้อมูลและป้องกันรั่ว

แบ่ง Fit/Tuning/Calibration/Independent Test ด้วย Channel, Creator group, Video ID และ Transcript hash ที่เชื่อมกัน Protected Validation/Test เดิมห้ามย้ายเป็น Train/Reference ชุดที่เปิดดูเพื่อแก้ระบบแล้วเป็น Development/Regression ไม่เรียก Fresh Test

Median, Label threshold, preprocessing และ Feature transformation ต้อง Fit จาก Fit partition หรือ Fit fold เท่านั้น Test ไม่ใช้เลือก Feature, Model, Threshold,ข้อความ หรือ Scope

ขั้นต่ำเริ่มต้น:

| Partition | วิดีโอ | ช่อง |
|---|---:|---:|
| Fit | 40 | 8 |
| Tuning | 30 | 5 |
| Calibration | 20 | 5 |
| Independent Test | 30 | 10 |

Calibration/Test ต้องมีอย่างน้อย 10 ตัวอย่างต่อ Label รวม หมวดที่จะรับรองต้องมี Test อย่างน้อย 10 คลิป 3 ช่อง และสอง Label ตัวเลขเป็น Guardrail โครงการ ไม่ใช่มาตรฐานพิสูจน์เชิงวิจัย และห้ามลดหลังดูผล

## Features และโมเดล

Candidate ใช้ Canonical topic presence แบบ Boolean ร่วมกับ Category, Format, Duration และ Frozen age context การพูดคำซ้ำไม่เพิ่ม Feature ไม่ใช้ Views/Likes/Comments/Rank/Channel ID/Title หรือ Classification confidence เป็น Input

เปรียบเทียบสามตัว:

1. Constant prior
2. Metadata-only Logistic Regression
3. Metadata + topics Logistic Regression, L2, C ใน 0.1/1/10

ใช้ Seed 261008, Group-aware tuning และ Sigmoid calibration บนข้อมูลคนละช่องกับ Fit/Tuning ไม่ใช้ Test calibrate ค่า Probability

## เกณฑ์ตรวจรับ

Primary metric คือ Channel-balanced Brier score Candidate ต้องดีกว่า Constant และ Metadata-only อย่างน้อย 0.01 บน Validation, Log loss ไม่แย่กว่า Baseline ที่ดีที่สุดเกิน 0.02 และ Brier รายหมวดไม่แย่กว่า Metadata-only เกิน 0.02

Calibration ใช้สาม Quantile bins แบบ tie-stable แต่ละ Bin อย่างน้อย 10 คลิป/3 ช่อง และช่องว่างระหว่างค่าเฉลี่ย Prediction กับอัตราจริงไม่เกิน 0.15 Independent Test ใช้ Paired bootstrap 2,000 รอบระดับช่อง 95%; ต้องสนับสนุนทิศทางว่าดีกว่า Baselineโดยช่วงไม่คร่อมศูนย์

หากจำนวน/สอง Label/Calibration/CI ไม่พอ ให้สถานะ experimental หรือ abstain ไม่เปลี่ยนเกณฑ์เพื่อให้ผ่าน และต้อง Freeze Scope ก่อนเปิด Test

## ข้อความและ Scenario

ถ้าผ่านทุก Gate จึงใช้คำว่า “โอกาสอยู่ในกลุ่มยอดวิวสูงกว่าค่ากลางของชุดอ้างอิง” พร้อม Population/บริบท/เวลา ไม่ใช้ “เพิ่มยอดวิว X%”

การจำลองเพิ่มหัวข้อเปลี่ยนเฉพาะ Feature ในสำเนาและเรียกผลต่างว่า “ส่วนต่างค่าประเมินแบบสมมุติ หน่วยจุดเปอร์เซ็นต์” ผลอาจบวก ศูนย์ ลบ หรือประเมินไม่ได้ ไม่ถือว่าผู้ใช้แก้คลิปแล้ว และไม่เป็นหลักฐานว่า Topic เป็นสาเหตุ

## สิทธิ์ ทรัพยากร และ Utility

Training/Serving จากข้อมูลจริงต้องมี Data-use decision = confirmed พร้อมหลักฐาน ผู้ทำงานห้ามยืนยันแทนเจ้าของโครงการ

งบรุ่นแรก: Training ไม่เกิน 30 นาที/8 GiB, P95 inference 500 ms, timeout 1.5 วินาที, CPU และไม่ดาวน์โหลดโมเดล/ใช้ Paid API

ก่อน 15 ต.ค. ต้อง Freeze Utility study: คลิปในขอบเขตหมวดละ 4, refusal 3, ผู้ประเมินจริงอย่างน้อย 3 คน เปรียบเทียบ Keyword เดิม / คำแนะนำมีวิธีทำและหลักฐาน / แบบที่มี Outcome เพิ่ม โดยวัดความเกี่ยวข้อง ไม่ซ้ำ ความถูกต้องหลักฐาน ความเข้าใจง่าย และนำไปใช้ได้ พร้อมตรวจว่าคนไม่เข้าใจตัวเลขเป็นคำรับประกันยอด

