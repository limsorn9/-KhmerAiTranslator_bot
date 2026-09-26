import os
import re
import json
import asyncio
from datetime import datetime
import pytz
from fastapi import FastAPI, Request
from telegram import Update, Bot
import firebase_admin
from firebase_admin import credentials, firestore
from groq import Groq
import google.generativeai as genai
import docx

# ----------------- INITIALIZATION -----------------
app = FastAPI()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("WARNING: TELEGRAM_TOKEN not set!")
bot = Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None

# Firebase Init
if not firebase_admin._apps:
    creds_json_str = os.environ.get("FIREBASE_CREDENTIALS")
    if creds_json_str:
        try:
            creds_dict = json.loads(creds_json_str)
            cred = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized successfully.")
        except Exception as e:
            print(f"❌ Failed to parse FIREBASE_CREDENTIALS: {e}")
    else:
        print("⚠️ FIREBASE_CREDENTIALS is missing! DB tracking will fail.")

db = firestore.client() if firebase_admin._apps else None

DAILY_LIMIT = 10
GEMINI_MODEL = "gemini-2.5-flash"

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

# ----------------- FIRESTORE LOGIC -----------------
def check_and_update_limit(user_id: int) -> bool:
    if not db:
        return True # Fail-open if no DB configured
        
    tz = pytz.timezone('Asia/Phnom_Penh')
    today_str = datetime.now(tz).strftime('%Y-%m-%d')
    user_ref = db.collection('users').document(str(user_id))
    
    doc = user_ref.get()
    if doc.exists:
        data = doc.to_dict()
        if data.get('last_reset_date') == today_str:
            count = data.get('daily_count', 0)
            if count >= DAILY_LIMIT:
                return False
            user_ref.update({'daily_count': count + 1})
            return True
        else:
            user_ref.update({'daily_count': 1, 'last_reset_date': today_str})
            return True
    else:
        user_ref.set({'daily_count': 1, 'last_reset_date': today_str, 'created_at': firestore.SERVER_TIMESTAMP})
        return True

# ----------------- LLM ROUTING -----------------
def is_khmer_text(text: str) -> bool:
    return bool(re.search(r'[\u1780-\u17FF]', text))

def translate_with_groq(text: str) -> str:
    # Try up to 3 times (with different keys) if quota exceeded
    for _ in range(3):
        try:
            api_key = get_next_groq_key()
            if not api_key:
                return "❌ គ្មាន GROQ_API_KEY នៅក្នុងប្រព័ន្ធ!"
                
            groq_client = Groq(api_key=api_key)
            prompt = f"You are a professional translator. Translate the following text to Khmer (km). Output ONLY the translated text, nothing else:\n\n{text}"
            response = groq_client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                continue # Retry with next key
            return f"❌ បរាជ័យ Groq៖ {str(e)}"
    return "⚠️ Groq គណនីទាំងអស់កំពុងអស់កូតា (Free Tier Limit)។ សូមរង់ចាំបន្តិចសិន!"

def process_with_gemini_text(text: str) -> str:
    for _ in range(3):
        try:
            api_key = get_next_gemini_key()
            if not api_key:
                return "❌ គ្មាន GEMINI_API_KEY នៅក្នុងប្រព័ន្ធ!"
                
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(GEMINI_MODEL)
            prompt = f"You are a professional translator. Translate the following text to English (en). Output ONLY the translated text, nothing else:\n\n{text}"
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                continue
            return f"❌ បរាជ័យ Gemini៖ {str(e)}"
    return "⚠️ Gemini គណនីទាំងអស់កំពុងអស់កូតា (Free Tier Quota)។ សូមរង់ចាំបន្តិចសិន!"

async def process_with_gemini_media(file_path: str, is_voice: bool = False) -> str:
    for _ in range(3):
        audio_file = None
        try:
            api_key = get_next_gemini_key()
            if not api_key:
                return "❌ គ្មាន GEMINI_API_KEY នៅក្នុងប្រព័ន្ធ!"
                
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(GEMINI_MODEL)
            
            audio_file = genai.upload_file(path=file_path)
            if is_voice:
                prompt = "Listen to this audio carefully and transcribe all the speech you hear into text. If it is in Khmer, write it in Khmer script. Output ONLY the transcribed text exactly as spoken, with no additional commentary."
            else:
                prompt = "Please extract all text visible in this image. Output ONLY the text exactly as seen."
                
            response = model.generate_content([prompt, audio_file])
            return response.text.strip()
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                continue
            return f"❌ បរាជ័យក្នុងការវិភាគ File៖ {str(e)}"
        finally:
            if audio_file:
                try:
                    genai.delete_file(audio_file.name)
                except:
                    pass
    return "⚠️ Gemini គណនីទាំងអស់កំពុងអស់កូតា (Free Tier Quota)។ សូមរង់ចាំបន្តិចសិន!"

# ----------------- TELEGRAM LOGIC -----------------
async def handle_update(update: Update):
    if not update.message:
        return
        
    msg = update.message
    user_id = msg.from_user.id
    chat_id = msg.chat_id
    
    # 1. Limit Check
    if not check_and_update_limit(user_id):
        await bot.send_message(
            chat_id=chat_id, 
            text="🚫 **លើសកំណត់ប្រចាំថ្ងៃ!**\nអ្នកបានប្រើប្រាស់អស់កំណត់ (១០ ដង/ថ្ងៃ) សម្រាប់ថ្ងៃនេះហើយ (Free Tier)។",
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
        elif msg.voice or msg.photo:
            file_id = msg.voice.file_id if msg.voice else msg.photo[-1].file_id
            ext = ".ogg" if msg.voice else ".jpg"
            file_to_delete = f"/tmp/media_{msg.message_id}{ext}"
            
            os.makedirs("/tmp", exist_ok=True)
            file_obj = await bot.get_file(file_id)
            await file_obj.download_to_drive(file_to_delete)
            
            res = await process_with_gemini_media(file_to_delete, is_voice=bool(msg.voice))
            await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"✅ **លទ្ធផល៖**\n\n`{res}`", parse_mode="Markdown")
            
        else:
            await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="❌ មិនគាំទ្រទម្រង់ឯកសារនេះទេ!")
            return

        # D. IF WE HAVE TEXT (Direct or Extracted), APPLY HYBRID ROUTING
        if extracted_text:
            if is_khmer_text(extracted_text):
                res = process_with_gemini_text(extracted_text)
            else:
                res = translate_with_groq(extracted_text)
            await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"✅ **លទ្ធផល៖**\n\n`{res}`", parse_mode="Markdown")
            
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
async def telegram_webhook(request: Request):
    if not bot:
        return {"error": "TELEGRAM_TOKEN is missing"}
        
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
