from sentence_transformers import SentenceTransformer

# Load NLP model once and reuse it
model = SentenceTransformer("all-MiniLM-L6-v2")
