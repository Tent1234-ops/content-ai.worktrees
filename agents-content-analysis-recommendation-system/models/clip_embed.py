import torch
import open_clip
from PIL import Image

model, _, preprocess = open_clip.create_model_and_transforms(
    "ViT-B-32",
    pretrained="openai"
)

def embed_image(path):

    image = preprocess(Image.open(path)).unsqueeze(0)

    with torch.no_grad():
        embedding = model.encode_image(image)

    return embedding.cpu().numpy()