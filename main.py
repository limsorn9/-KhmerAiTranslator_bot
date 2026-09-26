import os
import re
import json
import asyncio
import edge_tts
from deep_translator import GoogleTranslator
import subprocess
from datetime import datetime
import pytz
from fastapi import FastAPI, Request
from telegram import Update, Bot
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
            print("✅ Firebase initialized successfully.")
        except Exception as e:
            print(f"❌ Failed to parse FIREBASE_CREDENTIALS: {e}")
    else:
        print("⚠️ FIREBASE_CREDENTIALS is missing! DB tracking will fail.")

rtdb_ref = rtdb.reference('users') if firebase_admin._apps else None

DAILY_LIMIT = 10
GEMINI_MODELS = [
    "gemini-3.8-flash",     # newest - fastest
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",  # smartest pro
    "gemini-2.5-flash",     # stable fallback
    "gemini-2.0-flash",     # last resort
]

# Super Admin IDs - no quota limit (get your ID from @userinfobot on Telegram)
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

# ----------------- DB LOGIC (REALTIME DATABASE) -----------------
def check_and_update_limit(user_id: int) -> bool:
    if not rtdb_ref:
        return True # Fail-open if no DB configured
        
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

# ----------------- LLM ROUTING -----------------

async def send_tts(text: str, chat_id: int, reply_to_message_id: int):
    """Generate TTS using Microsoft Edge API and send as voice message"""
    try:
        lang = 'km' if is_khmer_text(text) else 'en'
        # Edge TTS voices: km-KH-SreymomNeural / km-KH-PisethNeural
        voice = 'km-KH-SreymomNeural' if lang == 'km' else 'en-US-AriaNeural'
        
        file_path = f"/tmp/tts_{chat_id}.mp3"
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(file_path)
        
        with open(file_path, 'rb') as f:
            await bot.send_voice(chat_id=chat_id, voice=f, reply_to_message_id=reply_to_message_id)
        os.remove(file_path)
    except Exception as e:
        print(f"TTS Error: {e}")

def is_khmer_text(text: str) -> bool:
    return bool(re.search(r'[\u1780-\u17FF]', text))

def translate_to_multi(text: str):
    targets = {
        'km': '🇰🇭 ខ្មែរ',
        'en': '🇬🇧 អង់គ្លេស',
        'th': '🇹🇭 ថៃ',
        'vi': '🇻🇳 វៀតណាម',
        'zh-CN': '🇨🇳 ចិន',
        'ja': '🇯🇵 ជបុ៉ន',
        'ko': '🇰🇷 កូរ៉េ'
    }
    res_str = ""
    km_text = ""
    for code, name in targets.items():
        try:
            trans = GoogleTranslator(source='auto', target=code).translate(text)
            res_str += f"{name}:\n{trans}\n\n"
            if code == 'km':
                km_text = trans
        except Exception:
            res_str += f"{name}:\n❌ Error\n\n"
    return res_str.strip(), km_text




async def process_audio_smart(file_path: str) -> str:
    # Use Groq Whisper to detect and transcribe. If Khmer, delegate to Gemini!
    for _ in range(3):
        try:
            api_key = get_next_groq_key()
            if not api_key:
                return "❌ គ្មាន GROQ_API_KEY!", ""
            groq_client = Groq(api_key=api_key)
            with open(file_path, "rb") as f:
                transcription = groq_client.audio.transcriptions.create(
                    file=(os.path.basename(file_path), f.read()),
                    model="whisper-large-v3-turbo",
                    response_format="verbose_json"
                )
            
            # User strictly requested Gemini for Khmer only
            lang = getattr(transcription, 'language', 'en')
            if lang in ['km', 'khmer']:
                khmer_text = await process_with_gemini_media(file_path, is_voice=True)
                if khmer_text.startswith("❌") or khmer_text.startswith("⚠"):
                    return khmer_text, ""
                return translate_to_multi(khmer_text)
            else:
                non_khmer_text = transcription.text
                return translate_to_multi(non_khmer_text)
                
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                continue
            return f"❌ បរាជ័យ Groq Audio៖ {str(e)}", ""
    return "⚠️ Groq Audio កំពុងអស់កូតា។", ""

