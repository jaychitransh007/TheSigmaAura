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

    /* --- Outfit card: 3-column PDP layout --- */
    .outfit-card {
      display: grid;
      grid-template-columns: 80px 1fr 40%;
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
      background: #fff;
      margin-bottom: 14px;
      min-height: 320px;
      animation: agentFadeIn 0.3s ease-out;
    }
    .outfit-thumbs {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 10px 8px;
      background: #faf7f2;
      border-right: 1px solid var(--line);
      align-items: center;
      overflow-y: auto;
    }
    .outfit-thumbs img {
      width: 64px;
      height: 64px;
      object-fit: cover;
      border-radius: 8px;
      border: 2px solid transparent;
      cursor: pointer;
      background: #efe9e0;
      transition: border-color 0.15s;
    }
    .outfit-thumbs img:hover { border-color: var(--muted); }
    .outfit-thumbs img.active { border-color: var(--accent); }
    .outfit-main-img {
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f5efe6;
      overflow: hidden;
    }
    .outfit-main-img img {
      max-width: 100%;
      max-height: 480px;
      object-fit: contain;
      display: block;
    }
    .outfit-info {
      padding: 16px;
      overflow-y: auto;
      font-size: 13px;
      border-left: 1px solid var(--line);
    }
    .outfit-info .outfit-rank {
      font-size: 11px;
      font-weight: 700;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 4px;
    }
    .outfit-info .outfit-title {
      font-size: 16px;
      font-weight: 700;
      margin-bottom: 10px;
    }
    .outfit-info .outfit-notes {
      margin-bottom: 12px;
      line-height: 1.5;
      color: var(--ink);
    }
    .outfit-info .outfit-notes p {
      margin: 0 0 6px 0;
    }
    .outfit-info .outfit-product {
      padding: 8px 0;
      border-top: 1px solid #eee;
    }
    .outfit-info .outfit-product:first-of-type { border-top: none; }
    .outfit-info .outfit-product a {
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }
    .outfit-info .outfit-product a:hover { text-decoration: underline; }
    .outfit-info .outfit-chips { margin: 10px 0; }
    .outfit-radar { margin: 12px 0 4px; text-align: center; }
    .outfit-feedback {
      display: flex;
      gap: 8px;
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }
    .outfit-feedback button {
      font-size: 12px;
      padding: 6px 14px;
      border-radius: 8px;
    }
    .outfit-feedback .btn-like {
      background: var(--accent);
      color: #fff;
    }
    .outfit-feedback .btn-dislike {
      background: #fff;
      color: #9d1e1e;
      border-color: #d4b8b8;
    }
    .outfit-feedback .btn-dislike:hover { background: #fdf0f0; }
    .dislike-form {
      display: none;
      margin-top: 10px;
    }
    .dislike-form.open { display: block; }
    .dislike-form textarea {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      font-size: 12px;
      resize: vertical;
      min-height: 50px;
    }
    .dislike-form .dislike-actions {
      display: flex;
      gap: 6px;
      margin-top: 6px;
    }
    .dislike-form button {
      font-size: 11px;
      padding: 5px 10px;
    }
    .feedback-status {
      font-size: 11px;
      margin-top: 6px;
      min-height: 16px;
    }
    .feedback-status.success { color: var(--accent); }
    .feedback-status.error { color: #9d1e1e; }

    @media (max-width: 900px) {
      .wrap { grid-template-columns: 1fr; }
      .chat { min-height: 70vh; }
      .outfit-card {
        grid-template-columns: 1fr;
        grid-template-rows: auto auto auto;
      }
      .outfit-thumbs {
        flex-direction: row;
        border-right: none;
        border-bottom: 1px solid var(--line);
        padding: 8px;
        overflow-x: auto;
        overflow-y: hidden;
        order: 2;
      }
      .outfit-main-img { order: 1; min-height: 260px; }
      .outfit-info {
        order: 3;
        border-left: none;
        border-top: 1px solid var(--line);
      }
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

    function escapeHtml(value) {
      return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
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

    function buildOutfitCard(outfit, conversationId) {
      const card = document.createElement("div");
      card.className = "outfit-card";

      // --- Col 1: Thumbnails ---
      const thumbs = document.createElement("div");
      thumbs.className = "outfit-thumbs";

      const images = [];
      const items = outfit.items || [];
      for (const item of items) {
        const src = firstImageUrl(item);
        if (src) {
          images.push({ src, label: item.title || item.garment_category || "Product" });
        }
      }
      if (outfit.tryon_image) {
        images.push({ src: outfit.tryon_image, label: "Virtual Try-On" });
      }

      // Default hero: try-on if present, otherwise first product image
      const defaultIdx = outfit.tryon_image ? images.length - 1 : 0;

      // --- Col 2: Hero image ---
      const heroWrap = document.createElement("div");
      heroWrap.className = "outfit-main-img";
      const heroImg = document.createElement("img");
      heroImg.alt = outfit.title || "Outfit";
      heroImg.loading = "lazy";
      if (images.length > 0) {
        heroImg.src = images[defaultIdx].src;
      }
      heroWrap.appendChild(heroImg);

      // Build thumbnail elements
      images.forEach(function(img, idx) {
        const thumb = document.createElement("img");
        thumb.src = img.src;
        thumb.alt = img.label;
        thumb.loading = "lazy";
        if (idx === defaultIdx) thumb.className = "active";
        thumb.addEventListener("click", function() {
          heroImg.src = img.src;
          thumbs.querySelectorAll("img").forEach(function(t) { t.classList.remove("active"); });
          thumb.classList.add("active");
        });
        thumbs.appendChild(thumb);
      });

      // --- Col 3: Info panel ---
      const info = document.createElement("div");
      info.className = "outfit-info";

      // Rank
      if (outfit.rank != null) {
        const rank = document.createElement("div");
        rank.className = "outfit-rank";
        rank.textContent = "#" + outfit.rank + " Recommendation";
        info.appendChild(rank);
      }

      // Title
      if (outfit.title) {
        const title = document.createElement("div");
        title.className = "outfit-title";
        title.textContent = outfit.title;
        info.appendChild(title);
      }

      // Per-product title + price
      for (const item of items) {
        const prod = document.createElement("div");
        prod.className = "outfit-product";
        const pTitle = item.title || item.product_id || "Untitled";
        let html = '<div style="font-weight:600; margin-bottom:2px;">' + escapeHtml(pTitle) + '</div>';
        if (item.price) {
          html += '<div style="margin-bottom:4px; color:#666;">' + escapeHtml(item.price) + '</div>';
        }
        prod.innerHTML = html;
        info.appendChild(prod);
      }

      // Style archetype radar chart
      const archetypes = [
        { key: "classic_pct", label: "Classic" },
        { key: "dramatic_pct", label: "Dramatic" },
        { key: "romantic_pct", label: "Romantic" },
        { key: "natural_pct", label: "Natural" },
        { key: "minimalist_pct", label: "Minimalist" },
        { key: "creative_pct", label: "Creative" },
        { key: "sporty_pct", label: "Sporty" },
        { key: "edgy_pct", label: "Edgy" },
      ];
      const radarDiv = document.createElement("div");
      radarDiv.className = "outfit-radar";
      const canvas = document.createElement("canvas");
      const size = 240;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = size * dpr;
      canvas.height = size * dpr;
      canvas.style.width = size + "px";
      canvas.style.height = size + "px";
      radarDiv.appendChild(canvas);
      info.appendChild(radarDiv);

      const ctx = canvas.getContext("2d");
      ctx.scale(dpr, dpr);
      const cx = size / 2;
      const cy = size / 2;
      const maxR = size / 2 - 30;
      const n = archetypes.length;
      const step = (2 * Math.PI) / n;
      const startAngle = -Math.PI / 2;

      function pointAt(i, r) {
        var a = startAngle + i * step;
        return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
      }

      // Grid rings at 25%, 50%, 75%, 100%
      ctx.strokeStyle = "#ddd";
      ctx.lineWidth = 0.5;
      for (var ring = 1; ring <= 4; ring++) {
        ctx.beginPath();
        var rr = maxR * ring / 4;
        for (var gi = 0; gi < n; gi++) {
          var gp = pointAt(gi, rr);
          if (gi === 0) ctx.moveTo(gp.x, gp.y); else ctx.lineTo(gp.x, gp.y);
        }
        ctx.closePath();
        ctx.stroke();
      }

      // Axis lines
      for (var ai = 0; ai < n; ai++) {
        var ap = pointAt(ai, maxR);
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(ap.x, ap.y);
        ctx.stroke();
      }

      // Data polygon
      var values = archetypes.map(function(a) { return outfit[a.key] || 0; });
      ctx.beginPath();
      ctx.fillStyle = "rgba(139, 92, 246, 0.25)";
      ctx.strokeStyle = "rgba(139, 92, 246, 0.85)";
      ctx.lineWidth = 2;
      for (var di = 0; di < n; di++) {
        var dp = pointAt(di, maxR * values[di] / 100);
        if (di === 0) ctx.moveTo(dp.x, dp.y); else ctx.lineTo(dp.x, dp.y);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Data points
      ctx.fillStyle = "rgba(139, 92, 246, 1)";
      for (var pi = 0; pi < n; pi++) {
        var pp = pointAt(pi, maxR * values[pi] / 100);
        ctx.beginPath();
        ctx.arc(pp.x, pp.y, 3, 0, 2 * Math.PI);
        ctx.fill();
      }

      // Labels
      ctx.fillStyle = "var(--ink, #222)";
      ctx.font = "600 11px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (var li = 0; li < n; li++) {
        var lp = pointAt(li, maxR + 16);
        ctx.fillText(archetypes[li].label, lp.x, lp.y);
      }

      // Feedback CTAs
      const fbWrap = document.createElement("div");
      fbWrap.className = "outfit-feedback";
      const likeBtn = document.createElement("button");
      likeBtn.className = "btn-like";
      likeBtn.textContent = "Like This";
      const dislikeBtn = document.createElement("button");
      dislikeBtn.className = "btn-dislike";
      dislikeBtn.textContent = "Didn't Like This";
      fbWrap.appendChild(likeBtn);
      fbWrap.appendChild(dislikeBtn);
      info.appendChild(fbWrap);

      // Dislike form
      const dislikeForm = document.createElement("div");
      dislikeForm.className = "dislike-form";
      const ta = document.createElement("textarea");
      ta.placeholder = "What's missing or what would you prefer?";
      dislikeForm.appendChild(ta);
      const dislikeActions = document.createElement("div");
      dislikeActions.className = "dislike-actions";
      const submitBtn = document.createElement("button");
      submitBtn.textContent = "Submit";
      const cancelBtn = document.createElement("button");
      cancelBtn.className = "secondary";
      cancelBtn.textContent = "Cancel";
      dislikeActions.appendChild(submitBtn);
      dislikeActions.appendChild(cancelBtn);
      dislikeForm.appendChild(dislikeActions);
      info.appendChild(dislikeForm);

      // Feedback status line
      const fbStatus = document.createElement("div");
      fbStatus.className = "feedback-status";
      info.appendChild(fbStatus);

      // Wire feedback handlers
      const outfitRank = outfit.rank || 0;
      const itemIds = items.map(function(i) { return i.product_id || ""; }).filter(Boolean);

      likeBtn.addEventListener("click", function() {
        sendFeedback(conversationId, outfitRank, "like", "", itemIds, fbStatus, fbWrap, dislikeForm);
      });
      dislikeBtn.addEventListener("click", function() {
        dislikeForm.classList.add("open");
      });
      cancelBtn.addEventListener("click", function() {
        dislikeForm.classList.remove("open");
        ta.value = "";
      });
      submitBtn.addEventListener("click", function() {
        const noteText = ta.value.trim();
        sendFeedback(conversationId, outfitRank, "dislike", noteText, itemIds, fbStatus, fbWrap, dislikeForm);
      });

      card.appendChild(thumbs);
      card.appendChild(heroWrap);
      card.appendChild(info);
      return card;
    }

    async function sendFeedback(conversationId, outfitRank, eventType, notes, itemIds, statusEl, fbWrap, dislikeForm) {
      statusEl.textContent = "Sending...";
      statusEl.className = "feedback-status";
      try {
        const res = await fetch("/v1/conversations/" + conversationId + "/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            outfit_rank: outfitRank,
            event_type: eventType,
            notes: notes,
            item_ids: itemIds
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Feedback failed");
        statusEl.textContent = eventType === "like" ? "Thanks for your feedback!" : "Feedback submitted. Thank you!";
        statusEl.className = "feedback-status success";
        fbWrap.style.display = "none";
        dislikeForm.classList.remove("open");
      } catch (e) {
        statusEl.textContent = "Error: " + (e.message || String(e));
        statusEl.className = "feedback-status error";
      }
    }

    function renderQuickReplies(suggestions) {
      if (!suggestions || !suggestions.length) return;
      const wrap = document.createElement("div");
      wrap.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px 0;";
      for (const text of suggestions) {
        const btn = document.createElement("button");
        btn.className = "secondary";
        btn.style.cssText = "font-size:13px;padding:6px 14px;border-radius:999px;";
        btn.textContent = text;
        btn.addEventListener("click", function() {
          messageEl.value = text;
          wrap.remove();
          send();
        });
        wrap.appendChild(btn);
      }
      feed.appendChild(wrap);
      feed.scrollTop = feed.scrollHeight;
    }

    function renderOutfits(outfits, conversationId) {
      if (!outfits || !outfits.length) return;
      for (const outfit of outfits) {
        const card = buildOutfitCard(outfit, conversationId);
        feed.appendChild(card);
      }
      feed.scrollTop = feed.scrollHeight;
    }

    function renderStages(stages) {
      stageBox.innerHTML = "";
      for (const stage of stages || []) {
        const div = document.createElement("div");
        div.className = "stage-item";
        div.textContent = stage.message
          || (stage.stage + (stage.detail ? "  " + stage.detail : ""));
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
        const res = await fetch("/v1/conversations/" + conversationId + "/turns/" + jobId + "/status");
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
        await new Promise(function(resolve) { setTimeout(resolve, 800); });
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
        const res = await fetch("/v1/conversations/" + conversationId + "/turns/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, message: message }),
        });
        const job = await res.json();
        if (!res.ok) throw new Error(job.detail || "Failed to start turn");
        const result = await pollJob(conversationId, job.job_id);
        addBubble(result.assistant_message || "", "assistant");
        if (result.response_type === "clarification") {
          renderQuickReplies(result.follow_up_suggestions || []);
        } else {
          renderOutfits(result.outfits || [], conversationId);
          renderQuickReplies(result.follow_up_suggestions || []);
        }
      } catch (e) {
        err.textContent = e.message || String(e);
      } finally {
        sendBtn.disabled = false;
        messageEl.disabled = false;
        messageEl.focus();
      }
    }

    document.getElementById("sendBtn").addEventListener("click", send);
    document.getElementById("newConversationBtn").addEventListener("click", function() {
      convIdEl.value = "";
      stageBox.innerHTML = "";
      addMeta("started a new conversation session");
    });
    logoutBtn.addEventListener("click", function() {
      window.location.href = "/";
    });
    messageEl.addEventListener("keydown", function(event) {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        send();
      }
    });
  </script>
</body>
</html>
"""
    return html.replace("__USER_ID__", escape(user_id))
