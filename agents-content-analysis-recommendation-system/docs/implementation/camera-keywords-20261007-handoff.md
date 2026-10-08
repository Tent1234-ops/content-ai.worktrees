# Camera Keyword Fix: 7 October 2026

## อาการและสาเหตุ

ผล#24ชื่อ `review camera` รับเป็นCameraได้ แต่ผู้ใช้ไม่เห็นคำแนะนำคำสำคัญ:

1. เมื่อมี `actionable_recommendations` หน้าResultซ่อนกล่องคำแนะนำKeywordเดิมทั้งหมด
2. Cameraถูกส่งไปใช้โปรไฟล์คำศัพท์ `general` ทำให้คำทั่วไป เช่นผม/ดู/อ่ะ ผ่านเข้ารายการแนะนำ
3. คำพ้องไม่ครอบคลุม `auto focus`, `auto-focus` และวีดีโอ จึงมองประเด็นที่พูดแล้วว่าไม่พบ

ไม่ได้เกิดจากไม่มีDatasetCamera และไม่แก้ด้วยการลดเกณฑ์จำแนกหรือแต่งคำแนะนำ

## สิ่งที่แก้

- `app/services/recommendation_catalog.py`: ใช้แหล่งแม่แบบ/คำพ้องเดียวกัน
- `recommendation_templates.json`: รุ่น `thai-action-templates-v2-camera-vocabulary`
  เพิ่มรูปสะกดที่ตรวจจากข้อความได้ ไม่ใช้คำผิดที่เดาความหมายจากเสียง
- `nlp.py`: Cameraมีหัวข้อมาตรฐานจากcatalogเดียวกับคำแนะนำแบบลงมือทำ
- `recommendation.py`: Cameraไม่ใช้general; ตัดคำทั่วไปและคงหัวข้อที่มีหลักฐานจริง
- `actionable_recommendations.py`: อ่านcatalogร่วมและคงกฎไม่แนะนำสิ่งที่ตรวจพบแล้ว
- `frontend_flutter/lib/screens/result_screen.dart`: แสดงสรุปคำสำคัญที่แนะนำและข้อเสนอ
  สำหรับช่วงเปิดก่อนรายละเอียด ใช้ชื่อไทยและจำนวนคลิปจากหลักฐานที่บันทึกไว้
  เลือกเฉพาะคำแนะนำที่ผ่านกฎความเกี่ยวข้อง ไม่ดึงKeywordเก่าที่เป็นคำฟุ่มเฟือยมาแสดง
- ผลเก่าไม่มีแม่แบบยังอ่านได้ คงข้อความบอกว่าเป็นคำแนะนำที่บันทึกไว้เดิม
- ไม่แก้Transcriptต้นฉบับ ไม่สร้างTimestamp ไม่เปลี่ยนผลเก่าหรือข้อมูลTrain/Test

## ผลจริงที่ตรวจได้

เมื่อกลับมาทำต่อ7ต.ค. พบผล#25ที่บันทึกไว้ก่อนหน้านี้ ไม่ใช่ผลวิเคราะห์ใหม่ของวันนี้
เวลาในDBคือ `2026-10-04 22:09:17` UTC หรือ5ต.ค.05:09:17ไทย:

- หมวดCamera, Model#43, Confidence96.4363% ไม่ใช่คะแนนคุณภาพคำแนะนำ
- คำที่พบจริง: วีดีโอ, auto focus, sensor
- หัวข้อมาตรฐาน: video recording, autofocus, image quality
- Keywordที่ขาดและมีหลักฐาน: handling, low light
- หลังตรวจความเกี่ยวข้อง เหลือข้อเสนอหลัก **ภาพในสภาพแสงน้อย**
- หลักฐาน5จาก25คลิปอ้างอิง รวม4ช่อง ไม่อ้างว่าการเพิ่มหัวข้อนี้ทำให้ยอดเพิ่มแน่นอน
- ไม่แนะนำauto focusหรือวิดีโอซ้ำ และไม่แนะนำผม/ดู/อ่ะ/ถ่าย

