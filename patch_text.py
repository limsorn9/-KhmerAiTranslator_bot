import re

with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = """    msg = update.message
    # រក្សាទុកឯកសារនៅក្នុង Memory
    context.user_data['pending_msg'] = msg
    
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
        f"📥 **ប្រភេទឯកសារ៖** {doc_type}\\n"
        f"🗣 **ភាសាដើម៖** (Groq AI ស្វែងរកដោយស្វ័យប្រវត្តិ ⚡️)\\n\\n"
        f"🎯 តើអ្នកចង់ឱ្យខ្ញុំបកប្រែទៅជាភាសាអ្វី?"
    )
    
    keyboard = build_language_keyboard("translate")
    await msg.reply_text(prompt_text, reply_markup=keyboard, reply_to_message_id=msg.message_id)"""

replacement = """    msg = update.message
    
    extracted_text = None
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
        f"📥 <b>ប្រភេទឯកសារ៖</b> {doc_type}\\n"
        f"🗣 <b>ភាសាដើម៖</b> (Groq AI ស្វែងរកដោយស្វ័យប្រវត្តិ ⚡️)\\n\\n"
        f"🎯 តើអ្នកចង់ឱ្យខ្ញុំបកប្រែទៅជាភាសាអ្វី?"
    )
    
    keyboard = build_language_keyboard("translate")
    
    # បន្ថែមប៊ូតុង ផ្ញើទៅអេដមីន ប្រសិនបើជារូបភាព
    if msg.photo:
        keyboard.inline_keyboard.insert(0, [InlineKeyboardButton("🧾 ផ្ញើទៅអេដមីន", callback_data="submit_receipt")])
        
    await msg.reply_text(prompt_text, reply_markup=keyboard, reply_to_message_id=msg.message_id, parse_mode="HTML")"""

content = content.replace(target, replacement)

# We also need to fix `button_callback` to read `extracted_text = context.user_data.get('extracted_text')`
target2 = """    if data.startswith('translate_'):
        code = data.split('_', 1)[1]
        
        target_info = LANG_INFO[code]
        target_lang = target_info.get('google_lang', code)
        voice_id = target_info['voice']
        
        processing_msg = query.message
        
        if extracted_text:"""

replacement2 = """    if data.startswith('translate_'):
        code = data.split('_', 1)[1]
        
        target_info = LANG_INFO[code]
        target_lang = target_info.get('google_lang', code)
        voice_id = target_info['voice']
        
        processing_msg = query.message
        extracted_text = context.user_data.get('extracted_text')
        
        if extracted_text:"""

content = content.replace(target2, replacement2)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)
