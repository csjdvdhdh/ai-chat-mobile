# AI Chat Mobile + Telegram Bot

## 1) تطبيق الويب (الجوال)
مرفوع على Railway — واجهة شات + ملفات + نسخ كود.

## 2) بوت تيليجرام
ملف: `telegram_bot.py`

### المطلوب
1. من https://my.telegram.org خذ:
   - TG_API_ID
   - TG_API_HASH
2. مفتاح ذكاء: GROQ_API_KEY أو OPENROUTER_API_KEY

### تشغيل محلي (أول مرة يسجل دخول)
```bash
pip install telethon requests
export TG_API_ID=123456
export TG_API_HASH=xxxx
export GROQ_API_KEY=xxxx
python telegram_bot.py
```
يدخل رقمك + رمز التحقق مرة واحدة ويحفظ الجلسة.

### الأوامر داخل تيليجرام
- `/ai سؤالك` — يسأل الذكاء
- `/ai` (رد على رسالة) — يحلل الرسالة
- `/clear` — يمسح سياق المحادثة
- `/start` — مساعدة

### على Railway (خدمة ثانية)
أضف Service جديد من نفس الريبو:
- Start Command: `python telegram_bot.py`
- Variables: TG_API_ID, TG_API_HASH, GROQ_API_KEY
- أول تشغيل يحتاج تفاعل (رقم + كود) — الأفضل تشغّله محلي مرة ثم ترفع ملف الجلسة، أو استخدم حساب بوت عادي لاحقاً.
