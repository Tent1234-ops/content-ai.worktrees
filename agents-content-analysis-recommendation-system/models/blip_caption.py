from PIL import Image
import torch
import cv2
from transformers import BlipProcessor, BlipForConditionalGeneration

print("Loading BLIP2...")

device = "cpu"

processor = BlipProcessor.from_pretrained(
    "Salesforce/blip-image-captioning-base"
)

model = BlipForConditionalGeneration.from_pretrained(
    "Salesforce/blip-image-captioning-base"
).to("cpu")

def caption_image(frame):

    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(frame)

    inputs = processor(image, return_tensors="pt").to(device)

    out = model.generate(**inputs)

    caption = processor.decode(out[0], skip_special_tokens=True)

    return caption