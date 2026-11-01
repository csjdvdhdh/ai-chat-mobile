#!/usr/bin/env python3
"""
Web app + Telegram bot bridge in ONE service (Railway).
Webhook on /telegram
Login via bot messages: /login → phone → code → (2fa) → TG_SESSION
"""

import os, uuid, asyncio, requests, base64 as b64
from flask import Flask, request, jsonify, render_template_string, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ai-bridge-secret")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
API_ID = int(os.environ.get("TG_API_ID", "0") or 0)
API_HASH = os.environ.get("TG_API_HASH", "").strip()
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
SESSION_STR = os.environ.get("TG_SESSION", "").strip()
PUBLIC_URL = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "") or os.environ.get("PUBLIC_URL", "")

SESSIONS = {}       # web chat sessions
HISTORY = {}        # telegram chat history
LOGIN = {}          # bot login state
user_client = None
_loop = None

# ---------- AI ----------
def ask_ai(question, history):
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
    msgs = [{"role": "system", "content": "Assistant. Same language as user. Concise. Code in ``` fences."}]
    msgs += history[-10:] + [{"role": "user", "content": question}]
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

# ---------- Telegram Bot API helpers ----------
def tg(method, **params):
    if not BOT_TOKEN:
        return {}
    return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=params, timeout=30).json()

def tsend(chat_id, text):
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    tg("sendMessage", chat_id=chat_id, text=text)

# ---------- Telethon login (lazy import) ----------
async def _telethon_send_code(phone):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    result = await client.send_code_request(phone)
    return client, result.phone_code_hash

async def _telethon_sign_in(client, phone, code, phone_code_hash, password=None):
    from telethon.errors import SessionPasswordNeededError
    try:
        if password:
            await client.sign_in(password=password)
        else:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        return client.session.save(), None
    except SessionPasswordNeededError:
        return None, "2fa"
    except Exception as e:
        return None, str(e)

def run_async(coro):
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
    return _loop.run_until_complete(coro)

# ---------- Bot message handler ----------
def handle_bot(msg):
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()

    if text.startswith("/start") or text.startswith("/help"):
        tsend(chat_id,
              "جسر حسابك ↔ الذكاء\n\n"
              "/login — ربط حسابك\n"
              "/status — حالة الربط\n"
              "/ai سؤالك — من البوت مباشرة\n\n"
              "بعد الربط: من حسابك اكتب /ai في أي شات")
        return

    if text.startswith("/status"):
        tsend(chat_id, "مرتبط ✓" if SESSION_STR or user_client else "غير مرتبط — /login")
        return

    if text.startswith("/login"):
        LOGIN[chat_id] = {"step": "phone"}
        tsend(chat_id, "أرسل رقمك مع رمز الدولة\nمثال: +9639xxxxxxx")
        return

    st = LOGIN.get(chat_id)
    if st:
        step = st.get("step")
        if step == "phone":
            phone = text.replace(" ", "")
            if not phone.startswith("+"):
                tsend(chat_id, "الرقم يبدأ بـ +")
                return
            if not API_ID or not API_HASH:
                tsend(chat_id, "TG_API_ID / TG_API_HASH ناقصين في Railway")
                return
            try:
                client, pch = run_async(_telethon_send_code(phone))
                LOGIN[chat_id] = {"step": "code", "phone": phone, "pch": pch, "client": client}
                tsend(chat_id, "تم إرسال الكود — أرسله هنا")
            except Exception as e:
                tsend(chat_id, f"فشل: {e}")
            return

        if step == "code":
            client = st["client"]
            session_str, err = run_async(_telethon_sign_in(client, st["phone"], text, st["pch"]))
            if err == "2fa":
                LOGIN[chat_id]["step"] = "2fa"
                tsend(chat_id, "أرسل كلمة مرور التحقق بخطوتين")
                return
            if err:
                tsend(chat_id, f"فشل: {err}")
                return
            LOGIN.pop(chat_id, None)
            tsend(chat_id,
                  "تم الربط ✓\n\n"
                  "انسخ السطر التالي وضعه Variable في Railway اسمه TG_SESSION ثم Redeploy:\n\n"
                  + session_str)
            return

        if step == "2fa":
            client = st["client"]
            session_str, err = run_async(_telethon_sign_in(client, st["phone"], None, None, password=text))
            if err:
                tsend(chat_id, f"فشل: {err}")
                return
            LOGIN.pop(chat_id, None)
            tsend(chat_id,
                  "تم الربط ✓\n\n"
                  "ضع هذا في Railway Variable → TG_SESSION ثم Redeploy:\n\n"
                  + session_str)
            return

    if text.startswith("/ai"):
        q = text[3:].strip()
        if not q and msg.get("reply_to_message"):
            q = (msg["reply_to_message"].get("text") or "").strip()
        if not q:
            tsend(chat_id, "/ai سؤالك")
            return
        hist = HISTORY.setdefault(chat_id, [])
        tsend(chat_id, "يفكر...")
        ans = ask_ai(q, hist)
        hist.append({"role": "user", "content": q})
        hist.append({"role": "assistant", "content": ans})
        if len(hist) > 20:
            HISTORY[chat_id] = hist[-20:]
        tsend(chat_id, ans)
        return

