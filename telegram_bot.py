#!/usr/bin/env python3
"""
Telegram AI Bot — login with phone+code, reply to /ai questions
Uses same GROQ / OpenRouter keys as the web app.
"""

import os
import asyncio
import json
from pathlib import Path

try:
    from telethon import TelegramClient, events
    from telethon.errors import SessionPasswordNeededError
    import requests
except ImportError:
    print("pip install telethon requests")
    raise SystemExit(1)

# --- config from env (set in Railway) ---
API_ID = int(os.environ.get("TG_API_ID", "0") or 0)
API_HASH = os.environ.get("TG_API_HASH", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
SESSION = os.environ.get("TG_SESSION", "ai_bot_session")

# free models
GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_BASE = "https://api.groq.com/openai/v1"
OR_BASE = "https://openrouter.ai/api/v1"

def ask_ai(question: str, history: list) -> str:
    key = GROQ_KEY or OPENROUTER_KEY
    if not key:
        return "مفتاح الذكاء غير موجود (GROQ_API_KEY أو OPENROUTER_API_KEY)"

    if GROQ_KEY:
        base, model = GROQ_BASE, GROQ_MODEL
        headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    else:
        base, model = OR_BASE, "openrouter/auto"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/csjdvdhdh/ai-chat-mobile",
            "X-Title": "TG AI Bot",
        }

    system = {
        "role": "system",
        "content": "You are a helpful assistant inside Telegram. Reply in the same language as the user. Be concise. Put code in markdown fences.",
    }
    msgs = [system] + history[-12:] + [{"role": "user", "content": question}]
    payload = {"model": model, "messages": msgs, "temperature": 0.7, "max_tokens": 1200}

    try:
        r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200 and GROQ_KEY:
            payload["model"] = "qwen/qwen3.8-27b"
            r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            return f"خطأ AI: {r.status_code} {r.text[:150]}"
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"خطأ: {e}"


# per-chat history (in memory)
CHAT_HISTORY = {}

client = TelegramClient(SESSION, API_ID, API_HASH)


@client.on(events.NewMessage(pattern=r"(?i)^/ai(?:\s+|$)(.*)"))
async def ai_handler(event):
    question = (event.pattern_match.group(1) or "").strip()
    if not question:
        # reply to a message?
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            question = (reply_msg.text or "").strip()
        if not question:
            await event.reply("استخدم: `/ai سؤالك هنا`\nأو رد على رسالة بـ `/ai`")
            return

    chat_id = event.chat_id
    hist = CHAT_HISTORY.setdefault(chat_id, [])

    await event.reply("يفكر...")
    answer = await asyncio.get_event_loop().run_in_executor(None, ask_ai, question, hist)

    hist.append({"role": "user", "content": question})
    hist.append({"role": "assistant", "content": answer})
    if len(hist) > 20:
        CHAT_HISTORY[chat_id] = hist[-20:]

    # Telegram message limit ~4096
    if len(answer) > 4000:
        answer = answer[:4000] + "\n\n...[مقصوص]"
    await event.reply(answer)


@client.on(events.NewMessage(pattern=r"(?i)^/(start|help)$"))
async def start_handler(event):
    await event.reply(
        "بوت الذكاء الاصطناعي\n\n"
        "الأوامر:\n"
        "`/ai سؤالك` — اسأل أي شيء\n"
        "`/ai` (رد على رسالة) — يحلل الرسالة\n"
        "`/clear` — مسح سياق هذه المحادثة\n"
    )


@client.on(events.NewMessage(pattern=r"(?i)^/clear$"))
async def clear_handler(event):
    CHAT_HISTORY.pop(event.chat_id, None)
    await event.reply("تم مسح السياق لهذه المحادثة")


async def main():
    if not API_ID or not API_HASH:
        print("ضع TG_API_ID و TG_API_HASH في المتغيرات")
        print("من https://my.telegram.org")
        return
    if not (GROQ_KEY or OPENROUTER_KEY):
        print("ضع GROQ_API_KEY أو OPENROUTER_API_KEY")
        return

    print("connecting...")
    await client.start()
    me = await client.get_me()
    print(f"logged in as {me.first_name} (@{me.username})")
    print("bot ready — send /ai in any chat")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
