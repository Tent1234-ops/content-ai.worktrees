from keybert import KeyBERT
from sentence_transformers import SentenceTransformer
from utils.text_clean import clean_text

print("Loading Keyword AI embedding model...", flush=True)
embedding_model = SentenceTransformer("BAAI/bge-m3")

kw_model = KeyBERT(model=embedding_model)


def extract_keywords(text):

    text = clean_text(text)

    keywords = kw_model.extract_keywords(

        text,

        keyphrase_ngram_range=(1,3),

        use_mmr=True,

        diversity=0.6,

        top_n=15
    )

    result = []

    for word, score in keywords:

        if score > 0.35:

            result.append(word)

    return result