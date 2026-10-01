# ข้อมูลใหม่และแผนเก็บเพิ่ม ณ 1 ตุลาคม 2026

## ผลตรวจไฟล์จริง

ใช้ parser NotebookLM เดิมและตรวจ metadata ของ YouTube จาก Video ID ไม่แก้ไฟล์ต้นฉบับ ไม่ Train ไม่ Import/Approve

| โฟลเดอร์ใต้ `Z:\Ai Content TrainTest Data` | ไฟล์อ่านได้ | ซ้ำในระบบ | ใหม่ที่ส่งเข้าคิวตรวจได้ |
|---|---:|---:|---:|
| `camera\+6` | 6 | 1 | 5 |
| `Test Data\headphone` | 10 | 0 | 10 |
| `Test Data\keyboard` | 10 | 0 | 10 |
| `Test Data\mouse` | 11 | 0 | 11 |
| `Test Data\speaker` | 11 | 0 | 11 |
| รวม | 48 | 1 | 47 |

Camera ที่ซ้ำ: `transcript_pG961MPC7bQ.md`, Video ID `pG961MPC7bQ`, Dataset **#422**, label `camera`, split `train` มีอยู่แล้ว จึงไม่นับเพิ่มแม้ไฟล์ Transcript ต่างกัน

คำว่า “ส่งเข้าคิวตรวจได้” หมายถึง format/identity/metadata ผ่านการตรวจเบื้องต้น ไม่ใช่ยืนยันว่าเนื้อหาดี label ถูก หรืออนุมัติแล้ว ทุกไฟล์ยังต้องตรวจเนื้อหาจริง ไม่มี Timestamp ให้ส่วน `Segment 1` เพราะหมายเลข Segment ไม่ใช่เวลา

## จำนวนในฐานข้อมูลกับจำนวนที่คาดหลัง Review

ข้อมูลที่ผ่าน contract ปัจจุบัน Phone **80**, Camera **74**, Laptop **85**; Unknown ที่ใช้ประเมิน **0**; คิว Review ค้างเดิม **0**

| กลุ่ม | ใช้ได้ใน DB ตอนนี้ | ไฟล์ใหม่ตาม split | เป้าปัจจุบัน | ยังขาดหากไฟล์ใหม่ผ่าน Review ทุกไฟล์ |
|---|---:|---:|---:|---:|
| Camera รวม Train/Validation/Test | 74 | 5 (3/1/1) | 80 | **1** |
| Unknown Validation | 0 | 5 จาก 5 ช่อง | 10 จากอย่างน้อย 3 ช่อง | **5** |
| Unknown Test | 0 | 2 จาก 2 ช่อง | 30 จากอย่างน้อย 3 ช่อง | **28**, ต้องมีอีกอย่างน้อย 1 ช่อง |
| Unknown ช่องฝั่ง Train | 0 | 35 จาก 21 ช่อง | ไม่ใช่ชุดประเมิน | เก็บสำรอง, ยังไม่นับ Validation/Test |

ดังนั้นจำนวนที่ขาดขั้นต่ำแบบมีเงื่อนไขคือ **34 คลิป** ไม่ใช่ให้ทิ้งไฟล์ 42 คลิปแล้วเริ่มใหม่ และไม่ใช่รับประกันว่ารวมครบแล้วโมเดลผ่าน

ตัวเลขบนหน้า Train ยังเป็นจำนวนเดิม เพราะ Phase 1 นี้ไม่ได้นำเข้าไฟล์ใหม่ ห้ามนำตัวเลขคาดการณ์ไปแสดงเป็นข้อมูลที่อนุมัติใน DB แล้ว

## ทำไม Unknown 42 จึงยังไม่ครบ Validation/Test

ระบบใช้ `channel_sha256_bucket_v2_70_15_15` กำหนดฝั่งตาม Channel ID แบบคงที่ ช่องเดียวกันต้องอยู่ฝั่งเดียว ไม่ว่าคลิปนั้นจะเป็น Phone หรือหูฟัง ชื่อโฟลเดอร์ `Test Data` จึงไม่ได้ทำให้คลิปเป็น Test อัตโนมัติ

35 คลิปอยู่ช่องฝั่ง Train ระบบปัจจุบันกันไว้เป็น `reserved_not_used` ไม่ฝึกให้เป็นหมวดที่สี่และไม่ย้ายไปเป็น Test เพราะฝั่ง Train/Validation/Test ต้องไม่ใช้ช่องซ้ำกัน การย้ายใหม่เพื่อให้ครบจำนวนต้องถือเป็นการออกแบบและประเมินใหม่ ไม่ใช่งานเติมตัวเลขใน Phase 1

Unknown Validation ใช้เลือกวิธีรับผลและเกณฑ์; Unknown Test ใช้รายงานผลหลังล็อกวิธีแล้ว ห้ามเปิดผล Test มาปรับกฎหรือ threshold

## ช่องที่ตรวจพบฝั่งถูกต้องในชุดนี้

