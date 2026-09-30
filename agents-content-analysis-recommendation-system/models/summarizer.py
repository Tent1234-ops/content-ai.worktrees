from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import re

print("Loading Structured Summarizer V10...")

model_name = "google/mt5-small"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)


def clean_text(text):
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_chunks(text, max_len=300):
    words = text.split()
    chunks, current = [], []

    for word in words:
        current.append(word)
        if len(" ".join(current)) > max_len:
            chunks.append(" ".join(current))
            current = []

    if current:
        chunks.append(" ".join(current))

    return chunks


# =========================
# 🔥 PROMPT อัปเกรด
# =========================
def build_prompt(chunk, keywords=None):
    kw = ", ".join(keywords[:8]) if keywords else ""

    return f"""
สรุปเป็น 1 ประโยค (ห้ามมั่ว ห้ามใช้คำทั่วไป)

เงื่อนไข:
- ต้องมี keyword: {kw}
- ต้องมี: ชื่อรุ่นสินค้า
- ต้องมี: feature หลัก (เช่น hot swap, gasket, rgb)
- ห้ามใช้คำเช่น: ดี, เท่, เล่น, ส่วนตัว

ข้อความ:
{chunk}

คำตอบ:
"""


def clean_output(text):
    text = re.sub(r"<extra_id_\d+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def summarize_text(text, keywords=None):
    try:
        text = clean_text(text)
        chunks = split_chunks(text)

        summaries = []

        for chunk in chunks:
            prompt = build_prompt(chunk, keywords)

            inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)

            outputs = model.generate(
                **inputs,
                max_new_tokens=50,
                num_beams=4,
                repetition_penalty=1.2,
                no_repeat_ngram_size=3,
                early_stopping=True
            )

            result = tokenizer.decode(outputs[0], skip_special_tokens=True)
            result = clean_output(result)

            if result and len(result) > 15:
                summaries.append(result)

        # =========================
        # 🔥 fallback
        # =========================
        if not summaries:
            if keywords:
                return f"{keywords[0]} รองรับ {', '.join(keywords[1:5])}"
            return text[:200]

        merged = " ".join(summaries)

        # =========================
        # 🔥 FINAL REFINE
        # =========================
        final_prompt = f"""
เขียนสรุปรีวิวสินค้า 1 ประโยค:

เงื่อนไข:
- ต้องเป็นประโยคธรรมชาติ
- ห้าม list keyword
- ต้องมี: รุ่นสินค้า + ฟีเจอร์หลัก

ข้อมูล:
{merged}

คำตอบ:
"""

        inputs = tokenizer(final_prompt, return_tensors="pt", truncation=True, max_length=512)

        outputs = model.generate(
            **inputs,
            max_new_tokens=40,
            num_beams=4
        )

        final = tokenizer.decode(outputs[0], skip_special_tokens=True)
        final = clean_output(final)

        if not final:
            return merged[:200]

        return final

    except Exception as e:
        print("Summary error:", e)
        return text[:200]