#!/usr/bin/env python3
"""
جسر حسابك ↔ AI
التسجيل يتم عبر رسائل تيليجرام (مو Logs):
  1) تبعت رقمك للبوت
  2) تبعت الكود للبوت
  3) ينربط حسابك
بعدها /ai يشتغل من حسابك.
يحتاج BOT_TOKEN + TG_API_ID + TG_API_HASH + GROQ_API_KEY
"""

import os
import time
import asyncio
import requests
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.sessions import StringSession

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
API_ID = int(os.environ.get("TG_API_ID", "0") or 0)
API_HASH = os.environ.get("TG_API_HASH", "").strip()
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
SESSION = os.environ.get("TG_SESSION", "").strip()

# login state per bot-chat
LOGIN = {}  # bot_chat_id -> {phone, phone_code_hash, step}
HISTORY = {}
OFFSET = 0
user_client = None  # Telethon client for the linked account


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
    msgs = [{"role": "system", "content": "Assistant on Telegram. Same language. Concise. Code in ```."}]
    msgs += hist[-10:] + [{"role": "user", "content": q}]
    payload = {"model": model, "messages": msgs, "temperature": 0.7, "max_tokens": 1200}
    try:
        r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200 and GROQ_KEY:
            payload["model"] = "qwen/qwen3.8-27b"
            r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            return f"AI {r.status_code}"
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return str(e)


def tg(method, **params):
    return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=params, timeout=35).json()


def send(chat_id, text):
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    tg("sendMessage", chat_id=chat_id, text=text)


async def ensure_user_client():
    global user_client
    if user_client and await user_client.is_user_authorized():
        return user_client
    if not SESSION:
        return None
    user_client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await user_client.connect()
    if not await user_client.is_user_authorized():
        return None
    return user_client


async def start_login(bot_chat_id, phone):
    global user_client
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        result = await client.send_code_request(phone)
        LOGIN[bot_chat_id] = {
            "phone": phone,
            "phone_code_hash": result.phone_code_hash,
            "step": "code",
            "client": client,
        }
        send(bot_chat_id, f"تم إرسال الكود إلى {phone}\nأرسل الكود الآن هنا")
    except Exception as e:
        send(bot_chat_id, f"فشل إرسال الكود: {e}")
        await client.disconnect()


async def finish_login(bot_chat_id, code):
    global user_client, SESSION
    st = LOGIN.get(bot_chat_id)
    if not st or st.get("step") != "code":
        send(bot_chat_id, "أرسل /login أولاً ثم رقمك")
        return
    client = st["client"]
    try:
        await client.sign_in(st["phone"], code, phone_code_hash=st["phone_code_hash"])
    except SessionPasswordNeededError:
        LOGIN[bot_chat_id]["step"] = "2fa"
        send(bot_chat_id, "الحساب فيه تحقق بخطوتين — أرسل كلمة المرور الآن")
        return
    except PhoneCodeInvalidError:
        send(bot_chat_id, "كود غلط — أرسله مرة ثانية")
        return
    except Exception as e:
        send(bot_chat_id, f"فشل الدخول: {e}")
        return

    s = client.session.save()
    user_client = client
    me = await client.get_me()
    LOGIN.pop(bot_chat_id, None)
    send(bot_chat_id,
         f"تم ربط حسابك: {me.first_name}\n"
         f"احفظ هذا في Railway Variable اسمه TG_SESSION ثم أعد التشغيل:\n\n{s}\n\n"
         f"بعدها من حسابك اكتب /ai في أي شات")
    # keep client running for /ai
    asyncio.create_task(run_userbot(client))


async def finish_2fa(bot_chat_id, password):
    global user_client
    st = LOGIN.get(bot_chat_id)
    if not st or st.get("step") != "2fa":
        send(bot_chat_id, "أرسل /login أولاً")
        return
    client = st["client"]
    try:
        await client.sign_in(password=password)
    except Exception as e:
        send(bot_chat_id, f"كلمة المرور غلط: {e}")
        return
    s = client.session.save()
    user_client = client
    me = await client.get_me()
    LOGIN.pop(bot_chat_id, None)
    send(bot_chat_id,
         f"تم الربط: {me.first_name}\n"
         f"ضع TG_SESSION في Railway:\n\n{s}")
    asyncio.create_task(run_userbot(client))


