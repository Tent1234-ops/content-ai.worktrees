# ขอบเขตรุ่นส่งและสถานะตรวจรับ

ตรวจโค้ดและข้อมูล 1 ตุลาคม 2026 อัปเดตหลักฐาน workflow จาก Closeout Phase 3 และ freeze รุ่นส่งใน Closeout Phase 6 วันที่ 2 ตุลาคม 2026

หลักฐานการใช้งานจริงเดิม: [acceptance-20260930.md](acceptance-20260930.md)
หลักฐานตรวจฐานข้อมูลรอบนี้: `artifacts/project-closeout/phase1-20261001/readiness-inventory-v2.json`
สถานะ “ผ่านเส้นทางเดิม” ไม่ใช่รับรองทุกกรณี และไม่ใช่ผลประเมินคลิปใหม่

## ตารางขอบเขต

| ข้อ | หน้า | API หลัก | ข้อมูล | ทำแล้ว/สถานะ | ขาดหรือข้อจำกัด | เกณฑ์ตรวจรับรุ่นส่ง | ผู้ตัดสินใจ |
|---|---|---|---|---|---|---|---|
| 1 สมัครสมาชิก | `/register` | POST `/auth/register` | users | ผ่านเส้นทางเว็บเดิม | ตรวจซ้ำหลัง UI สุดท้าย | สมัครได้, ชื่อ/อีเมลซ้ำถูกปฏิเสธ, ไม่สมัครเป็น Admin เอง | เจ้าของโครงการตรวจรับ |
| 2 Login | `/login` | POST `/auth/login`, GET `/auth/me` | users, sessions | ผ่าน User/Admin, กัน Guest | ตรวจซ้ำหลัง UI สุดท้าย | Login/Logout และสิทธิ์ข้ามบัญชีถูกต้อง | เจ้าของโครงการ |
| 3 อัปโหลด | `/upload` | GET `/analyze/settings`, POST `/analyze/save` | user_contents, jobs, settings snapshot | อัปโหลดคลิปจริงจบ, ไฟล์เสียถูกปฏิเสธ | ไม่ใช่ผลความแม่น, รุ่นใหม่ยังไม่ประเมิน | งานสำเร็จ/ผิดพลาด/เกินระยะเวลาชัดเจน, ใช้ค่าฝั่ง Server | เจ้าของโครงการ |
| 4.1 คำแนะนำ | `/result` | POST `/analyze/save`, GET `/contents/{id}` | analysis_results, recommendations, dataset_contents | มีบริการหลักฐาน/แนวทางภาษาไทยและบันทึกผล | **ยังไม่ผ่านใช้งานเชิงบวก**: Active #14 ไม่มี scope policy จึงงดแนะนำ | คลิปที่ผ่านหมวดมีคำแนะนำมีหลักฐาน, ไม่ผิดหมวด/ซ้ำ, Unknown งดแนะนำ | เจ้าของโครงการ; ข้อมูลและผู้ประเมินจำเป็น |
| 4.2 ความยาว | `/result` | ผลจาก API วิเคราะห์เดียวกัน | metadata/duration ของคลิปอ้างอิง | มี median/percentile และ insufficient evidence | รอบตรวจเดิมถูกกั้นโดย Unknown, ยังไม่ยืนยัน output เชิงบวก | แสดงจำนวนตัวอย่าง/เวลา/ช่วงได้; หลักฐานน้อยต้องไม่แต่งตัวเลข | เจ้าของโครงการ |
| 4.3 Hook | `/result` | ผลจาก API วิเคราะห์เดียวกัน | timed user transcript, reference evidence | แยกสิ่งที่พบกับสิ่งที่เสนอแล้ว | รอบเดิมมี Hook Terms แต่ไม่มีคำแนะนำเพราะ Unknown | ไม่เรียกคำที่ตรวจพบว่าคำแนะนำ, ไม่สร้างเวลาให้ข้อความไม่มีเวลา | เจ้าของโครงการ |
| 5 Dashboard | `/dashboard` สาธารณะ | `/dashboard/public/trends`, `/dashboard/public/history` และรายละเอียด | trend_snapshot_runs/items, hourly history | มีการ์ด/กราฟ/รายละเอียด YouTube และ Google | ช่องว่างข้อมูลยังมีจริง, TikTok ไม่มี provider | แยกหน่วย/อันดับ/หมวด, ไม่ต่อเส้นผ่านช่วงหายหรือใช้ 50 รายหมวดเป็นความนิยม | เจ้าของโครงการ |
| 6 รายการไอเดีย | `/history`, `/result` | `/contents/my`, `/contents/{id}`, GET/PUT `/contents/{id}/revision-plan` | user_contents, analysis_results, revision plans | บันทึกและเปิดหลัง Restart ผ่านเดิม | ตรวจข้อแนะนำแบบเลือกนำไปปรับหลังโมเดลพร้อม | เปิดผลเก่าได้ไม่เปลี่ยนเงียบ, บันทึกพลาดไม่แจ้งสำเร็จ | เจ้าของโครงการ |
| 7 สถิติย้อนหลัง | `/history` | `/contents/statistics` | user_contents, analysis_results | มีรายวัน/รายเดือนและแยกบัญชี | เก็บ UI รุ่นสุดท้าย | นับตรงผลจริง, ไม่มีข้อมูลเป็นสถานะที่ถูกต้อง, ไม่เห็นข้อมูลผู้อื่น | เจ้าของโครงการ |
| 8 ติดตามกลุ่ม | Dashboard ส่วนติดตาม | `/follows/topics`, `/follows/topic`, `/follows/preferences` | followed_topics, preferences | ผ่าน UI/fixture: ติดตามหมวด YouTube, เปิดหน้าคืนแล้วยังคงอยู่, กันซ้ำ, เลิกติดตาม และแยกบัญชี | Google ไม่มีหมวดเทียบเท่า; รอบนี้ไม่เพิ่ม keyword follow จาก Transcript | ติดตาม/เปิดคืน/เลิกติดตามได้จริง ไม่ถือคำว่า Search Trends เป็นหมวดสินค้า | เจ้าของโครงการ |
| 9 แจ้งเตือน | Dashboard/กระดิ่ง | `/notifications/`, `/notifications/mark_read` | notifications, watch sessions, snapshots | ผ่าน deterministic DB fixture: โหมด all/following/off, platform/scope/category, dedup, unread/read และสิทธิ์เจ้าของ | **ยังไม่ได้ยืนยัน delivery จากเหตุการณ์ provider ใหม่จริงระหว่างตรวจ** | เกิด Snapshot ใหม่ตามความสนใจแล้วแจ้งครั้งเดียว, อ่านแล้วจำสถานะ | เจ้าของโครงการ |
| 10 Admin Login | `/login` และหน้า Admin ทั้ง 7 | `/auth/*`, `/admin/me` | users, sessions | ผ่านสิทธิ์ User/Admin | ไม่มี Console ตามที่เคยให้เอาออก | API และหน้าเว็บกันผู้ไม่มีสิทธิ์, ไม่สร้าง Console เพิ่ม | เจ้าของโครงการ |
| 11 จัดการข้อมูลต้นแบบ | `/admin-transcript-import`, `/admin-dataset-review`, `/admin-datasets` | `/admin/dataset-review/*`, `/admin/datasets`, `/admin/reference-statistics/*` | dataset_contents, collection runs, review events, statistics history | ผ่าน CRUD UI บนแถวทดสอบนอก Train/Reference; Backend สร้าง hash/taxonomy, มี confirmation/audit; review/import/approve all ผ่าน fixture | Transcript ยังนำเข้าและตรวจด้วยคน ไม่ใช่นำเข้าอัตโนมัติเต็มกระบวนการ; ไม่ได้อนุมัติ 42 รายการจริงที่ค้าง | ตรวจและอนุมัติ, กันซ้ำ/ข้อมูลรั่ว, ลบแล้วไม่ถูกใช้อ้างอิง, กู้คืนไม่ข้ามข้อห้าม | เจ้าของโครงการ+อาจารย์เรื่องข้อความรายงาน |
| 12 ตั้งรอบเก็บ | `/admin-analysis-settings` แท็บอัปเดตเทรนด์ | `/admin/trend-settings` และ Scheduler API ใน panel | system_configs, scheduled collection slots | ผ่าน logic due/not-due/dedup/error fixture และติดตั้ง Windows Task `ContentAI-Trends-D33AFF90B7` แบบ `pythonw.exe`; manual run exit 0 | ไม่เรียก provider สดเพิ่มในรอบ Phase 3; คง 14:00–23:00 วันละ 10 รอบ | เปลี่ยนค่าแล้วรอบใหม่ใช้จริง, Restart จำค่า, งานรันซ่อนหน้าต่าง | เจ้าของโครงการ |
| 13 ผลโมเดลจัดกลุ่ม | `/admin-training` เป็น **Classification** | `/admin/training`, `/admin/training/models/{id}`; `/admin/clusters/runs` เป็น legacy | classification_models, model_evaluation_metrics; cluster_runs เดิม | มี Train/ผลประเมิน/เปิดใช้แบบมีเกณฑ์ | **ยังไม่ตรงคำว่า Clustering**: ไม่มีหน้าผลจัดกลุ่มปัจจุบัน; Phase 1 เพิ่ม readiness ตาม runtime | ตกลงใช้ผลจำแนกหมวดในรายงานหรือกำหนดงาน Clustering จริง ไม่เปลี่ยนชื่อหลอก | เจ้าของโครงการ+อาจารย์ |
| 14 Logs | `/admin-logs` | `/admin/logs` | system_logs | ชื่อเหตุการณ์ไทย เวลา ผู้กระทำ สถานะ และ sanitize detail ก่อนแสดง | Logs ไม่ใช่จับทุก Browser/OS bug; audit ต้นฉบับยังเก็บใน DB ตามเดิม | ดึงข้อมูลสำเร็จและล้มเหลวมีเหตุผล/เวลา, กรองได้, ไม่แสดง SQL trace/session/API key | เจ้าของโครงการ |
| 15 พารามิเตอร์ | `/admin-analysis-settings` | GET/PUT `/admin/analysis-settings`, GET `/analyze/settings` | system_configs, settings snapshots | ความยาวอัปโหลด/Whisper ที่ติดตั้ง/ระยะ Hook ใช้ค่าจริงและจำหลัง Restart | จำนวน Keywords เคยยกเลิกใน UI, จึงยังไม่ตรงรายงานข้อ 6.1 | ยืนยันแก้รายงาน; หากคงไว้ต้องเป็นจำนวนคำดิบที่แสดง ไม่ตัดการสกัด/หลักฐาน | เจ้าของโครงการ+อาจารย์ |
| 16 สถิติรวมผู้ใช้ | `/admin-users` | `/admin/usage-statistics` และ User Management API | users, user_contents, analysis_results | มีจำนวนผล/สถิติรวมและรายละเอียดผู้ใช้ | ตรวจรูปแบบตาราง/กราฟท้ายรอบ | ตัวเลขตรงฐานข้อมูล, ผู้ใช้ทั่วไปอ่านสถิติ Admin ไม่ได้ | เจ้าของโครงการ |
| 17 รายงานเทรนด์ | Dashboard ปัจจุบัน | `/dashboard/public/history`, `/dashboard/summary` | snapshot/hourly aggregate | มีกราฟย้อนหลังใช้ข้อมูลจริง | ยังไม่มีรายงาน Admin โดยเฉพาะ; `/admin/reports/overview` เก่านับ Dataset/Logs ไม่ใช่รายงานเทรนด์ | ยืนยันใช้ Dashboard เป็นรายงาน หรือเพิ่ม view อ่านอย่างเดียว reuse บริการเดิม | เจ้าของโครงการ+อาจารย์ |
| 18 เปรียบเทียบแพลตฟอร์ม | Dashboard แยก Tabs | public trends/history แยก platform | YouTube snapshots, Google snapshots | มี YouTube/Google แยกกัน | **ยังไม่ครบข้อความเดิม**: TikTok ว่าง ไม่มีรายงานเปรียบเทียบข้ามแพลตฟอร์ม | ยืนยันเปลี่ยนขอบเขตก่อน; หากเทียบ YT/Google ใช้เวลาเดียวกันแต่ไม่รวมอันดับ/หน่วย | เจ้าของโครงการ+อาจารย์ |

