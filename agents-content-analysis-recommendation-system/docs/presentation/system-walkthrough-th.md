# คู่มือทำความเข้าใจระบบ Content AI

> มีคู่มือแบบแยกหน้าที่อัปเดตหลังเพิ่มข้อมูลและเทรนวันที่ 3 ต.ค. 2026 แล้ว: [อ่านฉบับปัจจุบัน](current-system/README.md) ข้อมูลจำนวนตัวอย่างและสถานะด้านล่างเป็นของรุ่นวันที่ 2 ต.ค.

รุ่นอ้างอิง: `content-ai-closeout-20261002-phase6`  
สถานะวันที่ 2 ตุลาคม 2026: Software workflows ส่วนใหญ่พร้อมสาธิต แต่คำแนะนำจากคลิปใหม่ยังถูกงด เพราะ Active Classification Model ไม่มี Unknown scope policy ที่ผ่านการประเมิน

## 1. ระบบแก้ปัญหาอะไร

ระบบมีงานหลักสองส่วนที่ไม่ควรอธิบายรวมกัน:

1. **Dashboard เทรนด์** ช่วยตอบว่า ณ รอบข้อมูลที่ระบบเก็บไว้ มีวิดีโอหรือคำค้นใดอยู่ในอันดับของแต่ละแพลตฟอร์ม อันดับเปลี่ยนอย่างไร และข้อมูลช่วงใดหายไป
2. **วิเคราะห์คลิปของผู้ใช้** ถอดเสียง จำแนกหมวด แล้วเปรียบเทียบเนื้อหากับคลิปอ้างอิงที่ผ่านการตรวจ เพื่อเสนอประเด็นที่ควรพิจารณาเพิ่มพร้อมหลักฐาน

ความต่างจากการเปิด YouTube โดยตรงคือระบบเก็บ Snapshot หลายเวลา ทำกราฟย้อนหลัง แยกอันดับรวม/รายหมวด และเชื่อม Transcript กับ Dataset อ้างอิง แต่ระบบไม่ได้รู้เหตุผลที่คลิปดังทั้งหมด และไม่รับประกันว่าทำตามคำแนะนำแล้ว Engagement จะเพิ่ม

โค้ดหน้าหลักอยู่ที่ `frontend_flutter/lib/screens/dashboard_screen.dart`, `upload_screen.dart`, `result_screen.dart` และ route อยู่ใน `frontend_flutter/lib/routing/app_router.dart`

## 2. Dashboard ตั้งแต่แหล่งข้อมูลถึงกราฟ

### 2.1 การไหลของข้อมูล

```text
YouTube / Google
  -> ดึงข้อมูลตามรอบ
  -> แปลงชื่อ field ให้ระบบจัดเก็บได้
  -> trend_snapshot_runs + trend_snapshot_items
  -> สรุป trend_history_buckets
  -> Dashboard API
  -> Browser อ่าน DB ทุก 60 วินาที
```

- YouTube ใช้รายการจัดอันดับจาก provider และเก็บอันดับรวมกับอันดับ `category:<id>` แยกกัน
- Google เก็บคำค้นและค่าปริมาณค้นหาที่ provider ส่งมา ไม่เอายอดค้นหา Google ไปเทียบเป็นหน่วยเดียวกับยอดวิว YouTube
- `app/services/trending_fetcher.py::_normalize_trend_item()` ทำ **schema normalization** เช่นใช้ field กลาง `title`, `platform`, `rank` และ `captured_at` ไม่ได้ทำให้ `views` กับ `search_volume` กลายเป็นตัวเลขชนิดเดียวกัน
- `app/services/live_trend_snapshots.py` บันทึก snapshot และ `app/services/trend_history.py::archive_snapshot_run()` เก็บประวัติที่ยังอยู่หลัง raw snapshot ถูกลดจำนวน
- `app/routes/dashboard.py` ให้ endpoint `/dashboard/public/trends`, `/dashboard/public/youtube/categories` และ `/dashboard/public/history`

### 2.2 รอบเก็บข้อมูลกับรอบหน้าเว็บ

สองรอบนี้เป็นคนละอย่าง:

