import os
import re
import json
import asyncio
import time
import edge_tts
import pytesseract
from PIL import Image
from deep_translator import GoogleTranslator
import subprocess
from datetime import datetime
import pytz
from fastapi import FastAPI, Request
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
import firebase_admin
from firebase_admin import credentials, db as rtdb
from groq import Groq
from google import genai as google_genai
import docx

from contextlib import asynccontextmanager

# ----------------- INITIALIZATION -----------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("WARNING: TELEGRAM_TOKEN not set!")
bot = Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None

@asynccontextmanager
async def lifespan(app: FastAPI):
    if bot:
        await bot.initialize()
    yield
    if bot:
        await bot.shutdown()

app = FastAPI(lifespan=lifespan)

# Firebase Init
if not firebase_admin._apps:
    creds_json_str = os.environ.get("FIREBASE_CREDENTIALS")
    if creds_json_str:
        try:
            creds_dict = json.loads(creds_json_str)
            cred = credentials.Certificate(creds_dict)
            firebase_db_url = os.environ.get("FIREBASE_DB_URL", "")
            firebase_admin.initialize_app(cred, {
                'databaseURL': firebase_db_url
            })
            print("Firebase initialized successfully.")
        except Exception as e:
            print(f"Failed to parse FIREBASE_CREDENTIALS: {e}")
    else:
        print("FIREBASE_CREDENTIALS is missing! DB tracking will fail.")

rtdb_ref = rtdb.reference('users') if firebase_admin._apps else None

DAILY_LIMIT = 10
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]

# Super Admin IDs - no quota limit
SUPER_ADMINS = set(
    int(x.strip()) for x in os.environ.get("SUPER_ADMIN_IDS", "").split(",") if x.strip().isdigit()
)

# ----------------- API KEY ROTATION -----------------
def get_api_keys(env_var_name: str, fallback_var_name: str) -> list:
    keys_str = os.environ.get(env_var_name, os.environ.get(fallback_var_name, ""))
    return [k.strip() for k in keys_str.split(",") if k.strip()]

gemini_keys = get_api_keys("GEMINI_API_KEYS", "GEMINI_API_KEY")
groq_keys = get_api_keys("GROQ_API_KEYS", "GROQ_API_KEY")

gemini_idx = 0
groq_idx = 0

def get_next_gemini_key():
    global gemini_idx
    if not gemini_keys: return None
    key = gemini_keys[gemini_idx % len(gemini_keys)]
    gemini_idx += 1
    return key

def get_next_groq_key():
    global groq_idx
    if not groq_keys: return None
    key = groq_keys[groq_idx % len(groq_keys)]
    groq_idx += 1
    return key

# ----------------- DB LOGIC -----------------
def check_and_update_limit(user_id: int) -> bool:
    if not rtdb_ref:
        return True
    tz = pytz.timezone('Asia/Phnom_Penh')
    today_str = datetime.now(tz).strftime('%Y-%m-%d')
    user_node = rtdb_ref.child(str(user_id))
    data = user_node.get()
    if data:
        if data.get('last_reset_date') == today_str:
            count = data.get('daily_count', 0)
            if count >= DAILY_LIMIT:
                return False
            user_node.update({'daily_count': count + 1})
            return True
        else:
            user_node.update({'daily_count': 1, 'last_reset_date': today_str})
            return True
    else:
        user_node.set({
            'daily_count': 1,
            'last_reset_date': today_str,
            'created_at': datetime.now(tz).isoformat()
        })
        return True

# ----------------- PENDING TEXT STORE -----------------
PENDING_TRANSLATIONS = {}

