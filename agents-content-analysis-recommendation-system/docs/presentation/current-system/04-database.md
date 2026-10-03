# 4. Database ทุกตารางและการเชื่อมกัน

[กลับสารบัญ](README.md)

ตรวจ MySQL จริงวันที่ 3 ต.ค. 2026 พบ **41 ตาราง** ตรงกับ model ที่ประกาศใน [app/database/models.py](../../../app/database/models.py) ตารางไม่ใช่หน้าเว็บแบบหนึ่งต่อหนึ่ง: หน้าเดียวอาจอ่านหลายตาราง และบางตารางเป็นงานเบื้องหลัง/ของเดิมที่ยังเก็บไว้

คำว่า ID คือรหัสเชื่อมแถว ไม่ใช่คะแนน เช่น `dataset_id=123` แปลว่ารายการข้อมูล #123 ไม่ใช่ลำดับเทรนด์ 123

## กลุ่มบัญชีและสิทธิ์

| ตาราง | ได้ข้อมูลจากไหน/เก็บอะไร | ใช้ทำอะไร |
|---|---|---|
| `users` | Register หรือ Admin เพิ่มบัญชี; ชื่อ อีเมล hash รหัสผ่าน role สถานะ | Login ตรวจสิทธิ์ และจัดการผู้ใช้ |
| `user_trend_watch_sessions` | Login/เริ่ม session; เจ้าของ session, baseline, รอบล่าสุดที่เทียบ, active | ยืนยัน session และไม่แจ้งรายการเดิมซ้ำทุกครั้งที่เปิดหน้า |
| `system_configs` | ค่า Admin/ความชอบผู้ใช้; upload limit, Whisper, Hook, รอบเทรนด์, notification mode และ field เก่า | ตั้งค่าที่คงอยู่หลังรีสตาร์ต; ไม่ใช่ทุก field เก่ามี UI ใช้แล้ว |
| `system_logs` | โค้ดเรียก `log_system_event()` หรือ service audit; action/status/detail/user/time | ตรวจเหตุการณ์สำเร็จ/ล้มเหลว ไม่ใช่ตัวเก็บทุก error อัตโนมัติ |

## กลุ่มวิดีโอผู้ใช้และผลวิเคราะห์

| ตาราง | ได้ข้อมูลจากไหน/เก็บอะไร | ใช้ทำอะไร |
|---|---|---|
| `user_contents` | อัปโหลด; เจ้าของ ชื่อ path วิดีโอ Transcript/raw/cleaned เวลา | ประวัติและระบุเจ้าของผล ไม่ใช่ Train dataset |
| `keywords` | คำที่พบจากการวิเคราะห์ เก็บคำไม่ต้องเขียนซ้ำทุกคลิป | พจนานุกรมคำในผลที่บันทึก ไม่ใช่โมเดลเรียนรู้ทั้งหมด |
| `content_keywords` | คู่ content_id + keyword_id และคะแนนคำ | บอกว่าคลิปนี้มีคำใด เป็นตารางเชื่อมหลายคลิปกับหลายคำ |
| `analysis_results` | หมวด/Model ID/confidence/is_unknown + `summary` JSON จาก pipeline | เปิดผลเก่า คำแนะนำเต็ม หลักฐาน frozen settings/เวอร์ชัน; ใช้นับสถิติผลสำเร็จ |
| `recommendations` | คำแนะนำคำ/Hook/ความยาวแบบสรุป เชื่อม content_id | รองรับรายการประวัติและรูปแบบผลเดิม; ผลเชิงลึกอยู่ใน summary ด้วย |
| `clip_revision_plans` | ผู้ใช้เลือกข้อแนะนำและหมายเหตุ; analysis_id, fingerprint, revision | บันทึกแผน ไม่ตีความว่าเลือกแล้วทำเสร็จ |
| `clip_revision_comparisons` | อัปโหลดฉบับแก้ไข; parent/child, แผน, job status, settings และ comparison JSON | เทียบเนื้อหาใหม่กับเดิมอย่างตรวจย้อน รวมป้องกันส่งงานเดิมซ้ำ |

ความสัมพันธ์หลัก:

```text
users.user_id
  -> user_contents.user_id
       -> analysis_results.content_id -> classification_models.model_id
       -> recommendations.content_id
       -> content_keywords.content_id -> keywords.keyword_id

analysis_results.result_id -> clip_revision_plans.analysis_id
คลิปเดิม + คลิปใหม่ + แผน -> clip_revision_comparisons
```

