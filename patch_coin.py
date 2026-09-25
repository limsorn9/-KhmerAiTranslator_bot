import re

with open('bot.py', 'r', encoding='utf-8') as f: content = f.read()

target = """async def check_my_coin(update, context):
    user_id = update.effective_user.id
    balance = db.get_user_balance(user_id)
    total = balance['free'] + balance['paid']
    msg = (
        f"💰 **កាក់មាសរបស់អ្នក (Coins):** {total}\\n"
        f"🎁 កាក់ឥតគិតថ្លៃ (Free): {balance['free']}\\n"
        f"💳 កាក់បានទិញ (Paid): {balance['paid']}\\n\\n"
        f"💡 (កាក់ឥតគិតថ្លៃ ៥ នឹងផ្តល់ជូនជារៀងរាល់ថ្ងៃ!)\\n"
        f"👉 ទិញកាក់បន្ថែមវាយបញ្ជា /topup"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")"""

replacement = """async def check_my_coin(update, context):
    user_id = update.effective_user.id
    balance = db.get_user_balance(user_id)
    total = balance['free'] + balance['paid']
    
    msg = (
        f"💰 **កាក់មាសរបស់អ្នក (Coins):** {total}\\n"
        f"🎁 កាក់ឥតគិតថ្លៃ (Free): {balance['free']}\\n"
        f"💳 កាក់បានទិញ (Paid): {balance['paid']}\\n\\n"
        f"💡 (កាក់ឥតគិតថ្លៃ ៥ នឹងផ្តល់ជូនជារៀងរាល់ថ្ងៃ!)"
    )
    
    if user_id in ADMIN_IDS:
        msg += (
            "\\n\\n🛠 **សម្រាប់ Admin:**"
            "\\n👉 វាយបញ្ជា `/addcoin` រួចចុចផ្ញើ ដើម្បីបញ្ចូលកាក់ឱ្យភ្ញៀវ។"
            "\\n👉 ឬវាយទម្រង់កាត់ `/addcoin <ID> <ចំនួន>` ផ្ទាល់ក៏បាន។"
        )
    else:
        msg += "\\n\\n👉 ទិញកាក់បន្ថែមវាយបញ្ជា `/topup`"
        
    await update.message.reply_text(msg, parse_mode="Markdown")"""

content = content.replace(target, replacement)
with open('bot.py', 'w', encoding='utf-8') as f: f.write(content)