# ----------------- LANGUAGE CONFIG -----------------
LANG_CONFIG = {
    'km':    ('\U0001f1f0\U0001f1ed \u1781\u17d2\u1798\u17c2\u179a',       'km-KH-SreymomNeural'),
    'en':    ('\U0001f1ec\U0001f1e7 \u17a2\u1784\u17cb\u1782\u17d2\u179b\u17c1\u179f', 'en-US-AriaNeural'),
    'th':    ('\U0001f1f9\U0001f1ed \u1790\u17c3',                           'th-TH-PremwadeeNeural'),
    'vi':    ('\U0001f1fb\U0001f1f3 \u179c\u17c0\u178f\u178e\u17b6\u1798',  'vi-VN-HoaiMyNeural'),
    'zh-CN': ('\U0001f1e8\U0001f1f3 \u1785\u17b7\u1793',                    'zh-CN-XiaoxiaoNeural'),
    'ja':    ('\U0001f1ef\U0001f1f5 \u1787\u1794\u17bb\u17c9\u1793',        'ja-JP-NanamiNeural'),
    'ko':    ('\U0001f1f0\U0001f1f7 \u1780\u17bc\u179a\u17c9\u17c1',        'ko-KR-SunHiNeural'),
    'id':    ('\U0001f1ee\U0001f1e9 \u17a2\u17b7\u1793\u178c\u17bc\u1793\u17b9\u179f\u17b8', 'id-ID-GadisNeural'),
    'ms':    ('\U0001f1f2\U0001f1fe \u1798\u17d0\u17a2\u17b6\u179b\u17c1',  'ms-MY-YasminNeural'),
}

# ----------------- TTS -----------------
async def send_tts(translations: dict, chat_id: int, reply_to_message_id: int):
    """Edge-TTS: send one voice message per language."""
    for voice, text in translations.items():
        if not text:
            continue
        part_file = f"/tmp/tts_{chat_id}_{voice[:8]}.mp3"
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(part_file)
            with open(part_file, 'rb') as f:
                await bot.send_voice(chat_id=chat_id, voice=f,
                                     reply_to_message_id=reply_to_message_id)
        except Exception as e:
            print(f"TTS Error ({voice}): {e}")
        finally:
            if os.path.exists(part_file):
                try:
                    os.remove(part_file)
                except Exception:
                    pass

# ----------------- HELPERS -----------------
def is_khmer_text(text: str) -> bool:
    return bool(re.search(r'[\u1780-\u17FF]', text))

def translate_one(text: str, lang_code: str):
    """Translate with up to 3 retries."""
    for attempt in range(3):
        try:
            result = GoogleTranslator(source='auto', target=lang_code).translate(text)
            if result and result.strip():
                return result.strip()
        except Exception as e:
            print(f"GoogleTranslate attempt {attempt+1} failed for {lang_code}: {e}")
            time.sleep(0.5)
    return None

def translate_to_multi(text: str):
    """Translate text into all configured languages."""
    res_str = ""
    translations = {}
    for code, (name, voice) in LANG_CONFIG.items():
        trans = translate_one(text, code)
        if trans:
            res_str += f"{name}:\n{trans}\n\n"
            translations[voice] = trans
        else:
            res_str += f"{name}:\n\u274c \u1794\u179a\u17b6\u1787\u17d0\u1799\u17d4\n\n"
    return res_str.strip(), translations

# ----------------- AUDIO PROCESSING -----------------
async def process_audio_smart(file_path: str):
    """
    Groq Whisper listens to ALL languages.
    If Khmer detected -> Gemini transcribes (Gemini's ONLY role).
    Else -> Groq transcribes directly.
    Then Google Translate to all languages.
    """
    for _ in range(3):
        try:
            api_key = get_next_groq_key()
            if not api_key:
                return "\u274c \u1782\u17d2\u1798\u17b6\u1793 GROQ_API_KEY!", {}
            groq_client = Groq(api_key=api_key)
            with open(file_path, "rb") as f:
                transcription = groq_client.audio.transcriptions.create(
                    file=(os.path.basename(file_path), f.read()),
                    model="whisper-large-v3-turbo",
                    response_format="verbose_json"
                )
            lang = getattr(transcription, 'language', 'en')
            if lang in ['km', 'khmer']:
                khmer_text = await process_with_gemini_media(file_path, is_voice=True)
                if khmer_text.startswith("\u274c") or khmer_text.startswith("\u26a0"):
                    return khmer_text, {}
                return translate_to_multi(khmer_text)
            else:
                return translate_to_multi(transcription.text)
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                continue
            return f"\u274c \u1794\u179a\u17b6\u1787\u17d0\u1799 Groq: {str(e)}", {}
    return "\u26a0\ufe0f Groq \u17a2\u179f\u17cb Quota! \u179f\u17bc\u1798\u179a\u1784\u17cb\u1785\u17b6\u17c6 \u17e1 \u1793\u17b6\u1791\u17b8\u17d4", {}

