# Data-use decision: Outcome Prediction v1

ตรวจเมื่อ 8 ตุลาคม 2026 สถานะ **unverified**

ไฟล์ที่โปรแกรมใช้เป็น Gate: [outcome-prediction-data-use-v1.json](outcome-prediction-data-use-v1.json)

## คำตัดสินทางเทคนิค

อนุญาตให้ Audit แบบอ่านอย่างเดียวเพื่อหาความพร้อม แต่ยังบล็อกการ Train และ Serving Outcome model จากข้อมูลจริง เนื่องจากยังไม่พบหลักฐานจากเจ้าของโครงการว่า YouTube API project/use case นี้ได้รับสิทธิ์และยอมรับเงื่อนไขที่ใช้กับ Additional derived metrics และการเก็บสถิติระยะยาวแล้ว

สถานะนี้ไม่ได้หมายความว่างานมหาวิทยาลัยถูกห้ามแน่นอน แต่หมายความว่า Agent ไม่มีหลักฐานพอจะยืนยันแทนเจ้าของโครงการ และไม่ควรฝึก/แสดง Probability จริงก่อนตรวจให้ครบ

## เหตุผลที่ต้องตรวจ

เอกสาร YouTube ที่ตรวจวันที่ 8 ต.ค. 2026 ระบุว่า:

- การสร้าง Additional derived metrics ต้องอยู่ภายใต้ Amendment/Analytics & Reporting use case ที่เกี่ยวข้อง
- Policy guide ระบุว่าผู้พัฒนาต้องยื่นและได้รับอนุมัติตามกระบวนการที่ระบุ หากยังไม่อนุมัติไม่ควรสร้าง Derived metrics หรือเก็บข้อมูลเกินสิทธิ์ปกติ
- สิทธิ์เก็บ Statistical/Derived metrics ได้นานถึง 36 เดือนใช้กับกรณีที่ได้รับอนุมัติ ส่วน Title, creator name, description และ comment text มีหน้าที่ Refresh/Delete แยก
- ผลคำนวณของระบบต้องแยกจากข้อมูล API และไม่แสดงเหมือนเป็นค่าที่ YouTube รับรอง

แหล่งทางการ:

- [Complying with YouTube Developer Policies](https://developers.google.com/youtube/terms/developer-policies-guide)
- [Additional policies for derived metrics and data storage](https://developers.google.com/youtube/terms/derived-metrics-policy)
- [YouTube Data API video statistics](https://developers.google.com/youtube/v3/docs/videos#statistics)

## สิ่งที่เจ้าของโครงการต้องยืนยัน

1. Cloud/YouTube API project นี้ได้ยื่นและได้รับ Permission ที่ใช้กับ Analytics & Reporting/Additional metrics หรือยัง
2. หลักฐานอ้างอิงอะไร: Project/use-case identifier, วันที่, ผู้ตรวจ และขอบเขตที่อนุญาต โดยไม่เก็บ Credential ในเอกสาร
3. ระยะเวลา Refresh/Retention/Delete ของ Statistics, Titles, Channel names, Descriptions และข้อมูลอื่น
4. สิทธิ์ Transcript แยกจากสิทธิ์อ่าน Statistics เพราะ License metadata ใน Dataset ไม่ได้ยืนยัน Derived-metrics permission โดยอัตโนมัติ

เมื่อมีหลักฐาน ให้แก้ JSON ผ่าน Review ที่มีผู้รับผิดชอบ ไม่เปลี่ยนเพียง status เป็น confirmed โดยไม่มี confirmation_evidence

เอกสารนี้เป็น Technical gate ไม่ใช่คำวินิจฉัยทางกฎหมาย

