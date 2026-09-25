import os
import logging
import asyncio
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
import requests
import edge_tts
from groq import Groq

# កំណត់ Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ទាញយក Environment Variables
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("សូមដាក់ TELEGRAM_TOKEN នៅក្នុង Environment Variables របស់ Render!")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    logging.warning("សូមដាក់ GROQ_API_KEY នៅក្នុង Environment Variables! បើមិនដូច្នោះទេមុខងារសំឡេងនឹងមិនដើរទេ។")

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")

# បង្កើត Client សម្រាប់ Groq
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ភាសាអាស៊ានទាំង ១១ បូកបន្ថែម ចិន និង អង់គ្លេស
LANG_INFO = {
    'km': {'name': '🇰🇭 ខ្មែរ', 'voice': 'km-KH-SreymomNeural'},
    'th': {'name': '🇹🇭 ថៃ', 'voice': 'th-TH-PremwadeeNeural'},
    'vi': {'name': '🇻🇳 វៀតណាម', 'voice': 'vi-VN-HoaiMyNeural'},
    'lo': {'name': '🇱🇦 ឡាវ', 'voice': 'lo-LA-KeomanyNeural'},
    'my': {'name': '🇲🇲 ភូមា', 'voice': 'my-MM-NilarNeural'},
    'id': {'name': '🇮🇩 ឥណ្ឌូណេស៊ី', 'voice': 'id-ID-GadisNeural'},
    'ms': {'name': '🇲🇾 ម៉ាឡេស៊ី', 'voice': 'ms-MY-YasminNeural'},
    'tl': {'name': '🇵🇭 ហ្វីលីពីន', 'voice': 'fil-PH-BlessicaNeural'},
    'ms_bn': {'name': '🇧🇳 ប្រ៊ុយណេ', 'voice': 'ms-MY-YasminNeural', 'google_lang': 'ms'},
    'ta': {'name': '🇸🇬 សិង្ហបុរី', 'voice': 'ta-SG-VenbaNeural', 'google_lang': 'ta'},
    'pt': {'name': '🇹🇱 ទីម័រខាងកើត', 'voice': 'pt-PT-RaquelNeural'},
    'zh-CN': {'name': '🇨🇳 ចិន', 'voice': 'zh-CN-XiaoxiaoNeural'},
    'en': {'name': '🇬🇧 អង់គ្លេស', 'voice': 'en-US-AriaNeural'}
}

