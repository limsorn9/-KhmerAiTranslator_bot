import os

with open('doc_reader.py', 'r', encoding='utf-8') as f:
    content = f.read()

if "async def process_document" not in content:
    new_code = """
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
"""
    with open('doc_reader.py', 'a', encoding='utf-8') as f:
        f.write(new_code)
    print("Fixed doc_reader.py")
else:
    print("process_document already exists.")
