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

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")

# ភាសាអាស៊ានទាំង ១១ បូកបន្ថែម ចិន និង អង់គ្លេស
LANG_INFO = {
    'km': {'name': '🇰🇭 ខ្មែរ', 'voice': 'km-KH-SreymomNeural', 'sr_lang': 'km-KH'},
    'th': {'name': '🇹🇭 ថៃ', 'voice': 'th-TH-PremwadeeNeural', 'sr_lang': 'th-TH'},
    'vi': {'name': '🇻🇳 វៀតណាម', 'voice': 'vi-VN-HoaiMyNeural', 'sr_lang': 'vi-VN'},
    'lo': {'name': '🇱🇦 ឡាវ', 'voice': 'lo-LA-KeomanyNeural', 'sr_lang': 'lo-LA'},
    'my': {'name': '🇲🇲 ភូមា', 'voice': 'my-MM-NilarNeural', 'sr_lang': 'my-MM'},
    'id': {'name': '🇮🇩 ឥណ្ឌូណេស៊ី', 'voice': 'id-ID-GadisNeural', 'sr_lang': 'id-ID'},
    'ms': {'name': '🇲🇾 ម៉ាឡេស៊ី', 'voice': 'ms-MY-YasminNeural', 'sr_lang': 'ms-MY'},
    'tl': {'name': '🇵🇭 ហ្វីលីពីន', 'voice': 'fil-PH-BlessicaNeural', 'sr_lang': 'fil-PH'},
    'ms_bn': {'name': '🇧🇳 ប្រ៊ុយណេ', 'voice': 'ms-MY-YasminNeural', 'google_lang': 'ms', 'sr_lang': 'ms-MY'},
    'ta': {'name': '🇸🇬 សិង្ហបុរី', 'voice': 'ta-SG-VenbaNeural', 'google_lang': 'ta', 'sr_lang': 'ta-SG'},
    'pt': {'name': '🇹🇱 ទីម័រខាងកើត', 'voice': 'pt-PT-RaquelNeural', 'sr_lang': 'pt-PT'},
    'zh-CN': {'name': '🇨🇳 ចិន', 'voice': 'zh-CN-XiaoxiaoNeural', 'sr_lang': 'zh-CN'},
    'en': {'name': '🇬🇧 អង់គ្លេស', 'voice': 'en-US-AriaNeural', 'sr_lang': 'en-US'}
}

def build_language_keyboard(prefix):
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
        "សួស្តី! 👋 ខ្ញុំគឺជា Bot បកប្រែភាសាអាស៊ាន (ឥតគិតថ្លៃ ១០០%)។\n\n"
        "ដើម្បីចាប់ផ្ដើម សូមគ្រាន់តែផ្ញើ **សំឡេង (Voice) វីដេអូ ឬអត្ថបទ** មកខ្ញុំ។ បន្ទាប់មក ខ្ញុំនឹងសួរអ្នកថាតើអ្នកចង់បកប្រែវាទៅជាភាសាអ្វី! 🚀"
    )
    await update.message.reply_text(welcome_message)

async def prompt_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    # រក្សាទុកឯកសារនៅក្នុង Memory
    context.user_data['pending_msg'] = msg
    
    if msg.text:
        doc_type = "📝 អត្ថបទ (Text)"
        prompt_text = (
            f"📥 **ប្រភេទឯកសារ៖** {doc_type}\n"
            f"🗣 **ភាសាដើម៖** (ស្វែងរកដោយស្វ័យប្រវត្តិ 🤖)\n\n"
            f"🎯 តើអ្នកចង់ឱ្យខ្ញុំបកប្រែទៅជាភាសាអ្វី?"
        )
        keyboard = build_language_keyboard("translate")
    else:
        if msg.video: doc_type = "🎬 វីដេអូ (Video)"
        elif msg.audio: doc_type = "🎵 ចម្រៀង/សំឡេង (Audio)"
        elif msg.voice: doc_type = "🎙 សារសំឡេង (Voice Note)"
        else: doc_type = "📁 ឯកសារ (Document)"
        
        context.user_data['pending_doc_type'] = doc_type
        prompt_text = (
            f"📥 **ប្រភេទឯកសារ៖** {doc_type}\n\n"
            f"❓ តើសំឡេងនេះនិយាយជាភាសាអ្វី? (សូមជ្រើសរើសភាសាដើម)"
        )
        keyboard = build_language_keyboard("source")
        
    await msg.reply_text(prompt_text, reply_markup=keyboard, reply_to_message_id=msg.message_id)

