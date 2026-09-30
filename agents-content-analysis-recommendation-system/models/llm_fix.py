from openai import OpenAI

client = OpenAI()

def fix_transcript(text):

    prompt = f"""
แก้ transcript ภาษาไทยจากวิดีโอรีวิวสินค้า
ให้แก้คำสะกดผิดของ brand / tech term

ตัวอย่าง
ajax -> ajazz
ak820mac -> ak820 max
gasket เอาจร -> gasket mount

ข้อความ:

{text}

ตอบเฉพาะข้อความที่แก้แล้ว
"""

    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.2
    )

    return res.choices[0].message.content