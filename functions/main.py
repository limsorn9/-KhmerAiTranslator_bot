import os
import re
import json
import asyncio
from datetime import datetime
import pytz
from firebase_functions import https_fn, options
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update, Bot
from groq import Groq
import google.generativeai as genai

# Initialize Firebase Admin
if not firebase_admin._apps:
    firebase_admin.initialize_app()
db = firestore.client()

DAILY_LIMIT = 15

# Helper functions for Limits
def check_and_update_limit(user_id: int) -> bool:
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

# Helper functions for LLM Routing
def is_khmer_text(text: str) -> bool:
    return bool(re.search(r'[\u1780-\u17FF]', text))

def translate_with_groq(text: str) -> str:
    groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    prompt = f"You are a professional translator. Translate the following text to Khmer (km). Output ONLY the translated text, nothing else:\n\n{text}"
    response = groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

def translate_with_gemini(text: str) -> str:
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"You are a professional translator. Translate the following text to English (en). Output ONLY the translated text, nothing else:\n\n{text}"
    response = model.generate_content(prompt)
    return response.text.strip()

async def transcribe_with_gemini_audio(file_path: str) -> str:
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Upload to Gemini File API
    audio_file = genai.upload_file(path=file_path)
    
    prompt = "Listen to this audio carefully and transcribe all the speech you hear into text. If it is in Khmer, write it in Khmer script. Output ONLY the transcribed text exactly as spoken, with no additional commentary."
    response = model.generate_content([prompt, audio_file])
    text = response.text.strip()
    
    # Clean up from Gemini Server
    try:
        genai.delete_file(audio_file.name)
    except Exception as e:
        print(f"Error cleaning up Gemini file: {e}")
        
    return text

async def process_telegram_update(update_json: dict):
    bot = Bot(token=os.environ.get("TELEGRAM_TOKEN"))
    update = Update.de_json(update_json, bot)
    
    if not update.message:
        return
        
    msg = update.message
    user_id = msg.from_user.id
    chat_id = msg.chat_id
    
    # 1. Limit Check
    if not check_and_update_limit(user_id):
        await bot.send_message(chat_id=chat_id, text="🚫 **លើសកំណត់ប្រចាំថ្ងៃ!**\nអ្នកបានប្រើប្រាស់អស់ទំហំកំណត់ឥតគិតថ្លៃ (១៥ ដង/ថ្ងៃ) សម្រាប់ថ្ងៃនេះហើយ។ សូម **Upgrade to Premium** ដើម្បីប្រើប្រាស់ដោយគ្មានដែនកំណត់! 💎", parse_mode="Markdown")
        return
        
    # 2. Handle Text
    if msg.text:
        text = msg.text
        status_msg = await bot.send_message(chat_id=chat_id, text="⏳ កំពុងបកប្រែអត្ថបទ...")
        try:
            if is_khmer_text(text):
                res = translate_with_gemini(text)
            else:
                res = translate_with_groq(text)
            await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"✅ **លទ្ធផល៖**\n\n`{res}`", parse_mode="Markdown")
        except Exception as e:
            await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"❌ បរាជ័យ៖ {str(e)}")
            
    # 3. Handle Voice
    elif msg.voice:
        if msg.voice.duration > 60:
            await bot.send_message(chat_id=chat_id, text="❌ សារសំឡេងរបស់អ្នកមានប្រវែងវែងជាង ៦០ វិនាទី! សូមផ្ញើជាសំឡេងខ្លីៗក្រោម ១ នាទី។")
            return
            
        status_msg = await bot.send_message(chat_id=chat_id, text="⏳ កំពុងស្តាប់សំឡេង...")
        try:
            file_obj = await bot.get_file(msg.voice.file_id)
            tmp_path = f"/tmp/voice_{msg.message_id}.ogg"
            
            # Download to /tmp
            await file_obj.download_to_drive(tmp_path)
            
            # Process with Gemini
            transcribed_text = await transcribe_with_gemini_audio(tmp_path)
            
            # Remove local file immediately to prevent memory leak
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
            await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"✅ **អត្ថបទដែលបានស្តាប់៖**\n\n`{transcribed_text}`", parse_mode="Markdown")
        except Exception as e:
            await bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"❌ បរាជ័យក្នុងការស្តាប់សំឡេង៖ {str(e)}")

@https_fn.on_request(
    secrets=["TELEGRAM_TOKEN", "GEMINI_API_KEY", "GROQ_API_KEY"],
    region="asia-southeast1",
    memory=options.MemoryOption.MB_512
)
def telegram_webhook(req: https_fn.Request) -> https_fn.Response:
    if req.method == 'POST':
        try:
            update_json = req.get_json()
            # Firebase Functions runtime doesn't run an asyncio event loop natively in sync functions
            # So we create one to run our async telegram bot code
            asyncio.run(process_telegram_update(update_json))
            return https_fn.Response("OK", status=200)
        except Exception as e:
            print(f"Error handling webhook: {e}")
            return https_fn.Response("Error", status=500)
    return https_fn.Response("Method not allowed", status=405)
