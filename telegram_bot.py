#!/usr/bin/env python3
"""
Userbot bridge: your Telegram account <-> AI
Login once with phone + code (or set TG_SESSION string).
In any chat type:  /ai سؤال
Or reply to a message with /ai
"""

import os
import asyncio
import requests
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

API_ID = int(os.environ.get("TG_API_ID", "0") or 0)
API_HASH = os.environ.get("TG_API_HASH", "").strip()
PHONE = os.environ.get("TG_PHONE", "").strip()          # e.g. +9639xxxxxxx
SESSION_STR = os.environ.get("TG_SESSION", "").strip()  # after first login
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

GROQ_MODEL = "openai/gpt-oss-20b"
HISTORY = {}  # chat_id -> messages


def ask_ai(question, history):
    key = GROQ_KEY or OPENROUTER_KEY
    if not key:
        return "ضع GROQ_API_KEY في المتغيرات"

    if GROQ_KEY:
        base, model = "https://api.groq.com/openai/v1", GROQ_MODEL
        headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    else:
        base, model = "https://openrouter.ai/api/v1", "openrouter/auto"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/csjdvdhdh/ai-chat-mobile",
            "X-Title": "TG Userbot AI",
        }

    system = {"role": "system", "content": "Helpful assistant on Telegram. Same language as user. Concise. Code in ``` fences."}
    msgs = [system] + history[-10:] + [{"role": "user", "content": question}]
    payload = {"model": model, "messages": msgs, "temperature": 0.7, "max_tokens": 1200}

    try:
        r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200 and GROQ_KEY:
            payload["model"] = "qwen/qwen3.8-27b"
            r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            return f"AI error {r.status_code}: {r.text[:120]}"
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"error: {e}"


async def main():
    if not API_ID or not API_HASH:
        print("Variables needed: TG_API_ID, TG_API_HASH from https://my.telegram.org")
        return
    if not (GROQ_KEY or OPENROUTER_KEY):
        print("Variables needed: GROQ_API_KEY")
        return

    if SESSION_STR:
        client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    else:
        client = TelegramClient("ai_userbot", API_ID, API_HASH)

    await client.connect()

    if not await client.is_user_authorized():
        if not PHONE:
            print("Set TG_PHONE=+96xxxxxxx for first login, or set TG_SESSION after login")
            return
        print(f"sending code to {PHONE}...")
        await client.send_code_request(PHONE)
        # In Railway there is no interactive input — user must set TG_LOGIN_CODE then restart once
        code = os.environ.get("TG_LOGIN_CODE", "").strip()
        if not code:
            print("CODE SENT. Put the code in variable TG_LOGIN_CODE and redeploy once.")
            await client.disconnect()
            return
        try:
            await client.sign_in(PHONE, code)
        except SessionPasswordNeededError:
            pw = os.environ.get("TG_2FA_PASSWORD", "").strip()
            if not pw:
                print("2FA needed — set TG_2FA_PASSWORD and redeploy")
                await client.disconnect()
                return
            await client.sign_in(password=pw)

        # print session string so user can save it
        s = StringSession.save(client.session)
        print("SAVE THIS AS TG_SESSION (then remove TG_LOGIN_CODE):")
        print(s)

    me = await client.get_me()
    print(f"linked account: {me.first_name} (@{me.username}) id={me.id}")
    print("ready — type /ai in any chat from THIS account")

    @client.on(events.NewMessage(outgoing=True, pattern=r"(?i)^/ai(?:\s+|$)([\s\S]*)"))
    async def on_ai(event):
        question = (event.pattern_match.group(1) or "").strip()
        if not question and event.is_reply:
            rm = await event.get_reply_message()
            question = (rm.text or "").strip()
        if not question:
            await event.reply("استخدم: /ai سؤالك\nأو رد على رسالة بـ /ai")
            return

        chat_id = event.chat_id
        hist = HISTORY.setdefault(chat_id, [])
        status = await event.reply("يفكر...")
        answer = await asyncio.get_event_loop().run_in_executor(None, ask_ai, question, hist)
        hist.append({"role": "user", "content": question})
        hist.append({"role": "assistant", "content": answer})
        if len(hist) > 20:
            HISTORY[chat_id] = hist[-20:]
        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n..."
        await status.edit(answer)

    @client.on(events.NewMessage(outgoing=True, pattern=r"(?i)^/clear$"))
    async def on_clear(event):
        HISTORY.pop(event.chat_id, None)
        await event.reply("تم مسح السياق")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
