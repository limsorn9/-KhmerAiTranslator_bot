FROM python:3.10-slim

# ដំឡើង FFmpeg សម្រាប់ដំណើរការសំឡេង
RUN apt-get update && apt-get install -y ffmpeg

WORKDIR /app

# ចម្លងឯកសារ Requirements
COPY requirements.txt .

# ដំឡើង Libraries ទាំងអស់
RUN pip install --no-cache-dir -r requirements.txt

# ចម្លងកូដទាំងអស់ចូលក្នុង Docker
COPY . .

# Command សម្រាប់ដំណើរការ Bot
CMD ["python", "bot.py"]
