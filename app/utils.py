from PyPDF2 import PdfReader
from flashtext import KeywordProcessor
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import ssl


try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

nltk.download("punkt")
nltk.download("punkt_tab")
nltk.download("stopwords")

keyword_processor = KeywordProcessor()
# Add common skill-related words (you can expand this list)
keyword_processor.add_keywords_from_list([
    "Python", "Machine Learning", "Deep Learning", "NLP", "FastAPI",
    "Django", "Flask", "TensorFlow", "PyTorch", "Data Science",
    "AWS", "Docker", "Kubernetes", "SQL", "PostgreSQL"
])


def extract_text_from_pdf(pdf_file):
    """Extracts text from a PDF file."""
    reader = PdfReader(pdf_file)
    return " ".join([page.extract_text() for page in reader.pages if page.extract_text()])


def extract_skills(text):
    """Extracts keywords that match skills using FlashText."""
    return keyword_processor.extract_keywords(text)


def clean_text(text):
    """Tokenizes and removes stopwords for better matching."""
    tokens = word_tokenize(text.lower())
    return " ".join([word for word in tokens if word.isalnum() and word not in stopwords.words("english")])