- Browser poll: `dashboard_screen.dart` ใช้ `Timer.periodic(Duration(seconds: 60))` เพื่ออ่านค่าล่าสุดจาก Backend/Database ไม่เรียก provider ทุกครั้ง
- Collection schedule รุ่นส่ง: ชั่วโมงละครั้ง 10 รอบ ระหว่าง 14:00-23:00 Asia/Bangkok ค่าจริงอ่านจาก `app/services/trend_settings.py::trend_schedule()` และ Admin settings
- Windows Task ใช้ `pythonw.exe` เพื่อไม่ให้ terminal เด้ง รายละเอียดอยู่ใน `scripts/run_trend_scheduler.py` และ `scripts/install_trend_scheduler.ps1`

ดังนั้นคำว่า “อัปเดตทุก 60 วินาที” บนหน้าเว็บหมายถึงตรวจ DB ทุก 60 วินาที ไม่ได้หมายถึงใช้ YouTube quota ทุก 60 วินาที

### 2.3 อันดับขึ้นลงและช่วงข้อมูลขาด

- อันดับใหม่เทียบกับ snapshot ก่อนหน้าที่มี `platform`, `region` และ `ranking_scope` เดียวกัน
- สูตรอันดับขยับ = `อันดับเก่า - อันดับใหม่` เพราะเลขอันดับน้อยกว่าดีกว่า เช่น จาก #10 เป็น #4 ได้ `10 - 4 = +6`
- อันดับรายหมวดไม่เทียบกับอันดับรวม และ YouTube ไม่แย่งอันดับกับ Google
- กราฟสร้างจุดขาดเมื่อไม่มี observation จริง ไม่ลากเส้นข้ามช่วงว่าง โค้ด UI ใช้ `FlSpot.nullSpot` ใน `frontend_flutter/lib/widgets/trend_history_panel.dart`

### 2.4 Notification

`app/services/live_trend_notifications.py::compare_live_trend_snapshot()` เทียบ baseline ของ watch session กับ snapshot ใหม่ แล้วสร้างแจ้งเตือนสำหรับรายการใหม่ตามโหมดและหมวดที่ติดตาม การเปิด Dashboard ไม่ได้แปลว่าทุก 60 วินาทีจะมีแจ้งเตือน ต้องมี snapshot ใหม่ที่เข้าเงื่อนไขจริง ตารางหลักคือ `user_trend_watch_sessions`, `followed_topics` และ `notifications`

## 3. Analysis ตั้งแต่อัปโหลดถึงบันทึกผล

```text
ตรวจไฟล์/ความยาว
  -> แยกเสียงและ Faster Whisper
  -> Raw transcript + Cleaned transcript + Timestamp segments
  -> สกัด feature จากข้อความ
  -> Active Model จำแนก Phone/Camera/Laptop
  -> Acceptance ตรวจ confidence และ Unknown policy
  -> เลือก Dataset หมวดเดียวกัน
  -> หาเรื่องที่พูดแล้ว/ยังไม่พบ/ตรวจไม่ได้
  -> คำแนะนำ + หลักฐาน + ช่วงความยาว
  -> ผู้ใช้เลือกแผนและบันทึก
```

### 3.1 Upload และ ASR

- `app/routes/analyze.py::_save_validated_upload()` ตรวจไฟล์และระยะสูงสุดจาก Server settings
- Endpoint หลักคือ `POST /analyze/save`; หน้าเว็บเรียกจาก `frontend_flutter/lib/screens/upload_screen.dart`
- `models/speech_to_text.py` ใช้ Faster Whisper ตามรุ่นที่ตั้งไว้ ปัจจุบันคือ `small`
- Transcript เก็บทั้ง raw, cleaned และ segments การ normalize แก้เฉพาะศัพท์ที่มีหลักฐาน ไม่เขียน Transcript ทั้งก้อนใหม่
- หาก ASR ล้มเหลว สถานะคือ “ตรวจไม่ได้” ไม่ใช่ “ผู้ใช้ไม่ได้พูดหัวข้อนั้น”

### 3.2 Feature และ Classification

Feature ของโมเดลปัจจุบันมาจากข้อความ เช่นคำและกลุ่มตัวอักษรที่ TF-IDF ให้น้ำหนัก ไม่ได้ใช้ยอดวิวหรือยอดไลก์เป็น feature จำแนกหมวด `app/services/classification.py::classify_text_domain()` โหลด Active Model และเป็นจุดตัดสินหมวดเดียว

Acceptance มีหน้าที่แยก “โมเดลทายอะไร” ออกจาก “ระบบยอมรับผลหรือไม่” ถ้า scope policy ไม่พร้อม ระบบต้องคืน Unknown/งดคำแนะนำเฉพาะหมวด ไม่ให้ keyword rule ทายทับ ปัจจุบัน Active Model #14 โหลดได้ แต่ `scope_policy_missing` จึง `can_accept_predictions=false`

