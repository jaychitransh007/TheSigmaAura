from html import escape


def get_web_ui_html(user_id: str = "") -> str:
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sigma Aura</title>
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
    .agent {
      background: transparent;
      border: none;
      color: var(--muted);
      font-size: 13px;
      padding: 4px 0;
      margin: 0 0 2px 0;
      max-width: 100%;
      animation: agentFadeIn 0.3s ease-out;
    }
    .agent .dot {
      display: inline-block;
      width: 6px; height: 6px;
      background: var(--accent);
      border-radius: 50%;
      margin-right: 8px;
      animation: pulse 1.2s ease-in-out infinite;
    }
    .agent.done .dot { animation: none; opacity: 0.4; }
    @keyframes agentFadeIn { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:translateY(0); } }
    @keyframes pulse { 0%,100% { opacity:0.3; } 50% { opacity:1; } }
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
    .card .body a {
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }
    .card .body a:hover { text-decoration: underline; }
    .tryon-section {
      margin-bottom: 12px;
      border: 1px solid #d4c9b8;
      border-radius: 12px;
      overflow: hidden;
      background: #fffcf6;
    }
    .tryon-section img {
      width: 100%;
      max-height: 400px;
      object-fit: contain;
      display: block;
      background: #f5efe6;
    }
    .tryon-label {
      padding: 6px 12px;
      font-size: 11px;
      font-weight: 700;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 1px;
      background: #f0ebe3;
    }
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
    .stage-item {
      padding: 6px 4px;
      border-bottom: 1px dashed #e8e2da;
      animation: stageFadeIn 0.3s ease-out;
    }
    .stage-item:last-child { border-bottom:none; }
    @keyframes stageFadeIn { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:translateY(0); } }
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
      <h1>Sigma Aura</h1>
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

    function addAgentBubble(text) {
      const div = document.createElement("div");
      div.className = "bubble agent";
      const dot = document.createElement("span");
      dot.className = "dot";
      div.appendChild(dot);
      div.appendChild(document.createTextNode(text));
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

    function firstImageUrl(item) {
      return (
        item.image_url ||
        item.primary_image_url ||
        item.images__0__src ||
        item.images_0_src ||
        ""
      );
    }

    function renderRecommendations(items) {
      if (!items || !items.length) return;
      const wrap = document.createElement("div");
      wrap.className = "cards";
      for (const item of items) {
        const card = document.createElement("div");
        card.className = "card";
        const image = document.createElement("img");
        image.src = firstImageUrl(item);
        image.alt = item.title || "Catalog match";
        image.loading = "lazy";
        const body = document.createElement("div");
        body.className = "body";
        const url = item.product_url || item.url || "";
        const title = item.title || item.product_id || "Untitled";
        body.innerHTML = `
          <div style="font-weight:700; margin-bottom:6px;">${escapeHtml(title)}</div>
          <div style="margin-bottom:8px;">Similarity ${Number(item.similarity || 0).toFixed(3)}</div>
          <div class="chip">${escapeHtml(item.garment_category || "Unknown")}</div>
          <div class="chip">${escapeHtml(item.garment_subtype || "Unknown")}</div>
          <div class="chip">${escapeHtml(item.primary_color || "Unknown")}</div>
          <div class="chip">${escapeHtml(item.price || "Unknown")}</div>
          ${url ? `<div style="margin-top:8px;"><a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">Open product</a></div>` : ""}
        `;
        card.appendChild(image);
        card.appendChild(body);
        wrap.appendChild(card);
      }
      feed.appendChild(wrap);
      feed.scrollTop = feed.scrollHeight;
    }

    function renderOutfits(outfits) {
      if (!outfits || !outfits.length) return;
      for (const outfit of outfits) {
        if (outfit.tryon_image) {
          const tryonWrap = document.createElement("div");
          tryonWrap.className = "tryon-section";
          const label = document.createElement("div");
          label.className = "tryon-label";
          label.textContent = `#${outfit.rank || ""} Virtual Try-On — ${outfit.title || ""}`;
          const tryonImg = document.createElement("img");
          tryonImg.src = outfit.tryon_image;
          tryonImg.alt = "Virtual try-on: " + (outfit.title || "");
          tryonImg.loading = "lazy";
          tryonWrap.appendChild(label);
          tryonWrap.appendChild(tryonImg);
          feed.appendChild(tryonWrap);
        }
        const meta = document.createElement("div");
        meta.className = "meta";
        const bits = [];
        if (outfit.rank != null) bits.push(`#${outfit.rank}`);
        if (outfit.title) bits.push(outfit.title);
        if (outfit.reasoning) bits.push(outfit.reasoning);
        meta.textContent = bits.join("  ");
        feed.appendChild(meta);
        renderRecommendations(outfit.items || []);
      }
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
        div.textContent = stage.message
          || `${stage.stage}${stage.detail ? "  " + stage.detail : ""}`;
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
      let renderedCount = 0;
      const agentBubbles = [];
      while (true) {
        const res = await fetch(`/v1/conversations/${conversationId}/turns/${jobId}/status`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Polling failed");
        renderStages(data.stages || []);
        const stages = data.stages || [];
        for (let i = renderedCount; i < stages.length; i++) {
          const msg = stages[i].message;
          if (msg) {
            agentBubbles.push(addAgentBubble(msg));
          }
        }
        renderedCount = stages.length;
        if (data.status === "completed") {
          for (const b of agentBubbles) b.classList.add("done");
          return data.result;
        }
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
      messageEl.disabled = true;
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
        addBubble(result.assistant_message || "", "assistant");
        renderOutfits(result.outfits || []);
      } catch (e) {
        err.textContent = e.message || String(e);
      } finally {
        sendBtn.disabled = false;
        messageEl.disabled = false;
        messageEl.focus();
      }
    }

    document.getElementById("sendBtn").addEventListener("click", send);
    document.getElementById("newConversationBtn").addEventListener("click", () => {
      convIdEl.value = "";
      stageBox.innerHTML = "";
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