# ---------- Webhook ----------
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json(force=True, silent=True) or {}
    msg = data.get("message") or data.get("edited_message")
    if msg:
        try:
            handle_bot(msg)
        except Exception as e:
            print("bot err", e)
    return jsonify({"ok": True})

@app.route("/setup_webhook")
def setup_webhook():
    """Call once: /setup_webhook?url=https://your-app.up.railway.app"""
    url = request.args.get("url") or (f"https://{PUBLIC_URL}" if PUBLIC_URL else "")
    if not url:
        return "pass ?url=https://xxx.up.railway.app", 400
    hook = url.rstrip("/") + "/telegram"
    r = tg("setWebhook", url=hook)
    return jsonify(r)

# ---------- Web chat (same as before, shortened) ----------
WEB_HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>AI Chat</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui;background:#0d0d14;color:#eee;height:100dvh;display:flex;flex-direction:column}
header{background:#1a1a24;padding:12px;display:flex;justify-content:space-between;align-items:center}
header button{background:#0d0d14;color:#eee;border:1px solid #333;border-radius:8px;padding:6px 12px}
#msgs{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px}
.b{max-width:85%;padding:10px 14px;border-radius:16px;line-height:1.45;font-size:14px;white-space:pre-wrap}
.u{align-self:flex-start;background:#6c5ce7}
.a{align-self:flex-end;background:#1e1e2a}
#bar{padding:10px;background:#1a1a24;display:flex;gap:8px}
#bar input{flex:1;background:#0d0d14;border:1px solid #333;border-radius:20px;padding:12px;color:#eee}
#bar button{width:46px;height:46px;border-radius:50%;border:none;background:#6c5ce7;color:#fff}
</style></head><body>
<header><b>AI Chat</b><button onclick="clr()">محادثة جديدة</button></header>
<div id="msgs"></div>
<div id="bar"><input id="inp" placeholder="رسالة..."><button onclick="send()">➤</button></div>
<script>
const m=document.getElementById('msgs'),i=document.getElementById('inp');
function add(t,c){const d=document.createElement('div');d.className='b '+c;d.textContent=t;m.appendChild(d);m.scrollTop=1e9}
async function send(){const t=i.value.trim();if(!t)return;add(t,'u');i.value='';
const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:t})});
const j=await r.json();add(j.reply||j.error||'?','a')}
async function clr(){await fetch('/api/clear',{method:'POST'});m.innerHTML=''}
i.onkeydown=e=>{if(e.key==='Enter')send()}
</script></body></html>"""

@app.route("/")
def index():
    return render_template_string(WEB_HTML)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "فارغ"}), 400
    sid = session.get("sid") or str(uuid.uuid4())
    session["sid"] = sid
    hist = SESSIONS.setdefault(sid, [])
    hist.append({"role": "user", "content": message})
    if len(hist) > 16:
        hist[:] = hist[-16:]
    reply = ask_ai(message, hist[:-1])
    hist.append({"role": "assistant", "content": reply})
    return jsonify({"reply": reply})

@app.route("/api/clear", methods=["POST"])
def api_clear():
    sid = session.get("sid")
    if sid:
        SESSIONS[sid] = []
    return jsonify({"ok": True})

@app.route("/health")
def health():
    return jsonify({
        "bot": bool(BOT_TOKEN),
        "api_id": bool(API_ID),
        "groq": bool(GROQ_KEY or OPENROUTER_KEY),
        "session": bool(SESSION_STR),
    })

if __name__ == "__main__":
    # set webhook if domain known
    if BOT_TOKEN and PUBLIC_URL:
        hook = f"https://{PUBLIC_URL}/telegram"
        print("webhook →", tg("setWebhook", url=hook))
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