### 3.3 Keyword และ Topic Gap

- `app/services/nlp.py::run_nlp_pipeline()` สกัดคำจาก Transcript
- `extract_comparable_keyword_candidates()` รวมคำพ้องเป็นแนวคิดมาตรฐานสำหรับเทียบ Dataset
- `app/services/recommendation.py::build_recommendation_from_analysis_data()` เลือกคลิปอ้างอิงหมวดเดียวกับ classification ที่ได้รับการยอมรับ
- `app/services/recommendation_evidence.py` เก็บข้อความต้นทาง, Dataset ID, video/channel, วันที่เผยแพร่, วันที่เก็บสถิติ และ Timestamp เมื่อมีจริง
- “ยังไม่ตรวจพบ” ต่างจาก “ตรวจไม่ได้” และระบบห้ามสร้าง Timestamp ให้ Transcript ที่ไม่มีเวลา

### 3.4 คำแนะนำและความยาว

`app/services/actionable_recommendations.py::build_actionable_recommendations()` เปลี่ยน topic gap เป็นสิ่งที่ทำต่อได้: สิ่งที่พบ, สิ่งที่เสนอ, วิธีเพิ่มเนื้อหา, ตัวอย่างประโยค และเหตุผล จำกัด 2-3 ข้อที่สำคัญโดยไม่จำกัดจำนวนคำที่สกัด

หลักฐานเชิงเปรียบเทียบใน `app/services/topic_comparisons.py` แบ่งคลิปที่พูดถึง/ไม่พูดถึงหัวข้อใน cohort ที่พอเทียบกันได้ รายงานค่ากลาง จำนวนวิดีโอ จำนวนช่อง และความไม่แน่นอน ถ้าตัวอย่างน้อยจะใช้เพียง “พบในคลิปอ้างอิง” ไม่อ้างความต่าง

Recommended Duration ใช้ median และ P25-P75 จากคลิปหมวดเดียวกันที่มี metadata พอ ถ้าน้อยกว่าเกณฑ์ต้องแสดงหลักฐานไม่เพียงพอ ไม่สร้างตัวเลขให้ดูแม่น

### 3.5 Save, Plan และ Revision

- `app/services/persistence.py::save_video_analysis_result()` บันทึกผลและ snapshot ของ settings/model/method ณ เวลานั้น
- `GET/PUT /contents/{content_id}/revision-plan` เก็บข้อที่ผู้ใช้เลือกว่าจะนำไปปรับ
- `app/services/revision_comparisons.py::create_revision_job()` เชื่อมไฟล์แก้ไขกับ parent/plan เดิม
- การเปรียบเทียบเรียกว่า “การเปลี่ยนแปลงเนื้อหา” ไม่ใช่คะแนนว่าฉบับใหม่จะดังขึ้น
- ผลเก่าต้องเปิดจาก payload ที่บันทึกไว้ ไม่คำนวณทับด้วย Dataset ปัจจุบันอย่างเงียบ ๆ

## 4. การ Train Classification Model

### 4.1 ลำดับข้อมูล

```text
Transcript + human-reviewed taxonomy label + Channel ID
  -> ตรวจ eligibility
  -> แบ่ง Train / Validation / Test ตาม Channel
  -> สร้าง TF-IDF features
  -> Fit candidate models
  -> Validation เลือกวิธีและ threshold
  -> Test ประเมินครั้งสุดท้าย
  -> model.joblib + evaluation.json + metrics ใน DB
  -> Admin Activate แบบ manual เมื่อผ่าน gate
```

- Dataset readiness อยู่ใน `app/services/model_management.py::training_dataset()`
- การแยกช่องและตรวจ leakage อยู่ใน `app/services/classification_training.py::prepare_classification_dataset()`
- Grouped cross-validation ใช้ `StratifiedGroupKFold` โดย group คือ Channel ID จึงไม่ให้คลิปจากช่องเดียวกันอยู่ทั้ง train และ validation fold
- `train_and_evaluate_classification_models()` เปรียบเทียบ candidate หลายชนิด
- `activate_classification_model()` เปลี่ยน Active Model หลังผ่านเกณฑ์เท่านั้น การ Train ไม่ Activate อัตโนมัติ
- หน้า Admin เรียก `/admin/training/runs` และ `/admin/training/models/{id}/activate` จาก `app/routes/model_management.py`