| ชุด | ช่อง | Channel ID | Video ID ใหม่ที่พบ |
|---|---|---|---|
| Validation | yesiamdart | `UCRl23ivYSO9bUeauxpczhWg` | `C7SFF-1WP7M` |
| Validation | GU ZAP | `UCQ-6HE34kpItHWDFFZT4kCA` | `4LQe_rruRCM` |
| Validation | เสียบปลั๊ก - What the Plug | `UCOTjZo7gNiXwZyJtr2Fh_wg` | `DjjjExMR80Q` |
| Validation | IT With Somchai | `UCHv-RLqnzHA7d0YLSreGDKw` | `9y_3bF6ftug` |
| Validation | Fantech Thailand | `UCiC4yvEG3ejE_nwTdiAtExA` | `d7JOYWApaNo` |
| Test | S-DIMENSION | `UCposjF5nGLBxHYvUKak18ow` | `32tv5O0SGOA` |
| Test | TAE TESTER | `UCS675I--lxvLnN3th-Hq2_Q` | `O0XqwjgisFg` |

ตารางนี้ยืนยัน **split เท่านั้น** ไม่รับรองคุณภาพ Transcript ความเป็นอิสระ หรือแนะนำให้กระจุก 28 คลิปในช่องเดียว ควรกระจายหูฟัง/คีย์บอร์ด/เมาส์/ลำโพง หลายช่อง และตรวจว่าเป็นคลิปนอกสามหมวดจริง

ก่อนทำ Transcript เพิ่ม ให้รวบรวม URL/Channel ID แล้ว Preview ในหน้า Train หรือใช้คำสั่งเดิม:

```powershell
python scripts/plan_classification_collection.py --channel UCposjF5nGLBxHYvUKak18ow --channel UCS675I--lxvLnN3th-Hq2_Q
```

ใช้ `UC...` ของช่อง ไม่ใช่ @handle หรือ Video ID; รับได้ไม่เกิน 50 ช่องต่อครั้ง ยังไม่เขียนฐานข้อมูล ตรวจตัวอย่างใหม่ซ้ำกับ catalog ก่อนนำเข้า

## Test สำหรับพรีเซนต์ไม่ใช่แค่ Transcript

- Transcript ใหม่ของสามหมวดและ Unknown ใช้ประเมินตัวจำแนกข้อความได้ แต่ไม่ทดสอบการถอดเสียง การอัปโหลด และ UI ทั้งวงจร
- เป้าหมายคลิปใหม่ Phone/Camera/Laptop หมวดละ 10 เป็นแผนประเมินปลายทาง ไม่ใช่บอกให้ทำ Transcript เพิ่ม 30 แล้วเอาไป Train
- รอบนี้ได้ไฟล์ `.md` ไม่ได้มีวิดีโอใหม่สามหมวด/คลิปถ่ายเองสำหรับอัปโหลดตามแผน จึงยังไม่รับรองงานดังกล่าว
- Manifest เดิม `artifacts/evaluation/recommendation-utility-pending-20260930/preflight-final-v2/manifest.json` มี 4 กรณีเดิมเป็น **regression** ไม่ใช่ fresh heldout ได้แก่ Phone/หูฟัง/คีย์บอร์ด/เมาส์
- Manifest เดิมยังไม่มี YouTube/Channel ID ของคลิป regression ครบ จึงยังยืนยันไม่ได้ว่าตรงกับไฟล์ใหม่หรือไม่จากชื่อโฟลเดอร์อย่างเดียว ต้องตรวจที่มาและลงทะเบียนก่อนประเมินใหม่
- ตรวจ partition ใน DB รวม identity ที่กันไว้แล้ว ไม่พบ Video/Transcript/Channel ซ้ำข้ามชุดที่มีผลต่อข้อมูลที่เลือก และไม่พบ split assignment ผิด ข้อนี้ไม่แทนการตรวจประวัติเคยใช้แก้ระบบ

## หลักฐานและคำสั่งที่ใช้

ใต้ `artifacts/project-closeout/phase1-20261001/`:

- `new-transcripts.json`: export จาก parser เดิม 48/48 ไฟล์ผ่านรูปแบบ
- `transcript-audit.json`: audit ครั้งแรกที่ network ใน sandbox ล้มเหลว เก็บไว้เป็นบันทึก ไม่ใช้สรุป metadata
- `transcript-audit-live.json`: audit สำเร็จ, Video ID/hash/Channel ID/split และเวลาเก็บ metadata
- `readiness-inventory-v2.json`: registry ครบ 34 โมเดล, collection plan จริง, channel preview, fingerprint ก่อน/หลัง และค่าการตั้งค่าที่ใช้ตรวจ UI

```powershell
python scripts/import_notebooklm_batch.py artifacts/project-closeout/phase1-20261001/new-transcripts.json --output artifacts/project-closeout/phase1-20261001/transcript-audit-live.json --fetch-metadata
python scripts/audit_project_closeout.py --batch-audit artifacts/project-closeout/phase1-20261001/transcript-audit-live.json --output artifacts/project-closeout/phase1-20261001/readiness-inventory-v2.json
```

คำสั่งข้างต้นคือคำสั่งที่รันแล้ว ถ้ารันซ้ำต้องตั้งชื่อ output ใหม่เพราะไม่เขียนทับหลักฐานเดิม ไม่ใส่ `--apply` ในการตรวจอย่างเดียว และอย่าเผยแพร่ Transcript หรือ private credentials ใน artifacts โดยไม่ตรวจสิทธิ์
