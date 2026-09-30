from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

print("Loading Qwen2.5...")

model_name = "Qwen/Qwen2.5-3B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(model_name)

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float16,
    device_map="auto"
)


def ask_llm(prompt):

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    outputs = model.generate(
        **inputs,
        max_new_tokens=200
    )

    return tokenizer.decode(outputs[0], skip_special_tokens=True)


# FIX TRANSCRIPT
def fix_transcript(text):

    prompt = f"""
แก้ transcript จากวิดีโอรีวิวสินค้า
ให้แก้คำสะกดผิดของ brand / tech term

{text}

ตอบเฉพาะข้อความที่แก้แล้ว
"""

    return ask_llm(prompt)


# KEYWORD EXTRACTION
def extract_keywords(text):

    prompt = f"""
จาก transcript นี้
ดึง keyword สำคัญของวิดีโอ

{text}

ตอบเป็น list keyword ไม่เกิน 10 คำ
"""

    return ask_llm(prompt)