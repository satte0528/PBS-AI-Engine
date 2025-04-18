# syntax=docker/dockerfile:1

FROM python:3.11-slim

# 1) Set a working directory
WORKDIR /app

# 2) Copy in requirements.txt and install deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# 3) Pre‑download NLTK data so it’s baked into the image
RUN python - <<EOF
import nltk
nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')
EOF

# 4) Copy application code
COPY . .

# 5) Expose port and set env for unbuffered logs
EXPOSE 8000
ENV PYTHONUNBUFFERED=1

# 6) Launch Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