เมื่อบันทึกผลหนึ่งครั้ง มีหลายแถวเกิดขึ้นใน transaction เดียว ไม่ใช่เอา Transcript ยาว ๆ ใส่ `summary` แบบ VARCHAR สั้นเหมือน bug รุ่นเก่า ปัจจุบันใช้ชนิดข้อความขนาดใหญ่ และรอบตรวจจริงบันทึก/เปิดใหม่หลังรีสตาร์ตได้

## กลุ่ม Dataset และการฝึกโมเดล

| ตาราง | ได้ข้อมูลจากไหน/เก็บอะไร | ใช้ทำอะไร |
|---|---|---|
| `taxonomy_nodes` | รายการหมวดมาตรฐาน/ลำดับชั้น เช่น Technology > Electronics > Phone | อ้าง label เดียวกันใน Import, Train, Analyze ไม่ใช้ชื่อที่พิมพ์ผิดเป็นหมวดใหม่ |
| `dataset_collection_runs` | รอบนำเข้า/เก็บข้อมูล; วิธี แหล่ง จำนวน สถานะ และ path/hash artifact | รู้ว่าชุดนี้เข้ามาตอนไหน ใช้เครื่องมือ/รุ่นใด |
| `dataset_contents` | Transcript และ metadata ของแต่ละคลิป พร้อม provenance, label, split, eligibility, soft delete | แหล่งฝึก/ตรวจ/อ้างอิงที่กรองตามวัตถุประสงค์ ไม่ได้ใช้ทุกแถวพร้อมกัน |
| `dataset_review_events` | ผล approve/reject จากรอบนำเข้า; หมวดที่เสนอ/ตรวจรับ ผู้ตรวจ คุณภาพ เวลา และเหตุผล | ตรวจว่าใครรับรองข้อมูลต้นแบบ; การแก้จากหน้า Datasets ภายหลังบันทึกแยกใน `system_logs` ไม่ใช่ version history ของ Transcript ทุกฉบับ |
| `model_training_runs` | กดเริ่มเทรน; parameters, dataset fingerprint, progress/heartbeat, result/error | หน้า Training แสดงงานเบื้องหลังและประวัติ ไม่ทำงานค้างใน request |
| `classification_models` | ผลการ Train; รุ่น ชนิด model, path artifact, metadata, is_active, เวลาฝึก | ทะเบียนว่า Analyze จะโหลดโมเดลใด ไม่เก็บน้ำหนัก Whisper ที่นี่ |
| `model_evaluation_metrics` | การ Evaluate; model_id, split, metric, sample size, per-class/confusion details | ตารางคะแนนและเงื่อนไข Activate |

### ทำไม `dataset_contents` มี column มาก

| กลุ่ม field | ใช้กับอะไร |
|---|---|
| `transcript`, `taxonomy_leaf_key` | ข้อความ input และ label สำหรับฝึก/ตรวจ classifier |
| `source_youtube_id`, `source_channel_id`, `creator_group_key`, `data_split` | ป้องกันคลิป/ช่องซ้ำข้ามชุด ไม่ใช่ input ที่สอนโมเดลให้จำชื่อช่อง |
| `views`, `likes`, `comments`, `average_views_per_day`, `engagement_rate` | คัดและอธิบายคลิปอ้างอิง ไม่ได้ใส่ให้ classifier ตัดสินหมวด |
| `published_at`, `statistics_captured_at` | รู้ว่าสถิติเป็นของเวลาใด เทียบอายุ/ความสดได้ |
| `duration_seconds`, metadata | คำแนะนำความยาวและกลุ่มเปรียบเทียบ |
| source/version/URL/license/review fields | ตรวจที่มาและสิทธิ์ใช้งาน ไม่อ้างข้อมูลที่ไม่รู้ต้นทาง |
| `transcript_sha256` | ตรวจความเปลี่ยนแปลง/ความซ้ำของข้อความ ไม่ใช่ encryption หรือคะแนนคุณภาพ |
| `is_training_eligible`, สิทธิ์ keyword/duration | แถวเดียวอาจฝึกได้แต่ยังอ้าง duration ไม่ได้ |
| `deleted_at` และผู้ลบ | Soft delete เพื่อหยุดใช้ในงานใหม่และกู้คืนได้ |

จำนวนทั้งหมดในตารางจึง **ไม่เท่ากับจำนวนฝึกโมเดล** วันที่ตรวจมีทั้งหมด 472 แถว แต่ eligible สามหมวด 245 และ fit จริง 191 จำนวนที่เลือกอ้างอิงยังเป็นอีกชุด และเปลี่ยนตามเงื่อนไขของงาน

