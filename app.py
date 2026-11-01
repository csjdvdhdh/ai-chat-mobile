#!/usr/bin/env python3
"""
AI Chat + Telegram account bridge — better web UI, login from site.
"""

import os, uuid, asyncio, requests, traceback
from flask import Flask, request, jsonify, render_template_string, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ai-bridge-secret")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
API_ID = int(os.environ.get("TG_API_ID", "0") or 0)
API_HASH = os.environ.get("TG_API_HASH", "").strip()
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
SESSION_STR = os.environ.get("TG_SESSION", "").strip()
PUBLIC_URL = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "") or os.environ.get("PUBLIC_URL", "")

WEB_SESSIONS = {}
TG_HISTORY = {}
LOGIN_STATE = {}  # sid -> telethon state
_loop = None

def get_loop():
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
    return _loop

def run_async(coro):
    return get_loop().run_until_complete(coro)

def ask_ai(question, history):
    key = GROQ_KEY or OPENROUTER_KEY
    if not key:
        return "أضف GROQ_API_KEY في Railway Variables"
    if GROQ_KEY:
        base, model = "https://api.groq.com/openai/v1", "openai/gpt-oss-20b"
        headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    else:
        base, model = "https://openrouter.ai/api/v1", "openrouter/auto"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/csjdvdhdh/ai-chat-mobile",
            "X-Title": "AI Chat",
        }
    msgs = [{"role": "system", "content": "Helpful assistant. Same language as user. Concise. Code in ``` fences."}]
    msgs += history[-12:] + [{"role": "user", "content": question}]
    payload = {"model": model, "messages": msgs, "temperature": 0.7, "max_tokens": 1500}
    try:
        r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200 and GROQ_KEY:
            payload["model"] = "qwen/qwen3.8-27b"
            r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            return f"خطأ {r.status_code}: {r.text[:150]}"
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"خطأ: {e}"

def tg(method, **params):
    if not BOT_TOKEN:
        return {}
    return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=params, timeout=30).json()

def tsend(chat_id, text):
    tg("sendMessage", chat_id=chat_id, text=(text or "")[:4000])

# ---- Telethon helpers ----
async def tg_send_code(phone):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    res = await client.send_code_request(phone)
    return client, res.phone_code_hash

async def tg_sign_in(client, phone, code, pch, password=None):
    from telethon.errors import SessionPasswordNeededError
    try:
        if password is not None:
            await client.sign_in(password=password)
        else:
            await client.sign_in(phone, code, phone_code_hash=pch)
        return client.session.save(), None
    except SessionPasswordNeededError:
        return None, "2fa"
    except Exception as e:
        return None, str(e)

