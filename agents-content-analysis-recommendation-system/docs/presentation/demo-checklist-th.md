# เช็กลิสต์เดโม Content AI 8-10 นาที

รุ่น: `content-ai-closeout-20261002-phase6`  
URL: `http://127.0.0.1:8080/#/dashboard`

## ก่อนเริ่มเดโม

- [ ] MySQL เปิดและ `.env` ส่วนตัวอยู่เฉพาะเครื่อง ไม่แชร์หน้าจอไฟล์นี้
- [ ] รัน `python -B scripts/setup_faster_whisper.py --model small --verify-only`
- [ ] รัน `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_demo.ps1`
- [ ] รัน `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_demo_readiness.ps1`
- [ ] เปิด Dashboard, History, Admin Training และ Admin Settings อย่างละหนึ่งครั้ง
- [ ] ปิด notification popup, email, terminal ที่มี path/ข้อมูลส่วนตัว และ browser password manager
- [ ] ห้ามกด Train, Activate, Approve All หรือเปลี่ยนช่วงเก็บข้อมูลระหว่างซ้อม
- [ ] เตรียมภาพสำรองใน `artifacts/project-closeout/phase6-20261002T181200+0700/presentation-evidence/`

ถ้า launcher แจ้งพอร์ตถูกใช้ ให้หยุด service ที่ทราบเจ้าของเอง หรือใช้พอร์ตอื่นพร้อม build ที่ชี้ API ถูกต้อง ห้าม kill PID ที่ไม่ทราบที่มา

## ลำดับเดโม

### 0:00-0:45 โจทย์และสิ่งที่ผู้ใช้ได้

พูดสั้น ๆ:

> ระบบช่วยผู้สร้างคอนเทนต์ดูเทรนด์ย้อนหลังและวิเคราะห์ Transcript ของคลิป เพื่อเสนอประเด็นที่ควรพิจารณาเพิ่มพร้อมหลักฐาน ไม่ได้ทำนายว่าคลิปจะดังแน่นอน

เปิดหน้า Dashboard สาธารณะ ชี้ให้เห็นว่ายังไม่ Login ก็ดูเทรนด์ได้ แต่ Upload/History ต้อง Login

### 0:45-3:00 Dashboard

1. เปิดแท็บ YouTube แสดงการ์ดภาพปก ช่อง ยอดวิว ความยาวและอันดับ
2. กด “ดูเพิ่มเติม” ให้เห็นว่าโหลด 24 จาก 50 แล้วเพิ่มรายการได้
3. เลือกหมวด ให้เห็นว่าอันดับเริ่ม #1 ภายในหมวด ไม่ใช่อันดับรวม
4. เปิดรายละเอียดคลิปและกราฟย้อนหลัง กดตาราง “ข้อมูลที่ใช้วาดกราฟ”
5. ชี้ช่วงข้อมูลขาดและอธิบายว่าไม่ลากเส้นหลอก
6. เปิด Google และอธิบายว่าจำนวนค้นหาไม่เอาไปรวมกับยอดวิว YouTube

ประโยคตอบเรื่องรอบข้อมูล:

> หน้าเว็บอ่าน Database ทุก 60 วินาที แต่ provider collection รุ่นนี้ทำชั่วโมงละครั้ง 10 รอบช่วงบ่ายสองถึงเที่ยงคืน เพื่อลด quota การอ่านหน้าเว็บจึงไม่เรียก YouTube API ซ้ำ

### 3:00-5:15 Analysis และหลักฐาน

1. Login ด้วยบัญชีสาธิตส่วนตัวโดยไม่เปิดเผยรหัสผ่าน
2. เปิด “วิเคราะห์คลิปของฉัน” ชี้ max 300 วินาที, Whisper small และ Hook 60 วินาที
3. อธิบาย flow: upload -> ASR -> transcript -> features -> classification acceptance -> same-category reference -> topic gap -> advice/evidence/duration -> save
4. เปิดผลเก่าจาก History เพื่อสาธิตโครงสร้างหน้าผล โดยพูดชัดว่าเป็น **ผลที่บันทึกไว้ก่อน freeze ไม่ใช่ positive run ใหม่ของรุ่นนี้**
5. เปิด Admin Training ให้เห็นข้อความว่า Active Model ยังไม่พร้อมให้คำแนะนำเฉพาะหมวด

