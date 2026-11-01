#!/usr/bin/env python3
import os, uuid, requests
from flask import Flask, request, jsonify, render_template_string, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-ai-chat-secret")
SESSIONS = {}

MODELS = {
  "groq-llama": {"name":"Groq Llama-3.1-8B","model":"llama-3.1-8b-instant","base":"https://api.groq.com/openai/v1","key":"GROQ_API_KEY"},
  "groq-mixtral": {"name":"Groq Mixtral","model":"mixtral-8x7b-32768","base":"https://api.groq.com/openai/v1","key":"GROQ_API_KEY"},
  "openrouter": {"name":"OpenRouter Free","model":"openrouter/auto","base":"https://openrouter.ai/api/v1","key":"OPENROUTER_API_KEY"},
}

HTML = '<!DOCTYPE html>\n<html lang="ar" dir="rtl">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">\n<meta name="apple-mobile-web-app-capable" content="yes">\n<meta name="theme-color" content="#0d0d14">\n<title>AI Chat</title>\n<style>\n*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}\nbody{font-family:system-ui,-apple-system,sans-serif;background:#0d0d14;color:#eee;height:100dvh;display:flex;flex-direction:column;overflow:hidden}\nheader{background:#1a1a24;padding:12px 14px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #2a2a3a;flex-shrink:0}\nheader h1{font-size:16px;font-weight:600}\nheader select{background:#0d0d14;color:#eee;border:1px solid #333;border-radius:8px;padding:6px 10px;font-size:13px;max-width:160px}\n#msgs{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px;-webkit-overflow-scrolling:touch}\n.bubble{max-width:85%;padding:10px 14px;border-radius:16px;line-height:1.45;font-size:15px;word-break:break-word}\n.user{align-self:flex-start;background:#6c5ce7;border-bottom-right-radius:4px}\n.bot{align-self:flex-end;background:#1e1e2a;border-bottom-left-radius:4px}\n.sys{align-self:center;background:transparent;color:#666;font-size:12px}\n#bar{padding:10px 12px 16px;background:#1a1a24;border-top:1px solid #2a2a3a;display:flex;gap:8px;flex-shrink:0}\n#bar input{flex:1;background:#0d0d14;border:1px solid #333;border-radius:24px;padding:12px 16px;color:#eee;font-size:15px;outline:none}\n#bar button{width:48px;height:48px;border-radius:50%;border:none;background:#6c5ce7;color:#fff;font-size:18px;cursor:pointer;flex-shrink:0}\n#bar button:disabled{opacity:.5}\n.typing{color:#888;font-size:13px;padding:4px 8px}\n</style>\n</head>\n<body>\n<header>\n  <h1>AI Chat</h1>\n  <select id="model">\n    <option value="groq-llama">Groq Llama</option>\n    <option value="groq-mixtral">Groq Mixtral</option>\n    <option value="openrouter">OpenRouter</option>\n  </select>\n</header>\n<div id="msgs">\n  <div class="bubble sys">اختر نموذج وابدأ المحادثة — السياق محفوظ عند التبديل</div>\n</div>\n<div id="bar">\n  <input id="inp" type="text" placeholder="اكتب رسالة..." autocomplete="off">\n  <button id="send">➤</button>\n</div>\n<script>\nconst msgs=document.getElementById(\'msgs\');\nconst inp=document.getElementById(\'inp\');\nconst sendBtn=document.getElementById(\'send\');\nconst modelSel=document.getElementById(\'model\');\nlet busy=false;\nfunction add(role,text){\n  const d=document.createElement(\'div\');\n  d.className=\'bubble \'+role;\n  d.textContent=text;\n  msgs.appendChild(d);\n  msgs.scrollTop=msgs.scrollHeight;\n}\nasync function send(){\n  const text=inp.value.trim();\n  if(!text||busy)return;\n  busy=true;sendBtn.disabled=true;\n  add(\'user\',text);inp.value=\'\';\n  const typing=document.createElement(\'div\');\n  typing.className=\'typing\';typing.textContent=\'يفكر...\';\n  msgs.appendChild(typing);msgs.scrollTop=msgs.scrollHeight;\n  try{\n    const r=await fetch(\'/api/chat\',{\n      method:\'POST\',\n      headers:{\'Content-Type\':\'application/json\'},\n      body:JSON.stringify({message:text,model:modelSel.value})\n    });\n    const j=await r.json();\n    typing.remove();\n    if(j.error) add(\'bot\',\'خطأ: \'+j.error);\n    else add(\'bot\',j.reply);\n  }catch(e){\n    typing.remove();\n    add(\'bot\',\'فشل الاتصال\');\n  }\n  busy=false;sendBtn.disabled=false;inp.focus();\n}\nsendBtn.onclick=send;\ninp.onkeydown=e=>{if(e.key===\'Enter\')send()};\nmodelSel.onchange=()=>{\n  add(\'sys\',\'تم التبديل إلى \'+modelSel.options[modelSel.selectedIndex].text+\' — السياق محفوظ\');\n};\n</script>\n</body>\n</html>'

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True) or {}
    message = (data.get("message") or "").strip()
    model_id = data.get("model") or "groq-llama"
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
    model = MODELS.get(model_id) or MODELS["groq-llama"]
    api_key = os.environ.get(model["key"], "")
    if not api_key:
        return jsonify({"error": f"مفتاح {model['key']} غير موجود في Railway Variables"}), 400
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if "openrouter" in model["base"]:
        headers["HTTP-Referer"] = "https://github.com/csjdvdhdh/ai-chat-mobile"
        headers["X-Title"] = "AI Chat Mobile"
    payload = {
        "model": model["model"],
        "messages": history,
        "temperature": 0.7,
    }
    try:
        r = requests.post(f"{model['base']}/chat/completions", headers=headers, json=payload, timeout=60)
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