# ----------------- IMAGE PROCESSING -----------------
def extract_image_text_local(file_path: str) -> str:
    """Tesseract OCR: fast local extraction (Khmer + English)."""
    try:
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang='khm+eng').strip()
        if not text:
            text = pytesseract.image_to_string(img).strip()
        return text
    except Exception:
        return ""

async def process_with_gemini_media(file_path: str, is_voice: bool = False) -> str:
    if is_voice:
        prompt = (
            "Listen to this audio carefully and transcribe all the speech you hear into text. "
            "If it is in Khmer, write it in Khmer script. "
            "Output ONLY the transcribed text exactly as spoken, with no additional commentary."
        )
    else:
        local_text = extract_image_text_local(file_path)
        if local_text and len(local_text.strip()) > 3:
            return local_text
        prompt = (
            "Please extract all text visible in this image. "
            "Output ONLY the text exactly as seen. "
            "If there is no clear text, output exactly: NO_TEXT"
        )

    for model_name in GEMINI_MODELS:
        uploaded_file = None
        client = None
        try:
            api_key = get_next_gemini_key()
            if not api_key:
                return "\u274c \u1782\u17d2\u1798\u17b6\u1793 GEMINI_API_KEY!"
            client = google_genai.Client(api_key=api_key)
            uploaded_file = client.files.upload(file=file_path)
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt, uploaded_file]
            )
            result = response.text.strip()
            if result == "NO_TEXT" or not result:
                return "\u26a0\ufe0f \u179a\u17bc\u1794\u1797\u17b6\u1796\u1798\u17b7\u1793\u1785\u17d2\u1794\u17b6\u179f\u17cb \u1798\u17b7\u1793\u1798\u17b6\u1793\u17a2\u1780\u17d2\u179f\u179a\u178f\u17c2! \u179f\u17bc\u1798\u1795\u17d2\u1789\u17be\u179a\u179f\u17b6\u179a\u1790\u17d2\u1798\u17b8\u17d4"
            return result
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "503" in err or "unavailable" in err.lower():
                continue
            return f"\u274c \u1782\u17d2\u1798\u17b6\u1793\u17a1\u1797\u17b6\u1796 Gemini: {err}"
        finally:
            if uploaded_file and client:
                try:
                    client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass
    return "\u26a0\ufe0f Gemini \u1798\u17b6\u1793\u1797\u17b6\u1796\u1794\u17d2\u179a\u17be\u1794 Overload! \u179f\u17bc\u1798\u179a\u1784\u17cb\u1785\u17b6\u17c6 \u17e1-\u17e2 \u1793\u17b6\u1791\u17b8\u17d4"

# ----------------- LANGUAGE SELECTOR -----------------
async def show_language_selector(chat_id: int, reply_msg_id: int,
                                  extracted_text: str, user_id: int):
    PENDING_TRANSLATIONS[user_id] = extracted_text
    buttons = []
    row = []
    for code, (name, _voice) in LANG_CONFIG.items():
        row.append(InlineKeyboardButton(name, callback_data=f"translate_{code}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(
        "\U0001f310 \u1794\u1780\u1794\u17d2\u179a\u17be\u1782\u17d2\u179a\u1794\u17cb\u1797\u17b6\u179f\u17b6",
        callback_data="translate_all"
    )])
    keyboard = InlineKeyboardMarkup(buttons)
    preview = extracted_text[:250] + ("..." if len(extracted_text) > 250 else "")
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "\U0001f4c4 \u17a2\u1780\u17d2\u179f\u179a\u178f\u17b9\u1780\u1785\u17d2\u1793\u17b6\u1789\u17d6\n\n"
            f"{preview}\n\n"
            "\u2753 \u179f\u17bc\u1798\u1787\u17d2\u179a\u17be\u179f\u179a\u17be\u179f\u1797\u17b6\u179f\u17b6\u178f\u17b9\u1780\u1785\u1784\u17cb\u1794\u1780\u1794\u17d2\u179a\u17be \u2193"
        ),
        reply_to_message_id=reply_msg_id,
        reply_markup=keyboard
    )

