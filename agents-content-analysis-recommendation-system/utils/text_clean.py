import re

def clean_text(text):

    text = text.lower()

    text = re.sub(r"[^\u0E00-\u0E7Fa-zA-Z0-9\s\-]", " ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()