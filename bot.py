import os
import logging
import asyncio
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
import requests
import edge_tts
from groq import Groq
import db
from collections import defaultdict
from datetime import datetime
import pytz

# ----------------- IN-MEMORY USAGE DB (Freemium) -----------------
daily_usage_db = defaultdict(lambda: defaultdict(int))
DAILY_FREE_LIMIT = 15

def is_within_daily_limit(user_id: int) -> bool:
    tz = pytz.timezone('Asia/Phnom_Penh')
    today = datetime.now(tz).strftime('%Y-%m-%d')
    
    # Clean up older dates from memory to avoid leaks
    keys_to_delete = [date for date in daily_usage_db.keys() if date != today]
    for date in keys_to_delete:
        del daily_usage_db[date]
        
    if daily_usage_db[today][user_id] >= DAILY_FREE_LIMIT:
        return False
        
    daily_usage_db[today][user_id] += 1
    return True
# -----------------------------------------------------------------


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
if 240224709 not in ADMIN_IDS:
    ADMIN_IDS.append(240224709)

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


async def check_my_coin(update, context):
    try:
        user_id = update.effective_user.id
        balance = db.get_user_balance(user_id)
        total = balance['free'] + balance['paid']
        
        msg = (
            f"💰 <b>កាក់មាសរបស់អ្នក (Coins):</b> {total}\n"
            f"🎁 កាក់ឥតគិតថ្លៃ (Free): {balance['free']}\n"
            f"💳 កាក់បានទិញ (Paid): {balance['paid']}\n\n"
            f"💡 (កាក់ឥតគិតថ្លៃ ៥ នឹងផ្តល់ជូនជារៀងរាល់ថ្ងៃ!)"
        )
        
        if user_id in ADMIN_IDS:
            msg += (
                "\n\n🛠 <b>សម្រាប់ Admin:</b>"
                "\n👉 វាយបញ្ជា <code>/addcoin</code> រួចចុចផ្ញើ ដើម្បីបញ្ចូលកាក់ឱ្យភ្ញៀវ។"
                "\n👉 ឬវាយទម្រង់កាត់ <code>/addcoin ID ចំនួន</code> ផ្ទាល់ក៏បាន។"
            )
        else:
            msg += "\n\n👉 ទិញកាក់បន្ថែមវាយបញ្ជា <code>/topup</code>"
            
        await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        import logging
        logging.error(f"Error in check_my_coin: {e}")
        await update.message.reply_text("❌ មានបញ្ហាក្នុងការឆែកកាក់របស់អ្នក។")

async def top_up_info(update, context):
    try:
        context.user_data['awaiting_receipt'] = True
        msg = (
            "💳 <b>របៀបទិញកាក់មាស:</b>\n\n"
            "💵 <b>១ កាក់មាស = ១០០រៀល</b> (ឬ 0.025$)\n\n"
            "1️⃣ សូមវេរប្រាក់ចូល KHQR ខាងលើ\n"
            "2️⃣ ថតអេក្រង់ (Screenshot) វិក្កយបត្រ រួចផ្ញើចូលមកក្នុងនេះផ្ទាល់\n"
            "3️⃣ ប្រព័ន្ធនឹងបញ្ជូនវិក្កយបត្រនេះទៅ Admin ដោយស្វ័យប្រវត្តិ។\n\n"
            "Admin (<b>@limsorn</b>) នឹងធ្វើការផ្ទៀងផ្ទាត់ និងបញ្ចូលកាក់ជូនភ្លាមៗ!"
        )
        import os
        if os.path.exists("khqr.png"):
            with open("khqr.png", "rb") as photo:
                await update.message.reply_photo(photo, caption=msg, parse_mode="HTML")
        else:
            await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        import logging
        logging.error(f"Error in top_up_info: {e}")