```text
dataset_collection_runs -> dataset_contents -> dataset_review_events
                                      |
                           Train / Validation / Test
                                      |
model_training_runs -> classification_models -> model_evaluation_metrics
                                      |
                                model.joblib
```

## กลุ่มเทรนด์และกราฟ

| ตาราง | ได้ข้อมูลจากไหน/เก็บอะไร | ใช้ทำอะไร |
|---|---|---|
| `trend_snapshot_runs` | รอบเรียก provider; เวลา region ชนิด global/categories status และ provider_status | หัวรอบการเก็บ แม้เรียกไม่สำเร็จก็มีสถานะ |
| `trend_snapshot_items` | รายการที่เก็บได้ใน run; title/category/provider_rank/scope/view/search volume/URL/metadata | รายการ Dashboard รายละเอียด เทียบอันดับภายใน scope เดียว |
| `trend_collection_slots` | เวลาเป้าหมายตามตาราง เช่น 22:00 วันนี้ พร้อม actor/status | ป้องกัน Backend กับ Task Scheduler ทำรอบเดียวซ้ำ และตรวจรอบที่พลาด |
| `trend_history_buckets` | สรุปต้น/ท้ายชั่วโมงของแต่ละ platform/scope จาก Snapshot จริง | ประวัติกราฟหลังลดจำนวน raw snapshots ไม่ต้องเก็บทุกนาทีตลอดไป |
| `trend_history_attempts` | ผลพยายามเก็บแต่ละ run/platform/scope; สำเร็จ/ล้มเหลวและจำนวน | แยกข้อมูลขาดจากค่าศูนย์ ทำ coverage ของกราฟ |
| `trending_items` | โครงสร้างสรุปเทรนด์แบบเก่า จากบริการเก็บ/จัดกลุ่มเดิม | รักษารองรับโค้ดเก่า ไม่ใช่แหล่งหลักของ Dashboard ปัจจุบัน |

คลิปเดียวอาจมีหลายแถวเพราะอยู่คนละเวลา หรืออยู่ทั้ง global และ category ไม่ถือว่าเป็นวิดีโอคนละคลิป ถ้าจะนับหัวข้อต้องตัดซ้ำตาม Video ID/ขอบเขตที่กำหนดก่อน

Raw snapshot ไม่ได้เก็บถาวรทุกแถว มี retention ตามจำนวนรอบ ก่อนลบจะเก็บสรุปรายชั่วโมง ปัจจุบันบริการ history มี retention 90 วัน แต่ UI ให้ดู 7 วันเท่านั้น สองค่านี้ทำหน้าที่ต่างกัน

## กลุ่มติดตามและแจ้งเตือน

| ตาราง | ได้ข้อมูลจากไหน/เก็บอะไร | ใช้ทำอะไร |
|---|---|---|
| `followed_topics` | ผู้ใช้กดติดตาม; user, match_type, value, platform, เวลา | รายการสนใจ/หมวด YouTube และเงื่อนไขแจ้งเตือน |
| `notifications` | พบรายการใหม่ตรงเงื่อนไข; เจ้าของ ข้อความ source/snapshot และ read state | กระดิ่ง/กล่องข้อความส่วนตัว ไม่ใช่การ Subscribe ช่องผ่านบัญชี YouTube |

สองตารางนี้เชื่อมกับ `user_trend_watch_sessions` เพื่อรู้ว่าผู้ใช้นี้เทียบถึงรอบไหนแล้ว

## กลุ่มสถิติคลิปอ้างอิงหลายเวลา

| ตาราง | ได้ข้อมูลจากไหน/เก็บอะไร | ใช้ทำอะไร |
|---|---|---|
| `reference_statistics_configs` | ตั้งค่ารอบ/งบคำขอการอัปเดตสถิติคลิปอ้างอิง | ควบคุมการเรียก metadata โดยไม่ต้องทำ Transcript ซ้ำ |
| `reference_statistics_runs` | รอบดึงสถิติจาก Video ID; จำนวนสำเร็จ/ล้มเหลว เวลา | ตรวจต้นทุนคำขอและสถานะงาน |
| `reference_video_statistics` | ค่าวิว/ไลก์/ความคิดเห็นต่อคลิปต่อเวลา พร้อมชนิด metric และ error/status | ใช้สองเวลาคำนวณการโต รู้ว่า missing ไม่ใช่ 0 |

`dataset_contents` เก็บค่าล่าสุดเพื่ออ่านง่าย ส่วนตารางนี้เก็บประวัติ ไม่ได้เอาค่าใหม่เขียนทับจนไม่รู้ค่าเก่า

