# Khmer Text Constants - Written directly as UTF-8
# This file avoids all Unicode escape sequence corruption issues.

MSG_START = (
    "👋 សួស្តី! ខ្ញុំជា KhmerAI Translator Bot\n\n"
    "📌 ខ្ញុំអាចជួយអ្នកបាន៖\n"
    "• ✍️ ផ្ញើអត្ថបទ ភាសាណាក៏បាន → បកប្រែ ៩ ភាសា\n"
    "• 🎤 ផ្ញើសំឡេង (Voice message)\n"
    "• 📹 ផ្ញើវីដេអូ (Video)\n"
    "• 📄 ផ្ញើឯកសារ (.txt, .docx)\n"
    "• 🖼️ ផ្ញើរូបភាព\n\n"
    "⚡ Free Tier: ១០ ដង/ថ្ងៃ\n"
    "📊 ប្រើ /mycoin ដើម្បីមើលចំនួនប្រើប្រាស់\n"
    "👉 សូមផ្ញើសារណាមួយដើម្បីចាប់ផ្តើម!"
)

MSG_TOPUP = (
    "💎 អាប់ដេតទៅ Premium (បញ្ចូលប្រាក់)\n\n"
    "🆓 Free Tier: ១០ ដង/ថ្ងៃ\n"
    "⭐ Premium: ១ សារ = ១ កាក់ (Coin)\n\n"
    "📲 សូមស្កេន QR Code ខាងក្រោមដើម្បីបង់ប្រាក់ រួចផ្ញើវិក្កយបត្រ (វិក័យប័ត្រ) និង /id របស់អ្នកទៅកាន់ Admin @YourAdminHandle ដើម្បីបញ្ចូលទឹកប្រាក់។"
)

MSG_ID = "🔑 Telegram ID របស់អ្នកគឺ: `{}`"

MSG_ADMIN_ADD = "✅ បានបញ្ចូលទឹកប្រាក់ចំនួន {amount} កាក់ ទៅកាន់ ID {user_id} ដោយជោគជ័យ។ ទឹកប្រាក់សរុប: {balance} កាក់"
MSG_ADMIN_REMOVE = "✅ បានដកទឹកប្រាក់ចំនួន {amount} កាក់ ពី ID {user_id} ដោយជោគជ័យ។ ទឹកប្រាក់នៅសល់: {balance} កាក់"
MSG_ADMIN_CHECK = "👤 ទឹកប្រាក់របស់ ID {user_id} គឺ: {balance} កាក់"
MSG_NOT_ADMIN = "❌ អ្នកមិនមានសិទ្ធិប្រើប្រាស់បញ្ជានេះទេ! (សម្រាប់តែ Admin)"
MSG_INVALID_FORMAT = "❌ ទម្រង់ខុស! សូមប្រើ: {format}"

MSG_UNKNOWN_CMD = "❓ ពាក្យបញ្ជានេះមិនត្រូវបានគាំទ្រទេ។ សូមសាកល្បង /start"

MSG_QUOTA_EXCEEDED = (
    "🚫 អ្នកបានប្រើគ្រប់ ១០ ដងសម្រាប់ថ្ងៃនេះហើយ (Free Tier)!\n\n"
    "💡 ប្រើ /topup ដើម្បី Upgrade!"
)

MSG_PROCESSING = "⏳ កំពុងដំណើរការ..."
MSG_TRANSLATING = "⏳ កំពុងបកប្រែ..."
MSG_DOC_UNSUPPORTED = "❌ ទទួលយកតែ .txt និង .docx ប៉ុណ្ណោះ!"
MSG_FORMAT_UNSUPPORTED = "❌ ទម្រង់ឯកសារនេះមិនត្រូវបានគាំទ្រទេ!"
MSG_IMAGE_NO_TEXT = "⚠️ រូបភាពមិនច្បាស់ ឬ គ្មានអក្សរ! សូមផ្ញើរូបភាពថ្មី។"
MSG_GROQ_QUOTA = "⚠️ Groq អស់ Quota! សូមរង់ចាំ ១ នាទី។"
MSG_GEMINI_OVERLOAD = "⚠️ Gemini Overload! សូមរង់ចាំ ១-២ នាទី។"
MSG_NO_GROQ_KEY = "❌ គ្មាន GROQ_API_KEY!"
MSG_NO_GEMINI_KEY = "❌ គ្មាន GEMINI_API_KEY!"
MSG_EXPIRED = "⚠️ អត្ថបទផុតអាយុហើយ! សូមផ្ញើសារថ្មីម្តងទៀត។"
MSG_RESULT = "✅ លទ្ធផល:"
MSG_TRANSLATE_FAIL = "❌ បរាជ័យបកប្រែ! សូមព្យាយាមម្តងទៀត។"

BTN_TRANSLATE_ALL = "🌐 បកប្រែគ្រប់ភាសា"

SELECTOR_HEADER = "📄 អក្សរដែលបានទាញចេញ:\n\n"
SELECTOR_FOOTER = "\n\n❓ សូមជ្រើសរើសភាសាដែលចង់បកប្រែ ↓"

def msg_mycoin(count: int, daily_limit: int, remaining: int, balance: float) -> str:
    return (
        f"📊 ស្ថានភាពគណនីរបស់អ្នក\n\n"
        f"✅ ប្រើប្រាស់ Free ថ្ងៃនេះ: {count}/{daily_limit} ដង\n"
        f"🔋 Free នៅសល់: {remaining} ដង\n\n"
        f"💰 ទឹកប្រាក់ Premium (Wallet): {balance} កាក់\n\n"
        f"🔄 កូតា Free នឹង Reset ឡើងវិញនៅថ្ងៃស្អែក។"
    )
