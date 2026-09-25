import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
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

    processing_msg = await message.reply_text("⏳ កំពុងទាញយកឯកសារ... សូមរង់ចាំបន្តិច។")
    
    input_path = f"temp_input_{update.update_id}{file_extension}"
    
    try:
        await file_obj.download_to_drive(input_path)

        # បម្លែងទៅជា WAV
        await processing_msg.edit_text("⏳ កំពុងទាញយកសំឡេងចេញពីឯកសារ (Audio Extraction)...")
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_channels(1).set_frame_rate(16000)

        # កាត់សំឡេងជាដុំតូចៗ (១នាទីម្ដង) ដើម្បីកុំឲ្យ Google API បដិសេធ
        chunk_length_ms = 60000 
        chunks = [audio[i:i+chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]
        
        recognizer = sr.Recognizer()
        original_text = ""
        
        await processing_msg.edit_text(f"⏳ កំពុងស្តាប់សំឡេង និងសរសេរជាអក្សរ ({len(chunks)} ផ្នែក)...")
        
        for i, chunk in enumerate(chunks):
            chunk_path = f"temp_chunk_{update.update_id}_{i}.wav"
            chunk.export(chunk_path, format="wav")
            with sr.AudioFile(chunk_path) as source:
                audio_data = recognizer.record(source)
                try:
                    # ស្តាប់សំឡេង (អាចដូរ 'en-US' ទៅជាភាសាផ្សេងបាន បើដឹងថាជាភាសាអី)
                    text = recognizer.recognize_google(audio_data, language='en-US')
                    original_text += text + ". "
                except sr.UnknownValueError:
                    pass # រំលងបើស្ដាប់អត់បាន
                except sr.RequestError as e:
                    logging.error(f"Google API Error: {e}")
            
            if os.path.exists(chunk_path):
                os.remove(chunk_path)

        if not original_text.strip():
            await processing_msg.edit_text("❌ សុំទោស ខ្ញុំស្ដាប់សំឡេងនេះមិនយល់ទេ។ អាចមកពីសំឡេងមិនច្បាស់ គ្មានអ្នកនិយាយ ឬជាភាសាផ្សេង។")
            return

        # បកប្រែ
        await processing_msg.edit_text("⏳ កំពុងបកប្រែអត្ថបទមកជាភាសាខ្មែរ...")
        translator = GoogleTranslator(source='auto', target=TARGET_LANGUAGE)
        
        # deep-translator មានកំណត់ប្រវែងអត្ថបទ ដូច្នេះយើងត្រូវបកប្រែជាដុំៗដូចគ្នា
        text_chunks = [original_text[i:i+4000] for i in range(0, len(original_text), 4000)]
        translated_text = ""
        for t_chunk in text_chunks:
            translated_text += translator.translate(t_chunk) + " "

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
    application.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_media))
    
    port = int(os.environ.get("PORT", 10000))
    
    if RENDER_URL:
        # ដំណើរការតាម Webhook (នៅលើ Render)
        print(f"🤖 Telegram Bot ដំណើរការតាមរយៈ Webhook នៅលើ URL: {RENDER_URL}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=f"{RENDER_URL}/{TOKEN}"
        )
    else:
        # ដំណើរការធម្មតា (នៅលើកុំព្យូទ័រផ្ទាល់ខ្លួន)
        print("🤖 Telegram Bot ដំណើរការតាមរយៈ Polling...")
        application.run_polling()

if __name__ == "__main__":
    main()