# ----------------- TELEGRAM LOGIC -----------------
async def handle_update(update: Update):

    # Handle inline keyboard callbacks
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        data = query.data

        if not data.startswith("translate_"):
            return

        text = PENDING_TRANSLATIONS.get(user_id)
        if not text:
            await query.edit_message_text(
                "\u26a0\ufe0f \u17a2\u178f\u17d2\u1790\u1794\u178f\u1795\u17bb\u178f\u17a2\u17b6\u1799\u17bb\u17d4 "
                "\u179f\u17bc\u1798\u1795\u17d2\u1789\u17be\u179a\u179f\u17b6\u179a\u1790\u17d2\u1798\u17b8\u1798\u17d2\u178f\u1784\u178f\u17be\u178f\u17d4"
            )
            return

        status = await bot.send_message(
            chat_id=chat_id,
            text="\u23f3 \u1780\u17c6\u1796\u17bb\u1784\u1794\u1780\u1794\u17d2\u179a\u17be..."
        )

        if data == "translate_all":
            res_str, translations_dict = translate_to_multi(text)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status.message_id,
                text=f"\u2705 \u179b\u1791\u17d2\u1792\u1795\u179b\u17d6\n\n{res_str}"
            )
            if translations_dict:
                await send_tts(translations_dict, chat_id, status.message_id)
        else:
            lang_code = data.replace("translate_", "")
            if lang_code in LANG_CONFIG:
                name, voice = LANG_CONFIG[lang_code]
                trans = translate_one(text, lang_code)
                if trans:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status.message_id,
                        text=f"\u2705 {name}:\n\n{trans}"
                    )
                    await send_tts({voice: trans}, chat_id, status.message_id)
                else:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status.message_id,
                        text=f"\u274c \u1794\u179a\u17b6\u1787\u17d0\u1799\u1794\u1780\u1794\u17d2\u179a\u17be {name}! "
                             f"\u179f\u17bc\u1798\u1795\u17d2\u179a\u17d0\u1799\u17a2\u17b6\u1793\u1798\u17d2\u178f\u1784\u178f\u17be\u178f\u17d4"
                    )

        PENDING_TRANSLATIONS.pop(user_id, None)
        return

    if not update.message:
        return

    msg = update.message
    user_id = msg.from_user.id
    chat_id = msg.chat_id

    # Handle commands
    if msg.text and msg.text.startswith('/'):
        cmd = msg.text.split()[0].lower()

        if cmd == '/start':
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "\U0001f44b \u179f\u17bd\u179f\u17d2\u178f\u17b8! \u1781\u17d2\u1789\u17bb\u1798\u1787\u17b6 KhmerAI Translator Bot\n\n"
                    "\U0001f4cc \u1781\u17d2\u1789\u17bb\u1798\u17a2\u17b6\u1785\u1787\u17bd\u1799\u17a2\u17d2\u1793\u1780\u1794\u17b6\u1793\u17d6\n"
                    "\u2022 \u270d\ufe0f \u1795\u17d2\u1789\u17be\u179a\u17a2\u178f\u17d2\u1790\u1794\u178f\u1797\u17b6\u179f\u17b6\u178e\u17b6\u1780\u17cb\u1794\u17b6\u1793 \u2192 \u1794\u1780\u1794\u17d2\u179a\u17be \u17e9 \u1797\u17b6\u179f\u17b6\n"
                    "\u2022 \U0001f3a4 \u1795\u17d2\u1789\u17be\u179a\u179f\u17c6\u179b\u17be\u1784 (Voice message)\n"
                    "\u2022 \U0001f4f9 \u1795\u17d2\u1789\u17be\u179a\u179c\u17b8\u178f\u17b9\u17a2\u17bc (Video)\n"
                    "\u2022 \U0001f4c4 \u1795\u17d2\u1789\u17be\u179a\u17a1\u1780\u179f\u17b6\u179a (.txt, .docx)\n"
                    "\u2022 \U0001f5bc\ufe0f \u1795\u17d2\u1789\u17be\u179a\u179a\u17bc\u1794\u1797\u17b6\u1796\n\n"
                    "\u26a1 Free Tier: \u17e1\u17e0 \u178f\u1784/\u1790\u17d2\u1784\u17b9\n"
                    "\U0001f4ca \u1794\u17d2\u179a\u17be /mycoin \u178f\u17d0\u1789\u1798\u17be\u179b\u1785\u17c6\u1793\u17bd\u1793\u1794\u17d2\u179a\u17be\u1794\u17d2\u179a\u17b6\u179f\u17cb\n"
                    "\U0001f449 \u179f\u17bc\u1798\u1795\u17d2\u1789\u17be\u179a\u179f\u17b6\u179a\u178e\u17b6\u1798\u17bd\u1799\u178f\u17d0\u1789\u1785\u17b6\u1794\u17cb\u1795\u17d2\u178f\u17be\u1798!"
                )
            )
            return

        elif cmd == '/mycoin':
            tz = pytz.timezone('Asia/Phnom_Penh')
            today_str = datetime.now(tz).strftime('%Y-%m-%d')
            count = 0
            if rtdb_ref:
                data = rtdb_ref.child(str(user_id)).get()
                if data and data.get('last_reset_date') == today_str:
                    count = data.get('daily_count', 0)
            remaining = max(0, DAILY_LIMIT - count)
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "\U0001f4ca \u179f\u17d2\u1790\u17b6\u1793\u1797\u17b6\u1796\u1794\u17d2\u179a\u1785\u17b6\u17c6\u1790\u17d2\u1784\u17b9\n\n"
                    f"\u2705 \u1794\u17b6\u1793\u1794\u17d2\u179a\u17be: {count}/{DAILY_LIMIT} \u178f\u1784\n"
                    f"\U0001f50b \u1793\u17c5\u179f\u179b\u17cb: {remaining} \u178f\u1784\n\n"
                    "\U0001f504 \u1780\u17bc\u178f\u17b6\u1793\u17b9\u1784 Reset \u17a1\u17be\u1784\u179c\u17b7\u1789\u1793\u17c5\u1790\u17d2\u1784\u17b9\u179f\u17d2\u17a2\u17b6\u1780\u17d4"
                )
            )
            return

        elif cmd == '/topup':
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "\U0001f48e Upgrade to Premium\n\n"
                    "\U0001f193 Free Tier: \u17e1\u17e0 \u178f\u1784/\u1790\u17d2\u1784\u17b9\n"
                    "\u2b50 Premium: \u1798\u17b7\u1793\u1798\u17b6\u1793\u178f\u17d2\u179a\u17bc\u1788\u17d4\n\n"
                    "\U0001f4e9 \u178f\u17c6\u1793\u17b6\u1780\u17cb\u178f\u17c6\u1793\u1784\u17a2\u17d2\u1793\u1780\u1782\u17d2\u179a\u1794\u17cb\u1782\u17d2\u179a\u1784: @YourAdminHandle"
                )
            )
            return

        else:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "\u2753 \u1796\u17b6\u1780\u17d2\u1799\u1794\u1789\u17d2\u1787\u17b6\u1793\u17b8\u1798\u17b7\u1793\u178f\u17d2\u179a\u17bc\u179c\u1794\u17b6\u1793\u1782\u17b6\u17c6\u178f\u17d2\u179a\u178f\u17c2\u17d4 "
                    "\u179f\u17bc\u1798\u179f\u17b6\u1780\u179b\u17d2\u1794\u1784 /start"
                )
            )
            return

    # Quota check (skip for admins)
    is_admin = user_id in SUPER_ADMINS
    if not is_admin and not check_and_update_limit(user_id):
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "\U0001f6ab \u17a2\u17d2\u1793\u1780\u1794\u17b6\u1793\u1794\u17d2\u179a\u17be\u1782\u17d2\u179a\u1794\u17cb \u17e1\u17e0 \u178f\u1784"
                "\u179f\u1798\u17d2\u179a\u17b6\u1794\u17cb\u1790\u17d2\u1784\u17b9\u1793\u17c1\u17a0\u17be\u1799 (Free Tier)!\n\n"
                "\U0001f4a1 \u1794\u17d2\u179a\u17be /topup \u178f\u17d0\u1789\u1798\u17be\u179b Upgrade!"
            )
        )
        return

    status_msg = await bot.send_message(
        chat_id=chat_id,
        text="\u23f3 \u1780\u17c6\u1796\u17bb\u1784\u178f\u17c6\u178e\u17be\u179a\u1780\u17b6\u179a..."
    )

    extracted_text = ""
    file_to_delete = None

    try:
        # A. TEXT
        if msg.text:
            extracted_text = msg.text

        # B. DOCUMENTS
        elif msg.document:
            file_name = msg.document.file_name.lower()
            if file_name.endswith('.txt') or file_name.endswith('.docx'):
                file_obj = await bot.get_file(msg.document.file_id)
                file_to_delete = f"/tmp/doc_{msg.message_id}_{file_name}"
                os.makedirs("/tmp", exist_ok=True)
                await file_obj.download_to_drive(file_to_delete)
                if file_name.endswith('.txt'):
                    with open(file_to_delete, 'r', encoding='utf-8') as f:
                        extracted_text = f.read()
                elif file_name.endswith('.docx'):
                    doc = docx.Document(file_to_delete)
                    extracted_text = "\n".join([para.text for para in doc.paragraphs])
            else:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    text="\u274c \u178f\u1785\u1780\u1799\u1780\u178f\u17be \u17e2 \u178f\u17c6\u179a\u1784 .txt \u1793\u17b7\u1784 .docx \u1794\u17d0\u178e\u17d2\u178e\u17c4\u17c7!"
                )
                return

        # C. VOICE / VIDEO / PHOTO
        elif msg.voice or msg.photo or msg.video or msg.video_note:
            if msg.voice:
                file_id = msg.voice.file_id
                ext = ".ogg"
            elif msg.video:
                file_id = msg.video.file_id
                ext = ".mp4"
            elif msg.video_note:
                file_id = msg.video_note.file_id
                ext = ".mp4"
            else:
                file_id = msg.photo[-1].file_id
                ext = ".jpg"

            file_to_delete = f"/tmp/media_{msg.message_id}{ext}"
            os.makedirs("/tmp", exist_ok=True)
            file_obj = await bot.get_file(file_id)
            await file_obj.download_to_drive(file_to_delete)

            is_audio = bool(msg.voice or msg.video or msg.video_note)
            final_file = file_to_delete

            if ext == ".mp4":
                final_file = f"/tmp/audio_{msg.message_id}.wav"
                try:
                    subprocess.run(
                        ["ffmpeg", "-i", file_to_delete, "-q:a", "0", "-map", "a", final_file, "-y"],
                        check=True, capture_output=True
                    )
                except Exception as e:
                    print(f"FFmpeg Error: {e}")
                    final_file = file_to_delete

            translations_dict = {}
            if is_audio:
                res, translations_dict = await process_audio_smart(final_file)
            else:
                img_res = await process_with_gemini_media(final_file, is_voice=False)
                if img_res.startswith("\u274c") or img_res.startswith("\u26a0"):
                    res = img_res
                else:
                    res, translations_dict = translate_to_multi(img_res)

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text=f"\u2705 \u179b\u1791\u17d2\u1792\u1795\u179b\u17d6\n\n{res}"
            )

            if translations_dict and not res.startswith("\u274c") and not res.startswith("\u26a0"):
                await send_tts(translations_dict, chat_id, status_msg.message_id)

            if final_file != file_to_delete and os.path.exists(final_file):
                try:
                    os.remove(final_file)
                except Exception:
                    pass

        else:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text="\u274c \u178f\u1798\u17d2\u179a\u1784\u17a1\u1780\u179f\u17b6\u179a\u1793\u17c1\u17a0\u1798\u17b7\u1793\u178f\u17d2\u179a\u17bc\u179c\u1794\u17b6\u1793\u1782\u17b6\u17c6\u178f\u17d2\u179a\u178f\u17c2!"
            )
            return

        # D. TEXT / DOCUMENT -> show language selector
        if extracted_text:
            await bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            await show_language_selector(chat_id, msg.message_id, extracted_text, user_id)

    except Exception as e:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"\u274c \u1798\u17b6\u1793\u1794\u1789\u17d2\u17a0\u17b6\u1794\u17d2\u179a\u1796\u17d0\u1793\u17d2\u1792\u17d6 {str(e)}"
        )

    finally:
        if file_to_delete and os.path.exists(file_to_delete):
            try:
                os.remove(file_to_delete)
            except Exception as e:
                print(f"Failed to delete {file_to_delete}: {e}")

# ----------------- FASTAPI ROUTES -----------------
@app.post("/")
@app.post("/{token}")
async def telegram_webhook(request: Request, token: str = None):
    if not bot:
        return {"error": "TELEGRAM_TOKEN is missing"}
    if token and token != TELEGRAM_TOKEN:
        return {"error": "Unauthorized"}
    try:
        update_json = await request.json()
        update = Update.de_json(update_json, bot)
        await handle_update(update)
        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook Error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/")
async def root():
    return {"status": "KhmerAI Translator Bot is running!"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
