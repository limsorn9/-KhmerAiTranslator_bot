import re

with open('bot.py', 'r', encoding='utf-8') as f: content = f.read()

# 1. Add submit_receipt button
target1 = """    keyboard = []
    for code, info in LANG_INFO.items():
        keyboard.append([InlineKeyboardButton(info['name'], callback_data=f"translate_{code}")])"""
        
replacement1 = """    keyboard = []
    
    # បើភ្ញៀវផ្ញើរូបភាព បន្ថែមប៊ូតុងសម្រាប់បញ្ជូនវិក្កយបត្រ
    if update.message.photo:
        keyboard.append([InlineKeyboardButton("🧾 បញ្ជូនវិក្កយបត្រ (Submit Receipt)", callback_data="submit_receipt")])
        
    for code, info in LANG_INFO.items():
        keyboard.append([InlineKeyboardButton(info['name'], callback_data=f"translate_{code}")])"""

content = content.replace(target1, replacement1)

# 2. Add callback handler for submit_receipt
target2 = """    if data.startswith('translate_'):"""

replacement2 = """    if data == "submit_receipt":
        if not msg.photo:
            await query.edit_message_text("❌ នេះមិនមែនជារូបភាពទេ!")
            return
            
        photo = msg.photo[-1]
        file_unique_id = photo.file_unique_id
        
        import db
        if db.check_receipt(file_unique_id):
            await query.edit_message_text("❌ វិក្កយបត្រនេះត្រូវបានផ្ញើរួចម្ដងហើយ! ហាមផ្ញើវិក្កយបត្រស្ទួន។")
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
            await query.edit_message_text("✅ វិក្កយបត្ររបស់អ្នកត្រូវបានបញ្ជូនទៅកាន់ Admin រួចរាល់ហើយ។ សូមរង់ចាំការបញ្ចូលកាក់បន្តិច!")
        else:
            await query.edit_message_text("⚠️ មានបញ្ហាក្នុងការបញ្ជូនទៅ Admin។ សូមទាក់ទង Admin ដោយផ្ទាល់។")
        return
        
    if data.startswith('translate_'):"""

content = content.replace(target2, replacement2)

with open('bot.py', 'w', encoding='utf-8') as f: f.write(content)