### 4.2 ความหมายของตัวเลข

สมมุติมีคลิปคำตอบจริง 10 คลิป ทายถูก 8 คลิป:

- **Accuracy = 8/10 = 80%** ดูภาพรวม แต่หมวดใหญ่สามารถกลบหมวดเล็ก
- **Recall ของ Camera** ถ้ามี Camera จริง 5 คลิป แต่จับถูก 2 คลิป Recall = 2/5 = 40% แปลว่าพลาด Camera 3 คลิป
- **Precision ของ Camera** ถ้าระบบทาย Camera 4 คลิป แต่ถูกจริง 2 คลิป Precision = 2/4 = 50%
- **F1** ประนีประนอม Precision กับ Recall ของหมวดนั้น
- **Macro F1** หา F1 ของแต่ละหมวดแล้วเฉลี่ยเท่ากัน จึงไม่ให้หมวดข้อมูลเยอะมีน้ำหนักเหนือหมวดอื่น
- **Confidence** คือความมั่นใจภายในโมเดลต่อคลิปหนึ่ง ไม่ใช่ Accuracy และโมเดลอาจมั่นใจสูงแต่ทายผิดได้

ผล registry เดิมของ Model #14 คือ Validation n=21, Accuracy 0.857, Macro F1 0.805 และ Laptop Recall 0.40 ส่วน Test เดิม n=17 ได้ 1.00 แต่ไม่ใช่ fresh heldout รอบส่ง จึงห้ามสรุปว่าโมเดลปัจจุบันแม่น 100% กับคลิปใหม่

## 5. Recommendation ไม่ใช่ Classification Model

Classification ตอบว่า “คลิปอยู่หมวดใด” ส่วน Recommendation ตอบว่า “เมื่อยอมรับหมวดแล้ว คลิปอ้างอิงในหมวดเดียวกันมีประเด็นใดที่ผู้ใช้ยังไม่พูดและมีหลักฐานอะไร” การเพิ่ม Dataset/reference statistics เปลี่ยนหลักฐานแนะนำได้โดยไม่จำเป็นต้อง train classifier ใหม่ทุกครั้ง

ยอดวิว/ไลก์/ความคิดเห็นใช้บอกลักษณะของคลิปอ้างอิงและการเปรียบเทียบเชิงพรรณนา ไม่ได้เป็น label ว่าคำนั้นเป็นสาเหตุให้ยอดเพิ่ม ความสัมพันธ์อาจมาจากชื่อช่อง อายุคลิป คุณภาพการถ่าย หรือปัจจัยอื่น

## 6. ตาราง Database ที่ใช้จริง

| Flow | ตาราง | มาจากไหน / เก็บอะไร / ใช้ต่ออย่างไร |
|---|---|---|
| บัญชี | `users` | Register/Admin สร้างบัญชี; เก็บ role/status/password hash; Auth และ ownership ใช้ต่อ |
| คลิปผู้ใช้ | `user_contents` | Upload ที่บันทึกสำเร็จ; เก็บชื่อและ transcript; เชื่อมผล/ประวัติ |
| ผลวิเคราะห์ | `analysis_results` | Pipeline บันทึก classification, summary และ payload แบบ versioned; Result/History เปิดย้อนหลัง |
| แผนแก้คลิป | `clip_revision_plans` | ผู้ใช้เลือกข้อแนะนำ; ใช้เป็นเป้าหมายของ revision |
| เทียบฉบับแก้ | `clip_revision_comparisons` | Revision job เก็บ parent/child/method/status/result |
| Dataset | `dataset_contents` | แถวที่ผ่าน review; ใช้ Train, Keyword reference หรือ Duration ตาม role/eligibility |
| รอบนำเข้า | `dataset_collection_runs` | Collector/NotebookLM batch, config, artifact path และสถานะ |
| การตรวจ | `dataset_review_events` | Admin approve/reject พร้อมผู้ตรวจและเวลา; เป็น audit |
| Taxonomy | `taxonomy_nodes` | โครงสร้างหมวดและ version; classification/dataset validation ใช้ร่วมกัน |
| โมเดล | `classification_models` | model key/version/path/status/active/threshold/policy |
| Metrics | `model_evaluation_metrics` | Validation/Test metrics ภาพรวมและรายหมวด |
| งาน Train | `model_training_runs` | งานเบื้องหลัง, config, progress และผล |
| Snapshot | `trend_snapshot_runs`, `trend_snapshot_items` | รอบ provider และรายการอันดับ ณ เวลานั้น |
| ประวัติกราฟ | `trend_history_buckets`, `trend_history_attempts` | สรุป observation และช่วงเก็บไม่สำเร็จ |
| หัวข้อเทรนด์ | `trend_topics`, `trend_topic_versions`, `trend_topic_definitions`, `trend_topic_aliases`, `trend_topic_observations`, `trend_topic_evidence`, `trend_topic_counts`, `trend_topic_jobs`, `trend_topic_configs` | ทะเบียนหัวข้อ/คำพ้อง/หลักฐาน/ผลนับแบบ versioned |
| ติดตาม | `followed_topics`, `user_trend_watch_sessions`, `notifications` | ความสนใจ, baseline session และ notification ต่อผู้ใช้ |
| สถิติอ้างอิง | `reference_statistics_configs`, `reference_statistics_runs`, `reference_video_statistics` | ยอดหลายเวลาของคลิปอ้างอิง ใช้แยกยอดสะสมกับการเติบโต |
| ตั้งค่า | `system_configs` | Analysis/Trend/Admin settings ที่ Backend อ่านจริง |
| Audit | `system_logs` | Event ที่โค้ดเรียก log ไว้ ไม่ใช่ Browser/OS debugger ทุกกรณี |