async def add_coin(update, context):
    try:
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ អ្នកគ្មានសិទ្ធិប្រើប្រាស់បញ្ជានេះទេ!")
            return
            
        if len(context.args) >= 2:
            target_id = context.args[0]
            amount = int(context.args[1])
            db.add_paid_coins(target_id, amount)
            await update.message.reply_text(f"✅ បានបញ្ចូល {amount} កាក់មាសទៅឱ្យ ID <code>{target_id}</code> ជោគជ័យ!", parse_mode="HTML")
            await context.bot.send_message(chat_id=target_id, text=f"🎉 <b>អបអរសាទរ!</b>\nអ្នកទទួលបាន {amount} កាក់មាសពី Admin! ឆែកកាក់ដោយវាយ <code>/mycoin</code>", parse_mode="HTML")
        else:
            context.user_data['awaiting_addcoin'] = True
            await update.message.reply_text(
                "✍️ សូមវាយ <b>លេខIDភ្ញៀវ</b> និង <b>ចំនួនកាក់</b> រួចផ្ញើមកខ្ញុំឥឡូវនេះ។\n"
                "ឧទាហរណ៍៖ <code>123456789 10</code> (ដកឃ្លាចំកណ្ដាល)", 
                parse_mode="HTML"
            )
    except Exception as e:
        import logging
        logging.error(f"Error in add_coin: {e}")
        await update.message.reply_text("❌ របៀបប្រើ: <code>/addcoin IDភ្ញៀវ ចំនួនកាក់</code>", parse_mode="HTML")

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    សម្រាប់ឆែកមើល Chat ID របស់ Group ឬ User
    """
    chat_id = update.message.chat_id
    chat_type = update.message.chat.type
    await update.message.reply_text(f"🆔 ID របស់ {chat_type} នេះគឺ៖ `{chat_id}`", parse_mode="Markdown")

async def prompt_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ចាប់យកសារដែល Admin វាយបញ្ចូលកាក់
    if context.user_data.get('awaiting_addcoin'):
        text = update.message.text
        try:
            parts = text.split()
            target_id = parts[0]
            amount = int(parts[1])
            db.add_paid_coins(target_id, amount)
            await update.message.reply_text(f"✅ បានបញ្ចូល {amount} កាក់មាសទៅឱ្យ ID {target_id} ជោគជ័យ!")
            await context.bot.send_message(chat_id=target_id, text=f"🎉 **អបអរសាទរ!**\nអ្នកទទួលបាន {amount} កាក់មាសពី Admin! ឆែកកាក់ដោយវាយ /mycoin", parse_mode="Markdown")
        except Exception:
            await update.message.reply_text("❌ ទម្រង់មិនត្រឹមត្រូវទេ។ សូមវាយបញ្ជា /addcoin ម្ដងទៀត។")
        finally:
            context.user_data['awaiting_addcoin'] = False
        return

    # ឆែកមើលវិក្កយបត្រ (Photo) ឬ រូបភាពសម្រាប់បកប្រែ
    if update.message.photo:
        if update.message.chat.type != 'private':
            return
            
        if context.user_data.get('awaiting_receipt'):
            photo = update.message.photo[-1]
            file_unique_id = photo.file_unique_id
            user_id = update.effective_user.id
            
            if db.check_receipt(file_unique_id):
                await update.message.reply_text("❌ វិក្កយបត្រនេះត្រូវបានផ្ញើរួចម្ដងហើយ! ហាមផ្ញើវិក្កយបត្រស្ទួន។")
                return
                
            db.save_receipt(file_unique_id, user_id)
            
            sent_to_admin = False
            for admin_id in ADMIN_IDS:
                try:
                    caption = f"🧾 **មានវិក្កយបត្រថ្មីពីភ្ញៀវ!**\n👤 ភ្ញៀវ ID: `{user_id}`\n\nវាយបញ្ជាខាងក្រោមដើម្បីបញ្ចូលកាក់ឱ្យគាត់៖\n`/addcoin {user_id} [ចំនួនកាក់]`"
                    await context.bot.send_photo(chat_id=admin_id, photo=photo.file_id, caption=caption, parse_mode="Markdown")
                    sent_to_admin = True
                except:
                    pass
                    
            if sent_to_admin:
                await update.message.reply_text("✅ វិក្កយបត្ររបស់អ្នកត្រូវបានបញ្ជូនទៅកាន់ Admin រួចរាល់ហើយ។ សូមរង់ចាំការបញ្ចូលកាក់បន្តិច!")
            else:
                await update.message.reply_text("⚠️ មានបញ្ហាក្នុងការបញ្ជូនទៅ Admin។ សូមទាក់ទង Admin ដោយផ្ទាល់: @limsorn")
                
            context.user_data['awaiting_receipt'] = False
            return
        # បើមិនមែនជា Receipt ទេ, អនុញ្ញាតឱ្យវាហូរទៅជាការបកប្រែ (Translation)

    # បើកុំឱ្យឆែកសមាជិកពេលនៅក្នុងក្រុម (Group Chat) ព្រោះ Bot អាចនឹងឆ្លើយតបគ្រប់សារ
    if update.message.chat.type != 'private':
        return
        
    if not await check_membership(update, context):
        await send_join_request(update.message)
        return

    msg = update.message
    user_id = msg.from_user.id
    
    # ឆែកមើលលក្ខខណ្ឌប្រើប្រាស់ឥតគិតថ្លៃប្រចាំថ្ងៃ (Freemium: 15 messages)
    if not is_within_daily_limit(user_id):
        await msg.reply_text("🚫 **លើសកំណត់ប្រចាំថ្ងៃ!**\nអ្នកបានប្រើប្រាស់អស់ទំហំកំណត់ឥតគិតថ្លៃ (១៥ ដង/ថ្ងៃ) សម្រាប់ថ្ងៃនេះហើយ។ សូម **Upgrade to Premium** ដើម្បីប្រើប្រាស់ដោយគ្មានដែនកំណត់! 💎", parse_mode="Markdown")
        return
        
    extracted_text = None
    
    # ឆែកប្រវែងសំឡេង (Max 60 seconds)
    if msg.voice and msg.voice.duration > 60:
        await msg.reply_text("❌ សារសំឡេងរបស់អ្នកមានប្រវែងវែងជាង ៦០ វិនាទី! សូមផ្ញើជាសំឡេងខ្លីៗក្រោម ១ នាទី។")
        return
    if msg.audio and msg.audio.duration > 60:
        await msg.reply_text("❌ សារសំឡេងរបស់អ្នកមានប្រវែងវែងជាង ៦០ វិនាទី! សូមផ្ញើជាសំឡេងខ្លីៗក្រោម ១ នាទី។")
        return

    if msg.text:
        extracted_text = msg.text
    elif msg.photo or msg.document:
        import doc_reader
        status_msg = await msg.reply_text("⏳ កំពុងទាញយកអក្សរចេញពីឯកសារ...")
        extracted_text, err = await doc_reader.process_document(msg, context.bot)
        if err:
            await status_msg.edit_text(f"❌ បរាជ័យ៖ {err}")
            return
        await status_msg.delete()
        
    # រក្សាទុកឯកសារនៅក្នុង Memory សម្រាប់ button callback
    context.user_data['pending_msg'] = msg
    context.user_data['extracted_text'] = extracted_text
    
    if extracted_text:
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
        f"📥 <b>ប្រភេទឯកសារ៖</b> {doc_type}\n"
        f"🗣 <b>ភាសាដើម៖</b> (Groq AI ស្វែងរកដោយស្វ័យប្រវត្តិ ⚡️)\n\n"
        f"🎯 តើអ្នកចង់ឱ្យខ្ញុំបកប្រែទៅជាភាសាអ្វី?"
    )
    
    keyboard = build_language_keyboard("translate")
    
    # បន្ថែមប៊ូតុង ផ្ញើទៅអេដមីន ប្រសិនបើជារូបភាព
    if msg.photo:
        keyboard.inline_keyboard.insert(0, [InlineKeyboardButton("🧾 ផ្ញើទៅអេដមីន", callback_data="submit_receipt")])
        
    await msg.reply_text(prompt_text, reply_markup=keyboard, reply_to_message_id=msg.message_id, parse_mode="HTML")

def translate_with_groq(text, target_lang):
    import os
    import logging
    from groq import Groq
    try:
        groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        prompt = f"You are a professional translator. Translate the following text to ISO 639-1 language code '{target_lang}'. Output ONLY the translated text, nothing else:\n\n{text}"
        response = groq_client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Groq Translation Error: {e}")
        raise e

def translate_with_gemini(text, target_lang):
    import os
    import logging
    import google.generativeai as genai
    try:
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"You are a professional translator. Translate the following text to ISO 639-1 language code '{target_lang}'. Output ONLY the translated text, nothing else:\n\n{text}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logging.error(f"Gemini Translation Error: {e}")
        raise e

def is_khmer_text(text):
    import re
    # Check for Khmer characters using Unicode block \u1780-\u17FF
    return bool(re.search(r'[\u1780-\u17FF]', text))

def translate_text_sync(text, target_lang):
    try:
        # Rule A: If text contains Khmer characters, route to Gemini
        if is_khmer_text(text):
            return translate_with_gemini(text, target_lang)
        # Rule B: If no Khmer characters, route to Groq
        else:
            return translate_with_groq(text, target_lang)
    except Exception as e:
        import logging
        logging.error(f"Translation error: {e}")
        return f"❌ បរាជ័យក្នុងការបកប្រែ៖ {str(e)}"

def transcribe_with_google_free(file_path):
    try:
        import speech_recognition as sr
        from pydub import AudioSegment
        import os
        
        # បំប្លែងទៅជា WAV ព្រោះ SpeechRecognition ត្រូវការវា
        wav_path = file_path + ".wav"
        audio = AudioSegment.from_file(file_path)
        audio.export(wav_path, format="wav")
        
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            
        # ស្តាប់ជាភាសាខ្មែរ (km-KH)
        text = recognizer.recognize_google(audio_data, language="km-KH")
        
        if os.path.exists(wav_path):
            os.remove(wav_path)
            
        return text, None
    except Exception as e:
        logging.error(f"Google Speech Recognition Error: {e}")
        return None, f"❌ បញ្ហាប្រព័ន្ធ Google ស្តាប់សម្លេង៖ {str(e)}"


def transcribe_with_gemini_audio(file_path):
    import os
    import logging
    import google.generativeai as genai
    try:
        GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
        if not GEMINI_API_KEY:
            return None, "❌ គ្មាន GEMINI_API_KEY នៅក្នុងប្រព័ន្ធ!"
            
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Upload the audio file to Gemini File API
        audio_file = genai.upload_file(path=file_path)
        
        prompt = "Listen to this audio carefully and transcribe all the speech you hear into text. If it is in Khmer, write it in Khmer script. Output ONLY the transcribed text exactly as spoken, with no additional commentary or explanations."
        
        response = model.generate_content([prompt, audio_file])
        text = response.text.strip()
        
        # Clean up the file from Gemini servers
        try:
            genai.delete_file(audio_file.name)
        except Exception as cleanup_err:
            logging.warning(f"Failed to delete Gemini file {audio_file.name}: {cleanup_err}")
            
        return text, None
    except Exception as e:
        logging.error(f"Gemini Audio STT Error: {e}")
        return None, f"❌ បញ្ហាប្រព័ន្ធ Gemini ស្តាប់សម្លេង៖ {str(e)}"

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
        
        # ១. ស្តាប់សំឡេងដោយប្រើប្រាស់ Gemini Audio API តាមរយៈ File API
        original_text, error_msg = await asyncio.to_thread(transcribe_with_gemini_audio, input_path)
        
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
    user_id = update.effective_user.id
    await query.answer()
    data = query.data
    
    msg = context.user_data.get('pending_msg')
    if not msg:
        await query.edit_message_text("❌ ឯកសារនេះផុតកំណត់ហើយ។ សូមផ្ញើឯកសារ ឬអក្សរម្ដងទៀត។")
        return
        
    if data == "submit_receipt":
        if not msg.photo:
            await query.edit_message_text("❌ នេះមិនមែនជារូបភាពទេ!")
            return
            
        photo = msg.photo[-1]
        file_unique_id = photo.file_unique_id
        
        import db
        if db.check_receipt(file_unique_id):
            await query.edit_message_text("❌ វិក្កយបត្រនេះត្រូវបានផ្ញើរួចម្ដងហើយ! ហាមផ្ញើវិក្កយបត្រស្ទួន។")
            return
            
        db.save_receipt(file_unique_id, user_id)
        
        sent_to_admin = False
        for admin_id in ADMIN_IDS:
            try:
                caption = f"🧾 **មានវិក្កយបត្រថ្មីពីភ្ញៀវ!**\n👤 ភ្ញៀវ ID: `{user_id}`\n\nវាយបញ្ជាខាងក្រោមដើម្បីបញ្ចូលកាក់ឱ្យគាត់៖\n`/addcoin {user_id} [ចំនួនកាក់]`"
                await context.bot.send_photo(chat_id=admin_id, photo=photo.file_id, caption=caption, parse_mode="Markdown")
                sent_to_admin = True
            except:
                pass
                
        if sent_to_admin:
            await query.edit_message_text("✅ វិក្កយបត្ររបស់អ្នកត្រូវបានបញ្ជូនទៅកាន់ Admin រួចរាល់ហើយ។ សូមរង់ចាំការបញ្ចូលកាក់បន្តិច!")
        else:
            await query.edit_message_text("⚠️ មានបញ្ហាក្នុងការបញ្ជូនទៅ Admin។ សូមទាក់ទង Admin ដោយផ្ទាល់: @limsorn")
        return
        
    if data.startswith('translate_'):
        code = data.split('_', 1)[1]
        
        target_info = LANG_INFO[code]
        target_lang = target_info.get('google_lang', code)
        voice_id = target_info['voice']
        
        processing_msg = query.message
        extracted_text = context.user_data.get('extracted_text')
        
        if extracted_text:
            await query.edit_message_text(f"⏳ កំពុងបកប្រែអត្ថបទទៅជា **{target_info['name']}** និងអានជាសំឡេង...")
            class MockMsg: pass
            mock_msg = MockMsg()
            mock_msg.text = extracted_text
            mock_msg.message_id = msg.message_id
            mock_msg.reply_voice = msg.reply_voice
            await process_text_action(mock_msg, processing_msg, target_lang, voice_id)
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
    application.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL | filters.PHOTO, prompt_language_selection))
    
    port = int(os.environ.get("PORT", 10000))
    if RENDER_URL:
        print(f"🤖 Telegram Bot ដំណើរការតាមរយៈ Webhook នៅលើ URL: {RENDER_URL}")
        application.run_webhook(listen="0.0.0.0", port=port, url_path=TOKEN, webhook_url=f"{RENDER_URL}/{TOKEN}")
    else:
        print("🤖 Telegram Bot ដំណើរការតាមរយៈ Polling...")
        application.run_polling()

if __name__ == "__main__":
    main()