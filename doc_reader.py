import os
import docx
import openpyxl
from PIL import Image
import pytesseract
import logging

def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    try:
        if ext == '.docx':
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif ext == '.xlsx':
            wb = openpyxl.load_workbook(file_path, data_only=True)
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    row_data = [str(cell) for cell in row if cell is not None]
                    if row_data:
                        text += " ".join(row_data) + "\n"
        elif ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        elif ext in ['.png', '.jpg', '.jpeg', '.webp']:
            # 1. សាកល្បងប្រើ Google Gemini ព្រោះវាឥតគិតថ្លៃ និងពូកែអានអក្សរខ្មែរជាងគេ
            try:
                GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
                if GEMINI_API_KEY:
                    import google.generativeai as genai
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    img = Image.open(file_path)
                    response = model.generate_content([
                        "Extract all the text from this image. Output only the extracted text exactly as it appears. Do not add any explanation.",
                        img
                    ])
                    text = response.text.strip()
                    if not text:
                        return None, "❌ មិនមានអក្សរនៅក្នុងឯកសារនេះទេ! (Gemini)"
                    return text, None
            except Exception as gemini_e:
                logging.warning(f"Gemini Vision failed: {gemini_e}")
                if "API key not valid" in str(gemini_e):
                    return None, "❌ API Key របស់ Gemini មិនត្រឹមត្រូវទេ! សូមពិនិត្យមើល GEMINI_API_KEY នៅក្នុង Render ឡើងវិញ។"
                return None, f"❌ បរាជ័យក្នុងការអានដោយ Gemini៖ {gemini_e}"
            # 2. បើ Gemini បរាជ័យ (ឬគ្មាន Key) សាកល្បងប្រើ Groq Vision API
            if not text:
                try:
                    import base64
                    from groq import Groq
                    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
                    if GROQ_API_KEY:
                        client = Groq(api_key=GROQ_API_KEY)
                        with open(file_path, "rb") as image_file:
                            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        
                        models_to_try = [
                            "llama-3.2-90b-vision-preview",
                        ]
                        
                        # ស្វែងរកឈ្មោះម៉ូដែល Vision ដែលកំពុងបើកឱ្យប្រើដោយស្វ័យប្រវត្តិ
                        try:
                            all_models = client.models.list().data
                            vision_models = [m.id for m in all_models if "vision" in m.id.lower() or "vl" in m.id.lower() or "qwen" in m.id.lower()]
                            if vision_models:
                                models_to_try = vision_models
                        except Exception:
                            pass
                            
                        for model_name in models_to_try:
                            try:
                                response = client.chat.completions.create(
                                    messages=[
                                        {
                                            "role": "user",
                                            "content": [
                                                {"type": "text", "text": "Extract all the text from this image. Output only the extracted text exactly as it appears. Do not add any explanation or conversational text."},
                                                {
                                                    "type": "image_url",
                                                    "image_url": {
                                                        "url": f"data:image/jpeg;base64,{encoded_string}",
                                                    },
                                                },
                                            ],
                                        }
                                    ],
                                    model=model_name,
                                )
                                text = response.choices[0].message.content.strip()
                                if text:
                                    break
                            except Exception as loop_e:
                                logging.warning(f"Failed with {model_name}: {loop_e}")
                                vision_error = str(loop_e)
                except Exception as vision_e:
                    vision_error = str(vision_e)
                    logging.warning(f"Groq Vision failed, falling back to Tesseract: {vision_e}")
                
            # បើ Groq បរាជ័យ ឬអត់បាន text ទើបប្រើ Tesseract
            if not text:
                try:
                    img = Image.open(file_path)
                    text = pytesseract.image_to_string(img, lang='khm+eng').strip()
                    if not text:
                        text = pytesseract.image_to_string(img, lang='eng').strip()
                    if not text:
                        text = pytesseract.image_to_string(img, lang='khm').strip()
                except Exception as tess_e:
                    tess_error = str(tess_e)
                    
        else:
            return None, f"❌ មិនគាំទ្រប្រភេទឯកសារ {ext} នេះទេ!"
            
        if not text or not text.strip():
            err_msg = "❌ មិនមានអក្សរនៅក្នុងឯកសារនេះទេ! អាចថារូបភាពមិនច្បាស់ (សូមផ្ញើជា File/Document ជំនួសវិញ)។"
            try:
                if vision_error:
                    err_msg += f"\\n\\n[Debug] Groq API Error: {vision_error}"
            except:
                pass
            return None, err_msg
            
        return text.strip(), None
    except Exception as e:
        logging.error(f"Error extracting text from {file_path}: {e}")
        return None, f"❌ បរាជ័យក្នុងការអានឯកសារ៖ {str(e)}"

async def process_document(msg, bot):
    import os
    import asyncio
    
    file_obj = None
    if msg.photo:
        file_obj = await bot.get_file(msg.photo[-1].file_id)
        ext = ".jpg"
    elif msg.document:
        file_obj = await bot.get_file(msg.document.file_id)
        ext = os.path.splitext(msg.document.file_name)[1]
    else:
        return None, "❌ មិនមានឯកសារទេ"

    temp_path = f"temp_doc_{msg.message_id}{ext}"
    try:
        await file_obj.download_to_drive(temp_path)
        # ត្រូវប្រើ asyncio.to_thread ព្រោះ extract_text គឺមានដំណើរការយឺត (blocking)
        ex_txt, err = await asyncio.to_thread(extract_text, temp_path)
        return ex_txt, err
    except Exception as e:
        return None, f"❌ កំហុសពេលទាញយកឯកសារ៖ {str(e)}"
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