สิ่งที่ต้องพูดตรง ๆ:

> รุ่นส่งปัจจุบัน fail closed เพราะโมเดลยังไม่มี Unknown scope policy ที่ผ่าน Validation ดังนั้นผมไม่ใช้ภาพเก่ามาอ้างว่า Analyze ใหม่ผ่าน จุดนี้เป็น release blocker ที่รายงานไว้ ไม่ใช่ UI bug

Unknown/หลักฐานไม่พอ:

> ถ้าระบบไม่ยอมรับหมวด, ASR ล้ม หรือคลิปอ้างอิงไม่พอ ระบบต้องบอกสาเหตุและงดคำแนะนำ ไม่เลือก Dataset หมวดอื่นมาทดแทน

### 5:15-6:45 Training และ Metrics

เปิด Admin Training แล้วอธิบาย:

- Train/Validation/Test แยกตามช่องเพื่อไม่ให้สำนวนช่องเดียวกันรั่วข้ามชุด
- Validation ใช้เลือกวิธีและ threshold; Test ใช้ประเมินครั้งสุดท้าย
- Accuracy ดูภาพรวม, Recall บอกว่าหมวดนั้นจับได้กี่ส่วน, Macro F1 ให้ทุกหมวดน้ำหนักเท่ากัน, Confidence เป็นค่าต่อคลิปไม่ใช่ความแม่นระบบ
- Validation เดิม Laptop Recall 40% จึงเป็นหลักฐานว่าต้องเพิ่ม hard cases ไม่ควรพูดเพียง Test เดิม 100%

### 6:45-8:00 Admin และ Database

เปิดเมนู Admin ตามเวลา:

1. Dataset Review: Candidate ต้องมีคนตรวจ
2. Dataset: แก้/ทิ้ง/กู้ได้ แต่โมเดลเดิมไม่ retrain เอง
3. Analysis Settings: ค่าที่ Backend ใช้จริง
4. Logs: audit event ที่บันทึกไว้ ไม่ใช่ตัวจับ bug ทุกชนิด

สรุปตารางสำคัญ: `dataset_contents` เป็นข้อมูลอ้างอิงที่ approve, `classification_models` เก็บ artifact/version, `user_contents` และ `analysis_results` เก็บผลผู้ใช้, `trend_snapshot_*` และ `trend_history_*` เก็บเทรนด์หลายเวลา

### 8:00-9:00 ผลตรวจและข้อจำกัด

- Software: Backend 480 tests, Flutter 125 tests, browser 6/6 กลุ่ม
- Model: ไม่มี fresh heldout รอบส่ง จึงไม่ประกาศ accuracy ใหม่
- Utility: ไม่มีผู้ประเมินจริงครบ จึงไม่อ้างว่าคำแนะนำเพิ่ม Engagement
- Git worktree metadata เสีย รุ่นส่งจึงระบุด้วย checksum/manifest แทน commit

ปิดด้วย:

> สิ่งที่ระบบพิสูจน์ได้ตอนนี้คือ workflow และหลักฐานย้อนกลับ ส่วนคุณภาพโมเดลกับประโยชน์ของคำแนะนำยังแยกเป็นงานประเมินที่ไม่ควรแต่งผลให้ผ่าน

## แผนสำรองเมื่อ API หรืออินเทอร์เน็ตไม่พร้อม

ใช้เฉพาะภาพจาก release browser รอบ `r10` ซึ่งเป็นข้อมูลจริงที่เก็บวันที่ 2 ตุลาคม 2026:

- `dashboard-youtube-more.png`: 24/50 และอันดับ YouTube
- `dashboard-history.png`: กราฟ/สัดส่วนพร้อมช่วงข้อมูล
- `dashboard-history-evidence.png`: ตารางตัวเลขต้นทาง
- `dashboard-google.png`: Google แยกแพลตฟอร์ม
- `admin-training-blocked.png`: Active Model blocked
- `saved-result-historical.png`: ผลเก่าที่เปิดจาก History ต้องติดป้าย Historical saved result