## ข้อเสนอเปลี่ยนรายงาน

ยังไม่ได้รับคำยืนยันอาจารย์ในรอบนี้ ไม่มีข้อใดถูกประกาศว่าเปลี่ยนแล้ว

| ข้อ | ข้อเสนอ | สถานะ | หลักฐานคำยืนยัน |
|---|---|---|---|
| 11 | Transcript นำเข้า/Review ด้วยคน, สถิติและ metadata อัปเดตอัตโนมัติ | pending | มี workflow จริง แต่ยังไม่มีคำยืนยันเปลี่ยนข้อความรายงาน |
| 13 | “ผลประเมินโมเดลจำแนกหมวดและการปฏิเสธนอกขอบเขต” แทน “จัดกลุ่ม” | pending | ถามเจ้าของโครงการแล้ว ยังรอคำตอบ |
| 15 | ตัดการตั้งจำนวน Keywords หรือจำกัดเฉพาะการแสดงคำดิบ | pending | ผู้ใช้เคยให้เอา UI ออก ไม่เท่ากับอาจารย์อนุมัติขอบเขตใหม่ |
| 17 | ใช้ Dashboard เป็นรายงานเทรนด์ หรือ view Admin แบบอ่านอย่างเดียว | pending | ยังไม่มีคำตัดสินว่าต้องมีหน้าแยก |
| 18 | YouTube/Google คนละหน่วย, ไม่พัฒนา TikTok ในรุ่นส่ง | pending | ถามเจ้าของโครงการแล้ว ยังรอคำตอบ |