`clusters`, `cluster_runs`, `cluster_memberships`, `keywords`, `content_keywords`, `recommendations` และ `trending_items` เป็นโครงสร้างเดิมหรือ compatibility บางส่วน ไม่ควรพรีเซนต์ว่าเป็นแกนหลักของ pipeline รุ่นส่งโดยไม่มีการตรวจ route ที่ใช้งาน

## 7. หน้าที่ Admin

- **จัดการผู้ใช้**: ดูสถิติ, เปลี่ยน role/status, revoke session และลบตาม guard (`app/routes/user_management.py`)
- **เทรนโมเดล AI**: ดู readiness, เริ่ม background training, metrics และ activate แบบยืนยัน (`app/routes/model_management.py`)
- **ตั้งค่าการวิเคราะห์**: max duration, Whisper model ที่พร้อม และ Hook duration (`/admin/analysis-settings`)
- **นำเข้า Transcript**: สร้าง candidate เท่านั้น ไม่เข้า training ทันที (`app/routes/dataset_review.py::create_notebooklm_candidate()`)
- **ตรวจสอบ Dataset**: คน approve/reject พร้อมหมวด/คุณภาพ
- **จัดการ Dataset**: แก้ transcript/taxonomy พร้อม hash, trash/restore; การแก้ไม่ทำให้โมเดลที่ train แล้วเปลี่ยน ต้อง train/activate รุ่นใหม่
- **บันทึกการทำงาน**: ดูเฉพาะ event ที่ระบบบันทึกผ่าน `log_system_event()` จึงช่วยตาม provider/import/admin operation แต่ไม่แทน stack trace ทุก bug

## 8. ข้อจำกัดที่ต้องบอกตรง ๆ

1. Active Model รุ่นส่งยังขาด validated Unknown scope policy จึงงด positive recommendation จากคลิปใหม่
2. ไม่มี fresh heldout Phone/Camera/Laptop/Unknown ตาม protocol และไม่มีผู้ประเมินมนุษย์ 3 คน จึงยังไม่รับรอง generalization หรือ utility
3. Trend ไม่ realtime ทุกวินาที รุ่นส่งเก็บชั่วโมงละครั้งในช่วง 14:00-23:00 และหน้าเว็บอ่าน DB ทุก 60 วินาที
4. Google กับ YouTube มีคนละหน่วย จึงแยกแท็บและไม่จัดอันดับรวม
5. TikTok ไม่มี provider ฟรีที่เสถียรและตรวจสอบได้ รุ่นส่งแสดง unavailable ไม่แต่งข้อมูล
6. ASR อาจถอดชื่อสินค้า/ศัพท์เฉพาะผิด ความผิดพลาดส่งต่อไปยัง classification และ recommendation ได้
7. ช่วงไม่มี snapshot ต้องเป็นช่องว่าง ไม่ตีความเป็นศูนย์
8. ขอบเขตรายงานที่ยังรออาจารย์ยืนยัน: Classification แทน Clustering, YouTube/Google แทน YouTube/TikTok และยกเลิกการจำกัดจำนวน keyword จากหน้า Admin

หลักฐานตรวจรับทั้งหมดอยู่ใน `docs/implementation/project-closeout-final-acceptance.md`
