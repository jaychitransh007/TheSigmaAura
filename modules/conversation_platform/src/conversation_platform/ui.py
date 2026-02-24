def get_web_ui_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sigma Aura Conversation Stylist</title>
  <style>
    :root {
      --bg: #f4efe8;
      --surface: #fffdf9;
      --ink: #1e1f22;
      --muted: #6a6f76;
      --line: #dad3cb;
      --accent: #1f6f5f;
      --accent-2: #c97a2b;
    }
    body {
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at 15% 10%, #f7e9d7 0%, var(--bg) 45%, #f1ece5 100%);
    }
    .wrap {
      max-width: 1100px;
      margin: 24px auto;
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 16px;
      padding: 0 16px;
    }
    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
    }
    .controls {
      padding: 14px;
    }
    .controls h1 {
      margin: 0 0 12px 0;
      font-size: 18px;
    }
    .field {
      margin-bottom: 10px;
    }
    .field label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
    }
    .field input, .field select, .field textarea {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 9px 10px;
      background: #fff;
      font-size: 14px;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .chat {
      display: grid;
      grid-template-rows: 1fr auto;
      min-height: 78vh;
    }
    .feed {
      padding: 14px;
      overflow: auto;
    }
    .bubble {
      padding: 10px 12px;
      border-radius: 12px;
      margin: 0 0 10px 0;
      max-width: 82%;
      border: 1px solid var(--line);
      line-height: 1.35;
      white-space: pre-wrap;
    }
    .user {
      margin-left: auto;
      background: #ebf4f2;
      border-color: #b7d5ce;
    }
    .assistant {
      background: #fff8ef;
      border-color: #eadcc8;
    }
    .meta {
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 8px;
    }
    .composer {
      border-top: 1px solid var(--line);
      padding: 12px;
    }
    .btns {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    button {
      border: 1px solid transparent;
      border-radius: 10px;
      padding: 8px 12px;
      font-weight: 600;
      cursor: pointer;
      background: var(--accent);
      color: #fff;
    }
    button.secondary {
      background: #fff;
      color: var(--ink);
      border-color: var(--line);
    }
    .cards {
      margin-top: 8px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
      gap: 8px;
    }
    .card {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 10px;
      overflow: hidden;
    }
    .card img {
      width: 100%;
      height: 170px;
      object-fit: cover;
      background: #f0f0f0;
      display: block;
    }
    .card .body {
      padding: 8px;
      font-size: 12px;
    }
    .card-actions {
      margin-top: 8px;
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 6px;
    }
    .mini-btn {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 6px 6px;
      background: #fff;
      color: var(--ink);
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
    }
    .mini-btn.buy {
      background: var(--accent-2);
      border-color: var(--accent-2);
      color: #fff;
    }
    .mini-btn:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
    .feedback-note {
      margin-top: 6px;
      color: var(--muted);
      font-size: 11px;
      min-height: 14px;
    }
    .err {
      color: #9d1e1e;
      font-size: 13px;
      margin-top: 8px;
      white-space: pre-wrap;
    }
    .stages {
      margin-top: 10px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
      padding: 8px;
      min-height: 100px;
      max-height: 220px;
      overflow: auto;
      font-size: 12px;
    }
    .stage-item {
      padding: 6px 4px;
      border-bottom: 1px dashed #e8e2da;
    }
    .stage-item:last-child {
      border-bottom: none;
    }
    .stage-name {
      font-weight: 600;
    }
    @media (max-width: 900px) {
      .wrap { grid-template-columns: 1fr; }
      .chat { min-height: 70vh; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <aside class="panel controls">
      <h1>Conversation Stylist</h1>
      <div class="field">
        <label>User ID</label>
        <input id="userId" value="user_123" />
      </div>
      <div class="field">
        <label>Conversation ID</label>
        <input id="conversationId" placeholder="auto-created on first send" readonly />
      </div>
      <div class="row">
        <div class="field">
          <label>Strictness</label>
          <select id="strictness">
            <option value="balanced">balanced</option>
            <option value="safe">safe</option>
            <option value="bold">bold</option>
          </select>
        </div>
        <div class="field">
          <label>Max Results</label>
          <input id="maxResults" type="number" min="1" max="50" value="8" />
        </div>
      </div>
      <div class="field">
        <label>Hard Filter Profile</label>
        <select id="hardFilterProfile">
          <option value="rl_ready_minimal">rl_ready_minimal</option>
          <option value="legacy">legacy</option>
        </select>
      </div>
      <div class="field">
        <label>Image Upload (first turn required)</label>
        <input id="imageInput" type="file" accept="image/*" />
      </div>
      <div class="btns">
        <button class="secondary" id="newConversationBtn">New Conversation</button>
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
          <textarea id="message" rows="3" placeholder="Need work looks in earthy tones."></textarea>
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
    const imageInputEl = document.getElementById("imageInput");
    const strictnessEl = document.getElementById("strictness");
    const maxResultsEl = document.getElementById("maxResults");
    const hardFilterEl = document.getElementById("hardFilterProfile");
    const stageBox = document.getElementById("stageBox");
    const sendBtn = document.getElementById("sendBtn");

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

    async function sendFeedbackAction(eventType, item, recommendationRunId, noteEl) {
      const userId = userIdEl.value.trim();
      const conversationId = convIdEl.value.trim();
      if (!userId || !conversationId || !recommendationRunId) {
        noteEl.textContent = "feedback unavailable";
        return;
      }
      const payload = {
        user_id: userId,
        conversation_id: conversationId,
        recommendation_run_id: recommendationRunId,
        garment_id: item.garment_id,
        event_type: eventType,
        notes: "ui_action",
      };
      const res = await fetch("/v1/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "feedback failed");
      noteEl.textContent = `${eventType} saved (reward ${data.reward_value})`;
      addMeta(`feedback: ${eventType} -> ${item.title}`);

      if (eventType === "share" && navigator.share) {
        try {
          await navigator.share({
            title: item.title || "Style recommendation",
            text: `Check this recommendation: ${item.title || "look"}`,
            url: item.image_url || undefined,
          });
        } catch (_) {
          // user canceled share, no-op
        }
      }
    }

    function addRecommendationCards(items, recommendationRunId) {
      if (!items || !items.length) return;
      const wrap = document.createElement("div");
      wrap.className = "cards";
      for (const item of items) {
        const card = document.createElement("div");
        card.className = "card";
        const img = document.createElement("img");
        img.src = item.image_url || "";
        img.alt = item.title || "";
        const body = document.createElement("div");
        body.className = "body";
        const recommendationKind = item.recommendation_kind || "single_garment";
        const componentTitles = Array.isArray(item.component_titles) ? item.component_titles.filter(Boolean).join(" + ") : "";
        body.innerHTML = `
          <div><strong>#${item.rank} ${item.title || ""}</strong></div>
          <div>type: ${recommendationKind}</div>
          <div>${componentTitles ? `components: ${componentTitles}` : ""}</div>
          <div>score: ${(item.score || 0).toFixed(3)} | conf: ${(item.compatibility_confidence || 0).toFixed(2)}</div>
          <div>${item.reasons || ""}</div>
        `;

        const actions = document.createElement("div");
        actions.className = "card-actions";
        const likeBtn = document.createElement("button");
        likeBtn.className = "mini-btn";
        likeBtn.textContent = "Like";
        const shareBtn = document.createElement("button");
        shareBtn.className = "mini-btn";
        shareBtn.textContent = "Share";
        const buyBtn = document.createElement("button");
        buyBtn.className = "mini-btn buy";
        buyBtn.textContent = "Buy Now";

        const note = document.createElement("div");
        note.className = "feedback-note";
        if (!recommendationRunId) {
          likeBtn.disabled = true;
          shareBtn.disabled = true;
          buyBtn.disabled = true;
          note.textContent = "Feedback disabled (no run id)";
        }

        likeBtn.addEventListener("click", async () => {
          try {
            await sendFeedbackAction("like", item, recommendationRunId, note);
          } catch (e) {
            note.textContent = String(e);
          }
        });
        shareBtn.addEventListener("click", async () => {
          try {
            await sendFeedbackAction("share", item, recommendationRunId, note);
          } catch (e) {
            note.textContent = String(e);
          }
        });
        buyBtn.addEventListener("click", async () => {
          try {
            await sendFeedbackAction("buy", item, recommendationRunId, note);
          } catch (e) {
            note.textContent = String(e);
          }
        });
        actions.appendChild(likeBtn);
        actions.appendChild(shareBtn);
        actions.appendChild(buyBtn);
        body.appendChild(actions);
        body.appendChild(note);
        card.appendChild(img);
        card.appendChild(body);
        wrap.appendChild(card);
      }
      feed.appendChild(wrap);
      feed.scrollTop = feed.scrollHeight;
    }

    function renderStages(stages) {
      stageBox.innerHTML = "";
      if (!stages || !stages.length) return;
      for (const s of stages) {
        const div = document.createElement("div");
        div.className = "stage-item";
        const time = (s.timestamp || "").split("T")[1] || "";
        div.innerHTML = `
          <div class="stage-name">${s.stage}</div>
          <div>${s.detail || ""}</div>
          <div style="color:#777;">${time}</div>
        `;
        stageBox.appendChild(div);
      }
      stageBox.scrollTop = stageBox.scrollHeight;
    }

    async function fileToDataUrl(file) {
      return await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
    }

    async function ensureConversation() {
      if (convIdEl.value) return convIdEl.value;
      const payload = { user_id: userIdEl.value.trim() };
      const res = await fetch("/v1/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create conversation");
      convIdEl.value = data.conversation_id;
      addMeta("conversation: " + data.conversation_id);
      return data.conversation_id;
    }

    async function pollTurnJob(conversationId, jobId) {
      while (true) {
        const res = await fetch(`/v1/conversations/${conversationId}/turns/${jobId}/status`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to fetch turn status");
        renderStages(data.stages || []);
        if (data.status === "completed") return data.result;
        if (data.status === "failed") throw new Error(data.error || "Turn failed");
        await new Promise((r) => setTimeout(r, 700));
      }
    }

    async function sendTurn() {
      err.textContent = "";
      const msg = messageEl.value.trim();
      if (!msg) return;
      if (!userIdEl.value.trim()) {
        err.textContent = "user_id is required.";
        return;
      }
      sendBtn.disabled = true;
      sendBtn.textContent = "Processing...";
      addBubble(msg, "user");
      renderStages([{ timestamp: new Date().toISOString(), stage: "ui", detail: "queued turn request" }]);

      try {
        const conversationId = await ensureConversation();
        const imageRefs = [];
        if (imageInputEl.files && imageInputEl.files.length > 0) {
          const file = imageInputEl.files[0];
          const dataUrl = await fileToDataUrl(file);
          imageRefs.push(dataUrl);
        }

        const payload = {
          user_id: userIdEl.value.trim(),
          message: msg,
          image_refs: imageRefs,
          strictness: strictnessEl.value,
          hard_filter_profile: hardFilterEl.value,
          max_results: parseInt(maxResultsEl.value || "8", 10),
        };

        const startRes = await fetch(`/v1/conversations/${conversationId}/turns/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const startData = await startRes.json();
        if (!startRes.ok) throw new Error(startData.detail || "Failed to start turn");
        addMeta(`job: ${startData.job_id}`);

        const data = await pollTurnJob(conversationId, startData.job_id);

        addBubble(data.assistant_message || "(empty assistant message)", "assistant");
        if (data.needs_clarification && data.clarifying_question) {
          addBubble("Need more detail: " + data.clarifying_question, "assistant");
        }
        addMeta(
          `resolved: occasion=${data.resolved_context.occasion}, archetype=${data.resolved_context.archetype}, ` +
          `gender=${data.resolved_context.gender}, age=${data.resolved_context.age}`
        );
        addRecommendationCards(data.recommendations || [], data.recommendation_run_id);
        messageEl.value = "";
        imageInputEl.value = "";
      } catch (e) {
        err.textContent = String(e);
      } finally {
        sendBtn.disabled = false;
        sendBtn.textContent = "Send";
      }
    }

    sendBtn.addEventListener("click", sendTurn);
    messageEl.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") sendTurn();
    });
    document.getElementById("newConversationBtn").addEventListener("click", () => {
      convIdEl.value = "";
      addMeta("new conversation requested");
    });
  </script>
</body>
</html>
"""