async def process_with_gemini_media(file_path: str, is_voice: bool = False) -> str:
    if is_voice:
        prompt = "Listen to this audio carefully and transcribe all the speech you hear into text. If it is in Khmer, write it in Khmer script. Output ONLY the transcribed text exactly as spoken, with no additional commentary."
    else:
        prompt = "Please extract all text visible in this image. Output ONLY the text exactly as seen."

    for model_name in GEMINI_MODELS:
        uploaded_file = None
        client = None
        try:
            api_key = get_next_gemini_key()
            if not api_key:
                return "❌ គ្មាន GEMINI_API_KEY នៅក្នុងប្រព័ន្ធ!"
            client = google_genai.Client(api_key=api_key)
            uploaded_file = client.files.upload(file=file_path)
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt, uploaded_file]
            )
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "503" in err or "unavailable" in err.lower():
                continue  # Try next model
            return f"❌ បរាជ័យក្នុងការវិភាគ File៖ {err}"
        finally:
            if uploaded_file and client:
                try:
                    client.files.delete(name=uploaded_file.name)
                except:
                    pass
    return "⚠️ Gemini Models ទាំងអស់កំពុងរវល់ (503/429)។ សូមរង់ចាំបន្តិចសិន!"

# ----------------- TELEGRAM LOGIC -----------------
async def handle_update(update: Update):
    if not update.message:
        return
        
    msg = update.message
    user_id = msg.from_user.id
    chat_id = msg.chat_id

    # 0. HANDLE COMMANDS FIRST (no quota needed)
    if msg.text and msg.text.startswith('/'):
        cmd = msg.text.split()[0].lower()
        if cmd == '/start':
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "👋 សួស្តី! ខ្ញុំជាគ្រូសន KhmerAI Translator Bot\n\n"
                    "📌 ខ្ញុំអាចជួយអ្នកបាន៖\n"
                    "• ✍️ ផ្ញើអត្ថបទ ខ្មែរ→English, English→ខ្មែរ និងភាសាក្នុងតំបន់\n"
                    "• 🎤 ផ្ញើសំឡេង (Voice message)\n"
                    "• 📄 ផ្ញើឯកសារ (.txt, .docx)\n"
                    "• 🖼️ ផ្ញើរូបភាព\n\n"
                    "⚡ Free Tier: ១០ សារ/ថ្ងៃ\n"
                    "📊 ប្រើ: /mycoin សម្រាប់ឆែកសមតុល្យ\n"
                    "👉 សូមផ្ញើសារណាមួយដើម្បីចាប់ផ្តើម!"
                ),
                parse_mode="Markdown"
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
                text=f"📊 **ស្ថានភាពការប្រើប័របស់ថ្ង័នេៀ**\n\n"
                     f"✅ បានប្រើ៖ **{count}/{DAILY_LIMIT}** ដង\n"
                     f"🔋 នៅសល់៖ **{remaining}** ដង\n\n"
                     f"🔄 កូតានឹង Reset ឥប័នវិញនៅក្នុងទិនថ្ង័នៅ។",
                parse_mode="Markdown"
            )
            return
        elif cmd == '/topup':
            await bot.send_message(
                chat_id=chat_id,
                text="💎 **Upgrade to Premium**\n\n"
                     "🆓 Free Tier: ១០ សារ/ថ្ង័\n"
                     "⭐ Premium: សារគ្មានដែន\n\n"
                     "📩 តំនាកតាមអ្នកគ្រប់គ្រង: @YourAdminHandle",
                parse_mode="Markdown"
            )
            return
        else:
            await bot.send_message(chat_id=chat_id, text="❓ ពាក័បញ្ជានេៀមិនត្រូវបានគាំត្រទេ។ សាកល្បង /start")
            return

    # 1. Limit Check (skip for Super Admins)
    is_admin = user_id in SUPER_ADMINS
    if not is_admin and not check_and_update_limit(user_id):
        await bot.send_message(
            chat_id=chat_id, 
            text="🚫 **លើសកំណត់ប្រចាំថ្ង័!**\nអ្នកបានប្រើប័រអស់កំណត់ (១០ ដង/ថ្ង័) សម្រាប់ថ្ង័នេៀេលបហឹយ (Free Tier)។\n\n💡 ប្រើ /topup ដើមបី Upgrade!",
            parse_mode="Markdown"
        )
        return

    status_msg = await bot.send_message(chat_id=chat_id, text="⏳ កំពុងដំណើរការ...")
    
    extracted_text = ""
    file_to_delete = None
    
    try:
        # A. HANDLE TEXT
        if msg.text:
            extracted_text = msg.text
            
        # B. HANDLE DOCUMENTS (TXT, DOCX)
        elif msg.document:
            file_name = msg.document.file_name.lower()
            if file_name.endswith('.txt') or file_name.endswith('.docx'):
                file_obj = await bot.get_file(msg.document.file_id)
                file_to_delete = f"/tmp/doc_{msg.message_id}_{file_name}"
                
                # Create /tmp if not exists (for local testing mostly, Render has /tmp)
                os.makedirs("/tmp", exist_ok=True)
                await file_obj.download_to_drive(file_to_delete)
                
                if file_name.endswith('.txt'):
                    with open(file_to_delete, 'r', encoding='utf-8') as f:
                        extracted_text = f.read()
                elif file_name.endswith('.docx'):
                    doc = docx.Document(file_to_delete)
                    extracted_text = "\n".join([para.text for para in doc.paragraphs])
            else:
                await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="❌ ទទួលយកតែឯកសារ .txt និង .docx ប៉ុណ្ណោះសម្រាប់អត្ថបទ!")
                return
                
        # C. HANDLE VOICE OR PHOTO
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
            
            # Extract audio from video to save Gemini upload time/size
            if ext == ".mp4":
                final_file = f"/tmp/audio_{msg.message_id}.wav"
                try:
                    subprocess.run(["ffmpeg", "-i", file_to_delete, "-q:a", "0", "-map", "a", final_file, "-y"], check=True)
                except Exception as e:
                    print(f"FFmpeg Error: {e}")
                    final_file = file_to_delete # fallback to original video
            
            km_text = ""
            if is_audio:
                res, km_text = await process_audio_smart(final_file)
            else:
                img_res = await process_with_gemini_media(final_file, is_voice=False)
                if img_res.startswith("❌") or img_res.startswith("⚠"):
                    res = img_res
                else:
                    res, km_text = translate_to_multi(img_res)
            
            await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"✅ លទ្ធផល៖\n\n{res}")
            
            # Generate TTS if it was a voice/video translation
            if is_audio and km_text and not res.startswith("❌") and not res.startswith("⚠"):
                await send_tts(km_text, chat_id, status_msg.message_id)
            
            if final_file != file_to_delete and os.path.exists(final_file):
                try: os.remove(final_file)
                except: pass
            
        else:
            await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="❌ មិនគាំទ្រទម្រង់ឯកសារនេះទេ!")
            return

        # D. IF WE HAVE TEXT (Direct or Extracted), APPLY HYBRID ROUTING
        if extracted_text:
            res_str, km_text = translate_to_multi(extracted_text)
            await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"✅ លទ្ធផល៖\n\n{res_str}")
            
    except Exception as e:
        await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"❌ មានបញ្ហាប្រព័ន្ធ៖ {str(e)}")
        
    finally:
        # CRITICAL: Always delete the downloaded file to prevent Render Free Tier disk space issues
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
    
    # Optional security check if token is provided in URL
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
    return {"status": "Bot is running on Render Free Tier! FastAPI Webhook active."}

# Render binds to os.environ.get("PORT", 8000)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
