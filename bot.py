import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
import speech_recognition as sr
from deep_translator import GoogleTranslator
from pydub import AudioSegment

# កំណត់ Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Telegram Token (ទាញយកពី Environment Variables ដែលដាក់ក្នុង Render)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("សូមដាក់ TELEGRAM_TOKEN នៅក្នុង Environment Variables របស់ Render!")
TARGET_LANGUAGE = "km"

# ទាញយក URL របស់វិបសាយ Render ដោយស្វ័យប្រវត្តិ
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")

# ----------------- TELEGRAM BOT LOGIC -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "សួស្តី! 👋 ខ្ញុំគឺជា Bot បកប្រែសំឡេង និងវីដេអូមកជាភាសាខ្មែរ (ឥតគិតថ្លៃ ១០០%)។\n\n"
        "ដើម្បីចាប់ផ្ដើម សូមគ្រាន់តែផ្ញើ **Voice (សំឡេង), បទចម្រៀង (MP3) ឬវីដេអូ** មកកាន់ខ្ញុំ។ ខ្ញុំនឹងស្ដាប់ និងបកប្រែវាជូនអ្នកភ្លាមៗ! 🚀"
    )
    await update.message.reply_text(welcome_message)

def process_audio_sync(input_path, update_id):
    """
    រត់កូដធ្ងន់ៗ (បម្លែងសំឡេង, ស្ដាប់, និងបកប្រែ) នៅក្នុង Background Thread 
    ដើម្បីកុំឱ្យគាំង Event Loop របស់ Telegram Bot ។
    """
    try:
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_channels(1).set_frame_rate(16000)

        chunk_length_ms = 60000 
        chunks = [audio[i:i+chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]
        
        recognizer = sr.Recognizer()
        original_text = ""
        
        for i, chunk in enumerate(chunks):
            chunk_path = f"temp_chunk_{update_id}_{i}.wav"
            chunk.export(chunk_path, format="wav")
            with sr.AudioFile(chunk_path) as source:
                audio_data = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio_data, language='en-US')
                    original_text += text + ". "
                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    logging.error(f"Google API Error: {e}")
            
            if os.path.exists(chunk_path):
                os.remove(chunk_path)

        if not original_text.strip():
            return None, "❌ សុំទោស ខ្ញុំស្ដាប់សំឡេងនេះមិនយល់ទេ។ អាចមកពីសំឡេងមិនច្បាស់ គ្មានអ្នកនិយាយ ឬជាភាសាផ្សេង។"

        translator = GoogleTranslator(source='auto', target=TARGET_LANGUAGE)
        text_chunks = [original_text[i:i+4000] for i in range(0, len(original_text), 4000)]
        translated_text = ""
        for t_chunk in text_chunks:
            translated_text += translator.translate(t_chunk) + " "

        return original_text, translated_text
    except Exception as e:
        return None, f"❌ មានបញ្ហាកើតឡើងក្នុងការដំណើរការ៖ {str(e)}"

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
            await message.reply_text("សូមផ្ញើតែឯកសារវីដេអូ ឬសំឡេង (MP3, WAV, MP4, OGG) ប៉ុណ្ណោះ!")
            return
    else:
        await message.reply_text("សូមផ្ញើឯកសារវីដេអូ ឬសំឡេងមកកាន់បត ដើម្បីធ្វើការបកប្រែ។")
        return

    processing_msg = await message.reply_text("⏳ កំពុងទាញយកឯកសារ និងដំណើរការ... (អាចប្រើពេលបន្តិច)")
    
    input_path = f"temp_input_{update.update_id}{file_extension}"
    
    try:
        await file_obj.download_to_drive(input_path)

        # បញ្ជូនការងារធ្ងន់ៗទៅកាន់ Thread ផ្សេងដើម្បីកុំឱ្យគាំង Telegram Bot
        result = await asyncio.to_thread(process_audio_sync, input_path, update.update_id)
        
        if result[0] is None:
            await processing_msg.edit_text(result[1])
        else:
            original_text, translated_text = result
            result_text = (
                f"✅ **ការបកប្រែជោគជ័យ (Khmer)**\n\n"
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
    application = ApplicationBuilder().token(TOKEN).build()
    
    # បន្ថែមប៊ូតុង /start
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_media))
    
    port = int(os.environ.get("PORT", 10000))
    
    if RENDER_URL:
        # ដំណើរការតាម Webhook (នៅលើ Render)
        print(f"🤖 Telegram Bot ដំណើរការតាមរយៈ Webhook នៅលើ URL: {RENDER_URL}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=TOKEN,
            webhook_url=f"{RENDER_URL}/{TOKEN}"
        )
    else:
        # ដំណើរការធម្មតា (នៅលើកុំព្យូទ័រផ្ទាល់ខ្លួន)
        print("🤖 Telegram Bot ដំណើរការតាមរយៈ Polling...")
        application.run_polling()

if __name__ == "__main__":
    main()