FROM python:3.10-slim

# ដំឡើង FFmpeg និង Tesseract OCR សម្រាប់ដំណើរការសំឡេង និងទាញអក្សរពីរូបភាព
RUN apt-get update && apt-get install -y ffmpeg tesseract-ocr tesseract-ocr-eng tesseract-ocr-khm tesseract-ocr-all

WORKDIR /app

# ចម្លងឯកសារ Requirements
COPY requirements.txt .

# ដំឡើង Libraries ទាំងអស់
RUN pip install --no-cache-dir -r requirements.txt

# ចម្លងកូដទាំងអស់ចូលក្នុង Docker
COPY . .

# Command សម្រាប់ដំណើរការ Bot
CMD ["python", "bot.py"]
