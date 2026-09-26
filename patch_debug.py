import os

with open('doc_reader.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = """            except Exception as vision_e:
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
            return None, "❌ មិនមានអក្សរនៅក្នុងឯកសារនេះទេ! អាចថារូបភាពមិនច្បាស់ (សូមផ្ញើជា File/Document ជំនួសវិញ)។" """

replacement = """            except Exception as vision_e:
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
            return None, err_msg """

if target in content:
    content = content.replace(target, replacement)
    with open('doc_reader.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("ជោគជ័យ")
else:
    print("រកមិនឃើញកូដ")
