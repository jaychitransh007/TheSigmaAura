from html import escape


def get_web_ui_html(user_id: str = "") -> str:
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sigma Aura Conversation Platform</title>
  <style>
    :root {
      --bg: #f4efe8;
      --surface: #fffdf9;
      --ink: #1e1f22;
      --muted: #6a6f76;
      --line: #dad3cb;
      --accent: #1f6f5f;
    }
    body {
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at 15% 10%, #f7e9d7 0%, var(--bg) 45%, #f1ece5 100%);
    }
    .wrap {
      max-width: 1120px;
      margin: 24px auto;
      display: grid;
      grid-template-columns: 300px 1fr;
      gap: 16px;
      padding: 0 16px;
    }
    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
    }
    .controls, .composer, .feed { padding: 14px; }
    .chat { display: grid; grid-template-rows: 1fr auto; min-height: 78vh; }
    .field { margin-bottom: 10px; }
    .field label { display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }
    .field input, .field textarea {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 9px 10px;
      background: #fff;
      font-size: 14px;
    }
    .btns { display:flex; gap:8px; flex-wrap:wrap; }
    button {
      border: 1px solid transparent;
      border-radius: 10px;
      padding: 8px 12px;
      font-weight: 600;
      cursor: pointer;
      background: var(--accent);
      color: #fff;
    }
    button.secondary { background:#fff; color:var(--ink); border-color:var(--line); }
    .feed { overflow:auto; }
    .bubble {
      padding: 10px 12px;
      border-radius: 12px;
      margin: 0 0 10px 0;
      max-width: 84%;
      border: 1px solid var(--line);
      line-height: 1.4;
      white-space: pre-wrap;
    }
    .user { margin-left:auto; background:#ebf4f2; border-color:#b7d5ce; }
    .assistant { background:#fff8ef; border-color:#eadcc8; }
    .meta { font-size:12px; color:var(--muted); margin-bottom:8px; }
    .cards {
      margin-top: 8px;
      display:grid;
      grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap:10px;
    }
    .card {
      background:#fff;
      border:1px solid var(--line);
      border-radius:12px;
      overflow:hidden;
    }
    .card img { width:100%; height:220px; object-fit:cover; display:block; background:#efe9e0; }
    .card .body { padding:10px; font-size:12px; }
    .chip {
      display:inline-block;
      margin: 0 6px 6px 0;
      padding:4px 8px;
      font-size:11px;
      border-radius:999px;
      background:#f3eee7;
      border:1px solid #e6ddd2;
    }
    .stages {
      margin-top: 10px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
      padding: 8px;
      min-height: 100px;
      max-height: 240px;
      overflow: auto;
      font-size: 12px;
    }
    .stage-item { padding: 6px 4px; border-bottom: 1px dashed #e8e2da; }
    .stage-item:last-child { border-bottom:none; }
    .query-box {
      margin-top:10px;
      padding:8px;
      border:1px dashed var(--line);
      border-radius:10px;
      background:#fff;
      font-size:11px;
      color:var(--muted);
      white-space:pre-wrap;
      max-height:220px;
      overflow:auto;
    }
    .err { color:#9d1e1e; font-size:13px; margin-top:8px; white-space:pre-wrap; }
    @media (max-width: 900px) {
      .wrap { grid-template-columns: 1fr; }
      .chat { min-height: 70vh; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <aside class="panel controls">
      <h1>Conversation Platform</h1>
      <div class="field">
        <label>User ID</label>
        <input id="userId" value="__USER_ID__" />
      </div>
      <div class="field">
        <label>Conversation ID</label>
        <input id="conversationId" placeholder="auto-created on first send" readonly />
      </div>
      <div class="btns">
        <button class="secondary" id="newConversationBtn">New Conversation</button>
        <button class="secondary" id="logoutBtn">Logout</button>
      </div>
      <div class="err" id="errorBox"></div>
      <div class="field" style="margin-top:10px;">
        <label>Agent Processing Stages</label>
        <div id="stageBox" class="stages"></div>
      </div>
      <div class="field">
        <label>Retrieval Query</label>
        <div id="queryBox" class="query-box">No query generated yet.</div>
      </div>
    </aside>
    <main class="panel chat">
      <div class="feed" id="feed"></div>
      <div class="composer">
        <div class="field">
          <label>Your message</label>
          <textarea id="message" rows="3" placeholder="Need casual office wear and want to look taller."></textarea>
        </div>
        <div class="btns">
          <button id="sendBtn">Send</button>
        </div>
      </div>
    </main>
  </div>
  <script>
    const feed = document.getElementById("feed");
    const err = document.getElementById("errorBox");
    const queryBox = document.getElementById("queryBox");
    const userIdEl = document.getElementById("userId");
    const convIdEl = document.getElementById("conversationId");
    const messageEl = document.getElementById("message");
    const stageBox = document.getElementById("stageBox");
    const sendBtn = document.getElementById("sendBtn");
    const logoutBtn = document.getElementById("logoutBtn");

    function addBubble(text, kind) {
      const div = document.createElement("div");
      div.className = "bubble " + kind;
      div.textContent = text;
      feed.appendChild(div);
      feed.scrollTop = feed.scrollHeight;
      return div;
    }

    function addMeta(text) {
      const div = document.createElement("div");
      div.className = "meta";
      div.textContent = text;
      feed.appendChild(div);
      feed.scrollTop = feed.scrollHeight;
    }

    function renderRecommendations(items) {
      if (!items || !items.length) return;
      const wrap = document.createElement("div");
      wrap.className = "cards";
      for (const item of items) {
        const card = document.createElement("div");
        card.className = "card";
        const image = document.createElement("img");
        image.src = item.image_url || "";
        image.alt = item.title || "Catalog match";
        image.loading = "lazy";
        const body = document.createElement("div");
        body.className = "body";
        body.innerHTML = `
          <div style="font-weight:700; margin-bottom:6px;">${escapeHtml(item.title || "Untitled")}</div>
          <div style="margin-bottom:8px;">Similarity ${Number(item.similarity || 0).toFixed(3)}</div>
          <div class="chip">${escapeHtml(item.garment_category || "Unknown")}</div>
          <div class="chip">${escapeHtml(item.garment_subtype || "Unknown")}</div>
          <div class="chip">${escapeHtml(item.primary_color || "Unknown")}</div>
          <div class="chip">${escapeHtml(item.price || "Unknown")}</div>
        `;
        card.appendChild(image);
        card.appendChild(body);
        wrap.appendChild(card);
      }
      feed.appendChild(wrap);
      feed.scrollTop = feed.scrollHeight;
    }

    function escapeHtml(value) {
      return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function renderStages(stages) {
      stageBox.innerHTML = "";
      for (const stage of stages || []) {
        const div = document.createElement("div");
        div.className = "stage-item";
        div.textContent = `${stage.timestamp}  ${stage.stage}${stage.detail ? "  " + stage.detail : ""}`;
        stageBox.appendChild(div);
      }
      stageBox.scrollTop = stageBox.scrollHeight;
    }

    async function ensureConversation() {
      if (convIdEl.value.trim()) return convIdEl.value.trim();
      const res = await fetch("/v1/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userIdEl.value.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create conversation");
      convIdEl.value = data.conversation_id;
      addMeta("conversation created");
      return data.conversation_id;
    }

    async function pollJob(conversationId, jobId) {
      while (true) {
        const res = await fetch(`/v1/conversations/${conversationId}/turns/${jobId}/status`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Polling failed");
        renderStages(data.stages || []);
        if (data.status === "completed") return data.result;
        if (data.status === "failed") throw new Error(data.error || "Turn failed");
        await new Promise((resolve) => setTimeout(resolve, 800));
      }
    }

    async function send() {
      err.textContent = "";
      const userId = userIdEl.value.trim();
      const message = messageEl.value.trim();
      if (!userId) {
        err.textContent = "User ID is required.";
        return;
      }
      if (!message) {
        err.textContent = "Message is required.";
        return;
      }
      sendBtn.disabled = true;
      try {
        const conversationId = await ensureConversation();
        addBubble(message, "user");
        messageEl.value = "";
        const res = await fetch(`/v1/conversations/${conversationId}/turns/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, message }),
        });
        const job = await res.json();
        if (!res.ok) throw new Error(job.detail || "Failed to start turn");
        const result = await pollJob(conversationId, job.job_id);
        queryBox.textContent = result.retrieval_query_document || "No query generated.";
        addBubble(result.assistant_message || "", "assistant");
        renderRecommendations(result.recommendations || []);
      } catch (e) {
        err.textContent = e.message || String(e);
      } finally {
        sendBtn.disabled = false;
      }
    }

    document.getElementById("sendBtn").addEventListener("click", send);
    document.getElementById("newConversationBtn").addEventListener("click", () => {
      convIdEl.value = "";
      stageBox.innerHTML = "";
      queryBox.textContent = "No query generated yet.";
      addMeta("started a new conversation session");
    });
    logoutBtn.addEventListener("click", () => {
      window.location.href = "/";
    });
    messageEl.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        send();
      }
    });
  </script>
</body>
</html>
"""
    return html.replace("__USER_ID__", escape(user_id))
