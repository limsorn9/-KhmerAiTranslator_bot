import os
import logging
import asyncio
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
import speech_recognition as sr
import requests
from pydub import AudioSegment
import edge_tts
from concurrent.futures import ThreadPoolExecutor

# កំណត់ Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Telegram Token
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("សូមដាក់ TELEGRAM_TOKEN នៅក្នុង Environment Variables របស់ Render!")

# ទាញយក URL របស់វិបសាយ Render ដោយស្វ័យប្រវត្តិ
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")

# ភាសា និងសំឡេងរបស់ Microsoft Edge TTS
VOICES = {
    'km': 'km-KH-SreymomNeural',
    'en': 'en-US-AriaNeural',
    'zh-CN': 'zh-CN-XiaoxiaoNeural'
}

LANG_NAMES = {
    'km': '🇰🇭 ខ្មែរ',
    'en': '🇬🇧 English',
    'zh-CN': '🇨🇳 中文 (Chinese)'
}

# ----------------- TELEGRAM BOT LOGIC -----------------
async def post_init(application):
    # បង្កើត Menu សម្រាប់ Bot
    await application.bot.set_my_commands([
        BotCommand("start", "ចាប់ផ្ដើមបត (Start Bot)"),
        BotCommand("lang", "ជ្រើសរើសភាសាបកប្រែ (Change Language)")
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "សួស្តី! 👋 ខ្ញុំគឺជា Bot បកប្រែភាសា (ឥតគិតថ្លៃ ១០០%)។\n\n"
        "🎙 **មុខងារទី១៖** ផ្ញើសំឡេង (Voice) ឬវីដេអូ មកខ្ញុំដើម្បីបកប្រែ។\n"
        "📝 **មុខងារទី២៖** ផ្ញើអក្សរ (Text) មកខ្ញុំ ខ្ញុំនឹងបកប្រែ និងអានជាសំឡេងឱ្យអ្នកស្ដាប់! 🚀\n\n"
        "💡 អ្នកអាចវាយបញ្ជា /lang ដើម្បីប្តូរភាសាដែលត្រូវបកប្រែទៅបាន។"
    )
    await update.message.reply_text(welcome_message)

async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇰🇭 ខ្មែរ (Khmer)", callback_data='lang_km')],
        [InlineKeyboardButton("🇬🇧 អង់គ្លេស (English)", callback_data='lang_en')],
        [InlineKeyboardButton("🇨🇳 ចិន (Chinese)", callback_data='lang_zh-CN')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('សូមជ្រើសរើសភាសាដែលអ្នកចង់ឱ្យខ្ញុំបកប្រែទៅ៖', reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith('lang_'):
        selected_lang = data.split('_')[1]
        context.user_data['target_lang'] = selected_lang
        lang_name = LANG_NAMES.get(selected_lang, selected_lang)
        await query.edit_message_text(text=f"✅ បានប្តូរការកំណត់។ ចាប់ពីពេលនេះទៅ ខ្ញុំនឹងបកប្រែទៅជា៖ **{lang_name}**")

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

def translate_text_sync(text, target_lang):
    """
    បកប្រែអក្សរដោយប្រើប្រាស់ Google Translate API ផ្ទាល់
    """
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target_lang,
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

def process_audio_sync(input_path, update_id, target_lang):
    try:
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_channels(1).set_frame_rate(16000)

        chunk_length_ms = 60000 
        chunks = [audio[i:i+chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            args_list = [(i, chunk, update_id) for i, chunk in enumerate(chunks)]
            results = list(executor.map(process_single_chunk, args_list))
            
        results.sort(key=lambda x: x[0])
        original_text = " ".join([x[1] for x in results if x[1]])

        if not original_text.strip():
            return None, "❌ សុំទោស ខ្ញុំស្ដាប់សំឡេងនេះមិនយល់ទេ។ អាចមកពីសំឡេងមិនច្បាស់ គ្មានអ្នកនិយាយ ឬជាភាសាផ្សេង។"

        text_chunks = [original_text[i:i+4000] for i in range(0, len(original_text), 4000)]
        translated_text = ""
        for t_chunk in text_chunks:
            translated_text += translate_text_sync(t_chunk, target_lang) + " "

        return original_text, translated_text
    except Exception as e:
        return None, f"❌ មានបញ្ហាកើតឡើងក្នុងការដំណើរការ៖ {str(e)}"

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    target_lang = context.user_data.get('target_lang', 'km')
    
    processing_msg = await update.message.reply_text("⏳ កំពុងបកប្រែ និងអានជាសំឡេង...")
    
    try:
        translated_text = await asyncio.to_thread(translate_text_sync, user_text, target_lang)
        
        audio_path = f"temp_tts_{update.update_id}.mp3"
        voice_id = VOICES.get(target_lang, 'km-KH-SreymomNeural')
        
        communicate = edge_tts.Communicate(translated_text, voice_id)
        await communicate.save(audio_path)
        
        await processing_msg.edit_text(f"✅ **ចុចលើអត្ថបទខាងក្រោមដើម្បី Copy:**\n\n`{translated_text}`", parse_mode="Markdown")
        
        with open(audio_path, 'rb') as audio_file:
            await update.message.reply_voice(audio_file)
            
        if os.path.exists(audio_path):
            os.remove(audio_path)
    except Exception as e:
        logging.error(f"Error TTS: {e}")
        await processing_msg.edit_text(f"❌ មានបញ្ហា៖ {str(e)}")

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    target_lang = context.user_data.get('target_lang', 'km')
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

        result = await asyncio.to_thread(process_audio_sync, input_path, update.update_id, target_lang)
        
        if result[0] is None:
            await processing_msg.edit_text(result[1])
        else:
            original_text, translated_text = result
            result_text = (
                f"✅ **ការបកប្រែជោគជ័យ (ចុចលើអត្ថបទខាងក្រោមដើម្បី Copy):**\n\n"
                f"`{translated_text}`\n\n"
                f"---\n"
                f"📝 *អត្ថបទដើម:*\n`{original_text}`"
            )
            await processing_msg.edit_text(result_text, parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Error: {e}")
        await processing_msg.edit_text(f"❌ មានបញ្ហាកើតឡើង៖ {str(e)}")

    finally:
        if os.path.exists(input_path):
            os.remove(input_path)

def main():
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("lang", lang_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_media))
    
    port = int(os.environ.get("PORT", 10000))
    
    if RENDER_URL:
        print(f"🤖 Telegram Bot ដំណើរការតាមរយៈ Webhook នៅលើ URL: {RENDER_URL}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=TOKEN,
            webhook_url=f"{RENDER_URL}/{TOKEN}"
        )
    else:
        print("🤖 Telegram Bot ដំណើរការតាមរយៈ Polling...")
        application.run_polling()

if __name__ == "__main__":
    main()