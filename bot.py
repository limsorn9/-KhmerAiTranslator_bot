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
ADMIN_IDS = [int(i) for i in os.environ.get("ADMIN_IDS", "").split(",") if i]

# ការកំណត់ការចូលរួមក្រុម
REQUIRED_GROUP_ID = os.environ.get("REQUIRED_GROUP_ID", "-1004293304141") # លេខ ID របស់ក្រុម/Channel
GROUP_INVITE_LINK = "https://t.me/ssonlinechanel"

# បង្កើត Client សម្រាប់ Groq
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ភាសាអាស៊ានទាំង ១១ បូកបន្ថែម ចិន អង់គ្លេស និងភាសាពេញនិយម ១០ ទៀត
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
    'en': {'name': '🇬🇧 អង់គ្លេស', 'voice': 'en-US-AriaNeural'},
    'ja': {'name': '🇯🇵 ជប៉ុន', 'voice': 'ja-JP-NanamiNeural'},
    'fr': {'name': '🇫🇷 បារាំង', 'voice': 'fr-FR-DeniseNeural'},
    'ko': {'name': '🇰🇷 កូរ៉េ', 'voice': 'ko-KR-SunHiNeural'},
    'es': {'name': '🇪🇸 អេស្ប៉ាញ', 'voice': 'es-ES-ElviraNeural'},
    'de': {'name': '🇩🇪 អាល្លឺម៉ង់', 'voice': 'de-DE-KatjaNeural'},
    'ru': {'name': '🇷🇺 រុស្ស៊ី', 'voice': 'ru-RU-SvetlanaNeural'},
    'ar': {'name': '🇸🇦 អារ៉ាប់', 'voice': 'ar-SA-ZariyahNeural'},
    'hi': {'name': '🇮🇳 ឥណ្ឌា', 'voice': 'hi-IN-SwaraNeural'},
    'it': {'name': '🇮🇹 អ៊ីតាលី', 'voice': 'it-IT-ElsaNeural'},
    'tr': {'name': '🇹🇷 ទួរគី', 'voice': 'tr-TR-EmelNeural'}
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

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not REQUIRED_GROUP_ID:
        return True # ប្រសិនបើមិនទាន់ដាក់ ID ក្រុមទេ អនុញ្ញាតឱ្យប្រើសិន
    
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_GROUP_ID, user_id=user_id)
        if member.status in ['left', 'kicked']:
            return False
        return True
    except Exception as e:
        logging.error(f"Membership check error: {e}")
        return False

async def send_join_request(message):
    keyboard = [[InlineKeyboardButton("ចូលរួមក្រុម (Join Group)", url=GROUP_INVITE_LINK)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        "🔒 **សូមអភ័យទោស! អ្នកមិនទាន់អាចប្រើប្រាស់ Bot នេះបានទេ។**\n\n"
        "ដើម្បីអាចបកប្រែបាន លុះត្រាតែអ្នកបានចូលរួមនៅក្នុងក្រុមរបស់យើងជាមុនសិន។ សូមចុចប៊ូតុងខាងក្រោមដើម្បីចូលរួម បន្ទាប់មកសូមសាកល្បងម្ដងទៀត។",
        reply_markup=reply_markup
    )

async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "ចាប់ផ្ដើមបត (Start Bot)"),
        BotCommand("mycoin", "ឆែកកាក់របស់អ្នក (Check Coins)"),
        BotCommand("topup", "ទិញកាក់មាស (Top up Coins)"),
        BotCommand("id", "ឆែក ID (Check ID)")
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == 'private':
        if not await check_membership(update, context):
            await send_join_request(update.message)
            return

    welcome_message = (
        "សួស្តី! 👋 ខ្ញុំគឺគ្រូសន អ្នកជំនាញខាងបកប្រែសម្លេង វីដេអូ និងអត្ថបទ ពីគ្រប់ភាសាទៅជាភាសាក្នុងអាស៊ាន និងភាសាពេញនិយមដទៃទៀត អ្នកអាចប្រើប្រាស់ខ្ញុំដោយឥតគិតថ្លៃ។\n\n"
        "ដើម្បីចាប់ផ្ដើម សូមគ្រាន់តែផ្ញើ **សំឡេង (Voice) វីដេអូ ឬអត្ថបទ** មកខ្ញុំ 🚀\n\n"
        "💡 វាយបញ្ជា /mycoin ដើម្បីឆែកមើលកាក់របស់អ្នក។"
    )
    await update.message.reply_text(welcome_message)