def process_single_chunk(args):
    i, chunk, update_id, sr_lang = args
    chunk_path = f"temp_chunk_{update_id}_{i}.wav"
    chunk.export(chunk_path, format="wav")
    recognizer = sr.Recognizer()
    text = ""
    with sr.AudioFile(chunk_path) as source:
        audio_data = recognizer.record(source)
        try:
            # ប្រើប្រាស់ភាសាដើមដែល User បានជ្រើសរើស ធ្វើឱ្យស្ដាប់បានត្រឹមត្រូវ ១០០%
            text = recognizer.recognize_google(audio_data, language=sr_lang)
        except sr.UnknownValueError:
            pass
        except sr.RequestError as e:
            logging.error(f"Google API Error: {e}")
            
    if os.path.exists(chunk_path):
        os.remove(chunk_path)
    return i, text

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

def process_audio_sync(input_path, update_id, sr_lang, target_lang):
    try:
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_channels(1).set_frame_rate(16000)

        chunk_length_ms = 60000 
        chunks = [audio[i:i+chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            args_list = [(i, chunk, update_id, sr_lang) for i, chunk in enumerate(chunks)]
            results = list(executor.map(process_single_chunk, args_list))
            
        results.sort(key=lambda x: x[0])
        original_text = " ".join([x[1] for x in results if x[1]])

        if not original_text.strip():
            return None, "❌ សុំទោស ខ្ញុំស្ដាប់សំឡេងនេះមិនយល់ទេ។ អាចមកពីសំឡេងមិនច្បាស់ គ្មានអ្នកនិយាយ ឬអ្នកជ្រើសរើសភាសាដើមខុស។"

        text_chunks = [original_text[i:i+4000] for i in range(0, len(original_text), 4000)]
        translated_text = ""
        for t_chunk in text_chunks:
            translated_text += translate_text_sync(t_chunk, target_lang) + " "

        return original_text, translated_text
    except Exception as e:
        return None, f"❌ មានបញ្ហាកើតឡើងក្នុងការដំណើរការ៖ {str(e)}"

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

async def process_media_action(msg, processing_msg, sr_lang, target_lang, voice_id):
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
        result = await asyncio.to_thread(process_audio_sync, input_path, msg.message_id, sr_lang, target_lang)
        
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
            
            # បង្កើតជាសំឡេងត្រលប់ទៅវិញ
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
        
    if data.startswith('source_'):
        code = data.split('_', 1)[1]
        context.user_data['pending_source'] = code
        doc_type = context.user_data.get('pending_doc_type', 'ឯកសារ')
        source_name = LANG_INFO[code]['name']
        
        prompt_text = (
            f"📥 **ប្រភេទឯកសារ៖** {doc_type}\n"
            f"🗣 **ភាសាដើម៖** {source_name}\n\n"
            f"🎯 តើអ្នកចង់ឱ្យខ្ញុំបកប្រែទៅជាភាសាអ្វី?"
        )
        keyboard = build_language_keyboard("translate")
        await query.edit_message_text(prompt_text, reply_markup=keyboard)
        
    elif data.startswith('translate_'):
        code = data.split('_', 1)[1]
        
        target_info = LANG_INFO[code]
        target_lang = target_info.get('google_lang', code)
        voice_id = target_info['voice']
        
        processing_msg = query.message
        
        if msg.text:
            await query.edit_message_text(f"⏳ កំពុងបកប្រែអត្ថបទទៅជា **{target_info['name']}** និងអានជាសំឡេង...")
            await process_text_action(msg, processing_msg, target_lang, voice_id)
        else:
            source_code = context.user_data.get('pending_source', 'km')
            source_info = LANG_INFO[source_code]
            sr_lang = source_info['sr_lang']
            
            await query.edit_message_text(f"⏳ កំពុងស្ដាប់សំឡេងម៉ាស៊ីន និងបកប្រែទៅជា **{target_info['name']}**...")
            await process_media_action(msg, processing_msg, sr_lang, target_lang, voice_id)

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