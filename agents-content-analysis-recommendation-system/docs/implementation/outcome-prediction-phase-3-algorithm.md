# Outcome Prediction Phase 3: วิธีทำงานของโมเดล

เอกสารนี้อธิบาย Candidate รุ่น `reference_relative_views_v1` เท่านั้น สถานะปัจจุบันยังไม่ใช่โมเดลที่เปิดให้ผู้ใช้จริง เพราะข้อมูลจริงและสิทธิ์ยังไม่ผ่าน และ Independent Test ยังไม่เปิด

## คำถามที่โมเดลตอบ

โมเดลประเมินว่า ภายในกลุ่มอ้างอิงที่ระบุ คลิปมีโอกาสอยู่ในกลุ่มที่ยอดวิว ณ เวลาสังเกตสูงกว่าค่ากลางของ Fit partition เท่าไร

ค่านี้ไม่ใช่:

- โอกาสที่ทำตามคำแนะนำแล้วยอดวิวจะเพิ่ม
- จำนวนยอดวิวใน 7 วัน
- เปอร์เซ็นต์ยอดวิวที่จะเพิ่ม
- ความมั่นใจของโมเดลจำแนก Phone, Camera หรือ Laptop

## ข้อมูลเข้าและ Label

`x` ประกอบด้วยหัวข้อมาตรฐานที่ตรวจพบแบบ true/false, หมวดที่ตรวจรับแล้ว, รูปแบบคลิปที่ยืนยันแล้ว, ความยาว และบริบทอายุคลิปที่ freeze ไว้ ห้ามใส่ Views, Likes, Comments, Rank, Channel ID, Video ID, URL, ชื่อคลิป หรือ Classification confidence เป็น feature

`y` ไม่ได้ถูก AI ตั้งเอง ระบบนำยอดวิวจริง ณ Observation มาเทียบกับ channel-balanced weighted median ของ Context cell ที่เรียนจาก Fit partition เท่านั้น ค่าที่มากกว่า median เป็น 1 ค่าที่เท่ากับหรือต่ำกว่าเป็น 0 โดย Tuning และ Calibration ใช้ benchmark จาก Fit เดิม ไม่คำนวณ median ใหม่ตามชุดของตน

แต่ละช่องมีน้ำหนักรวมเท่ากัน และคลิปภายในช่องแบ่งน้ำหนักของช่องนั้น เพื่อไม่ให้ช่องที่มีหลายคลิปครอบงำผล อย่างไรก็ตาม วิธีนี้ยังไม่กำจัดอิทธิพลชื่อเสียงช่อง งบโฆษณา Thumbnail หรือเวลาเผยแพร่

## การฝึกและเลือกโมเดล

ระบบเปรียบเทียบสามแบบบนกลุ่มและน้ำหนักเดียวกัน:

1. Constant prior จาก Fit partition
2. Logistic Regression ที่ใช้ Metadata เท่านั้น
3. Logistic Regression ที่ใช้ Metadata และ Canonical topics

Candidate ใช้ L2 Logistic Regression และลอง `C = 0.1, 1, 10` ตาม Protocol เลือกจาก Brier score บน Tuning partition ที่แยก Channel จาก Fit จากนั้นใช้ Calibration partition ซึ่งไม่เคยใช้ Fit estimator หรือเลือก C เพื่อ fit weighted sigmoid calibrator ระบบไม่รวม Tuning หรือ Calibration กลับเข้า Fit หลัง Calibration

สูตรก่อน Calibration คือ:

```text
score = intercept + sum(weight_i * feature_i)
raw_probability = 1 / (1 + exp(-score))
```

Calibration ปรับ raw probability ให้สอดคล้องกับสัดส่วนที่พบใน partition แยก ไม่ได้เปลี่ยนความสัมพันธ์เชิงสังเกตให้เป็นเหตุและผล

## วิธีอ่านผลประเมิน

- Brier score และ Log loss ยิ่งต่ำยิ่งดี
- AUROC และ PR-AUC คำนวณเฉพาะเมื่อมีทั้งสอง Label
- Calibration bins เปรียบเทียบค่าประเมินเฉลี่ยกับสัดส่วนที่พบจริง พร้อมจำนวนคลิปและช่อง
- Paired channel bootstrap สุ่ม Channel แบบใส่คืน เพื่อแสดงความไม่แน่นอนของผลต่าง Brier
- Coefficients บอกความสัมพันธ์ภายในโมเดล ไม่ใช่ผล causal ของการเพิ่มหัวข้อ

ตัวอย่างสมมุติเพื่อสอนสูตร: หาก score เป็น 0, sigmoid ให้ค่า 0.5 ตัวเลขนี้ไม่ได้มาจากผลจริงและห้ามนำไปแสดงเป็นผลประเมินของผู้ใช้

## สถานะ Phase 3

ผลสูงสุดของ Phase นี้คือ `validation_passed` หรือ `experimental` เท่านั้น ต้องรอ Independent Test ใน Phase 6 ก่อนเป็น `qualified` และยังต้องผ่านสิทธิ์, schema, scope และการอนุมัติ Activation แยกต่างหาก

ผล fixture ปัจจุบันมีไว้ตรวจว่าโค้ดฝึก ประเมิน serialize/reload และ gates ทำงาน Fixture ถูกออกแบบให้ Topic แยก Label ได้ จึงห้ามใช้อ้างคุณภาพกับข้อมูลจริงหรืออ้างว่าพิสูจน์ Engagement uplift
