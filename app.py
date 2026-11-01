#!/usr/bin/env python3
import os, uuid, requests, re, html as htmlmod
from flask import Flask, request, jsonify, render_template_string, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-ai-chat-secret")
SESSIONS = {}

DEFAULT_MODEL = "openai/gpt-oss-20b"

HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#0d0d14">
<title>AI Chat</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{font-family:system-ui,-apple-system,sans-serif;background:#0d0d14;color:#eee;height:100dvh;display:flex;flex-direction:column;overflow:hidden}
header{background:#1a1a24;padding:12px 14px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #2a2a3a;flex-shrink:0}
header h1{font-size:16px;font-weight:600}
header .actions{display:flex;gap:8px}
header button{background:#0d0d14;color:#eee;border:1px solid #333;border-radius:8px;padding:6px 12px;font-size:13px;cursor:pointer}
header button:active{background:#2a2a3a}
#msgs{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px;-webkit-overflow-scrolling:touch}
.row{display:flex;flex-direction:column;max-width:92%}
.row.user{align-self:flex-start}
.row.bot{align-self:flex-end}
.bubble{padding:10px 14px;border-radius:16px;line-height:1.5;font-size:14.5px;word-break:break-word;white-space:pre-wrap}
.row.user .bubble{background:#6c5ce7;border-bottom-right-radius:4px}
.row.bot .bubble{background:#1e1e2a;border-bottom-left-radius:4px}
.bubble pre{background:#0d0d14;border:1px solid #333;border-radius:10px;padding:10px 12px;margin:8px 0;overflow-x:auto;direction:ltr;text-align:left;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;line-height:1.45;white-space:pre}
.bubble code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;background:#0d0d14;padding:1px 4px;border-radius:4px}
.bubble pre code{background:transparent;padding:0}
.sys{align-self:center;color:#666;font-size:12px;padding:4px}
.copy-btn{margin-top:4px;align-self:flex-start;background:transparent;border:none;color:#6c5ce7;font-size:12px;cursor:pointer;padding:2px 6px}
.copy-btn:active{opacity:.6}
#bar{padding:10px 12px 16px;background:#1a1a24;border-top:1px solid #2a2a3a;display:flex;gap:8px;flex-shrink:0}
#bar input{flex:1;background:#0d0d14;border:1px solid #333;border-radius:24px;padding:12px 16px;color:#eee;font-size:15px;outline:none}
#bar button{width:48px;height:48px;border-radius:50%;border:none;background:#6c5ce7;color:#fff;font-size:18px;cursor:pointer;flex-shrink:0}
#bar button:disabled{opacity:.5}
.typing{color:#888;font-size:13px;padding:4px 8px}
</style>
</head>
<body>
<header>
  <h1>AI Chat</h1>
  <div class="actions">
    <button id="newchat">محادثة جديدة</button>
    <button id="delchat">حذف</button>
  </div>
</header>
<div id="msgs">
  <div class="sys">مرحبا — ابدأ المحادثة</div>
</div>
<div id="bar">
  <input id="inp" type="text" placeholder="اكتب رسالة..." autocomplete="off">
  <button id="send">➤</button>
</div>
<script>
const msgs=document.getElementById('msgs');
const inp=document.getElementById('inp');
const sendBtn=document.getElementById('send');
let busy=false;

function escapeHtml(s){
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function formatMd(text){
  // code blocks ```
  let out = '';
  const parts = text.split(/```/);
  for(let i=0;i<parts.length;i++){
    if(i%2===1){
      let code = parts[i];
      // strip language tag first line
      code = code.replace(/^[a-zA-Z0-9_+-]*\n/, '');
      out += '<pre><code>'+escapeHtml(code.trim())+'</code></pre>';
    } else {
      let t = escapeHtml(parts[i]);
      // inline code
      t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
      // bold
      t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
      out += t;
    }
  }
  return out;
}

function add(role,text){
  if(role==='sys'){
    const d=document.createElement('div');
    d.className='sys';
    d.textContent=text;
    msgs.appendChild(d);
  } else {
    const row=document.createElement('div');
    row.className='row '+role;
    const bubble=document.createElement('div');
    bubble.className='bubble';
    if(role==='bot'){
      bubble.innerHTML = formatMd(text);
    } else {
      bubble.textContent = text;
    }
    row.appendChild(bubble);
    if(role==='bot'){
      const btn=document.createElement('button');
      btn.className='copy-btn';
      btn.textContent='نسخ';
      btn.onclick=()=>{
        navigator.clipboard.writeText(text).then(()=>{
          btn.textContent='تم ✓';
          setTimeout(()=>btn.textContent='نسخ',1200);
        });
      };
      row.appendChild(btn);
    }
    msgs.appendChild(row);
  }
  msgs.scrollTop=msgs.scrollHeight;
}

function clearUI(msg){
  msgs.innerHTML='';
  add('sys', msg||'محادثة جديدة');
}
document.getElementById('newchat').onclick=async()=>{
  await fetch('/api/clear',{method:'POST'});
  clearUI('محادثة جديدة');
};
document.getElementById('delchat').onclick=async()=>{
  await fetch('/api/clear',{method:'POST'});
  clearUI('تم حذف المحادثة');
};

async function send(){
  const text=inp.value.trim();
  if(!text||busy)return;
  busy=true;sendBtn.disabled=true;
  add('user',text);inp.value='';
  const typing=document.createElement('div');
  typing.className='typing';typing.textContent='يفكر...';
  msgs.appendChild(typing);msgs.scrollTop=msgs.scrollHeight;
  try{
    const r=await fetch('/api/chat',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:text})
    });
    const j=await r.json();
    typing.remove();
    if(j.error) add('bot','خطأ: '+j.error);
    else add('bot',j.reply);
  }catch(e){
    typing.remove();
    add('bot','فشل الاتصال');
  }
  busy=false;sendBtn.disabled=false;inp.focus();
}
sendBtn.onclick=send;
inp.onkeydown=e=>{if(e.key==='Enter')send()};
</script>
</body>
</html>"""

def get_key():
    for env in ("GROQ_API_KEY", "OPENROUTER_API_KEY"):
        val = os.environ.get(env, "").strip()
        if val:
            return val, env
    return "", ""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "رسالة فارغة"}), 400

    sid = session.get("sid")
    if not sid:
        sid = str(uuid.uuid4())
        session["sid"] = sid
    if sid not in SESSIONS:
        SESSIONS[sid] = []

    history = SESSIONS[sid]
    history.append({"role": "user", "content": message})
    if len(history) > 30:
        history[:] = history[-30:]

    api_key, key_name = get_key()
    if not api_key:
        return jsonify({"error": "أضف GROQ_API_KEY في Railway Variables"}), 400

    if key_name == "OPENROUTER_API_KEY":
        model_id = "openrouter/auto"
        base = "https://openrouter.ai/api/v1"
    else:
        model_id = DEFAULT_MODEL
        base = "https://api.groq.com/openai/v1"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if "openrouter" in base:
        headers["HTTP-Referer"] = "https://github.com/csjdvdhdh/ai-chat-mobile"
        headers["X-Title"] = "AI Chat Mobile"

    # nudge model to format code cleanly
    system = {
        "role": "system",
        "content": "When you write code, always put it inside markdown fenced code blocks with the language tag, for example ```python\\ncode\\n```. Keep explanations outside the code blocks. Reply in the same language the user uses."
    }
    msgs = [system] + history

    payload = {
        "model": model_id,
        "messages": msgs,
        "temperature": 0.7,
    }
    try:
        r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            if key_name == "GROQ_API_KEY":
                for fallback in ("qwen/qwen3.8-27b", "openai/gpt-oss-120b"):
                    payload["model"] = fallback
                    r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
                    if r.status_code == 200:
                        break
            if r.status_code != 200:
                return jsonify({"error": f"{r.status_code}: {r.text[:200]}"}), 502
        reply = r.json()["choices"][0]["message"]["content"]
        history.append({"role": "assistant", "content": reply})
        SESSIONS[sid] = history
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/clear", methods=["POST"])
def api_clear():
    sid = session.get("sid")
    if sid and sid in SESSIONS:
        SESSIONS[sid] = []
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