ผล#24ยังเหมือนเดิม ตรวจSHA256ของanalysis summaryก่อนและหลัง:
`1ac56256530e388bb20aefced1b1afbb8717dc9b38eb512383bb0934a1d08856`

ไฟล์ที่ผู้ใช้แจ้งเดิม `C:\Users\tent9\Downloads\review_camera.mp4` ไม่อยู่แล้วเมื่อ7ต.ค.
พบไฟล์ชื่อเดียวกัน1475529bytesที่ `videos/review_camera.mp4` ไม่ลบหรือย้ายไฟล์ใด

## หลักฐานทดสอบ

- รอบ5ต.ค.: Backend517testsผ่าน (`artifacts/camera-keywords-20261005/backend-tests.stderr.log`)
- รอบ7ต.ค.: Backend17focused testsผ่าน (Camera, actionable advice, Phone keyword evidence)
- Flutter15focused testsผ่าน รวมempty/legacy/presentation/duration/Camera keyword visibility
- Flutter analyzeผ่าน; release web buildผ่าน
- Browser7ต.ค.ผ่าน8checks: เปิดผล#25ผ่านHistoryที่1440และ1000px
  เห็นกล่องคำสำคัญและข้อเสนอช่วงเปิดเป็นไทยพร้อม5/25; ไม่พบBrowser/API error
- `artifacts/camera-keywords-20261007/browser-saved-25/verification.json`
  เก็บชัดว่า `real_asr=false`, `fresh_test=false`, `readonly_saved_content_id=25`
  ไม่อ้างว่าเป็นการอัปโหลด/ถอดเสียง/จำแนกใหม่ในรอบ7ต.ค.
- ภาพหน้าจอ: `reopened-1440.png`, `reopened-1000.png`, `advice-*.png`
  และข้อมูลAPIที่อ่านจริง `saved-result.json` ในโฟลเดอร์เดียวกัน

คำสั่งตรวจผลที่บันทึกโดยไม่สร้างงานวิเคราะห์ใหม่ (ใช้outputใหม่ทุกครั้ง):

```powershell
node scripts/browser/verify_presentation_model.cjs artifacts/camera-recheck content:25 videos/review_camera.mp4
```

## งานที่ค้างและสถานะโมเดล

**Model#43หมดสิทธิ์สาธิตแล้ว** เมื่อ6ต.ค.2026เวลา23:42ไทย
ตรวจreadinessเมื่อ7ต.ค.ได้ `blocked`, `presentation_expired`, `can_accept_predictions=false`
จึงยังไม่สามารถอ้างว่าคลิปอัปโหลดใหม่จะได้รับคำแนะนำเฉพาะหมวด

ส่งคำถามขอให้ผู้ใช้ยืนยันการต่อ48ชั่วโมงแล้ว ยังไม่ได้รับคำตอบ ณ checkpointนี้
ไม่ได้ต่ออายุเอง ไม่เปลี่ยนเป็นqualified ไม่ปิดUnknowngate และไม่แก้เกณฑ์80%
เมื่อได้รับคำยืนยัน ต้องเปิดโหมดสาธิตตามสิทธิ์ใหม่แล้วทดสอบMP4รอบใหม่แยกจากผล#25

ยังมีข้อจำกัดWhisper smallถอดคำเทคนิคคลาดเคลื่อนได้ และการพบในคลิปอ้างอิงไม่ยืนยัน
ผลเชิงเหตุและผลต่อEngagement การตรวจคลิปนี้เป็นregressionไม่ใช่Testอิสระใหม่

เว็บที่เปิดไว้: http://127.0.0.1:8080/#/history
เลือก `review camera` ผล#25; ผล#24เป็นผลก่อนแก้ที่เก็บไว้ตรวจย้อนกลับ