## ลำดับก่อนปิดพัฒนา 2 ตุลาคม

1. ต้องแก้: เส้นทาง Analysis ที่ถูก scope policy กั้น พร้อมข้อมูลตาม split และประเมินตามเกณฑ์เดิม เจ้าของโครงการต้องตรวจ/อนุมัติข้อมูล; ห้ามแก้ด้วยลด threshold หรือปิด Unknown
2. ต้องตัดสินใจ: ขอบเขต 11/13/15/17/18 ให้เจ้าของโครงการตกลงอาจารย์; ถ้าไม่ยืนยันให้รายงานเป็น gap ตามจริง
3. ต้องตรวจ: Notification หลังติดตาม, Scheduler หลังแก้เวลา, Import/Review และ Dataset restore ผ่าน UI จริง, ผลวิเคราะห์เชิงบวกและบันทึกกลับ
4. แล้วจึงเก็บ UI: ชื่อ/ข้อความ/ตาราง/ระยะห่าง/สถานะโหลดและผิดพลาด โดยไม่เปิดงานแพลตฟอร์มหรือโมเดลใหญ่ใหม่
5. เลื่อนได้เมื่อเวลาจำกัด: TikTok/Instagram, รายงานใหม่ที่ซ้ำ Dashboard, ฟีเจอร์นอกขอบเขตรุ่นส่ง

3–4 ตุลาคมกันไว้เรียนรู้ระบบ ซ้อมและรวบรวมหลักฐาน ไม่ใช้วันดังกล่าวแอบเพิ่มฟีเจอร์หลัก วันที่ส่ง 5 ตุลาคม 2026

## สถานะ Freeze วันที่ 2 ตุลาคม 2026

- รุ่นส่งคือ `content-ai-closeout-20261002-phase6`; Git identity ใช้ไม่ได้เพราะ worktree metadata เสีย จึงอ้าง `release-manifest.json` และ checksum แทน
- สถานะทุกข้อยังตรงกับตารางและ Final Acceptance ไม่มีการลบข้อ 4.1-4.3 หรือข้อ pending 11/13/15/17/18 เพื่อให้รายงานดูผ่าน
- หลัง freeze ห้าม Train, Activate, Approve All, เปลี่ยน Unknown threshold, collection interval หรือ random seeds ระหว่างซ้อม
- Software restart/backup/restore ผ่านตาม Phase 6 แต่ AI positive flow, fresh heldout และ human utility ยัง blocked/not evaluated
- หลักฐานรุ่นส่ง: `artifacts/project-closeout/phase6-20261002T181200+0700/release-manifest.json`
