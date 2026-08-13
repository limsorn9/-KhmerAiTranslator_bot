import os
import logging
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from openai import OpenAI

# កំណត់ Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Telegram Token ថ្មីរបស់អ្នក និង OpenAI API Key
TOKEN = "7720315035:AAElqTLlztR--BP4X6J9_mG1SjVF1ILkmJs"
client = OpenAI(api_key="YOUR_OPENAI_API_KEY") # ជំនួស OpenAI API Key របស់អ្នកនៅទីនេះ
TARGET_LANGUAGE = "Khmer"

# ----------------- FLASK SERVER (សម្រាប់ទុករក្សា Bot ឱ្យដើរលើ Render) -----------------
app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot is running online 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ----------------- TELEGRAM BOT LOGIC -----------------
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    file_obj = None

    if message.video:
        file_obj = await message.video.get_file()
        file_extension = ".mp4"
    elif message.audio:
        file_obj = await message.audio.get_file()
        file_extension = ".mp3"
    elif message.voice:
        file_obj = await message.voice.get_file()
        file_extension = ".ogg"
    elif message.document:
        doc = message.document
        if doc.mime_type and ("video" in doc.mime_type or "audio" in doc.mime_type):
            file_obj = await doc.get_file()
            file_extension = os.path.splitext(doc.file_name)[1]
        else:
            await message.reply_text("សូមផ្ញើតែឯកសារវីដេអូ ឬសំឡេង (MP3, WAV, MP4) ប៉ុណ្ណោះ!")
            return
    else:
        await message.reply_text("សូមផ្ញើឯកសារវីដេអូ ឬសំឡេងមកកាន់បត ដើម្បីធ្វើការបកប្រែ។")
        return

    processing_msg = await message.reply_text("⏳ កំពុងទាញយក និងដំណើរការបកប្រែ... សូមរង់ចាំបន្តិច។")
    input_path = f"temp_input{file_extension}"
    
    try:
        await file_obj.download_to_drive(input_path)

        # Whisper API សម្រាប់បម្លែងសំឡេងជាអត្ថបទ
        with open(input_path, "rb") as audio_file:
            transcript_obj = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        original_text = transcript_obj.text

        if not original_text.strip():
            await processing_msg.edit_text("❌ រកមិនឃើញអត្ថបទ ឬសំឡេងនៅក្នុងឯកសារនេះទេ។")
            return

        # GPT API សម្រាប់បកប្រែ
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"You are a professional translator. Translate everything accurately into {TARGET_LANGUAGE}."},
                {"role": "user", "content": original_text}
            ]
        )
        translated_text = response.choices[0].message.content

        result_text = (
            f"✅ **ការបកប្រែជោគជ័យ ({TARGET_LANGUAGE})**\n\n"
            f"{translated_text}\n\n"
            f"---\n"
            f"📝 *អត្ថបទដើម:* {original_text[:800]}..."
        )
        await processing_msg.edit_text(result_text, parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Error: {e}")
        await processing_msg.edit_text(f"❌ មានបញ្ហាកើតឡើង៖ {str(e)}")

    finally:
        if os.path.exists(input_path):
            os.remove(input_path)

def main():
    # ចាប់ផ្តើម Flask Server ក្នុង Background
    keep_alive()

    # ចាប់ផ្តើម Telegram Bot
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.VOICE | filters.DOCUMENT, handle_media))
    
    print("🤖 Telegram Bot กำลังรัน...")
    application.run_polling()

if __name__ == "__main__":
    main()