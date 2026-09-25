import re

with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update top_up_info to set awaiting_receipt
topup_old = """    if os.path.exists("khqr.png"):
        with open("khqr.png", "rb") as photo:
            await update.message.reply_photo(photo, caption=msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")"""
        
topup_new = """    context.user_data['awaiting_receipt'] = True
    if os.path.exists("khqr.png"):
        with open("khqr.png", "rb") as photo:
            await update.message.reply_photo(photo, caption=msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")"""

content = content.replace(topup_old, topup_new)

# 2. Update receipt checking logic in prompt_language_selection
receipt_old = """    # ឆែកមើលវិក្កយបត្រ (Photo)
    if update.message.photo:
        if update.message.chat.type != 'private':
            return
        photo = update.message.photo[-1]
        file_unique_id = photo.file_unique_id
        user_id = update.effective_user.id
        
        if db.check_receipt(file_unique_id):
            await update.message.reply_text("❌ វិក្កយបត្រនេះត្រូវបានផ្ញើរួចម្ដងហើយ! ហាមផ្ញើវិក្កយបត្រស្ទួន។")
            return
            
        db.save_receipt(file_unique_id, user_id)
        
        sent_to_admin = False
        for admin_id in ADMIN_IDS:
            try:
                caption = f"🧾 **មានវិក្កយបត្រថ្មីពីភ្ញៀវ!**\\n👤 ភ្ញៀវ ID: `{user_id}`\\n\\nវាយបញ្ជាខាងក្រោមដើម្បីបញ្ចូលកាក់ឱ្យគាត់៖\\n`/addcoin {user_id} [ចំនួនកាក់]`"
                await context.bot.send_photo(chat_id=admin_id, photo=photo.file_id, caption=caption, parse_mode="Markdown")
                sent_to_admin = True
            except:
                pass
                
        if sent_to_admin:
            await update.message.reply_text("✅ វិក្កយបត្ររបស់អ្នកត្រូវបានបញ្ជូនទៅកាន់ Admin រួចរាល់ហើយ។ សូមរង់ចាំការបញ្ចូលកាក់បន្តិច!")
        else:
            await update.message.reply_text("⚠️ មានបញ្ហាក្នុងការបញ្ជូនទៅ Admin។ សូមទាក់ទង Admin ដោយផ្ទាល់។")
        return"""

receipt_new = """    # ឆែកមើលវិក្កយបត្រ (Photo) ឬ រូបភាពសម្រាប់បកប្រែ
    if update.message.photo:
        if update.message.chat.type != 'private':
            return
            
        if context.user_data.get('awaiting_receipt'):
            photo = update.message.photo[-1]
            file_unique_id = photo.file_unique_id
            user_id = update.effective_user.id
            
            if db.check_receipt(file_unique_id):
                await update.message.reply_text("❌ វិក្កយបត្រនេះត្រូវបានផ្ញើរួចម្ដងហើយ! ហាមផ្ញើវិក្កយបត្រស្ទួន។")
                return
                
            db.save_receipt(file_unique_id, user_id)
            
            sent_to_admin = False
            for admin_id in ADMIN_IDS:
                try:
                    caption = f"🧾 **មានវិក្កយបត្រថ្មីពីភ្ញៀវ!**\\n👤 ភ្ញៀវ ID: `{user_id}`\\n\\nវាយបញ្ជាខាងក្រោមដើម្បីបញ្ចូលកាក់ឱ្យគាត់៖\\n`/addcoin {user_id} [ចំនួនកាក់]`"
                    await context.bot.send_photo(chat_id=admin_id, photo=photo.file_id, caption=caption, parse_mode="Markdown")
                    sent_to_admin = True
                except:
                    pass
                    
            if sent_to_admin:
                await update.message.reply_text("✅ វិក្កយបត្ររបស់អ្នកត្រូវបានបញ្ជូនទៅកាន់ Admin រួចរាល់ហើយ។ សូមរង់ចាំការបញ្ចូលកាក់បន្តិច!")
            else:
                await update.message.reply_text("⚠️ មានបញ្ហាក្នុងការបញ្ជូនទៅ Admin។ សូមទាក់ទង Admin ដោយផ្ទាល់។")
                
            context.user_data['awaiting_receipt'] = False
            return
        # បើមិនមែនជា Receipt ទេ, អនុញ្ញាតឱ្យវាហូរទៅជាការបកប្រែ (Translation)"""

content = content.replace(receipt_old, receipt_new)

# 3. Update button_callback to intercept documents and photos for text extraction
callback_target = """        # គណនាកាក់មាសដែលត្រូវកាត់
        cost = 1
        if msg.text:"""
        
callback_replacement = """        # Extract text if document or photo
        extracted_text = msg.text
        if msg.photo or (msg.document and not msg.document.mime_type.startswith(('audio/', 'video/'))):
            await query.edit_message_text("⏳ កំពុងទាញយកអក្សរចេញពីឯកសារ/រូបភាព... សូមរង់ចាំបន្តិច!")
            import doc_reader
            import os
            import asyncio
            
            file_obj = None
            if msg.photo:
                file_obj = await msg.photo[-1].get_file()
                ext = ".jpg"
            else:
                file_obj = await msg.document.get_file()
                ext = os.path.splitext(msg.document.file_name)[1]
            
            temp_path = f"temp_doc_{msg.message_id}{ext}"
            await file_obj.download_to_drive(temp_path)
            ex_txt, err = await asyncio.to_thread(doc_reader.extract_text, temp_path)
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
            if err:
                await query.edit_message_text(err)
                return
            extracted_text = ex_txt

        # គណនាកាក់មាសដែលត្រូវកាត់
        cost = 1
        if extracted_text:"""

content = content.replace(callback_target, callback_replacement)

# Update the rest of button_callback to use extracted_text
content = content.replace("cost = calculate_text_cost(msg.text)", "cost = calculate_text_cost(extracted_text)")
content = content.replace("if msg.text:", "if extracted_text:")
content = content.replace("await process_text_action(msg, processing_msg, target_lang, voice_id)", "class MockMsg: pass\\n            mock_msg = MockMsg()\\n            mock_msg.text = extracted_text\\n            mock_msg.message_id = msg.message_id\\n            mock_msg.reply_voice = msg.reply_voice\\n            await process_text_action(mock_msg, processing_msg, target_lang, voice_id)")

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)