async def run_userbot(client):
    @client.on(events.NewMessage(outgoing=True, pattern=r"(?i)^/ai(?:\s+|$)([\s\S]*)"))
    async def on_ai(event):
        q = (event.pattern_match.group(1) or "").strip()
        if not q and event.is_reply:
            rm = await event.get_reply_message()
            q = (rm.text or "").strip()
        if not q:
            await event.reply("/ai سؤالك")
            return
        hist = HISTORY.setdefault(event.chat_id, [])
        st = await event.reply("...")
        ans = await asyncio.get_event_loop().run_in_executor(None, ask_ai, q, hist)
        hist.append({"role": "user", "content": q})
        hist.append({"role": "assistant", "content": ans})
        if len(hist) > 20:
            HISTORY[event.chat_id] = hist[-20:]
        await st.edit((ans or "")[:4000])

    @client.on(events.NewMessage(outgoing=True, pattern=r"(?i)^/clear$"))
    async def on_clear(event):
        HISTORY.pop(event.chat_id, None)
        await event.reply("تم")

    print("userbot handlers ready")
    await client.run_until_disconnected()


def handle_bot_message(msg):
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()

    if text.startswith("/start") or text.startswith("/help"):
        send(chat_id,
             "جسر حسابك ↔ الذكاء\n\n"
             "1) /login\n"
             "2) أرسل رقمك مثل +9639xxxxxxx\n"
             "3) أرسل الكود اللي يوصلك\n"
             "4) انسخ TG_SESSION إلى Railway\n\n"
             "بعد الربط: من حسابك اكتب /ai")
        return

    if text.startswith("/login"):
        LOGIN[chat_id] = {"step": "phone"}
        send(chat_id, "أرسل رقمك الآن مع رمز الدولة\nمثال: +9639xxxxxxx")
        return

    if text.startswith("/status"):
        send(chat_id, "مرتبط" if (user_client) else "غير مرتبط — اكتب /login")
        return

    st = LOGIN.get(chat_id)
    if st:
        step = st.get("step")
        if step == "phone":
            phone = text.replace(" ", "")
            if not phone.startswith("+"):
                send(chat_id, "الرقم لازم يبدأ بـ +")
                return
            asyncio.get_event_loop().create_task(start_login(chat_id, phone))
            return
        if step == "code":
            asyncio.get_event_loop().create_task(finish_login(chat_id, text))
            return
        if step == "2fa":
            asyncio.get_event_loop().create_task(finish_2fa(chat_id, text))
            return

    # bot itself can also answer /ai for convenience
    if text.startswith("/ai"):
        q = text[3:].strip()
        if not q:
            send(chat_id, "/ai سؤالك")
            return
        hist = HISTORY.setdefault(chat_id, [])
        send(chat_id, "...")
        ans = ask_ai(q, hist)
        hist.append({"role": "user", "content": q})
        hist.append({"role": "assistant", "content": ans})
        send(chat_id, ans[:4000])
        return


async def poll_bot():
    global OFFSET
    me = tg("getMe")
    if not me.get("ok"):
        print("BOT_TOKEN غلط", me)
        return
    print("bot @" + str(me["result"].get("username")))

    # try existing session
    c = await ensure_user_client()
    if c:
        me2 = await c.get_me()
        print("account linked:", me2.first_name)
        asyncio.create_task(run_userbot(c))

    while True:
        try:
            data = tg("getUpdates", offset=OFFSET, timeout=25)
            if not data.get("ok"):
                await asyncio.sleep(2)
                continue
            for u in data.get("result", []):
                OFFSET = u["update_id"] + 1
                msg = u.get("message")
                if msg:
                    try:
                        handle_bot_message(msg)
                    except Exception as e:
                        print("handle", e)
        except Exception as e:
            print("poll", e)
            await asyncio.sleep(5)


def main():
    if not BOT_TOKEN:
        print("محتاج BOT_TOKEN من @BotFather")
        return
    if not API_ID or not API_HASH:
        print("محتاج TG_API_ID و TG_API_HASH من my.telegram.org")
        return
    if not (GROQ_KEY or OPENROUTER_KEY):
        print("محتاج GROQ_API_KEY")
        return
    asyncio.run(poll_bot())


if __name__ == "__main__":
    main()