ห้ามเรียกภาพสำรองว่า live หาก provider ไม่ตอบในวันพรีเซนต์ และห้ามใช้ artifact preview/fixture โดยไม่ติดป้าย

## คำถามที่อาจารย์น่าจะถาม

### ทำไมเก็บ YouTube หมวดละ 50

YouTube `videos.list chart=mostPopular` คืนได้สูงสุด 50 ต่อ request ระบบใช้ค่านี้เป็นขอบเขตรายการของ provider ไม่ใช่ sample size ที่พิสูจน์ทางสถิติ กราฟสัดส่วนใช้เฉพาะอันดับรวม ไม่เอาการขอ 50 ต่อหมวดมาสรุปว่าหมวดหนึ่งนิยมกว่าอีกหมวด

### Normalize แล้วเทียบยอดวิวกับยอดค้นหาหรือไม่

ไม่เทียบ Normalize เพียงจัดชื่อ field กลางเพื่อเก็บ/แสดงผล แพลตฟอร์มและหน่วยยังติดมากับแต่ละรายการ จึงแยกแท็บและอันดับ

### รู้ได้อย่างไรว่าอันดับขึ้น

เทียบ snapshot ก่อนหน้าใน platform/region/ranking scope เดียวกัน ใช้ `อันดับเก่า - อันดับใหม่` และไม่เทียบข้ามหมวดหรือข้ามแพลตฟอร์ม

### ทำไมข้อมูลไม่เปลี่ยนทุก 60 วินาที

60 วินาทีคือ browser poll ฐานข้อมูล รอบ collection จริงคือชั่วโมงละครั้ง ข้อมูลจะเปลี่ยนเมื่อ provider ส่งอันดับใหม่ ไม่ใช่ทุกครั้งที่หน้าเว็บอ่าน

### AI ใช้อะไรจำแนกหมวด

ใช้ TF-IDF จากคำและกลุ่มตัวอักษรใน Transcript แล้วส่งให้ classifier ยอดวิว/ไลก์ไม่ใช่ feature จำแนก แต่ใช้เป็น metadata ของหลักฐานแนะนำ

### Confidence 98% แปลว่าแม่น 98% หรือไม่

ไม่ใช่ เป็นความมั่นใจต่อ input หนึ่งตามโมเดล ต้องใช้ชุด Test ที่มีคำตอบจริงเพื่อคำนวณ Accuracy/F1/Recall

### แนะนำ keyword แล้วพิสูจน์ยอดเพิ่มได้หรือไม่

ยังพิสูจน์เหตุและผลไม่ได้ ระบบบอกได้ว่าหัวข้อนั้นพบในคลิปอ้างอิงและกลุ่มมีสถิติอย่างไร ต้องทดลองเผยแพร่หรือทำ user study เพิ่มก่อนอ้างว่า Engagement เพิ่ม

### แก้ Dataset แล้วโมเดลเปลี่ยนทันทีหรือไม่

ไม่เปลี่ยน Artifact เก่าถูก freeze ต้อง train/evaluate candidate ใหม่และ Admin activate แบบ manual

### Log ใช้หา bug ทุกอย่างได้หรือไม่

ไม่ได้ Log ครอบคลุม event ที่ Backend เรียกบันทึก เช่น provider/import/admin operation ส่วน Browser error, OS error และ stack trace บางชนิดต้องดู log process แยก

### ทำไมไม่เปิด Analysis ให้เดโมทั้งที่โมเดลมีคะแนน

เพราะคะแนนเดิมไม่มี Unknown rejection policy ที่ผ่าน Validation การเปิดใช้จะเสี่ยงเอาหูฟัง/เมาส์ไปแนะนำด้วย Dataset Phone ระบบจึง fail closed ตามเกณฑ์ที่ตั้งก่อนเห็นผล

## หลังเดโม

- [ ] รัน `scripts/stop_demo.ps1`
- [ ] อย่าลบ backup/model/history artifacts
- [ ] บันทึกคำถามที่ตอบไม่ได้เป็น backlog หลังส่ง ไม่แก้โมเดลสดระหว่างวันพรีเซนต์
