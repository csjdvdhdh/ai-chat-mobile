#!/usr/bin/env python3
"""
جسر: حسابك تيليجرام ↔ ذكاء اصطناعي على Railway
يسجل دخول بحسابك (رقم + كود) مرة واحدة ثم يربط.
من حسابك اكتب /ai في أي شات.
"""

import os
import asyncio
import requests
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

API_ID = int(os.environ.get("TG_API_ID", "0") or 0)
API_HASH = os.environ.get("TG_API_HASH", "").strip()
PHONE = os.environ.get("TG_PHONE", "").strip()
CODE = os.environ.get("TG_LOGIN_CODE", "").strip()
PASSWORD = os.environ.get("TG_2FA_PASSWORD", "").strip()
SESSION = os.environ.get("TG_SESSION", "").strip()
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

HISTORY = {}


def ask_ai(q, hist):
    key = GROQ_KEY or OPENROUTER_KEY
    if not key:
        return "GROQ_API_KEY ناقص"
    if GROQ_KEY:
        base, model = "https://api.groq.com/openai/v1", "openai/gpt-oss-20b"
        headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    else:
        base, model = "https://openrouter.ai/api/v1", "openrouter/auto"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/csjdvdhdh/ai-chat-mobile",
            "X-Title": "AI Bridge",
        }
    msgs = [{"role": "system", "content": "Assistant on Telegram. Same language as user. Concise. Code in ```."}]
    msgs += hist[-10:]
    msgs.append({"role": "user", "content": q})
    payload = {"model": model, "messages": msgs, "temperature": 0.7, "max_tokens": 1200}
    try:
        r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200 and GROQ_KEY:
            payload["model"] = "qwen/qwen3.8-27b"
            r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            return f"AI {r.status_code}: {r.text[:100]}"
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return str(e)


async def main():
    if not API_ID or not API_HASH:
        print("محتاج: TG_API_ID + TG_API_HASH من my.telegram.org")
        return
    if not (GROQ_KEY or OPENROUTER_KEY):
        print("محتاج: GROQ_API_KEY")
        return

    if SESSION:
        client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    else:
        client = TelegramClient(StringSession(), API_ID, API_HASH)

    await client.connect()

    if not await client.is_user_authorized():
        if not PHONE:
            print("حط TG_PHONE=+96xxxxxxx ثم أعد التشغيل")
            return
        print("إرسال كود إلى", PHONE)
        await client.send_code_request(PHONE)
        if not CODE:
            print(">>> الكود وصل على تيليجرام")
            print(">>> حط المتغير TG_LOGIN_CODE=الكود ثم Redeploy")
            await asyncio.sleep(3600)
            return
        try:
            await client.sign_in(PHONE, CODE)
        except SessionPasswordNeededError:
            if not PASSWORD:
                print(">>> حسابك فيه تحقق بخطوتين — حط TG_2FA_PASSWORD ثم Redeploy")
                await asyncio.sleep(3600)
                return
            await client.sign_in(password=PASSWORD)

        s = client.session.save()
        print("=" * 40)
        print("انسخ هذا المتغير TG_SESSION=")
        print(s)
        print("=" * 40)
        print("بعدها امسح TG_LOGIN_CODE و Redeploy")

    me = await client.get_me()
    print("تم الربط بحسابك:", me.first_name, me.id)
    print("من حسابك اكتب /ai في أي محادثة")

    @client.on(events.NewMessage(outgoing=True, pattern=r"(?i)^/ai(?:\s+|$)([\s\S]*)"))
    async def ai_cmd(event):
        q = (event.pattern_match.group(1) or "").strip()
        if not q and event.is_reply:
            rm = await event.get_reply_message()
            q = (rm.text or "").strip()
        if not q:
            await event.reply("/ai سؤالك\nأو رد على رسالة بـ /ai")
            return
        hist = HISTORY.setdefault(event.chat_id, [])
        st = await event.reply("...")
        ans = await asyncio.get_event_loop().run_in_executor(None, ask_ai, q, hist)
        hist.append({"role": "user", "content": q})
        hist.append({"role": "assistant", "content": ans})
        if len(hist) > 20:
            HISTORY[event.chat_id] = hist[-20:]
        await st.edit(ans[:4000])

    @client.on(events.NewMessage(outgoing=True, pattern=r"(?i)^/clear$"))
    async def clear_cmd(event):
        HISTORY.pop(event.chat_id, None)
        await event.reply("تم المسح")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
