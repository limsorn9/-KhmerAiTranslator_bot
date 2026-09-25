import re

# Patch db.py
with open('db.py', 'r', encoding='utf-8') as f:
    db_content = f.read()

new_db_functions = """
def check_receipt(receipt_id):
    if not db_ref: return False
    data = db_ref.child('receipts').child(receipt_id).get()
    return bool(data)

def save_receipt(receipt_id, user_id):
    if not db_ref: return
    db_ref.child('receipts').child(receipt_id).set({
        'user_id': str(user_id),
        'timestamp': get_today_str()
    })
"""
if "def check_receipt" not in db_content:
    db_content += new_db_functions
    with open('db.py', 'w', encoding='utf-8') as f:
        f.write(db_content)

# Patch bot.py
with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update top_up_info
topup_old = """async def top_up_info(update, context):
    msg = (
        "💳 **របៀបទិញកាក់មាស:**\\n\\n"
        "💵 **១ កាក់មាស = ១០០រៀល** (ឬ 0.025$)\\n\\n"
        "1️⃣ សូមវេរប្រាក់តាមគណនី ABA:\\n"
        "   - លេខគណនី: `000000000`\\n"
        "   - ឈ្មោះ: `Your Name`\\n"
        "2️⃣ ថតអេក្រង់ (Screenshot) ការវេរប្រាក់ រួចផ្ញើមកកាន់ Admin [@AdminUsername]\\n"
        f"3️⃣ កុំភ្លេចប្រាប់ ID របស់អ្នកទៅ Admin ផង (ID របស់អ្នកគឺ៖ `{update.effective_user.id}`)\\n\\n"
        "Admin នឹងធ្វើការបញ្ចូលកាក់ជូនភ្លាមៗ!"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")"""

topup_new = """async def top_up_info(update, context):
    msg = (
        "💳 **របៀបទិញកាក់មាស:**\\n\\n"
        "💵 **១ កាក់មាស = ១០០រៀល** (ឬ 0.025$)\\n\\n"
        "1️⃣ សូមវេរប្រាក់ចូល KHQR ខាងលើ\\n"
        "2️⃣ ថតអេក្រង់ (Screenshot) វិក្កយបត្រ រួចផ្ញើចូលមកក្នុងនេះផ្ទាល់\\n"
        "3️⃣ ប្រព័ន្ធនឹងបញ្ជូនវិក្កយបត្រនេះទៅ Admin ដោយស្វ័យប្រវត្តិ។\\n\\n"
        "Admin នឹងធ្វើការផ្ទៀងផ្ទាត់ និងបញ្ចូលកាក់ជូនភ្លាមៗ!"
    )
    if os.path.exists("khqr.png"):
        with open("khqr.png", "rb") as photo:
            await update.message.reply_photo(photo, caption=msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")"""

content = content.replace(topup_old, topup_new)

# 2. Update prompt_language_selection
prompt_insert_point = "    # បើកុំឱ្យឆែកសមាជិកពេលនៅក្នុងក្រុម (Group Chat) ព្រោះ Bot អាចនឹងឆ្លើយតបគ្រប់សារ"

photo_logic = """    # ឆែកមើលវិក្កយបត្រ (Photo)
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
        return

    # បើកុំឱ្យឆែកសមាជិកពេលនៅក្នុងក្រុម (Group Chat) ព្រោះ Bot អាចនឹងឆ្លើយតបគ្រប់សារ"""

content = content.replace(prompt_insert_point, photo_logic)

# 3. Add filters.PHOTO to MessageHandler
content = content.replace("filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL", "filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL | filters.PHOTO")

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)
