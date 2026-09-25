import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
import speech_recognition as sr
import requests
from pydub import AudioSegment
import edge_tts

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
        "សួស្តី! 👋 ខ្ញុំគឺជា Bot បកប្រែភាសា (ឥតគិតថ្លៃ ១០០%)។\n\n"
        "🎙 **មុខងារទី១៖** ផ្ញើសំឡេង (Voice) ឬវីដេអូ មកខ្ញុំដើម្បីបកប្រែជាអក្សរខ្មែរ។\n"
        "📝 **មុខងារទី២៖** ផ្ញើអក្សរ (Text) មកខ្ញុំ ខ្ញុំនឹងបកប្រែជាភាសាខ្មែរ រួចអានជាសំឡេងឱ្យអ្នកស្ដាប់! 🚀"
    )
    await update.message.reply_text(welcome_message)

from concurrent.futures import ThreadPoolExecutor

def process_single_chunk(args):
    i, chunk, update_id = args
    chunk_path = f"temp_chunk_{update_id}_{i}.wav"
    chunk.export(chunk_path, format="wav")
    recognizer = sr.Recognizer()
    text = ""
    with sr.AudioFile(chunk_path) as source:
        audio_data = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio_data, language='en-US')
        except sr.UnknownValueError:
            pass
        except sr.RequestError as e:
            logging.error(f"Google API Error: {e}")
            
    if os.path.exists(chunk_path):
        os.remove(chunk_path)
    return i, text

def process_audio_sync(input_path, update_id):
    """
    រត់កូដធ្ងន់ៗ (បម្លែងសំឡេង, ស្ដាប់, និងបកប្រែ) នៅក្នុង Background Thread 
    """
    try:
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_channels(1).set_frame_rate(16000)

        # កាត់សំឡេងជាដុំតូចៗ ១នាទីម្ដង
        chunk_length_ms = 60000 
        chunks = [audio[i:i+chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]
        
        # ប្រើ Multithreading ដើម្បីបញ្ជូនសំឡេងទៅ Google ព្រមៗគ្នា (ដើរលឿនជាងមុន ៥ដង)
        with ThreadPoolExecutor(max_workers=5) as executor:
            args_list = [(i, chunk, update_id) for i, chunk in enumerate(chunks)]
            results = list(executor.map(process_single_chunk, args_list))
            
        results.sort(key=lambda x: x[0]) # តម្រៀបតាមលំដាប់ដើម
        original_text = " ".join([x[1] for x in results if x[1]])

        if not original_text.strip():
            return None, "❌ សុំទោស ខ្ញុំស្ដាប់សំឡេងនេះមិនយល់ទេ។ អាចមកពីសំឡេងមិនច្បាស់ គ្មានអ្នកនិយាយ ឬជាភាសាផ្សេង។"

        text_chunks = [original_text[i:i+4000] for i in range(0, len(original_text), 4000)]
        translated_text = ""
        for t_chunk in text_chunks:
            translated_text += translate_text_sync(t_chunk) + " "

        return original_text, translated_text
    except Exception as e:
        return None, f"❌ មានបញ្ហាកើតឡើងក្នុងការដំណើរការ៖ {str(e)}"

def translate_text_sync(text):
    """
    បកប្រែអក្សរដោយប្រើប្រាស់ Google Translate API ផ្ទាល់ (ឥតគិតថ្លៃ និងមិនគាំង)
    """
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": TARGET_LANGUAGE,
            "dt": "t",
            "q": text
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        result = response.json()
        translated = "".join([sentence[0] for sentence in result[0]])
        return translated
    except Exception as e:
        logging.error(f"Translation error: {e}")
        return text

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    processing_msg = await update.message.reply_text("⏳ កំពុងបកប្រែ និងអានជាសំឡេង...")
    
    try:
        translated_text = await asyncio.to_thread(translate_text_sync, user_text)
        
        # ប្រើប្រាស់ Microsoft Edge TTS សម្រាប់អានសំឡេងខ្មែរឱ្យពិរោះ
        # km-KH-SreymomNeural គឺសំឡេងស្រី | km-KH-PisethNeural គឺសំឡេងប្រុស
        audio_path = f"temp_tts_{update.update_id}.mp3"
        communicate = edge_tts.Communicate(translated_text, "km-KH-SreymomNeural")
        await communicate.save(audio_path)
        
        await processing_msg.edit_text(f"✅ **បកប្រែជោគជ័យ:**\n\n{translated_text}")
        
        # ផ្ញើសំឡេងត្រលប់ទៅវិញ
        with open(audio_path, 'rb') as audio_file:
            await update.message.reply_voice(audio_file)
            
        if os.path.exists(audio_path):
            os.remove(audio_path)
    except Exception as e:
        logging.error(f"Error TTS: {e}")
        await processing_msg.edit_text(f"❌ មានបញ្ហា៖ {str(e)}")

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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
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