# ---- Web UI ----
PAGE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="theme-color" content="#0b0b12">
<title>AI Chat</title>
<style>
:root{--bg:#0b0b12;--card:#14141f;--line:#2a2a3a;--acc:#6c5ce7;--txt:#eee;--mut:#888}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--txt);min-height:100dvh}
.wrap{max-width:720px;margin:0 auto;min-height:100dvh;display:flex;flex-direction:column}
nav{display:flex;gap:4px;padding:10px 12px;background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}
nav button{flex:1;background:transparent;border:none;color:var(--mut);padding:10px;border-radius:10px;font-size:14px;cursor:pointer}
nav button.on{background:var(--acc);color:#fff}
.panel{display:none;flex:1;flex-direction:column;min-height:0}
.panel.on{display:flex}
/* chat */
#msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}
.row{display:flex;flex-direction:column;max-width:88%}
.row.me{align-self:flex-start}.row.ai{align-self:flex-end}
.bub{padding:11px 14px;border-radius:16px;line-height:1.5;font-size:14.5px;white-space:pre-wrap;word-break:break-word}
.row.me .bub{background:var(--acc);border-bottom-right-radius:4px}
.row.ai .bub{background:var(--card);border:1px solid var(--line);border-bottom-left-radius:4px}
.bub pre{background:#0a0a10;border:1px solid var(--line);border-radius:10px;padding:10px;margin:8px 0;overflow-x:auto;direction:ltr;text-align:left;font-family:ui-monospace,monospace;font-size:12.5px;position:relative}
.bub code{font-family:ui-monospace,monospace;font-size:12.5px}
.copyc{position:absolute;top:6px;right:6px;background:#2a2a3a;border:none;color:#ccc;border-radius:6px;padding:3px 8px;font-size:11px;cursor:pointer}
.sys{align-self:center;color:var(--mut);font-size:12px}
.bar{padding:10px 12px 16px;background:var(--card);border-top:1px solid var(--line);display:flex;gap:8px}
.bar input{flex:1;background:var(--bg);border:1px solid var(--line);border-radius:22px;padding:12px 16px;color:var(--txt);font-size:15px;outline:none}
.bar button{width:48px;height:48px;border-radius:50%;border:none;background:var(--acc);color:#fff;font-size:18px;cursor:pointer}
/* link panel */
.box{padding:20px 16px;display:flex;flex-direction:column;gap:12px}
.box h2{font-size:18px}
.box p{color:var(--mut);font-size:13px;line-height:1.5}
.box input,.box button.primary{width:100%;padding:14px;border-radius:12px;border:1px solid var(--line);background:var(--bg);color:var(--txt);font-size:15px}
.box button.primary{background:var(--acc);border:none;color:#fff;font-weight:600;cursor:pointer}
.box .hint{font-size:12px;color:var(--mut);background:var(--card);padding:10px;border-radius:10px;border:1px solid var(--line);word-break:break-all}
.ok{color:#2ecc71}.err{color:#e74c3c}
.status{font-size:13px;padding:8px 0}
</style>
</head>
<body>
<div class="wrap">
<nav>
  <button class="on" data-p="chat">محادثة</button>
  <button data-p="link">ربط تيليجرام</button>
  <button data-p="info">حالة</button>
</nav>

<section id="chat" class="panel on">
  <div id="msgs"><div class="sys">مرحبا — اكتب سؤالك</div></div>
  <div class="bar">
    <input id="inp" placeholder="اكتب رسالة..." autocomplete="off">
    <button id="send">➤</button>
  </div>
</section>

<section id="link" class="panel">
  <div class="box">
    <h2>ربط حساب تيليجرام</h2>
    <p>أدخل رقمك → استلم الكود على تيليجرام → أدخله هنا. بعدها تنسخ TG_SESSION إلى Railway.</p>
    <div id="lstep1">
      <input id="phone" type="tel" placeholder="+9639xxxxxxx">
      <button class="primary" id="btnPhone">إرسال الكود</button>
    </div>
    <div id="lstep2" style="display:none">
      <input id="code" type="text" placeholder="كود التحقق">
      <button class="primary" id="btnCode">تأكيد الكود</button>
    </div>
    <div id="lstep3" style="display:none">
      <input id="pw" type="password" placeholder="كلمة مرور 2FA">
      <button class="primary" id="btnPw">تأكيد</button>
    </div>
    <div id="lmsg" class="status"></div>
    <div id="lsession" class="hint" style="display:none"></div>
  </div>
</section>

<section id="info" class="panel">
  <div class="box">
    <h2>حالة الخدمة</h2>
    <div id="health" class="hint">جاري الفحص...</div>
    <p style="margin-top:12px">بعد ما يطلع TG_SESSION فوق، حطه Variable في Railway باسم <b>TG_SESSION</b> ثم Redeploy.</p>
    <p>من حسابك في تيليجرام اكتب <b>/ai سؤالك</b> في أي محادثة (بعد الربط).</p>
  </div>
</section>
</div>
<script>
const msgs=document.getElementById('msgs'),inp=document.getElementById('inp');
document.querySelectorAll('nav button').forEach(b=>{
  b.onclick=()=>{
    document.querySelectorAll('nav button').forEach(x=>x.classList.remove('on'));
    document.querySelectorAll('.panel').forEach(x=>x.classList.remove('on'));
    b.classList.add('on');
    document.getElementById(b.dataset.p).classList.add('on');
    if(b.dataset.p==='info') loadHealth();
  };
});
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function fmt(t){
  let o='';const p=t.split(/```/);
  for(let i=0;i<p.length;i++){
    if(i%2){let c=p[i].replace(/^[a-zA-Z0-9_+-]*\n/,'');const id='c'+Math.random().toString(36).slice(2,7);
      o+=`<pre><button class="copyc" data-id="${id}">نسخ</button><code id="${id}">${esc(c.trim())}</code></pre>`;}
    else o+=esc(p[i]).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  }return o;
}
function add(role,text){
  if(role==='sys'){const d=document.createElement('div');d.className='sys';d.textContent=text;msgs.appendChild(d)}
  else{const r=document.createElement('div');r.className='row '+(role==='me'?'me':'ai');
    const b=document.createElement('div');b.className='bub';
    if(role==='ai'){b.innerHTML=fmt(text);b.querySelectorAll('.copyc').forEach(btn=>{
      btn.onclick=()=>{navigator.clipboard.writeText(document.getElementById(btn.dataset.id).innerText);btn.textContent='✓';setTimeout(()=>btn.textContent='نسخ',1000)};
    })}else b.textContent=text;
    r.appendChild(b);msgs.appendChild(r)}
  msgs.scrollTop=1e9;
}
async function send(){
  const t=inp.value.trim();if(!t)return;inp.value='';add('me',t);
  const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:t})});
  const j=await r.json();add('ai',j.reply||j.error||'?');
}
document.getElementById('send').onclick=send;
inp.onkeydown=e=>{if(e.key==='Enter')send()};

const lmsg=document.getElementById('lmsg');
function setMsg(t,ok){lmsg.textContent=t;lmsg.className='status '+(ok?'ok':'err')}
document.getElementById('btnPhone').onclick=async()=>{
  const phone=document.getElementById('phone').value.trim();
  if(!phone.startsWith('+')){setMsg('الرقم يبدأ بـ +');return}
  setMsg('جاري إرسال الكود...');
  const r=await fetch('/api/login/phone',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone})});
  const j=await r.json();
  if(j.error){setMsg(j.error);return}
  setMsg('تم إرسال الكود — أدخله تحت',true);
  document.getElementById('lstep1').style.display='none';
  document.getElementById('lstep2').style.display='block';
};
document.getElementById('btnCode').onclick=async()=>{
  const code=document.getElementById('code').value.trim();
  setMsg('جاري التحقق...');
  const r=await fetch('/api/login/code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});
  const j=await r.json();
  if(j.need_2fa){setMsg('أدخل كلمة مرور 2FA',true);document.getElementById('lstep2').style.display='none';document.getElementById('lstep3').style.display='block';return}
  if(j.error){setMsg(j.error);return}
  setMsg('تم الربط ✓ انسخ TG_SESSION',true);
  document.getElementById('lstep2').style.display='none';
  const box=document.getElementById('lsession');box.style.display='block';box.textContent=j.session;
};
document.getElementById('btnPw').onclick=async()=>{
  const password=document.getElementById('pw').value;
  setMsg('جاري...');
  const r=await fetch('/api/login/2fa',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
  const j=await r.json();
  if(j.error){setMsg(j.error);return}
  setMsg('تم الربط ✓',true);
  document.getElementById('lstep3').style.display='none';
  const box=document.getElementById('lsession');box.style.display='block';box.textContent=j.session;
};
async function loadHealth(){
  const r=await fetch('/health');const j=await r.json();
  document.getElementById('health').textContent=
    `BOT_TOKEN: ${j.bot?'✓':'✗'}\nTG_API_ID: ${j.api_id?'✓':'✗'}\nGROQ: ${j.groq?'✓':'✗'}\nTG_SESSION: ${j.session?'✓':'✗'}`;
}
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(PAGE)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "فارغ"}), 400
    sid = session.get("sid") or str(uuid.uuid4())
    session["sid"] = sid
    hist = WEB_SESSIONS.setdefault(sid, [])
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
        WEB_SESSIONS[sid] = []
    return jsonify({"ok": True})

@app.route("/api/login/phone", methods=["POST"])
def login_phone():
    if not API_ID or not API_HASH:
        return jsonify({"error": "TG_API_ID / TG_API_HASH ناقصين"}), 400
    data = request.get_json(force=True) or {}
    phone = (data.get("phone") or "").replace(" ", "")
    if not phone.startswith("+"):
        return jsonify({"error": "الرقم يبدأ بـ +"}), 400
    sid = session.get("sid") or str(uuid.uuid4())
    session["sid"] = sid
    try:
        client, pch = run_async(tg_send_code(phone))
        LOGIN_STATE[sid] = {"client": client, "phone": phone, "pch": pch}
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/login/code", methods=["POST"])
def login_code():
    sid = session.get("sid")
    st = LOGIN_STATE.get(sid)
    if not st:
        return jsonify({"error": "ابدأ بإدخال الرقم أولاً"}), 400
    data = request.get_json(force=True) or {}
    code = (data.get("code") or "").strip()
    try:
        session_str, err = run_async(tg_sign_in(st["client"], st["phone"], code, st["pch"]))
        if err == "2fa":
            st["need_2fa"] = True
            return jsonify({"need_2fa": True})
        if err:
            return jsonify({"error": err}), 400
        LOGIN_STATE.pop(sid, None)
        return jsonify({"session": session_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/login/2fa", methods=["POST"])
def login_2fa():
    sid = session.get("sid")
    st = LOGIN_STATE.get(sid)
    if not st:
        return jsonify({"error": "ابدأ من جديد"}), 400
    data = request.get_json(force=True) or {}
    password = data.get("password") or ""
    try:
        session_str, err = run_async(tg_sign_in(st["client"], st["phone"], None, None, password=password))
        if err:
            return jsonify({"error": err}), 400
        LOGIN_STATE.pop(sid, None)
        return jsonify({"session": session_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Telegram webhook still available
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json(force=True, silent=True) or {}
    msg = data.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat_id = (msg.get("chat") or {}).get("id")
    if not chat_id:
        return jsonify({"ok": True})
    if text.startswith("/start"):
        tsend(chat_id, "استخدم الموقع لربط الحساب.\nمن حسابك بعد الربط: /ai سؤالك")
    elif text.startswith("/ai"):
        q = text[3:].strip()
        if q:
            hist = TG_HISTORY.setdefault(chat_id, [])
            ans = ask_ai(q, hist)
            hist.append({"role": "user", "content": q})
            hist.append({"role": "assistant", "content": ans})
            tsend(chat_id, ans)
    return jsonify({"ok": True})

@app.route("/setup_webhook")
def setup_webhook():
    url = request.args.get("url") or (f"https://{PUBLIC_URL}" if PUBLIC_URL else "")
    if not url:
        return "؟url=https://xxx.up.railway.app", 400
    return jsonify(tg("setWebhook", url=url.rstrip("/") + "/telegram"))

@app.route("/health")
def health():
    return jsonify({
        "bot": bool(BOT_TOKEN),
        "api_id": bool(API_ID and API_HASH),
        "groq": bool(GROQ_KEY or OPENROUTER_KEY),
        "session": bool(SESSION_STR),
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
