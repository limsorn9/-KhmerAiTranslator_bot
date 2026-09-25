import re

with open('requirements.txt', 'r', encoding='utf-8') as f:
    req_content = f.read()

if 'SpeechRecognition' not in req_content:
    with open('requirements.txt', 'a', encoding='utf-8') as f:
        f.write("\nSpeechRecognition\npydub\n")

with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = """def transcribe_with_google_cloud(file_path):
    \"\"\"
    Placeholder/Mock function for Google Cloud Speech-to-Text.
    In the future, integrate google-cloud-speech library here.
    \"\"\"
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
        return None, f"❌ បញ្ហាប្រព័ន្ធ Groq AI៖ {str(e)}" """

replacement = """def transcribe_with_google_free(file_path):
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
            # បើ Groq គិតថាជាភាសាខ្មែរ យើងបោះទៅឱ្យ Google ជាអ្នកស្តាប់វិញដើម្បីឱ្យច្បាស់
            logging.info("Detected Khmer voice by Groq. Rerouting to Google Free STT...")
            google_text, err = transcribe_with_google_free(file_path)
            if google_text:
                return google_text, None
            # បើ Google ស្តាប់បរាជ័យ ប្រើរបស់ Groq ធម្មតា
            return text, None
        else:
            # ប្រើ Groq's transcription សម្រាប់ភាសាផ្សេងៗ
            return text, None
    except Exception as e:
        logging.error(f"Groq API Error: {e}")
        return None, f"❌ បញ្ហាប្រព័ន្ធ Groq AI៖ {str(e)}" """

if target in content:
    content = content.replace(target, replacement)
    with open('bot.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("ជោគជ័យ! បានផ្លាស់ប្តូរការស្តាប់សម្លេងទៅប្រើ Google Free សម្រាប់ភាសាខ្មែរ។")
else:
    print("រកមិនឃើញកូដដែលត្រូវជំនួសទេ សូមពិនិត្យមើលម្តងទៀត!")
