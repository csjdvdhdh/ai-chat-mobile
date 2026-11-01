#!/usr/bin/env python3
"""
Telegram Bot only — no personal account login.
Set BOT_TOKEN from @BotFather + GROQ_API_KEY in Railway.
Anyone can message the bot and use /ai
"""

import os
import time
import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

GROQ_MODEL = "openai/gpt-oss-20b"
HISTORY = {}
OFFSET = 0


def ask_ai(question, history):
    key = GROQ_KEY or OPENROUTER_KEY
    if not key:
        return "ضع GROQ_API_KEY في متغيرات Railway"

    if GROQ_KEY:
        base, model = "https://api.groq.com/openai/v1", GROQ_MODEL
        headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    else:
        base, model = "https://openrouter.ai/api/v1", "openrouter/auto"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/csjdvdhdh/ai-chat-mobile",
            "X-Title": "TG AI Bot",
        }

    system = {
        "role": "system",
        "content": "Helpful assistant on Telegram. Reply in the user's language. Concise. Code in ``` fences.",
    }
    msgs = [system] + history[-10:] + [{"role": "user", "content": question}]
    payload = {"model": model, "messages": msgs, "temperature": 0.7, "max_tokens": 1200}

    try:
        r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200 and GROQ_KEY:
            payload["model"] = "qwen/qwen3.8-27b"
            r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            return f"خطأ AI {r.status_code}: {r.text[:120]}"
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"خطأ: {e}"


def tg(method, **params):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    return requests.post(url, json=params, timeout=35).json()


def send(chat_id, text, reply_to=None):
    if len(text) > 4000:
        text = text[:4000] + "\n\n..."
    p = {"chat_id": chat_id, "text": text}
    if reply_to:
        p["reply_to_message_id"] = reply_to
    tg("sendMessage", **p)


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
             "/ai سؤالك — اسأل\n"
             "/ai (رد على رسالة) — يحللها\n"
             "/clear — مسح السياق")
        return

    if text.startswith("/clear"):
        HISTORY.pop(chat_id, None)
        send(chat_id, "تم مسح السياق")
        return

    if text.startswith("/ai"):
        q = text[3:].strip()
        if not q and msg.get("reply_to_message"):
            q = (msg["reply_to_message"].get("text") or "").strip()
        if not q:
            send(chat_id, "اكتب:\n/ai سؤالك\nأو رد على رسالة بـ /ai", reply_to=mid)
            return
        hist = HISTORY.setdefault(chat_id, [])
        send(chat_id, "يفكر...", reply_to=mid)
        ans = ask_ai(q, hist)
        hist.append({"role": "user", "content": q})
        hist.append({"role": "assistant", "content": ans})
        if len(hist) > 20:
            HISTORY[chat_id] = hist[-20:]
        send(chat_id, ans, reply_to=mid)
        return


def main():
    global OFFSET
    if not BOT_TOKEN:
        print("ضع BOT_TOKEN من @BotFather")
        return
    if not (GROQ_KEY or OPENROUTER_KEY):
        print("ضع GROQ_API_KEY")
        return

    me = tg("getMe")
    if not me.get("ok"):
        print("توكن غير صالح:", me)
        return
    print("bot @" + str(me["result"].get("username")) + " running")

    while True:
        try:
            data = tg("getUpdates", offset=OFFSET, timeout=30)
            if not data.get("ok"):
                time.sleep(2)
                continue
            for u in data.get("result", []):
                OFFSET = u["update_id"] + 1
                try:
                    handle(u)
                except Exception as e:
                    print("err", e)
        except Exception as e:
            print("poll", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