## กลุ่มทะเบียนหัวข้อจากเทรนด์

เป็นโครงสร้าง Backend สำหรับจับหัวข้อจากชื่อคลิปและตรวจย้อน ไม่ใช่หลักฐานว่าเว็บมีกราฟทุกชนิดที่เคยวางแผนไว้แล้ว

| ตาราง | เก็บอะไร | ประโยชน์ |
|---|---|---|
| `trend_topics` | รหัสหัวข้อถาวร | เปลี่ยนชื่อแสดงได้โดยไม่สูญรหัสเดิม |
| `trend_topic_versions` | รุ่น extractor/alias และ catalog/manifest ที่ใช้ | เปลี่ยนกฎแล้วไม่เอาตัวเลขต่างวิธีมาปนกัน |
| `trend_topic_definitions` | ชื่อ/ชนิดหัวข้อในแต่ละรุ่น | รู้ว่าตอนนับใช้ความหมายใด |
| `trend_topic_aliases` | คำพ้องและกฎบริบทที่ตรวจแล้ว | รวมการสะกดต่างของเรื่องเดียวกัน ไม่รวมทุกคำที่แค่เกี่ยวข้อง |
| `trend_topic_configs` | active version ของการจับหัวข้อ | เลือกชุดกฎที่ใช้งานอยู่ แยกจาก classifier AI |
| `trend_topic_observations` | ข้อความต้นทางของแต่ละ run/scope พร้อม hash | คำนวณใหม่ได้จากข้อมูลที่เคยเก็บจริง ไม่สร้างช่วงอดีตที่ไม่เคยมี |
| `trend_topic_jobs` | คิวประมวลผล observation + version; attempts/lease/status | ประมวลผลเบื้องหลังและป้องกันทำข้อมูลซ้ำ |
| `trend_topic_evidence` | Video ID/title/URL/rank/matches ที่ทำให้พบหัวข้อ | คลิกตามหลักฐานได้และนับคลิปไม่ซ้ำในงาน |
| `trend_topic_counts` | topic_id, จำนวนคลิปที่พบ, จำนวนคลิปที่มีสิทธิ์นับในงาน | ตัวเลขสรุปที่อ้างกลับไปหา evidence ได้ |

## กลุ่มจัดกลุ่มแบบเดิม

| ตาราง | เก็บอะไร | สถานะการใช้งาน |
|---|---|---|
| `clusters` | ชื่อ/ข้อมูลของกลุ่มคอนเทนต์ | โครงสร้าง clustering เดิม ไม่ใช่ทะเบียน Phone/Camera/Laptop ของ classifier |
| `cluster_runs` | รอบที่รัน algorithm จัดกลุ่มและผลสรุป | รองรับ API/งานเก่า ไม่มีหน้า Console เดิมให้พรีเซนต์ว่าพร้อมครบ |
| `cluster_memberships` | สมาชิกคลิป/ข้อมูลในกลุ่มของรอบนั้น | ตรวจว่าคลิปใดถูกจัดในกลุ่มใด |

**จำแนกหมวด (Classification)** ใช้ label ที่กำหนดและข้อมูลมีคำตอบ ส่วน **จัดกลุ่ม (Clustering)** ให้ algorithm แบ่งกลุ่มตามความคล้ายโดยไม่ใช่คำตอบหมวดเดียวกัน อย่าเรียกหน้า Training ใหม่ว่าได้ปิดขอบเขต “โมเดลจัดกลุ่ม” แล้วโดยอัตโนมัติ ต้องปรับถ้อยคำรายงานให้ตรงกับระบบจริง

## สิ่งสำคัญที่อยู่นอก Database

- `videos/`: ไฟล์ผู้ใช้อัปโหลด
- `models_cache/faster_whisper/`: โมเดลถอดเสียงที่ติดตั้ง
- `artifacts/classification_training/<version>/`: ชุดข้อมูล frozen, `model.joblib`, รายงาน และ hash จากการฝึก
- `docs/`: คู่มือ ข้อตกลงข้อมูล และผลตรวจรับ
- สถานะงาน Analyze แบบ in-process: อยู่ใน RAM จนบันทึกผลเสร็จ จึงไม่ใช่ทุกอย่างจะรอดการปิด Backend กลางงาน

การสำรองระบบเพื่อพรีเซนต์ต้องสำรองทั้ง DB และไฟล์ที่อ้างถึง โดยเฉพาะ artifact โมเดล แค่ export SQL อย่างเดียวไม่ทำให้ถอดเสียง/จำแนกหมวดได้ถ้าไม่มีไฟล์โมเดล