async def check_my_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = db.get_user_balance(user_id)
    total = balance['free'] + balance['paid']
    msg = (
        f"💰 **កាក់មាសរបស់អ្នក (Coins):** {total}\n"
        f"🎁 កាក់ឥតគិតថ្លៃ (Free): {balance['free']}\n"
        f"💳 កាក់បានទិញ (Paid): {balance['paid']}\n\n"
        f"💡 (កាក់ឥតគិតថ្លៃ ៥ នឹងផ្តល់ជូនជារៀងរាល់ថ្ងៃ!)\n"
        f"👉 ទិញកាក់បន្ថែមវាយបញ្ជា /topup"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def top_up_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "💳 **របៀបទិញកាក់មាស:**\n\n"
        "💵 **១ កាក់មាស = ១០០រៀល** (ឬ 0.025$)\n\n"
        "1️⃣ សូមវេរប្រាក់តាមគណនី ABA:\n"
        "   - លេខគណនី: `000000000`\n"
        "   - ឈ្មោះ: `Your Name`\n"
        "2️⃣ ថតអេក្រង់ (Screenshot) ការវេរប្រាក់ រួចផ្ញើមកកាន់ Admin [@AdminUsername]\n"
        f"3️⃣ កុំភ្លេចប្រាប់ ID របស់អ្នកទៅ Admin ផង (ID របស់អ្នកគឺ៖ `{update.effective_user.id}`)\n\n"
        "Admin នឹងធ្វើការបញ្ចូលកាក់ជូនភ្លាមៗ!"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def add_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ អ្នកគ្មានសិទ្ធិប្រើប្រាស់បញ្ជានេះទេ!")
        return
        
    try:
        target_id = context.args[0]
        amount = int(context.args[1])
        db.add_paid_coins(target_id, amount)
        await update.message.reply_text(f"✅ បានបញ្ចូល {amount} កាក់មាសទៅឱ្យ ID {target_id} ជោគជ័យ!")
        await context.bot.send_message(chat_id=target_id, text=f"🎉 **អបអរសាទរ!**\nអ្នកទទួលបាន {amount} កាក់មាសពី Admin! ឆែកកាក់ដោយវាយ /mycoin", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text("❌ របៀបប្រើ: /addcoin <IDភ្ញៀវ> <ចំនួនកាក់>")


async def check_my_coin(update, context):
    user_id = update.effective_user.id
    balance = db.get_user_balance(user_id)
    total = balance['free'] + balance['paid']
    msg = (
        f"💰 **កាក់មាសរបស់អ្នក (Coins):** {total}\n"
        f"🎁 កាក់ឥតគិតថ្លៃ (Free): {balance['free']}\n"
        f"💳 កាក់បានទិញ (Paid): {balance['paid']}\n\n"
        f"💡 (កាក់ឥតគិតថ្លៃ ៥ នឹងផ្តល់ជូនជារៀងរាល់ថ្ងៃ!)\n"
        f"👉 ទិញកាក់បន្ថែមវាយបញ្ជា /topup"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def top_up_info(update, context):
    msg = (
        "💳 **របៀបទិញកាក់មាស:**\n\n"
        "💵 **១ កាក់មាស = ១០០រៀល** (ឬ 0.025$)\n\n"
        "1️⃣ សូមវេរប្រាក់តាមគណនី ABA:\n"
        "   - លេខគណនី: `000000000`\n"
        "   - ឈ្មោះ: `Your Name`\n"
        "2️⃣ ថតអេក្រង់ (Screenshot) ការវេរប្រាក់ រួចផ្ញើមកកាន់ Admin [@AdminUsername]\n"
        f"3️⃣ កុំភ្លេចប្រាប់ ID របស់អ្នកទៅ Admin ផង (ID របស់អ្នកគឺ៖ `{update.effective_user.id}`)\n\n"
        "Admin នឹងធ្វើការបញ្ចូលកាក់ជូនភ្លាមៗ!"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def add_coin(update, context):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ អ្នកគ្មានសិទ្ធិប្រើប្រាស់បញ្ជានេះទេ!")
        return
        
    try:
        target_id = context.args[0]
        amount = int(context.args[1])
        db.add_paid_coins(target_id, amount)
        await update.message.reply_text(f"✅ បានបញ្ចូល {amount} កាក់មាសទៅឱ្យ ID {target_id} ជោគជ័យ!")
        await context.bot.send_message(chat_id=target_id, text=f"🎉 **អបអរសាទរ!**\nអ្នកទទួលបាន {amount} កាក់មាសពី Admin! ឆែកកាក់ដោយវាយ /mycoin", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text("❌ របៀបប្រើ: /addcoin <IDភ្ញៀវ> <ចំនួនកាក់>")

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    សម្រាប់ឆែកមើល Chat ID របស់ Group ឬ User
    """
    chat_id = update.message.chat_id
    chat_type = update.message.chat.type
    await update.message.reply_text(f"🆔 ID របស់ {chat_type} នេះគឺ៖ `{chat_id}`", parse_mode="Markdown")

async def prompt_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # បើកុំឱ្យឆែកសមាជិកពេលនៅក្នុងក្រុម (Group Chat) ព្រោះ Bot អាចនឹងឆ្លើយតបគ្រប់សារ
    if update.message.chat.type != 'private':
        return
        
    if not await check_membership(update, context):
        await send_join_request(update.message)
        return

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
    application.add_handler(CommandHandler("id", get_chat_id))
    application.add_handler(CommandHandler("mycoin", check_my_coin))
    application.add_handler(CommandHandler("topup", top_up_info))
    application.add_handler(CommandHandler("addcoin", add_coin))
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