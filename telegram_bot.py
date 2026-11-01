#!/usr/bin/env python3
"""
Telegram Bot (Bot API) — put BOT_TOKEN + GROQ key in Railway vars.
Users talk to the bot with /ai
"""

import os
import time
import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
# optional overrides
API_ID = os.environ.get("TG_API_ID", "")
API_HASH = os.environ.get("TG_API_HASH", "")

GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_BASE = "https://api.groq.com/openai/v1"
OR_BASE = "https://openrouter.ai/api/v1"

# chat_id -> list of messages
HISTORY = {}
OFFSET = 0


def ask_ai(question: str, history: list) -> str:
    key = GROQ_KEY or OPENROUTER_KEY
    if not key:
        return "مفتاح الذكاء غير موجود في المتغيرات (GROQ_API_KEY)"

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
        "content": "You are a helpful assistant on Telegram. Reply in the user's language. Be concise. Put code in ``` fences.",
    }
    msgs = [system] + history[-10:] + [{"role": "user", "content": question}]
    payload = {"model": model, "messages": msgs, "temperature": 0.7, "max_tokens": 1200}

    try:
        r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200 and GROQ_KEY:
            payload["model"] = "qwen/qwen3.8-27b"
            r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            return f"خطأ AI: {r.status_code} — {r.text[:120]}"
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"خطأ: {e}"


def api(method, **params):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    r = requests.post(url, json=params, timeout=30)
    return r.json()


def send(chat_id, text, reply_to=None):
    if len(text) > 4000:
        text = text[:4000] + "\n\n...[مقصوص]"
    payload = {"chat_id": chat_id, "text": text}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    api("sendMessage", **payload)


def handle(update):
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    mid = msg.get("message_id")

    if text.startswith("/start") or text.startswith("/help"):
        send(chat_id,
             "بوت الذكاء الاصطناعي\n\n"
             "الأوامر:\n"
             "/ai سؤالك — اسأل أي شيء\n"
             "/ai (رد على رسالة) — يحلل الرسالة\n"
             "/clear — مسح السياق\n"
             "/id — رقم الشات")
        return

    if text.startswith("/id"):
        send(chat_id, f"chat_id: {chat_id}")
        return

    if text.startswith("/clear"):
        HISTORY.pop(chat_id, None)
        send(chat_id, "تم مسح السياق")
        return

    if text.startswith("/ai"):
        question = text[3:].strip()
        # reply to message?
        if not question and msg.get("reply_to_message"):
            question = (msg["reply_to_message"].get("text") or "").strip()
        if not question:
            send(chat_id, "استخدم:\n/ai سؤالك هنا\nأو رد على رسالة واكتب /ai", reply_to=mid)
            return

        hist = HISTORY.setdefault(chat_id, [])
        send(chat_id, "يفكر...", reply_to=mid)
        answer = ask_ai(question, hist)
        hist.append({"role": "user", "content": question})
        hist.append({"role": "assistant", "content": answer})
        if len(hist) > 20:
            HISTORY[chat_id] = hist[-20:]
        send(chat_id, answer, reply_to=mid)
        return


def main():
    global OFFSET
    if not BOT_TOKEN:
        print("ضع BOT_TOKEN من @BotFather في متغيرات Railway")
        return
    if not (GROQ_KEY or OPENROUTER_KEY):
        print("ضع GROQ_API_KEY أو OPENROUTER_API_KEY")
        return

    me = api("getMe")
    if not me.get("ok"):
        print("توكن البوت غير صالح:", me)
        return
    print("bot:", me["result"].get("username"), "— polling...")

    while True:
        try:
            data = api("getUpdates", offset=OFFSET, timeout=30)
            if not data.get("ok"):
                time.sleep(3)
                continue
            for upd in data.get("result", []):
                OFFSET = upd["update_id"] + 1
                try:
                    handle(upd)
                except Exception as e:
                    print("handle error:", e)
        except Exception as e:
            print("poll error:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
