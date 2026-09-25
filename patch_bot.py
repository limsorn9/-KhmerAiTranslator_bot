import re

with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add import db and math
content = content.replace("import urllib.parse\nimport traceback", "import urllib.parse\nimport traceback\nimport math\nimport db")

# 2. Add ADMIN_IDS
content = content.replace('RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")', 'RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")\nADMIN_IDS = [int(i) for i in os.environ.get("ADMIN_IDS", "").split(",") if i]')

# 3. Add mycoin, topup, addcoin to commands list
content = content.replace('BotCommand("start", "ចាប់ផ្ដើមបត (Start Bot)")\n    ])', 'BotCommand("start", "ចាប់ផ្ដើមបត (Start Bot)"),\n        BotCommand("mycoin", "ឆែកកាក់របស់អ្នក (Check Coins)"),\n        BotCommand("topup", "ទិញកាក់មាស (Top up Coins)"),\n        BotCommand("id", "ឆែក ID (Check ID)")\n    ])')

# 4. Add mycoin hint to start
content = content.replace('💡 វាយបញ្ជា /id ដើម្បីឆែកលេខសម្គាល់ក្រុម ឬគណនីរបស់អ្នក។', '💡 វាយបញ្ជា /mycoin ដើម្បីឆែកមើលកាក់របស់អ្នក។')

# 5. Add new commands
commands_code = """
async def check_my_coin(update, context):
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
    await update.message.reply_text(msg, parse_mode="Markdown")

async def top_up_info(update, context):
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
    await update.message.reply_text(msg, parse_mode="Markdown")

async def add_coin(update, context):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ អ្នកគ្មានសិទ្ធិប្រើប្រាស់បញ្ជានេះទេ!")
        return
        
    try:
        target_id = context.args[0]
        amount = int(context.args[1])
        db.add_paid_coins(target_id, amount)
        await update.message.reply_text(f"✅ បានបញ្ចូល {amount} កាក់មាសទៅឱ្យ ID {target_id} ជោគជ័យ!")
        await context.bot.send_message(chat_id=target_id, text=f"🎉 **អបអរសាទរ!**\\nអ្នកទទួលបាន {amount} កាក់មាសពី Admin! ឆែកកាក់ដោយវាយ /mycoin", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text("❌ របៀបប្រើ: /addcoin <IDភ្ញៀវ> <ចំនួនកាក់>")

async def get_chat_id"""
content = content.replace("async def get_chat_id", commands_code)

# 6. Replace button_callback
callback_code_old = """async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    msg = context.user_data.get('pending_msg')
    if not msg:
        await query.edit_message_text("❌ រកមិនឃើញឯកសារបណ្ដោះអាសន្នទេ។ សូមផ្ញើឯកសារម្ដងទៀត។")
        return
        
    if data.startswith('translate_'):
        code = data.split('_', 1)[1]
        
        target_info = LANG_INFO[code]
        target_lang = target_info.get('google_lang', code)
        voice_id = target_info['voice']
        
        processing_msg = query.message
        
        if msg.text:
            await query.edit_message_text(f"⏳ កំពុងធ្វើការបកប្រែទៅជា **{target_info['name']}** សូមរង់ចាំបន្តិច...")
            await process_text_action(msg, processing_msg, target_lang, voice_id)
        else:
            await query.edit_message_text(f"⏳ ឱ្យតែជាសម្លេង Groq AI ប្រើពេលមិនដល់១នាទីនោះទេ កំពុងបកប្រែទៅជា **{target_info['name']}**...")
            await process_media_action(msg, processing_msg, target_lang, voice_id)"""

callback_code_new = """
def calculate_text_cost(text):
    words = len(text.split())
    if words <= 100:
        return 1
    return 1 + (words // 100)

def calculate_media_cost(duration_seconds):
    if not duration_seconds: return 1
    return max(1, math.ceil(duration_seconds / 60))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    data = query.data
    
    msg = context.user_data.get('pending_msg')
    if not msg:
        await query.edit_message_text("❌ រកមិនឃើញឯកសារបណ្ដោះអាសន្នទេ។ សូមផ្ញើឯកសារម្ដងទៀត។")
        return
        
    if data.startswith('translate_'):
        code = data.split('_', 1)[1]
        
        # គណនាកាក់មាសដែលត្រូវកាត់
        cost = 1
        if msg.text:
            cost = calculate_text_cost(msg.text)
        else:
            duration = 0
            if msg.voice: duration = msg.voice.duration
            elif msg.audio: duration = msg.audio.duration
            elif msg.video: duration = msg.video.duration
            elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith(('audio/', 'video/')):
                duration = getattr(msg.document, 'duration', 1)
            cost = calculate_media_cost(duration)
            
        # ឆែកលុយ
        balance = db.get_user_balance(user_id)
        total_coins = balance['free'] + balance['paid']
        if total_coins < cost:
            await query.edit_message_text(
                f"❌ **លោកអ្នកមានកាក់មាសមិនគ្រប់គ្រាន់ទេ!**\\n"
                f"ការបកប្រែនេះត្រូវការអស់ **{cost} កាក់** ប៉ុន្តែអ្នកមានតែ **{total_coins} កាក់**។\\n"
                f"សូមវាយបញ្ជា /topup ដើម្បីទិញកាក់បន្ថែម។",
                parse_mode="Markdown"
            )
            return
            
        # កាត់លុយ
        db.deduct_coins(user_id, cost)
        
        target_info = LANG_INFO[code]
        target_lang = target_info.get('google_lang', code)
        voice_id = target_info['voice']
        
        processing_msg = query.message
        
        if msg.text:
            await query.edit_message_text(f"💰 (អស់ {cost} កាក់) កំពុងបកប្រែទៅជា **{target_info['name']}**... ⏳")
            await process_text_action(msg, processing_msg, target_lang, voice_id)
        else:
            await query.edit_message_text(f"💰 (អស់ {cost} កាក់) កំពុងស្ដាប់ និងបកប្រែទៅជា **{target_info['name']}**... ⏳")
            await process_media_action(msg, processing_msg, target_lang, voice_id)"""

content = content.replace(callback_code_old, callback_code_new)

# 7. Add handlers
handlers_old = """    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("id", get_chat_id))
    application.add_handler(CallbackQueryHandler(button_callback))"""

handlers_new = """    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("id", get_chat_id))
    application.add_handler(CommandHandler("mycoin", check_my_coin))
    application.add_handler(CommandHandler("topup", top_up_info))
    application.add_handler(CommandHandler("addcoin", add_coin))
    application.add_handler(CallbackQueryHandler(button_callback))"""

content = content.replace(handlers_old, handlers_new)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)
