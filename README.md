# AI Chat Mobile

تطبيق محادثة ذكاء اصطناعي للجوال (PWA) يعمل على Railway.

## المميزات
- واجهة موبايل كاملة
- تبديل نماذج مجانية بدون ضياع السياق
- Groq + OpenRouter (مفاتيح مجانية)
- يُرفع على Railway بضغطة

## ربط Railway
1. ادخل https://railway.com
2. New Project → Deploy from GitHub repo
3. اختر `csjdvdhdh/ai-chat-mobile`
4. أضف Variables:
   - GROQ_API_KEY (من console.groq.com)
   - OPENROUTER_API_KEY (اختياري)
5. Generate Domain → افتح الرابط على هاتفك

## تشغيل محلي
```bash
pip install -r requirements.txt
python app.py
```
