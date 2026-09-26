import os
import re

with open('doc_reader.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = """        elif ext in ['.png', '.jpg', '.jpeg', '.webp']:
            # ប្រើ OCR សម្រាប់រូបភាព (គាំទ្រទាំងខ្មែរនិងអង់គ្លេស)
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img, lang='khm+eng')
        else:
            return None, f"❌ មិនគាំទ្រប្រភេទឯកសារ {ext} នេះទេ!"
            
        if not text.strip():
            return None, "❌ មិនមានអក្សរនៅក្នុងឯកសារនេះទេ!"
            
        return text.strip(), None"""

replacement = """        elif ext in ['.png', '.jpg', '.jpeg', '.webp']:
            # សាកល្បងប្រើ Groq Vision API ដើម្បីអានអក្សរពីរូបភាពព្រោះវាច្បាស់ជាង
            try:
                import base64
                from groq import Groq
                GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
                if GROQ_API_KEY:
                    client = Groq(api_key=GROQ_API_KEY)
                    with open(file_path, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    
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
                        model="llama-3.2-11b-vision-preview",
                    )
                    text = response.choices[0].message.content.strip()
            except Exception as vision_e:
                logging.warning(f"Groq Vision failed, falling back to Tesseract: {vision_e}")
                
            # បើ Groq បរាជ័យ ឬអត់បាន text ទើបប្រើ Tesseract
            if not text:
                img = Image.open(file_path)
                text = pytesseract.image_to_string(img, lang='khm+eng').strip()
                if not text:
                    text = pytesseract.image_to_string(img, lang='eng').strip()
                if not text:
                    text = pytesseract.image_to_string(img, lang='khm').strip()
                    
        else:
            return None, f"❌ មិនគាំទ្រប្រភេទឯកសារ {ext} នេះទេ!"
            
        if not text or not text.strip():
            return None, "❌ មិនមានអក្សរនៅក្នុងឯកសារនេះទេ! អាចថារូបភាពមិនច្បាស់ (សូមផ្ញើជា File/Document ជំនួសវិញ)។"
            
        return text.strip(), None"""

if target in content:
    content = content.replace(target, replacement)
    with open('doc_reader.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("ជោគជ័យ")
else:
    print("រកមិនឃើញកូដ")
