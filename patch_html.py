import re

with open('bot.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# We will recreate bot.py but remove ALL duplicate definitions of check_my_coin, top_up_info, add_coin
# and rewrite them with HTML parse mode to prevent any Telegram parsing errors.

# 1. Filter out the old duplicate functions
new_lines = []
skip = False
for line in lines:
    if line.startswith("async def check_my_coin("):
        skip = True
    elif line.startswith("async def top_up_info("):
        skip = True
    elif line.startswith("async def add_coin("):
        skip = True
    elif skip and line.startswith("async def get_chat_id("):
        skip = False
    
    if not skip:
        new_lines.append(line)

content = "".join(new_lines)

# 2. Add the clean, robust HTML-based functions right before get_chat_id
html_functions = """
async def check_my_coin(update, context):
    try:
        user_id = update.effective_user.id
        balance = db.get_user_balance(user_id)
        total = balance['free'] + balance['paid']
        
        msg = (
            f"💰 <b>កាក់មាសរបស់អ្នក (Coins):</b> {total}\\n"
            f"🎁 កាក់ឥតគិតថ្លៃ (Free): {balance['free']}\\n"
            f"💳 កាក់បានទិញ (Paid): {balance['paid']}\\n\\n"
            f"💡 (កាក់ឥតគិតថ្លៃ ៥ នឹងផ្តល់ជូនជារៀងរាល់ថ្ងៃ!)"
        )
        
        if user_id in ADMIN_IDS:
            msg += (
                "\\n\\n🛠 <b>សម្រាប់ Admin:</b>"
                "\\n👉 វាយបញ្ជា <code>/addcoin</code> រួចចុចផ្ញើ ដើម្បីបញ្ចូលកាក់ឱ្យភ្ញៀវ។"
                "\\n👉 ឬវាយទម្រង់កាត់ <code>/addcoin ID ចំនួន</code> ផ្ទាល់ក៏បាន។"
            )
        else:
            msg += "\\n\\n👉 ទិញកាក់បន្ថែមវាយបញ្ជា <code>/topup</code>"
            
        await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        import logging
        logging.error(f"Error in check_my_coin: {e}")
        await update.message.reply_text("❌ មានបញ្ហាក្នុងការឆែកកាក់របស់អ្នក។")

async def top_up_info(update, context):
    try:
        context.user_data['awaiting_receipt'] = True
        msg = (
            "💳 <b>របៀបទិញកាក់មាស:</b>\\n\\n"
            "💵 <b>១ កាក់មាស = ១០០រៀល</b> (ឬ 0.025$)\\n\\n"
            "1️⃣ សូមវេរប្រាក់ចូល KHQR ខាងលើ\\n"
            "2️⃣ ថតអេក្រង់ (Screenshot) វិក្កយបត្រ រួចផ្ញើចូលមកក្នុងនេះផ្ទាល់\\n"
            "3️⃣ ប្រព័ន្ធនឹងបញ្ជូនវិក្កយបត្រនេះទៅ Admin ដោយស្វ័យប្រវត្តិ។\\n\\n"
            "Admin នឹងធ្វើការផ្ទៀងផ្ទាត់ និងបញ្ចូលកាក់ជូនភ្លាមៗ!"
        )
        import os
        if os.path.exists("khqr.png"):
            with open("khqr.png", "rb") as photo:
                await update.message.reply_photo(photo, caption=msg, parse_mode="HTML")
        else:
            await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        import logging
        logging.error(f"Error in top_up_info: {e}")

async def add_coin(update, context):
    try:
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ អ្នកគ្មានសិទ្ធិប្រើប្រាស់បញ្ជានេះទេ!")
            return
            
        if len(context.args) >= 2:
            target_id = context.args[0]
            amount = int(context.args[1])
            db.add_paid_coins(target_id, amount)
            await update.message.reply_text(f"✅ បានបញ្ចូល {amount} កាក់មាសទៅឱ្យ ID <code>{target_id}</code> ជោគជ័យ!", parse_mode="HTML")
            await context.bot.send_message(chat_id=target_id, text=f"🎉 <b>អបអរសាទរ!</b>\\nអ្នកទទួលបាន {amount} កាក់មាសពី Admin! ឆែកកាក់ដោយវាយ <code>/mycoin</code>", parse_mode="HTML")
        else:
            context.user_data['awaiting_addcoin'] = True
            await update.message.reply_text(
                "✍️ សូមវាយ <b>លេខIDភ្ញៀវ</b> និង <b>ចំនួនកាក់</b> រួចផ្ញើមកខ្ញុំឥឡូវនេះ។\\n"
                "ឧទាហរណ៍៖ <code>123456789 10</code> (ដកឃ្លាចំកណ្ដាល)", 
                parse_mode="HTML"
            )
    except Exception as e:
        import logging
        logging.error(f"Error in add_coin: {e}")
        await update.message.reply_text("❌ របៀបប្រើ: <code>/addcoin IDភ្ញៀវ ចំនួនកាក់</code>", parse_mode="HTML")

"""

content = content.replace("async def get_chat_id(", html_functions + "async def get_chat_id(")

# Also fix the start message bold markdown to HTML for consistency
welcome_old = '''    welcome_message = (
        "សួស្តី! 👋 ខ្ញុំគឺគ្រូសន អ្នកជំនាញខាងបកប្រែសម្លេង វីដេអូ និងអត្ថបទ ពីគ្រប់ភាសាទៅជាភាសាក្នុងអាស៊ាន និងភាសាពេញនិយមដទៃទៀត អ្នកអាចប្រើប្រាស់ខ្ញុំដោយឥតគិតថ្លៃ។\\n\\n"
        "ដើម្បីចាប់ផ្ដើម សូមគ្រាន់តែផ្ញើ **សំឡេង (Voice) វីដេអូ ឬអត្ថបទ** មកខ្ញុំ 🚀\\n\\n"
        "💡 វាយបញ្ជា /mycoin ដើម្បីឆែកមើលកាក់របស់អ្នក。"
    )
    await update.message.reply_text(welcome_message)'''

welcome_new = '''    welcome_message = (
        "សួស្តី! 👋 ខ្ញុំគឺគ្រូសន អ្នកជំនាញខាងបកប្រែសម្លេង វីដេអូ និងអត្ថបទ ពីគ្រប់ភាសាទៅជាភាសាក្នុងអាស៊ាន និងភាសាពេញនិយមដទៃទៀត អ្នកអាចប្រើប្រាស់ខ្ញុំដោយឥតគិតថ្លៃ។\\n\\n"
        "ដើម្បីចាប់ផ្ដើម សូមគ្រាន់តែផ្ញើ <b>សំឡេង (Voice) វីដេអូ ឬអត្ថបទ</b> មកខ្ញុំ 🚀\\n\\n"
        "💡 វាយបញ្ជា /mycoin ដើម្បីឆែកមើលកាក់របស់អ្នក។"
    )
    await update.message.reply_text(welcome_message, parse_mode="HTML")'''

content = content.replace(welcome_old, welcome_new)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)