def build_language_keyboard(prefix="translate"):
    keyboard = []
    row = []
    for code, info in LANG_INFO.items():
        row.append(InlineKeyboardButton(info['name'], callback_data=f"{prefix}_{code}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "ចាប់ផ្ដើមបត (Start Bot)")
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "សួស្តី! 👋 ខ្ញុំគឺជា Bot បកប្រែភាសាអាស៊ាន (បំពាក់ដោយ Groq AI ⚡️ លឿនដូចរន្ទះ)។\n\n"
        "ដើម្បីចាប់ផ្ដើម សូមគ្រាន់តែផ្ញើ **សំឡេង (Voice) វីដេអូ ឬអត្ថបទ** មកខ្ញុំ។ បន្ទាប់មក ខ្ញុំនឹងសួរអ្នកថាតើអ្នកចង់បកប្រែវាទៅជាភាសាអ្វី! 🚀"
    )
    await update.message.reply_text(welcome_message)

async def prompt_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    # រក្សាទុកឯកសារនៅក្នុង Memory
    context.user_data['pending_msg'] = msg
    
    if msg.text:
        doc_type = "📝 អត្ថបទ (Text)"
    elif msg.video: 
        doc_type = "🎬 វីដេអូ (Video)"
    elif msg.audio: 
        doc_type = "🎵 ចម្រៀង/សំឡេង (Audio)"
    elif msg.voice: 
        doc_type = "🎙 សារសំឡេង (Voice Note)"
    else: 
        doc_type = "📁 ឯកសារ (Document)"
        
    prompt_text = (
        f"📥 **ប្រភេទឯកសារ៖** {doc_type}\n"
        f"🗣 **ភាសាដើម៖** (Groq AI ស្វែងរកដោយស្វ័យប្រវត្តិ ⚡️)\n\n"
        f"🎯 តើអ្នកចង់ឱ្យខ្ញុំបកប្រែទៅជាភាសាអ្វី?"
    )
    
    keyboard = build_language_keyboard("translate")
    await msg.reply_text(prompt_text, reply_markup=keyboard, reply_to_message_id=msg.message_id)

def translate_text_sync(text, target_lang):
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

def transcribe_with_google_cloud(file_path):
    """
    Placeholder/Mock function for Google Cloud Speech-to-Text.
    In the future, integrate google-cloud-speech library here.
    """
    logging.info(f"Routing to Google Cloud for Khmer speech-to-text: {file_path}")
    return "នេះគឺជាអត្ថបទបណ្ដោះអាសន្នពី Google Cloud Speech-to-Text។"

def transcribe_with_groq(file_path):
    if not groq_client:
        return None, "❌ កូដ GROQ_API_KEY មិនទាន់បានដាក់ចូលក្នុង Render ទេ។ សូមបញ្ចូលវាសិន!"
    
    try:
        with open(file_path, "rb") as file:
            response = groq_client.audio.transcriptions.create(
                file=(file_path, file.read()),
                model="whisper-large-v3",
                response_format="verbose_json",
            )
            
        language = getattr(response, 'language', None) or (isinstance(response, dict) and response.get('language'))
        text = getattr(response, 'text', None) or (isinstance(response, dict) and response.get('text'))
        
        if language == 'km':
            # Route to Google Cloud Speech-to-Text for Khmer
            return transcribe_with_google_cloud(file_path), None
        else:
            # Use Groq's transcription for other languages
            return text, None
    except Exception as e:
        logging.error(f"Groq API Error: {e}")
        return None, f"❌ បញ្ហាប្រព័ន្ធ Groq AI៖ {str(e)}"

async def process_text_action(msg, processing_msg, target_lang, voice_id):
    try:
        translated_text = await asyncio.to_thread(translate_text_sync, msg.text, target_lang)
        
        audio_path = f"temp_tts_{msg.message_id}.mp3"
        communicate = edge_tts.Communicate(translated_text, voice_id)
        await communicate.save(audio_path)
        
        await processing_msg.edit_text(f"✅ **ចុចលើអត្ថបទខាងក្រោមដើម្បី Copy:**\n\n`{translated_text}`", parse_mode="Markdown")
        
        with open(audio_path, 'rb') as audio_file:
            await msg.reply_voice(audio_file)
            
        if os.path.exists(audio_path):
            os.remove(audio_path)
    except Exception as e:
        logging.error(f"Error TTS: {e}")
        await processing_msg.edit_text(f"❌ មានបញ្ហា៖ {str(e)}")

async def process_media_action(msg, processing_msg, target_lang, voice_id):
    file_obj = None
    if msg.video:
        file_obj = await msg.video.get_file()
        file_extension = ".mp4"
    elif msg.audio:
        file_obj = await msg.audio.get_file()
        file_extension = ".mp3"
    elif msg.voice:
        file_obj = await msg.voice.get_file()
        file_extension = ".ogg"
    elif msg.document:
        if msg.document.mime_type and ("video" in msg.document.mime_type or "audio" in msg.document.mime_type):
            file_obj = await msg.document.get_file()
            file_extension = os.path.splitext(msg.document.file_name)[1]
        else:
            await processing_msg.edit_text("❌ សូមផ្ញើតែឯកសារវីដេអូ ឬសំឡេងប៉ុណ្ណោះ!")
            return
            
    input_path = f"temp_input_{msg.message_id}{file_extension}"
    
    try:
        await file_obj.download_to_drive(input_path)
        
        # ១. ស្តាប់សំឡេងដោយប្រើប្រាស់ Groq AI ស្វ័យប្រវត្តិ
        original_text, error_msg = await asyncio.to_thread(transcribe_with_groq, input_path)
        
        if error_msg:
            await processing_msg.edit_text(error_msg)
            return
            
        if not original_text or not original_text.strip():
            await processing_msg.edit_text("❌ សុំទោស AI ស្ដាប់សំឡេងនេះមិនយល់ទេ។ អាចមកពីសំឡេងមិនច្បាស់ ឬគ្មានអ្នកនិយាយ។")
            return

        # ២. បកប្រែអត្ថបទ
        text_chunks = [original_text[i:i+4000] for i in range(0, len(original_text), 4000)]
        translated_text = ""
        for t_chunk in text_chunks:
            translated_text += await asyncio.to_thread(translate_text_sync, t_chunk, target_lang) + " "

        result_text = (
            f"✅ **ការបកប្រែជោគជ័យ (ចុចលើអត្ថបទខាងក្រោមដើម្បី Copy):**\n\n"
            f"`{translated_text}`\n\n"
            f"---\n"
            f"📝 *អត្ថបទដើម (Groq AI):*\n`{original_text}`"
        )
        await processing_msg.edit_text(result_text, parse_mode="Markdown")
        
        # ៣. បង្កើតជាសំឡេងត្រលប់ទៅវិញ
        audio_path = f"temp_tts_media_{msg.message_id}.mp3"
        communicate = edge_tts.Communicate(translated_text, voice_id)
        await communicate.save(audio_path)
        with open(audio_path, 'rb') as audio_file:
            await msg.reply_voice(audio_file)
        if os.path.exists(audio_path):
            os.remove(audio_path)

    except Exception as e:
        logging.error(f"Error: {e}")
        await processing_msg.edit_text(f"❌ មានបញ្ហាកើតឡើង៖ {str(e)}")
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    msg = context.user_data.get('pending_msg')
    if not msg:
        await query.edit_message_text("❌ ឯកសារនេះផុតកំណត់ហើយ។ សូមផ្ញើឯកសារ ឬអក្សរម្ដងទៀត។")
        return
        
    if data.startswith('translate_'):
        code = data.split('_', 1)[1]
        
        target_info = LANG_INFO[code]
        target_lang = target_info.get('google_lang', code)
        voice_id = target_info['voice']
        
        processing_msg = query.message
        
        if msg.text:
            await query.edit_message_text(f"⏳ កំពុងបកប្រែអត្ថបទទៅជា **{target_info['name']}** និងអានជាសំឡេង...")
            await process_text_action(msg, processing_msg, target_lang, voice_id)
        else:
            await query.edit_message_text(f"⚡️ ឱ្យ Groq AI ស្តាប់សំឡេង និងបកប្រែទៅជា **{target_info['name']}**...")
            await process_media_action(msg, processing_msg, target_lang, voice_id)

def main():
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_language_selection))
    application.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL, prompt_language_selection))
    
    port = int(os.environ.get("PORT", 10000))
    if RENDER_URL:
        print(f"🤖 Telegram Bot ដំណើរការតាមរយៈ Webhook នៅលើ URL: {RENDER_URL}")
        application.run_webhook(listen="0.0.0.0", port=port, url_path=TOKEN, webhook_url=f"{RENDER_URL}/{TOKEN}")
    else:
        print("🤖 Telegram Bot ដំណើរការតាមរយៈ Polling...")
        application.run_polling()

if __name__ == "__main__":
    main()