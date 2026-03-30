from html import escape


def get_web_ui_html(
    user_id: str = "",
    active_view: str = "dashboard",
    source: str = "",
    focus: str = "",
    conversation_id: str = "",
) -> str:
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet" />
  <title>Sigma Aura</title>
  <style>
    :root {
      --bg: #f6f0ea;
      --bg-soft: #efe6dc;
      --surface: #fffaf5;
      --surface-alt: #f7efe8;
      --surface-deep: #f0e6dc;
      --ink: #201915;
      --muted: #6e655f;
      --muted-soft: #938880;
      --line: #dfd1c4;
      --accent: #6f2f45;
      --accent-soft: #b88b96;
      --wardrobe: #5f6a52;
      --gold: #b08a4e;
      --shadow: 0 22px 60px rgba(54, 32, 24, 0.08);
    }
    body {
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(184, 139, 150, 0.22), transparent 28%),
        radial-gradient(circle at 85% 12%, rgba(176, 138, 78, 0.14), transparent 24%),
        linear-gradient(180deg, #fbf6f1 0%, var(--bg) 42%, #f1e6da 100%);
    }
    .page-view { display: none; }
    body.view-dashboard .page-dashboard,
    body.view-chat .page-chat,
    body.view-wardrobe .page-wardrobe,
    body.view-style .page-style,
    body.view-trips .page-trips {
      display: block;
    }
    body.view-dashboard #jobsRail,
    body.view-dashboard #stageRail {
      display: none;
    }
    .shell {
      max-width: 1320px;
      margin: 0 auto;
      padding: 24px 18px 28px;
    }
    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 24px;
      margin-bottom: 18px;
    }
    .section-nav {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 0 0 18px 0;
    }
    .section-nav a {
      display: inline-flex;
      align-items: center;
      padding: 9px 13px;
      border-radius: 999px;
      border: 1px solid rgba(223, 209, 196, 0.96);
      background: rgba(255,255,255,0.74);
      color: var(--ink);
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .brand-mark {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .eyebrow {
      font-size: 11px;
      letter-spacing: 0.22em;
      text-transform: uppercase;
      color: var(--accent);
      font-weight: 700;
    }
    .topbar h1 {
      margin: 0;
      font-family: "Cormorant Garamond", "Times New Roman", serif;
      font-size: 42px;
      line-height: 0.95;
      font-weight: 600;
      letter-spacing: -0.02em;
    }
    .topbar p {
      margin: 0;
      max-width: 560px;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.5;
    }
    .top-actions {
      display: flex;
      gap: 10px;
      align-items: center;
      padding-top: 10px;
    }
    .hub {
      display: grid;
      grid-template-columns: 300px minmax(0, 1fr);
      gap: 18px;
    }
    .panel {
      background: linear-gradient(180deg, rgba(255,255,255,0.82), rgba(255,250,245,0.96));
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }
    .rail {
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .main-stack {
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr) auto;
      gap: 18px;
      min-height: 82vh;
    }
    .hero {
      overflow: hidden;
      position: relative;
      padding: 26px;
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 18px;
      min-height: 250px;
      background:
        radial-gradient(circle at 25% 15%, rgba(184, 139, 150, 0.2), transparent 28%),
        linear-gradient(135deg, rgba(255,250,245,0.96), rgba(244,233,224,0.98));
    }
    .hero:after {
      content: "";
      position: absolute;
      right: -40px;
      top: -20px;
      width: 240px;
      height: 240px;
      border-radius: 999px;
      background: radial-gradient(circle, rgba(111, 47, 69, 0.08), transparent 68%);
      pointer-events: none;
    }
    .hero-copy {
      position: relative;
      z-index: 1;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 14px;
    }
    .hero-title {
      font-family: "Cormorant Garamond", "Times New Roman", serif;
      font-size: 54px;
      line-height: 0.95;
      letter-spacing: -0.02em;
      margin: 0;
      max-width: 420px;
    }
    .hero-sub {
      margin: 0;
      max-width: 460px;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.6;
    }
    .hero-pills, .chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .hero-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }
    .hero-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 14px;
      padding: 11px 15px;
      text-decoration: none;
      font-weight: 700;
      font-size: 13px;
      border: 1px solid transparent;
    }
    .hero-link.primary {
      background: var(--accent);
      color: #fff;
      box-shadow: 0 12px 26px rgba(111, 47, 69, 0.18);
    }
    .hero-link.secondary {
      background: rgba(255,255,255,0.84);
      color: var(--ink);
      border-color: rgba(223, 209, 196, 0.96);
    }
    .hero-pill, .context-chip, .mode-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 12px;
      border-radius: 999px;
      border: 1px solid rgba(111, 47, 69, 0.12);
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      font-size: 12px;
      font-weight: 600;
    }
    .hero-stat-panel {
      position: relative;
      z-index: 1;
      display: grid;
      gap: 12px;
      align-content: end;
    }
    .hero-stat-card, .rail-card, .insight-card {
      background: rgba(255, 250, 245, 0.88);
      border: 1px solid rgba(223, 209, 196, 0.92);
      border-radius: 18px;
      padding: 16px;
    }
    .hero-stat-card h3, .section-title {
      margin: 0 0 8px 0;
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--muted-soft);
    }
    .dashboard-snapshot {
      padding: 16px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: wrap;
    }
    .dashboard-snapshot strong {
      display: block;
      margin-bottom: 4px;
      font-size: 15px;
    }
    .dashboard-snapshot p {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      max-width: 620px;
    }
    .hero-stat-card strong {
      display: block;
      font-family: "Cormorant Garamond", "Times New Roman", serif;
      font-size: 30px;
      line-height: 1;
      margin-bottom: 6px;
    }
    .hero-stat-card p, .rail-card p, .insight-card p {
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
      font-size: 13px;
    }
    .insight-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }
    .memory-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .handoff-banner {
      display: none;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      padding: 14px 16px;
      margin: 0 0 18px 0;
      border-radius: 20px;
      border: 1px solid rgba(223, 209, 196, 0.96);
      background: linear-gradient(180deg, rgba(255,250,245,0.95), rgba(246,238,230,0.92));
      box-shadow: 0 16px 36px rgba(45, 28, 22, 0.05);
    }
    .handoff-banner.show {
      display: flex;
      flex-wrap: wrap;
    }
    .handoff-banner strong {
      display: block;
      margin-bottom: 4px;
      font-size: 13px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent);
    }
    .handoff-banner span {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }
    .insight-card strong {
      display: block;
      margin-bottom: 6px;
      font-size: 16px;
      font-weight: 700;
    }
    .chat-shell {
      display: grid;
      grid-template-rows: auto 1fr auto;
      min-height: 0;
      overflow: hidden;
    }
    .chat-head {
      padding: 18px 18px 12px;
      border-bottom: 1px solid rgba(223, 209, 196, 0.9);
      background: linear-gradient(180deg, rgba(255,250,245,0.9), rgba(252,246,240,0.75));
    }
    .chat-head-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 10px;
    }
    .chat-head-title {
      font-family: "Cormorant Garamond", "Times New Roman", serif;
      font-size: 30px;
      margin: 0;
    }
    .chat-head-copy {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
      margin: 0;
    }
    .feed { padding: 18px; overflow:auto; min-height: 0; }
    .composer { padding: 16px 18px 18px; border-top: 1px solid rgba(223, 209, 196, 0.9); background: rgba(255,250,245,0.92); }
    .field { margin-bottom: 10px; }
    .field label { display:block; font-size:11px; color:var(--muted-soft); margin-bottom:6px; letter-spacing:0.14em; text-transform:uppercase; font-weight:700; }
    .field input, .field textarea {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 11px 13px;
      background: rgba(255,255,255,0.95);
      font-size: 14px;
      color: var(--ink);
    }
    .field select {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 11px 13px;
      background: rgba(255,255,255,0.95);
      font-size: 14px;
    }
    .btns { display:flex; gap:8px; flex-wrap:wrap; }
    .composer-controls {
      display: grid;
      gap: 10px;
      margin-bottom: 10px;
    }
    .composer-meta-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: end;
    }
    .composer-extras {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    }
    .composer-extras .source-switch {
      opacity: 0;
      max-height: 0;
      overflow: hidden;
      transition: opacity 0.2s ease, max-height 0.2s ease;
    }
    .composer-extras .source-switch.visible {
      opacity: 1;
      max-height: 50px;
    }
    .source-switch {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      justify-content: flex-end;
    }
    .source-option {
      border: 1px solid rgba(223, 209, 196, 0.96);
      border-radius: 999px;
      padding: 8px 12px;
      background: #fff;
      color: var(--ink);
      box-shadow: none;
      font-size: 12px;
      font-weight: 700;
    }
    .source-option.active {
      background: rgba(111, 47, 69, 0.08);
      border-color: rgba(111, 47, 69, 0.2);
      color: var(--accent);
    }
    .composer-note {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      margin-top: -2px;
    }
    .composer-input-row { display:flex; gap:10px; align-items:flex-end; }
    .composer-input-row .field { flex:1; margin-bottom:0; }
    .attach-icon-btn {
      width:42px; height:42px; flex-shrink:0; border-radius:50%;
      background:#fff; border:1px solid var(--line); color:var(--accent);
      display:flex; align-items:center; justify-content:center; cursor:pointer;
      transition: background 0.18s, border-color 0.18s, color 0.18s, transform 0.18s;
    }
    .attach-icon-btn:hover { background:var(--accent); color:#fff; border-color:var(--accent); transform: translateY(-1px); }
    .attach-icon-btn svg { width:18px; height:18px; fill:currentColor; }
    .composer.dragover { outline:2px dashed var(--accent); outline-offset:-6px; border-radius:24px; background:#f6eeea; }
    .img-preview-chip {
      display:inline-flex; align-items:center; gap:6px;
      background:#fff; border:1px solid var(--line); border-radius:16px;
      padding:4px 8px 4px 4px; margin-bottom:8px; max-width:220px;
    }
    .img-preview-chip img { height:48px; border-radius:6px; object-fit:cover; }
    .img-preview-chip .remove-x {
      width:18px; height:18px; border-radius:50%; background:#e8e3dd; border:none;
      font-size:12px; line-height:18px; cursor:pointer; color:var(--ink); padding:0;
      display:flex; align-items:center; justify-content:center;
    }
    .img-preview-chip .remove-x:hover { background:#9d1e1e; color:#fff; }
    button {
      border: 1px solid transparent;
      border-radius: 14px;
      padding: 10px 14px;
      font-weight: 600;
      cursor: pointer;
      background: var(--accent);
      color: #fff;
      box-shadow: 0 10px 22px rgba(111, 47, 69, 0.16);
    }
    button.secondary { background:#fff; color:var(--ink); border-color:var(--line); box-shadow:none; }
    .secondary.studio-link {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 10px 14px;
      background: #fff;
      color: var(--ink);
      text-decoration: none;
      font-weight: 600;
    }
    .bubble {
      padding: 13px 14px;
      border-radius: 18px;
      margin: 0 0 12px 0;
      max-width: 84%;
      border: 1px solid var(--line);
      line-height: 1.55;
      white-space: pre-wrap;
      box-shadow: 0 10px 22px rgba(45, 28, 22, 0.04);
    }
    .user { margin-left:auto; background:linear-gradient(180deg, #f9ecef, #f5e3e8); border-color:#e8c9d1; }
    .assistant { background:linear-gradient(180deg, #fff8f1, #f9efe5); border-color:#eadcc8; }
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
    .followup-groups {
      display: grid;
      gap: 10px;
      margin: 0 0 12px 0;
    }
    .followup-group {
      display: grid;
      gap: 6px;
    }
    .followup-group strong {
      font-size: 11px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted-soft);
    }
    .followup-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .chip {
      display:inline-block;
      margin: 0 6px 6px 0;
      padding:5px 10px;
      font-size:11px;
      border-radius:999px;
      background:#f4ebe2;
      border:1px solid #e6ddd2;
    }
    .stages {
      margin-top: 10px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,0.88);
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
    .rail-card h2 {
      margin: 0 0 8px 0;
      font-family: "Cormorant Garamond", "Times New Roman", serif;
      font-size: 26px;
      line-height: 1;
      font-weight: 600;
    }
    .mini-status {
      font-size: 12px;
      margin-top: 8px;
      min-height: 16px;
      color: var(--muted);
    }
    .mini-status.success { color: var(--accent); }
    .mini-status.error { color: #9d1e1e; }

    .action-list {
      display: grid;
      gap: 10px;
    }
    .action-card {
      display: grid;
      gap: 4px;
      padding: 13px 14px;
      border-radius: 16px;
      border: 1px solid rgba(223, 209, 196, 0.95);
      background: linear-gradient(180deg, rgba(255,255,255,0.84), rgba(247,239,232,0.96));
      cursor: pointer;
      transition: transform 0.18s ease, border-color 0.18s ease;
    }
    .action-card:hover { transform: translateY(-1px); border-color: rgba(111, 47, 69, 0.24); }
    .action-card strong { font-size: 15px; }
    .action-card span { color: var(--muted); font-size: 12px; line-height: 1.45; }
    .section-block {
      padding: 20px 20px 22px;
    }
    .section-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 14px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }
    .section-copy h2 {
      margin: 0 0 6px 0;
      font-family: "Cormorant Garamond", "Times New Roman", serif;
      font-size: 34px;
      line-height: 0.98;
    }
    .section-copy p {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
      max-width: 640px;
    }
    .wardrobe-toolbar {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    .wardrobe-stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .wardrobe-stat {
      border: 1px solid rgba(223, 209, 196, 0.92);
      border-radius: 18px;
      padding: 14px;
      background: rgba(255,255,255,0.76);
    }
    .wardrobe-stat strong {
      display: block;
      font-family: "Cormorant Garamond", "Times New Roman", serif;
      font-size: 30px;
      line-height: 1;
      margin: 6px 0;
    }
    .wardrobe-layout {
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(260px, 0.85fr);
      gap: 14px;
    }
    .wardrobe-closet,
    .wardrobe-insights {
      border: 1px solid rgba(223, 209, 196, 0.92);
      border-radius: 22px;
      background: rgba(255,255,255,0.72);
      padding: 16px;
    }
    .wardrobe-filter-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    .filter-chip {
      border: 1px solid rgba(223, 209, 196, 0.96);
      border-radius: 999px;
      padding: 8px 12px;
      background: #fff;
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      box-shadow: none;
    }
    .filter-chip.active {
      background: rgba(95, 106, 82, 0.12);
      border-color: rgba(95, 106, 82, 0.24);
      color: var(--wardrobe);
    }
    .closet-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .closet-card {
      border: 1px solid rgba(223, 209, 196, 0.92);
      border-radius: 18px;
      overflow: hidden;
      background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(248,239,231,0.92));
      display: grid;
      grid-template-rows: 180px auto;
      min-height: 320px;
    }
    .closet-image {
      position: relative;
      background: linear-gradient(180deg, #f6eee5, #efe4d8);
    }
    .closet-image img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .closet-placeholder {
      width: 100%;
      height: 100%;
      display: grid;
      place-items: center;
      color: var(--muted-soft);
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    .closet-body {
      padding: 14px;
      display: grid;
      gap: 10px;
      align-content: start;
    }
    .closet-body h3 {
      margin: 0;
      font-size: 16px;
      line-height: 1.25;
    }
    .closet-body p {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .closet-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .studio-btn {
      border: 1px solid rgba(223, 209, 196, 0.96);
      border-radius: 12px;
      padding: 8px 12px;
      background: #fff;
      color: var(--ink);
      box-shadow: none;
      font-size: 12px;
      font-weight: 700;
    }
    .insight-stack {
      display: grid;
      gap: 12px;
    }
    .insight-panel {
      border: 1px solid rgba(223, 209, 196, 0.92);
      border-radius: 18px;
      padding: 14px;
      background: rgba(255,250,245,0.9);
    }
    .insight-panel h3 {
      margin: 0 0 8px 0;
      font-size: 14px;
    }
    .insight-list {
      display: grid;
      gap: 8px;
    }
    .insight-list div {
      padding: 10px 12px;
      border-radius: 14px;
      background: rgba(247,239,232,0.92);
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .wardrobe-empty {
      border: 1px dashed rgba(223, 209, 196, 0.96);
      border-radius: 18px;
      padding: 26px;
      text-align: center;
      color: var(--muted);
      background: rgba(255,255,255,0.54);
    }
    .studio-link {
      text-decoration: none;
    }
    .memory-card {
      padding: 18px;
    }
    .memory-list {
      display: grid;
      gap: 10px;
      margin-top: 12px;
    }
    .memory-item {
      width: 100%;
      text-align: left;
      border: 1px solid rgba(223, 209, 196, 0.92);
      border-radius: 16px;
      padding: 12px 13px;
      background: rgba(255,255,255,0.78);
      color: var(--ink);
      box-shadow: none;
    }
    .memory-item strong {
      display: block;
      margin-bottom: 4px;
      font-size: 13px;
    }
    .memory-item span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    .memory-empty {
      padding: 18px;
      border: 1px dashed rgba(223, 209, 196, 0.96);
      border-radius: 18px;
      color: var(--muted);
      background: rgba(255,255,255,0.5);
      text-align: center;
      font-size: 13px;
      line-height: 1.5;
    }
    .style-code-layout {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
      gap: 14px;
    }
    .style-profile-card,
    .style-guidance-card {
      border: 1px solid rgba(223, 209, 196, 0.92);
      border-radius: 22px;
      background: rgba(255,255,255,0.78);
      padding: 18px;
    }
    .style-hero {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      align-items: start;
      margin-bottom: 16px;
    }
    .style-hero h3 {
      margin: 0 0 6px 0;
      font-family: "Cormorant Garamond", "Times New Roman", serif;
      font-size: 34px;
      line-height: 0.98;
    }
    .style-hero p {
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
      font-size: 14px;
      max-width: 540px;
    }
    .palette-chip-row,
    .style-code-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .palette-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 8px 12px;
      background: rgba(247,239,232,0.95);
      border: 1px solid rgba(223, 209, 196, 0.96);
      font-size: 12px;
      font-weight: 700;
      color: var(--ink);
    }
    .palette-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      border: 1px solid rgba(32, 25, 21, 0.08);
      flex: 0 0 auto;
    }
    .style-facts {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 16px;
    }
    .style-fact {
      border: 1px solid rgba(223, 209, 196, 0.92);
      border-radius: 18px;
      padding: 14px;
      background: rgba(255,250,245,0.92);
    }
    .style-fact strong {
      display: block;
      margin: 6px 0 4px;
      font-size: 18px;
      line-height: 1.2;
    }
    .style-fact p {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .style-list {
      display: grid;
      gap: 8px;
    }
    .style-list div {
      padding: 11px 12px;
      border-radius: 14px;
      background: rgba(247,239,232,0.92);
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .style-empty {
      border: 1px dashed rgba(223, 209, 196, 0.96);
      border-radius: 18px;
      padding: 24px;
      text-align: center;
      color: var(--muted);
      background: rgba(255,255,255,0.54);
    }
    .journey-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .journey-card {
      border: 1px solid rgba(223, 209, 196, 0.92);
      border-radius: 22px;
      background: rgba(255,255,255,0.78);
      padding: 18px;
      display: grid;
      gap: 14px;
    }
    .journey-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      flex-wrap: wrap;
    }
    .journey-head h3 {
      margin: 0 0 6px 0;
      font-family: "Cormorant Garamond", "Times New Roman", serif;
      font-size: 30px;
      line-height: 0.98;
    }
    .journey-head p {
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
      font-size: 14px;
    }
    .journey-box {
      border: 1px solid rgba(223, 209, 196, 0.92);
      border-radius: 18px;
      padding: 14px;
      background: rgba(255,250,245,0.92);
    }
    .journey-box strong {
      display: block;
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted-soft);
      margin-bottom: 8px;
    }
    .journey-box p {
      margin: 0;
      color: var(--ink);
      line-height: 1.6;
      font-size: 14px;
    }
    .journey-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .journey-empty {
      border: 1px dashed rgba(223, 209, 196, 0.96);
      border-radius: 18px;
      padding: 20px;
      text-align: center;
      color: var(--muted);
      background: rgba(255,255,255,0.54);
    }

    /* --- Outfit card: stylist-led recommendation module --- */
    .outfit-card {
      display: grid;
      grid-template-columns: 80px 1fr 40%;
      border: 1px solid var(--line);
      border-radius: 24px;
      overflow: hidden;
      background: linear-gradient(180deg, rgba(255,250,245,0.98), rgba(248,239,231,0.94));
      margin-bottom: 18px;
      min-height: 320px;
      animation: agentFadeIn 0.3s ease-out;
      box-shadow: 0 22px 46px rgba(51, 30, 21, 0.08);
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
    .outfit-source-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }
    .source-pill, .source-mini-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 6px 11px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      border: 1px solid transparent;
    }
    .source-pill.wardrobe, .source-mini-pill.wardrobe {
      color: var(--wardrobe);
      background: rgba(95, 106, 82, 0.1);
      border-color: rgba(95, 106, 82, 0.18);
    }
    .source-pill.catalog, .source-mini-pill.catalog {
      color: var(--accent);
      background: rgba(111, 47, 69, 0.08);
      border-color: rgba(111, 47, 69, 0.16);
    }
    .source-pill.hybrid, .source-mini-pill.hybrid {
      color: var(--gold);
      background: rgba(176, 138, 78, 0.1);
      border-color: rgba(176, 138, 78, 0.18);
    }
    .outfit-summary {
      background: rgba(255,255,255,0.72);
      border: 1px solid rgba(223, 209, 196, 0.92);
      border-radius: 18px;
      padding: 14px 14px 12px;
      margin-bottom: 12px;
    }
    .outfit-summary-label, .outfit-rationale-label {
      font-size: 11px;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--muted-soft);
      font-weight: 700;
      margin-bottom: 7px;
    }
    .outfit-summary-text {
      margin: 0;
      font-size: 14px;
      line-height: 1.65;
      color: var(--ink);
    }
    .outfit-item-source {
      display: flex;
      gap: 8px;
      align-items: center;
      margin: 6px 0 2px;
      flex-wrap: wrap;
    }
    .outfit-product-title {
      font-weight: 600;
      line-height: 1.45;
    }
    .outfit-rationale {
      margin: 12px 0 0;
      border: 1px solid rgba(223, 209, 196, 0.92);
      border-radius: 18px;
      background: rgba(255,255,255,0.7);
      overflow: hidden;
    }
    .outfit-rationale summary {
      list-style: none;
      cursor: pointer;
      padding: 13px 14px;
      font-weight: 700;
      color: var(--ink);
    }
    .outfit-rationale summary::-webkit-details-marker { display: none; }
    .outfit-rationale-body {
      padding: 0 14px 14px;
      display: grid;
      gap: 10px;
    }
    .rationale-note {
      border-top: 1px solid rgba(223, 209, 196, 0.7);
      padding-top: 10px;
    }
    .rationale-note strong {
      display: block;
      margin-bottom: 4px;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted-soft);
    }
    .rationale-note p {
      margin: 0;
      line-height: 1.55;
      color: var(--muted);
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
    .outfit-info .outfit-product {
      padding: 10px 0;
      border-top: 1px solid rgba(223, 209, 196, 0.82);
    }
    .outfit-info .outfit-product:first-of-type { border-top: none; }
    .outfit-info .outfit-product .product-header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 2px;
    }
    .outfit-info .outfit-product .btn-buy {
      display: inline-block;
      padding: 4px 12px;
      font-size: 12px;
      font-weight: 700;
      color: #fff;
      background: var(--accent, #6d28d9);
      border-radius: 4px;
      text-decoration: none;
      white-space: nowrap;
      flex-shrink: 0;
    }
    .outfit-info .outfit-product .btn-buy:hover {
      opacity: 0.85;
      text-decoration: none;
    }
    .outfit-info .outfit-chips { margin: 10px 0; }
    .outfit-radar { margin: 12px 0 4px; text-align: center; }
    .outfit-criteria { margin: 12px 0 4px; }
    .criteria-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }
    .criteria-label {
      width: 110px;
      flex-shrink: 0;
      font-size: 12px;
      font-weight: 600;
      color: var(--ink);
    }
    .criteria-track {
      flex: 1;
      height: 8px;
      background: #e0e0e0;
      border-radius: 4px;
      overflow: hidden;
    }
    .criteria-fill {
      height: 100%;
      border-radius: 4px;
      transition: width 0.3s ease;
    }
    .criteria-pct {
      width: 36px;
      text-align: right;
      font-size: 12px;
      font-weight: 600;
      color: var(--ink);
    }
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
    .reaction-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }
    .reaction-chip {
      border: 1px solid rgba(223, 209, 196, 0.96);
      border-radius: 999px;
      padding: 7px 11px;
      background: #fff;
      color: var(--ink);
      box-shadow: none;
      font-size: 11px;
      font-weight: 700;
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

    .skeleton-line {
      height: 14px;
      border-radius: 8px;
      background: linear-gradient(90deg, rgba(223,209,196,0.3) 25%, rgba(223,209,196,0.5) 50%, rgba(223,209,196,0.3) 75%);
      background-size: 200% 100%;
      animation: shimmer 1.5s ease-in-out infinite;
    }
    .skeleton-line + .skeleton-line { margin-top: 8px; }
    .skeleton-line.short { width: 60%; }
    .skeleton-line.medium { width: 80%; }
    .skeleton-line.tall { height: 22px; width: 50%; }
    .skeleton-card {
      border: 1px solid rgba(223,209,196,0.6);
      border-radius: 18px;
      padding: 16px;
      background: rgba(255,255,255,0.5);
    }
    .skeleton-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .skeleton-closet-card {
      border: 1px solid rgba(223,209,196,0.6);
      border-radius: 18px;
      overflow: hidden;
      background: rgba(255,255,255,0.5);
    }
    .skeleton-closet-img {
      height: 160px;
      background: linear-gradient(90deg, rgba(223,209,196,0.25) 25%, rgba(223,209,196,0.45) 50%, rgba(223,209,196,0.25) 75%);
      background-size: 200% 100%;
      animation: shimmer 1.5s ease-in-out infinite;
    }
    .skeleton-closet-body { padding: 14px; }
    @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

    .feed-welcome {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 24px;
      padding: 36px 18px;
      text-align: center;
      min-height: 300px;
    }
    .welcome-hero { max-width: 480px; }
    .welcome-title {
      font-family: "Cormorant Garamond", "Times New Roman", serif;
      font-size: 32px;
      line-height: 1.05;
      margin: 8px 0 10px;
    }
    .welcome-sub {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
      margin: 0;
    }
    .welcome-prompts {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      max-width: 520px;
      width: 100%;
    }
    .welcome-card {
      text-align: left;
      padding: 14px;
      border-radius: 18px;
      border: 1px solid rgba(223, 209, 196, 0.95);
      background: linear-gradient(180deg, rgba(255,255,255,0.84), rgba(247,239,232,0.96));
      cursor: pointer;
      transition: transform 0.18s ease, border-color 0.18s ease;
      box-shadow: none;
    }
    .welcome-card:hover { transform: translateY(-1px); border-color: rgba(111, 47, 69, 0.24); }
    .welcome-card strong { display: block; font-size: 15px; margin-bottom: 4px; }
    .welcome-card span { display: block; color: var(--muted); font-size: 12px; line-height: 1.45; }

    /* --- Tablet (768–900px) --- */
    @media (max-width: 900px) {
      .shell { padding: 18px 14px 22px; }
      .topbar { flex-direction: column; }
      .hub { grid-template-columns: 1fr; }
      .hero { grid-template-columns: 1fr; padding: 22px; min-height: auto; }
      .hero-title { font-size: 44px; max-width: none; }
      .insight-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .memory-grid { grid-template-columns: 1fr; }
      .composer-meta-row { grid-template-columns: 1fr; }
      .wardrobe-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .wardrobe-layout,
      .style-code-layout { grid-template-columns: 1fr; }
      .closet-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .style-facts,
      .journey-grid { grid-template-columns: 1fr; }
      .outfit-card {
        grid-template-columns: 80px minmax(0, 1fr);
        grid-template-rows: auto auto;
      }
      .outfit-info {
        grid-column: 1 / -1;
        border-left: none;
        border-top: 1px solid var(--line);
      }
    }

    @media (max-width: 600px) {
      .welcome-prompts { grid-template-columns: 1fr; }
      .welcome-title { font-size: 26px; }
    }

    /* --- Phone (≤430px) --- */
    @media (max-width: 430px) {
      .shell { padding: 14px 10px 0; }
      .topbar h1 { font-size: 32px; }
      .topbar p { font-size: 13px; }
      .section-nav { gap: 6px; }
      .section-nav a { padding: 7px 10px; font-size: 11px; }
      .hero { padding: 16px; }
      .hero-title { font-size: 34px; }
      .hero-sub { font-size: 14px; }
      .hero-link { padding: 10px 13px; font-size: 12px; }
      .hero-pills { gap: 6px; }
      .hero-pill { font-size: 11px; padding: 5px 9px; }
      .insight-grid { grid-template-columns: 1fr; }
      .wardrobe-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .closet-grid { grid-template-columns: 1fr; }
      .closet-card { grid-template-rows: 160px auto; min-height: auto; }
      .chat-head { padding: 14px 14px 10px; }
      .chat-head-title { font-size: 24px; }
      .chip-row { gap: 6px; }
      .context-chip { font-size: 11px; padding: 6px 9px; }
      .feed { padding: 14px; }
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
      .outfit-main-img { order: 1; min-height: 220px; }
      .outfit-info {
        order: 3;
        border-left: none;
        border-top: 1px solid var(--line);
        grid-column: auto;
      }
      /* Sticky composer on mobile */
      .page-chat.chat-shell {
        display: grid;
        grid-template-rows: auto 1fr auto;
        height: calc(100vh - 140px);
        height: calc(100dvh - 140px);
      }
      .composer {
        position: sticky;
        bottom: 0;
        z-index: 10;
        padding: 12px 14px 14px;
        border-radius: 20px 20px 0 0;
        box-shadow: 0 -8px 24px rgba(45, 28, 22, 0.06);
      }
      .composer-input-row { gap: 8px; }
      .composer-note { display: none; }
      .source-switch { gap: 6px; }
      .source-option { padding: 6px 10px; font-size: 11px; }
      .attach-icon-btn { width: 38px; height: 38px; }
      #message { font-size: 16px; }
      .section-copy h2 { font-size: 26px; }
      .style-hero h3 { font-size: 26px; }
      .wardrobe-stat strong { font-size: 24px; }
      .hero-stat-card strong { font-size: 24px; }
    }

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
      }
    }
  </style>
</head>
<body class="view-__ACTIVE_VIEW__">
  <div class="shell">
    <div class="topbar">
      <div class="brand-mark">
        <div class="eyebrow">Sigma Aura</div>
        <h1>Your wardrobe,<br/>styled with intention.</h1>
        <p>A fashion copilot that helps you dress, pair, check, and plan with your wardrobe first and the catalog only when it actually helps.</p>
      </div>
      <div class="top-actions">
        <button class="secondary" id="newConversationBtn">New Conversation</button>
        <button class="secondary" id="logoutBtn">Logout</button>
      </div>
    </div>
    <div class="handoff-banner" id="handoffBanner">
      <div>
        <strong id="handoffTitle">Continue Your Styling Thread</strong>
        <span id="handoffCopy">This web view can pick up where your last styling interaction left off.</span>
      </div>
      <div class="mode-chip" id="handoffMode">Web Studio</div>
    </div>
    <nav class="section-nav" aria-label="Main navigation">
      <a href="/?user=__USER_ID__&view=dashboard__NAV_PARAMS__" aria-label="Home dashboard">Home</a>
      <a href="/?user=__USER_ID__&view=chat__NAV_PARAMS__" aria-label="Stylist chat">Chat</a>
      <a href="/?user=__USER_ID__&view=wardrobe__NAV_PARAMS__" aria-label="Wardrobe studio">Wardrobe</a>
      <a href="/?user=__USER_ID__&view=style__NAV_PARAMS__" aria-label="Style code profile">Style Code</a>
      <a href="/?user=__USER_ID__&view=trips__NAV_PARAMS__" aria-label="Trips and planning">Trips</a>
    </nav>
    <div class="hub">
      <aside class="panel rail" role="complementary" aria-label="Styling jobs and session">
        <div class="rail-card">
          <div class="eyebrow">Today With Aura</div>
          <h2>Start with the right styling job.</h2>
          <p>Ask for an outfit, style a garment, check a look, or plan a trip without needing to guess what Aura can do.</p>
        </div>
        <div class="action-list" id="jobsRail">
          <button class="action-card" data-prompt="Build me a polished outfit from my wardrobe for tomorrow night.">
            <strong>Dress Me</strong>
            <span>Occasion outfits from your wardrobe first, with an optional catalog upgrade.</span>
          </button>
          <button class="action-card" data-prompt="What goes with this piece? Use my wardrobe first.">
            <strong>Style This</strong>
            <span>Pair around a garment from your wardrobe or the catalog.</span>
          </button>
          <button class="action-card" data-prompt="Rate my outfit and suggest wardrobe swaps.">
            <strong>Check Me</strong>
            <span>Get a stylist critique, wardrobe swaps, and optional next-step shopping help.</span>
          </button>
          <button class="action-card" data-prompt="What collar, color, and silhouette suit me best?">
            <strong>Know Me</strong>
            <span>Ask about color, pattern, collars, archetypes, and the lines that suit you.</span>
          </button>
          <button class="action-card" data-prompt="Plan me a 5-day trip capsule using my wardrobe first.">
            <strong>Trips</strong>
            <span>Build daypart-aware multi-look plans with packing and gap-fill suggestions.</span>
          </button>
          <a class="action-card studio-link" href="/?user=__USER_ID__&focus=wardrobe">
            <strong>Wardrobe</strong>
            <span>Open the direct wardrobe manager to edit metadata, remove items, and inspect coverage detail.</span>
          </a>
        </div>
        <div class="rail-card" id="stageRail">
          <div class="section-title">Session</div>
          <div class="field">
            <label>User ID</label>
            <input id="userId" value="__USER_ID__" />
          </div>
          <div class="field">
            <label>Conversation ID</label>
            <input id="conversationId" placeholder="auto-created on first send" readonly />
          </div>
          <div class="err" id="errorBox"></div>
        </div>
        <div class="rail-card">
          <div class="section-title">Agent Processing Stages</div>
          <p>Follow Aura’s stylist workflow as it builds your answer.</p>
          <div id="stageBox" class="stages"></div>
        </div>
      </aside>
      <main class="main-stack">
        <section class="panel hero page-view page-dashboard" id="stylistHub">
          <div class="hero-copy">
            <div>
              <div class="eyebrow">Stylist Studio</div>
              <h2 class="hero-title">A calmer, smarter way to decide what to wear.</h2>
              <p class="hero-sub">Use your wardrobe with more intention, check if an outfit really works, or ask Aura to build around a garment image in seconds.</p>
            </div>
            <div class="hero-pills">
              <span class="hero-pill">Wardrobe-first answers</span>
              <span class="hero-pill">Catalog-only when asked</span>
              <span class="hero-pill">Outfit checks</span>
              <span class="hero-pill">Trip capsules</span>
            </div>
            <div class="hero-actions">
              <a class="hero-link primary" href="/?user=__USER_ID__&view=chat__NAV_PARAMS__">Start In Chat</a>
              <a class="hero-link secondary" href="/?user=__USER_ID__&view=wardrobe__NAV_PARAMS__">Open Wardrobe</a>
              <a class="hero-link secondary" href="/?user=__USER_ID__&view=style__NAV_PARAMS__">See My Style Code</a>
            </div>
          </div>
          <div class="hero-stat-panel">
            <div class="hero-stat-card">
              <h3>Style Profile</h3>
              <strong id="heroStyleLabel">Loading&hellip;</strong>
              <p id="heroStyleCopy">Your style profile will appear here once loaded.</p>
            </div>
            <div class="hero-stat-card">
              <h3>Wardrobe</h3>
              <strong id="heroWardrobeLabel">Loading&hellip;</strong>
              <p id="heroWardrobeCopy">Your wardrobe summary will appear here once loaded.</p>
            </div>
          </div>
        </section>
        <section class="panel dashboard-snapshot page-view page-dashboard">
          <div>
            <div class="section-title">Start Here</div>
            <strong>Begin with one styling decision, then go deeper only if you need to.</strong>
            <p>The dashboard should point you into the right workspace. Use chat for active styling, wardrobe for closet work, style code for guidance, and trips for planning.</p>
          </div>
          <div class="mode-chip">Dashboard-first flow</div>
        </section>
        <section class="insight-grid page-view page-dashboard">
          <div class="panel insight-card">
            <div class="section-title">Wardrobe Health</div>
            <strong>Build from what you own first</strong>
            <p>Ask for wardrobe-only looks, pairing support, and catalog gap-fillers only when needed.</p>
          </div>
          <div class="panel insight-card">
            <div class="section-title">Styling Advice</div>
            <strong>Ask specific fashion questions</strong>
            <p>Collar, color, pattern, silhouette, and archetype advice are all supported directly in chat.</p>
          </div>
          <div class="panel insight-card">
            <div class="section-title">Trips And Planning</div>
            <strong>Plan by day and moment</strong>
            <p>Capsules now scale to trip duration and can mix wardrobe looks with catalog-supported additions.</p>
          </div>
        </section>
        <section class="memory-grid page-view page-dashboard">
          <div class="panel memory-card">
            <div class="section-title">Recent Threads</div>
            <strong>Jump back into real styling jobs</strong>
            <p class="chat-head-copy">Aura remembers the kind of requests you actually made here so repeat usage feels faster.</p>
            <div class="memory-list" id="recentThreadsList">
              <div class="memory-empty">Your recent styling threads will appear here after you start using the chat.</div>
            </div>
          </div>
          <div class="panel memory-card">
            <div class="section-title">Saved Looks</div>
            <strong>Keep the looks worth revisiting</strong>
            <p class="chat-head-copy">Save strong outfit directions from the feed and pull them back into chat when you want to refine or shop them.</p>
            <div class="memory-list" id="savedLooksList">
              <div class="memory-empty">Saved looks will appear here once recommendations come through.</div>
            </div>
          </div>
        </section>
        <section class="panel chat-shell page-view page-chat" id="stylistChat">
          <div class="chat-head">
            <div class="chat-head-top">
              <h2 class="chat-head-title">Stylist Chat</h2>
              <div class="mode-chip">Multimodal input</div>
            </div>
            <p class="chat-head-copy">Type, attach a garment image, or paste a product URL. Use quick modes to make the request feel more natural and more specific.</p>
            <div class="chip-row">
              <button class="secondary context-chip prompt-chip" data-prompt="Use my wardrobe first for this outfit.">Use My Wardrobe</button>
              <button class="secondary context-chip prompt-chip" data-prompt="Show me options from the catalog only.">Catalog Only</button>
              <button class="secondary context-chip prompt-chip" data-prompt="Build this for a work look.">For Work</button>
              <button class="secondary context-chip prompt-chip" data-prompt="Build this for dinner.">For Dinner</button>
              <button class="secondary context-chip prompt-chip" data-prompt="Explain why this works for me.">Explain Why</button>
            </div>
          </div>
          <div class="feed" id="feed" aria-live="polite" aria-label="Conversation feed">
            <div id="feedWelcome" class="feed-welcome">
              <div class="welcome-hero">
                <div class="eyebrow">Your Stylist Is Ready</div>
                <h3 class="welcome-title">What would you like to work on today?</h3>
                <p class="welcome-sub">Describe a styling need, attach a garment photo, or pick one of these starting points.</p>
              </div>
              <div class="welcome-prompts">
                <button class="welcome-card" data-prompt="Build me a polished outfit from my wardrobe for a dinner this weekend.">
                  <strong>Dress Me</strong>
                  <span>Get an occasion outfit from your wardrobe first</span>
                </button>
                <button class="welcome-card" data-prompt="Rate my outfit and suggest wardrobe swaps.">
                  <strong>Check My Outfit</strong>
                  <span>Upload a photo for a stylist critique</span>
                </button>
                <button class="welcome-card" data-prompt="What goes with this piece? Use my wardrobe first.">
                  <strong>Style A Piece</strong>
                  <span>Pair around a garment you already own</span>
                </button>
                <button class="welcome-card" data-prompt="What collar, color, and silhouette suit me best?">
                  <strong>Know My Style</strong>
                  <span>Profile-grounded fashion advice</span>
                </button>
              </div>
            </div>
          </div>
          <div class="composer" id="composerArea" role="form" aria-label="Message composer">
        <div class="composer-controls">
          <div id="urlFieldWrapper" class="composer-meta-row" style="display:none;">
            <div class="field">
              <label for="productUrl">Product URL</label>
              <input id="productUrl" type="url" placeholder="Paste a product link for buy/skip or pairing help" />
            </div>
            <button id="urlFieldClose" type="button" class="remove-x" style="align-self:end;margin-bottom:10px;" title="Close URL field">&times;</button>
          </div>
          <div class="composer-extras">
            <button id="urlFieldToggle" type="button" class="source-option" style="font-size:11px;">+ Product URL</button>
            <div class="source-switch" id="sourceSwitch" role="group" aria-label="Source preference">
              <button class="source-option active" type="button" data-source="auto" aria-pressed="true">Auto</button>
              <button class="source-option" type="button" data-source="wardrobe" aria-pressed="false">Wardrobe First</button>
              <button class="source-option" type="button" data-source="catalog" aria-pressed="false">Catalog Only</button>
              <button class="source-option" type="button" data-source="hybrid" aria-pressed="false">Blend Both</button>
            </div>
          </div>
        </div>
        <div id="imagePreview" style="display:none;">
          <div class="img-preview-chip">
            <img id="imagePreviewImg" />
            <span id="imageFileName" style="font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100px;"></span>
            <button id="imageRemoveBtn" type="button" class="remove-x">&times;</button>
          </div>
        </div>
        <div class="composer-input-row">
          <button id="attachImgBtn" type="button" class="attach-icon-btn" title="Attach a garment image">
            <svg viewBox="0 0 24 24"><path d="M21 19V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2zM8.5 13.5l2.5 3 3.5-4.5 4.5 6H5l3.5-4.5z"/></svg>
          </button>
          <div class="field">
            <textarea id="message" rows="3" placeholder="Describe the styling help you need, or attach / paste a garment image for pairing suggestions."></textarea>
          </div>
          <button id="sendBtn" title="Send message">Send</button>
        </div>
        <input id="chatImageFile" type="file" accept="image/*" style="display:none;" />
          </div>
        </section>
        <section class="panel section-block page-view page-wardrobe" id="wardrobeStudio">
          <div class="section-head">
            <div class="section-copy">
              <div class="eyebrow">Wardrobe Studio</div>
              <h2>Your closet, styled as a living asset.</h2>
              <p>See what Aura knows about your wardrobe, which occasions you already cover, and which saved pieces are ready to style straight into chat.</p>
            </div>
            <div class="top-actions">
              <button class="secondary" id="loadWardrobeStudioBtn">Refresh Closet</button>
              <a class="secondary studio-link" href="/?user=__USER_ID__&focus=wardrobe" style="display:inline-flex;align-items:center;">Open Manager</a>
            </div>
          </div>
          <div class="wardrobe-toolbar">
            <span class="mode-chip">Wardrobe-first intelligence</span>
            <span class="mode-chip" id="wardrobeStatusPill">Waiting for user id</span>
          </div>
          <div class="wardrobe-stats">
            <div class="wardrobe-stat">
              <div class="section-title">Saved Pieces</div>
              <strong id="wardrobeCountStat">0</strong>
              <p id="wardrobeCountCopy">Load your saved wardrobe to inspect your current closet coverage.</p>
            </div>
            <div class="wardrobe-stat">
              <div class="section-title">Completeness</div>
              <strong id="wardrobeCompletenessStat">0%</strong>
              <p>Wardrobe coverage for the occasions Aura expects you to dress for most often.</p>
            </div>
            <div class="wardrobe-stat">
              <div class="section-title">Coverage</div>
              <strong id="wardrobeCoverageStat">0</strong>
              <p>Occasion buckets with active wardrobe coverage.</p>
            </div>
            <div class="wardrobe-stat">
              <div class="section-title">Missing</div>
              <strong id="wardrobeGapStat">0</strong>
              <p>Gap areas where the catalog can help without replacing what you already own.</p>
            </div>
          </div>
          <div class="wardrobe-layout">
            <div class="wardrobe-closet">
              <div class="section-head" style="margin-bottom: 10px;">
                <div class="section-copy">
                  <div class="section-title">Closet View</div>
                  <h2 style="font-size:28px;">Saved pieces ready to style</h2>
                </div>
              </div>
              <div class="wardrobe-filter-row" id="wardrobeFilterRow" role="group" aria-label="Wardrobe filters">
                <button class="filter-chip active" type="button" data-filter="all" aria-pressed="true">All</button>
                <button class="filter-chip" type="button" data-filter="tops" aria-pressed="false">Tops</button>
                <button class="filter-chip" type="button" data-filter="bottoms" aria-pressed="false">Bottoms</button>
                <button class="filter-chip" type="button" data-filter="shoes" aria-pressed="false">Shoes</button>
                <button class="filter-chip" type="button" data-filter="occasion" aria-pressed="false">Occasion-ready</button>
              </div>
              <div class="closet-grid" id="wardrobeClosetGrid">
                <div class="wardrobe-empty" style="grid-column: 1 / -1;">Load your wardrobe to browse saved pieces in the studio.</div>
              </div>
            </div>
            <aside class="wardrobe-insights">
              <div class="insight-stack">
                <div class="insight-panel">
                  <h3>Wardrobe Health</h3>
                  <p class="chat-head-copy" id="wardrobeSummaryText">Aura will summarize how complete your closet is once wardrobe data is available.</p>
                </div>
                <div class="insight-panel">
                  <h3>What’s Missing</h3>
                  <div class="insight-list" id="wardrobeGapList">
                    <div>No gap analysis loaded yet.</div>
                  </div>
                </div>
                <div class="insight-panel">
                  <h3>Occasion Coverage</h3>
                  <div class="insight-list" id="wardrobeCoverageList">
                    <div>No occasion coverage data loaded yet.</div>
                  </div>
                </div>
              </div>
            </aside>
          </div>
        </section>
        <section class="panel section-block page-view page-style" id="styleCodeStudio">
          <div class="section-head">
            <div class="section-copy">
              <div class="eyebrow">My Style Code</div>
              <h2>Your profile, translated into styling direction.</h2>
              <p>Turn Aura’s analysis into practical guidance for color, collars, silhouette, and style identity instead of forcing yourself to remember raw profile attributes.</p>
            </div>
            <div class="top-actions">
              <button class="secondary" id="loadStyleCodeBtn">Refresh Profile</button>
            </div>
          </div>
          <div class="style-code-layout">
            <div class="style-profile-card">
              <div class="style-hero">
                <div>
                  <div class="section-title">Style Identity</div>
                  <h3 id="styleIdentityHeading">Profile not loaded yet</h3>
                  <p id="styleIdentityCopy">Load your user id to see Aura’s current view of your archetype blend, palette direction, and the lines that suit you.</p>
                </div>
                <span class="mode-chip" id="styleCodeStatusPill">Waiting for profile</span>
              </div>
              <div class="palette-chip-row" id="stylePaletteRow">
                <span class="palette-chip"><span class="palette-dot" style="background:#e7d9c2;"></span>Palette pending</span>
              </div>
              <div class="style-facts" id="styleFactsGrid">
                <div class="style-fact">
                  <div class="section-title">Primary Archetype</div>
                  <strong>Pending</strong>
                  <p>Refresh your profile to reveal your current style-code summary.</p>
                </div>
              </div>
            </div>
            <aside class="style-guidance-card">
              <div class="insight-stack">
                <div class="insight-panel">
                  <h3>What To Lean Into</h3>
                  <div class="style-list" id="styleLeanList">
                    <div>No guidance available yet.</div>
                  </div>
                </div>
                <div class="insight-panel">
                  <h3>Useful Styling Questions</h3>
                  <div class="style-list" id="stylePromptList">
                    <div>Ask Aura what collars, colors, or silhouettes suit you once your profile is loaded.</div>
                  </div>
                </div>
              </div>
            </aside>
          </div>
        </section>
        <section class="panel section-block page-view page-trips" id="journeyStudios">
          <div class="section-head">
            <div class="section-copy">
              <div class="eyebrow">Guided Flows</div>
              <h2>Critique a look or plan an entire trip.</h2>
              <p>These are two high-frequency stylist jobs. Both still run through chat, but the workspace now gives them dedicated framing, follow-through, and next-step actions.</p>
            </div>
          </div>
          <div class="journey-grid">
            <section class="journey-card">
              <div class="journey-head">
                <div>
                  <div class="section-title">Outfit Check</div>
                  <h3>Personal stylist critique</h3>
                  <p>Use Aura to assess your current look, suggest wardrobe swaps, and only then open the door to catalog upgrades.</p>
                </div>
                <span class="mode-chip" id="outfitCheckStatusPill">Ready</span>
              </div>
              <div class="journey-box">
                <strong>Current Read</strong>
                <p id="outfitCheckSummary">Attach a look or ask “rate my outfit” to start a wardrobe-first outfit check.</p>
              </div>
              <div class="journey-actions">
                <button class="secondary" type="button" data-flow-prompt="Rate my outfit and suggest wardrobe swaps.">Rate My Outfit</button>
                <button class="secondary" type="button" data-flow-prompt="What would improve this look from my wardrobe first?">Wardrobe Swaps</button>
                <button class="secondary" type="button" data-flow-prompt="Show me better options from the catalog for this look.">Catalog Upgrade</button>
              </div>
              <div class="journey-box">
                <strong>Best Follow-Up</strong>
                <div class="style-list" id="outfitCheckFollowups">
                  <div>What would improve this look?</div>
                </div>
              </div>
            </section>
            <section class="journey-card">
              <div class="journey-head">
                <div>
                  <div class="section-title">Trip Planner</div>
                  <h3>Capsule, timeline, packing logic</h3>
                  <p>Ask Aura to plan by trip length, daypart, and context so the result feels like a real packing strategy rather than a short list of repeated looks.</p>
                </div>
                <span class="mode-chip" id="tripPlannerStatusPill">Ready</span>
              </div>
              <div class="journey-box">
                <strong>Current Plan</strong>
                <p id="tripPlannerSummary">Ask for a trip capsule to get wardrobe-first looks, packing cues, and catalog-supported gap fillers.</p>
              </div>
              <div class="journey-actions">
                <button class="secondary" type="button" data-flow-prompt="Plan me a 3-day trip capsule using my wardrobe first.">3-Day Capsule</button>
                <button class="secondary" type="button" data-flow-prompt="Plan me a 5-day trip capsule using my wardrobe first.">5-Day Capsule</button>
                <button class="secondary" type="button" data-flow-prompt="Build a shopping list for my trip gaps.">Trip Shopping List</button>
              </div>
              <div class="journey-box">
                <strong>Plan Prompts</strong>
                <div class="style-list" id="tripPlannerFollowups">
                  <div>Build a shopping list</div>
                  <div>Show me catalog gap fillers</div>
                </div>
              </div>
            </section>
          </div>
        </section>
      </main>
    </div>
  </div>
  <script>
    const feed = document.getElementById("feed");
    const err = document.getElementById("errorBox");
    const userIdEl = document.getElementById("userId");
    const convIdEl = document.getElementById("conversationId");
    const handoffBanner = document.getElementById("handoffBanner");
    const handoffTitle = document.getElementById("handoffTitle");
    const handoffCopy = document.getElementById("handoffCopy");
    const handoffMode = document.getElementById("handoffMode");
    const messageEl = document.getElementById("message");
    const stageBox = document.getElementById("stageBox");
    const sendBtn = document.getElementById("sendBtn");
    const logoutBtn = document.getElementById("logoutBtn");
    const recentThreadsList = document.getElementById("recentThreadsList");
    const savedLooksList = document.getElementById("savedLooksList");
    const productUrlEl = document.getElementById("productUrl");
    const chatImageFileEl = document.getElementById("chatImageFile");
    const attachImgBtn = document.getElementById("attachImgBtn");
    const imagePreview = document.getElementById("imagePreview");
    const imagePreviewImg = document.getElementById("imagePreviewImg");
    const imageRemoveBtn = document.getElementById("imageRemoveBtn");
    const imageFileNameEl = document.getElementById("imageFileName");
    const composerArea = document.getElementById("composerArea");
    const promptButtons = Array.from(document.querySelectorAll("[data-prompt]"));
    const sourceSwitch = document.getElementById("sourceSwitch");
    const sourceButtons = Array.from(document.querySelectorAll("[data-source]"));
    const wardrobeStudioBtn = document.getElementById("loadWardrobeStudioBtn");
    const wardrobeStatusPill = document.getElementById("wardrobeStatusPill");
    const wardrobeCountStat = document.getElementById("wardrobeCountStat");
    const wardrobeCountCopy = document.getElementById("wardrobeCountCopy");
    const wardrobeCompletenessStat = document.getElementById("wardrobeCompletenessStat");
    const wardrobeCoverageStat = document.getElementById("wardrobeCoverageStat");
    const wardrobeGapStat = document.getElementById("wardrobeGapStat");
    const wardrobeSummaryText = document.getElementById("wardrobeSummaryText");
    const wardrobeGapList = document.getElementById("wardrobeGapList");
    const wardrobeCoverageList = document.getElementById("wardrobeCoverageList");
    const wardrobeClosetGrid = document.getElementById("wardrobeClosetGrid");
    const wardrobeFilterRow = document.getElementById("wardrobeFilterRow");
    const loadStyleCodeBtn = document.getElementById("loadStyleCodeBtn");
    const styleIdentityHeading = document.getElementById("styleIdentityHeading");
    const styleIdentityCopy = document.getElementById("styleIdentityCopy");
    const styleCodeStatusPill = document.getElementById("styleCodeStatusPill");
    const stylePaletteRow = document.getElementById("stylePaletteRow");
    const styleFactsGrid = document.getElementById("styleFactsGrid");
    const styleLeanList = document.getElementById("styleLeanList");
    const stylePromptList = document.getElementById("stylePromptList");
    const outfitCheckStatusPill = document.getElementById("outfitCheckStatusPill");
    const outfitCheckSummary = document.getElementById("outfitCheckSummary");
    const outfitCheckFollowups = document.getElementById("outfitCheckFollowups");
    const tripPlannerStatusPill = document.getElementById("tripPlannerStatusPill");
    const tripPlannerSummary = document.getElementById("tripPlannerSummary");
    const tripPlannerFollowups = document.getElementById("tripPlannerFollowups");
    const flowPromptButtons = Array.from(document.querySelectorAll("[data-flow-prompt]"));
    const RECENT_THREADS_KEY = "sigma_aura_recent_threads";
    const SAVED_LOOKS_KEY = "sigma_aura_saved_looks";
    let pendingImageData = "";
    let wardrobeItems = [];
    let wardrobeSummary = null;
    let activeWardrobeFilter = "all";
    let styleCodeData = null;
    let activeSourcePreference = "auto";
    const pageParams = new URLSearchParams(window.location.search);

    function setImagePreview(dataUrl, fileName) {
      pendingImageData = dataUrl;
      imagePreviewImg.src = dataUrl;
      imageFileNameEl.textContent = fileName || "Pasted image";
      imagePreview.style.display = "block";
      if (typeof updateSourceSwitchVisibility === "function") updateSourceSwitchVisibility();
    }
    function clearImagePreview() {
      pendingImageData = "";
      imagePreviewImg.src = "";
      imageFileNameEl.textContent = "";
      imagePreview.style.display = "none";
      chatImageFileEl.value = "";
      if (typeof updateSourceSwitchVisibility === "function") updateSourceSwitchVisibility();
    }
    function handleImageFile(file) {
      if (!file || file.type.indexOf("image") === -1) return;
      if (file.size > 10 * 1024 * 1024) { err.textContent = "Image must be under 10 MB."; return; }
      var reader = new FileReader();
      reader.onload = function(e) { setImagePreview(e.target.result, file.name); };
      reader.readAsDataURL(file);
    }
    function seedPrompt(text) {
      messageEl.value = text || "";
      messageEl.focus();
      messageEl.setSelectionRange(messageEl.value.length, messageEl.value.length);
      if (typeof updateSourceSwitchVisibility === "function") updateSourceSwitchVisibility();
    }
    function sourcePreferencePhrase(source) {
      if (source === "wardrobe") return "Use my wardrobe first.";
      if (source === "catalog") return "Show me options from the catalog only.";
      if (source === "hybrid") return "Blend my wardrobe with catalog options.";
      return "";
    }
    function focusTargetId(focus) {
      if (focus === "wardrobe") return "wardrobeStudio";
      if (focus === "planner") return "journeyStudios";
      if (focus === "tryon") return "journeyStudios";
      if (focus === "profile") return "styleCodeStudio";
      if (focus === "chat") return "stylistChat";
      return "stylistHub";
    }
    function configureHandoffBanner() {
      const source = String(pageParams.get("source") || "").trim().toLowerCase();
      const focus = String(pageParams.get("focus") || "").trim().toLowerCase();
      const conversationId = String(pageParams.get("conversation_id") || "").trim();
      if (conversationId && !convIdEl.value.trim()) {
        convIdEl.value = conversationId;
      }
      if (!source && !focus && !conversationId) return;
      handoffBanner.classList.add("show");
      if (source === "whatsapp") {
        handoffTitle.textContent = "WhatsApp To Web Handoff";
        handoffMode.textContent = "WhatsApp Continuity";
        handoffCopy.textContent = "You opened Aura from WhatsApp. The same styling thread can continue here with the richer visual workspace.";
      } else {
        handoffTitle.textContent = "Continue In Aura";
        handoffMode.textContent = "Web Studio";
        handoffCopy.textContent = "This view is carrying forward the styling context from your last entry point.";
      }
      const target = document.getElementById(focusTargetId(focus));
      if (target) {
        setTimeout(function() {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 80);
      }
    }
    function readStorageList(key) {
      try {
        const parsed = JSON.parse(window.localStorage.getItem(key) || "[]");
        return Array.isArray(parsed) ? parsed : [];
      } catch (_error) {
        return [];
      }
    }
    function writeStorageList(key, items) {
      try {
        window.localStorage.setItem(key, JSON.stringify(items.slice(0, 6)));
      } catch (_error) {
        // Ignore storage issues in lightweight UI persistence.
      }
    }
    function saveRecentThread(message) {
      const trimmed = String(message || "").trim();
      if (!trimmed) return;
      const existing = readStorageList(RECENT_THREADS_KEY).filter(function(entry) {
        return entry.message !== trimmed;
      });
      existing.unshift({
        message: trimmed,
        timestamp: new Date().toISOString(),
      });
      writeStorageList(RECENT_THREADS_KEY, existing);
      renderRecentThreads();
    }
    function saveLook(outfit, responseMetadata) {
      if (!outfit || !outfit.title) return;
      const existing = readStorageList(SAVED_LOOKS_KEY).filter(function(entry) {
        return entry.title !== outfit.title;
      });
      existing.unshift({
        title: outfit.title,
        summary: buildStylistSummary(outfit),
        source: inferOutfitSource(outfit, responseMetadata || {}),
        saved_at: new Date().toISOString(),
      });
      writeStorageList(SAVED_LOOKS_KEY, existing);
      renderSavedLooks();
    }
    function renderRecentThreads() {
      const threads = readStorageList(RECENT_THREADS_KEY);
      if (!threads.length) {
        recentThreadsList.innerHTML = '<div class="memory-empty">Your recent styling threads will appear here after you start using the chat.</div>';
        return;
      }
      recentThreadsList.innerHTML = threads.map(function(entry) {
        return '<button class="memory-item" type="button" data-memory-prompt="' + escapeHtml(entry.message) + '">' +
          '<strong>' + escapeHtml(entry.message.slice(0, 56)) + (entry.message.length > 56 ? "..." : "") + '</strong>' +
          '<span>Reuse this styling request in chat.</span>' +
        '</button>';
      }).join("");
    }
    function renderSavedLooks() {
      const looks = readStorageList(SAVED_LOOKS_KEY);
      if (!looks.length) {
        savedLooksList.innerHTML = '<div class="memory-empty">Saved looks will appear here once recommendations come through.</div>';
        return;
      }
      savedLooksList.innerHTML = looks.map(function(entry) {
        return '<button class="memory-item" type="button" data-memory-prompt="' + escapeHtml("Show me a look like " + entry.title + ".") + '">' +
          '<strong>' + escapeHtml(entry.title) + '</strong>' +
          '<span>' + escapeHtml(sourceBadgeLabel(normalizeSourceToken(entry.source) || "catalog")) + " • " + escapeHtml(entry.summary.slice(0, 88)) + (entry.summary.length > 88 ? "..." : "") + '</span>' +
        '</button>';
      }).join("");
    }
    attachImgBtn.addEventListener("click", function() { chatImageFileEl.click(); });
    imageRemoveBtn.addEventListener("click", clearImagePreview);
    const urlFieldWrapper = document.getElementById("urlFieldWrapper");
    const urlFieldToggle = document.getElementById("urlFieldToggle");
    const urlFieldClose = document.getElementById("urlFieldClose");
    urlFieldToggle.addEventListener("click", function() {
      urlFieldWrapper.style.display = "";
      urlFieldToggle.style.display = "none";
      document.getElementById("productUrl").focus();
    });
    urlFieldClose.addEventListener("click", function() {
      urlFieldWrapper.style.display = "none";
      urlFieldToggle.style.display = "";
      document.getElementById("productUrl").value = "";
    });
    chatImageFileEl.addEventListener("change", function() {
      handleImageFile(chatImageFileEl.files && chatImageFileEl.files[0]);
    });
    promptButtons.forEach(function(button) {
      button.addEventListener("click", function() {
        seedPrompt(button.dataset.prompt || "");
      });
    });
    sourceSwitch.addEventListener("click", function(event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const nextSource = target.dataset.source || "";
      if (!nextSource) return;
      activeSourcePreference = nextSource;
      sourceButtons.forEach(function(button) {
        const isActive = button.dataset.source === nextSource;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
    });
    flowPromptButtons.forEach(function(button) {
      button.addEventListener("click", function() {
        seedPrompt(button.dataset.flowPrompt || "");
      });
    });
    wardrobeStudioBtn.addEventListener("click", loadWardrobeStudio);
    wardrobeFilterRow.addEventListener("click", function(event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const nextFilter = target.dataset.filter || "";
      if (!nextFilter) return;
      activeWardrobeFilter = nextFilter;
      Array.from(wardrobeFilterRow.querySelectorAll("[data-filter]")).forEach(function(button) {
        const isActive = button.dataset.filter === nextFilter;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
      renderWardrobeCloset();
    });
    wardrobeClosetGrid.addEventListener("click", function(event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const prompt = target.dataset.wardrobePrompt || "";
      if (!prompt) return;
      seedPrompt(prompt);
    });
    loadStyleCodeBtn.addEventListener("click", loadStyleCode);
    stylePromptList.addEventListener("click", function(event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const prompt = target.dataset.stylePrompt || "";
      if (!prompt) return;
      seedPrompt(prompt);
    });
    recentThreadsList.addEventListener("click", function(event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const trigger = target.closest("[data-memory-prompt]");
      if (!(trigger instanceof HTMLElement)) return;
      const prompt = trigger.dataset.memoryPrompt || "";
      if (!prompt) return;
      seedPrompt(prompt);
    });
    savedLooksList.addEventListener("click", function(event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const trigger = target.closest("[data-memory-prompt]");
      if (!(trigger instanceof HTMLElement)) return;
      const prompt = trigger.dataset.memoryPrompt || "";
      if (!prompt) return;
      seedPrompt(prompt);
    });
    outfitCheckFollowups.addEventListener("click", function(event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const prompt = target.dataset.flowPrompt || "";
      if (!prompt) return;
      seedPrompt(prompt);
    });
    tripPlannerFollowups.addEventListener("click", function(event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const prompt = target.dataset.flowPrompt || "";
      if (!prompt) return;
      seedPrompt(prompt);
    });
    userIdEl.addEventListener("change", loadWardrobeStudio);
    userIdEl.addEventListener("change", loadStyleCode);
    messageEl.addEventListener("paste", function(e) {
      var items = (e.clipboardData || {}).items || [];
      for (var i = 0; i < items.length; i++) {
        if (items[i].type.indexOf("image") !== -1) {
          e.preventDefault();
          handleImageFile(items[i].getAsFile());
          return;
        }
      }
    });
    // Drag-and-drop support on the composer area
    composerArea.addEventListener("dragenter", function(e) { e.preventDefault(); composerArea.classList.add("dragover"); });
    composerArea.addEventListener("dragover", function(e) { e.preventDefault(); composerArea.classList.add("dragover"); });
    composerArea.addEventListener("dragleave", function(e) { e.preventDefault(); composerArea.classList.remove("dragover"); });
    composerArea.addEventListener("drop", function(e) {
      e.preventDefault();
      composerArea.classList.remove("dragover");
      var file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      handleImageFile(file);
    });

    function dismissFeedWelcome() {
      const w = document.getElementById("feedWelcome");
      if (w) w.remove();
    }

    function addBubble(text, kind, imageDataUrl) {
      dismissFeedWelcome();
      const div = document.createElement("div");
      div.className = "bubble " + kind;
      if (imageDataUrl) {
        const img = document.createElement("img");
        img.src = imageDataUrl;
        img.style.cssText = "max-height:120px;border-radius:8px;display:block;margin-bottom:6px;";
        div.appendChild(img);
      }
      div.appendChild(document.createTextNode(text));
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

    function normalizeSourceToken(value) {
      const normalized = String(value || "").toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
      if (!normalized) return "";
      if (normalized.indexOf("wardrobe") !== -1) return "wardrobe";
      if (normalized.indexOf("catalog") !== -1) return "catalog";
      if (normalized.indexOf("hybrid") !== -1) return "hybrid";
      return normalized;
    }

    function sourceBadgeLabel(source) {
      if (source === "wardrobe") return "From Your Wardrobe";
      if (source === "catalog") return "Catalog Pick";
      if (source === "hybrid") return "Wardrobe + Catalog";
      return "Styled Look";
    }

    function sourceBadgeClass(source) {
      if (source === "wardrobe" || source === "catalog" || source === "hybrid") return source;
      return "catalog";
    }

    function inferOutfitSource(outfit, responseMetadata) {
      const answerSource = normalizeSourceToken(responseMetadata && responseMetadata.answer_source);
      if (answerSource === "wardrobe") return "wardrobe";
      if (answerSource === "catalog") return "catalog";
      if (answerSource === "hybrid") return "hybrid";
      const itemSources = Array.from(new Set((outfit.items || []).map(function(item) {
        return normalizeSourceToken(item && item.source);
      }).filter(Boolean)));
      if (itemSources.includes("wardrobe") && itemSources.includes("catalog")) return "hybrid";
      if (itemSources.includes("wardrobe")) return "wardrobe";
      if (itemSources.includes("catalog")) return "catalog";
      return answerSource || "catalog";
    }

    function buildEvaluationCriteria(outfit, responseMetadata) {
      const isOutfitCheck = String(responseMetadata && responseMetadata.primary_intent || "").toLowerCase() === "outfit_check"
        || String(responseMetadata && responseMetadata.answer_source || "").toLowerCase().indexOf("outfit_check") !== -1;
      if (isOutfitCheck) {
        return [
          { key: "body_harmony_pct", label: "Body Harmony" },
          { key: "color_suitability_pct", label: "Color Suitability" },
          { key: "style_fit_pct", label: "Style Fit" },
          { key: "pairing_coherence_pct", label: "Pairing" },
          { key: "occasion_pct", label: "Occasion" },
        ];
      }
      return [
        { key: "body_harmony_pct", label: "Body Harmony" },
        { key: "color_suitability_pct", label: "Color Suitability" },
        { key: "style_fit_pct", label: "Style Fit" },
        { key: "risk_tolerance_pct", label: "Risk Tolerance" },
        { key: "occasion_pct", label: "Occasion" },
        { key: "comfort_boundary_pct", label: "Comfort" },
        { key: "specific_needs_pct", label: "Specific Needs" },
        { key: "pairing_coherence_pct", label: "Pairing" },
      ];
    }

    function buildStylistSummary(outfit) {
      const summary = String(outfit.reasoning || "").trim();
      if (summary) return summary;
      const notes = [
        outfit.body_note,
        outfit.color_note,
        outfit.style_note,
        outfit.occasion_note,
      ].map(function(value) { return String(value || "").trim(); }).filter(Boolean);
      if (notes.length) return notes[0];
      return "A balanced look assembled to work as a complete styling direction instead of a single item suggestion.";
    }

    function wardrobeImageUrl(item) {
      if (item.image_url) return item.image_url;
      var p = item.image_path || "";
      if (!p) return "";
      if (p.startsWith("http://") || p.startsWith("https://")) return p;
      return "/v1/onboarding/images/local?path=" + encodeURIComponent(p);
    }

    function wardrobeFilterMatches(item, filter) {
      if (filter === "all") return true;
      const category = String(item.garment_category || "").toLowerCase();
      const occasionFit = String(item.occasion_fit || "").toLowerCase();
      if (filter === "tops") {
        return ["top", "shirt", "blouse", "tee", "tshirt", "sweater", "knit", "jacket", "blazer"].some(function(token) {
          return category.indexOf(token) !== -1;
        });
      }
      if (filter === "bottoms") {
        return ["pant", "trouser", "jean", "skirt", "short"].some(function(token) {
          return category.indexOf(token) !== -1;
        });
      }
      if (filter === "shoes") {
        return ["shoe", "heel", "boot", "loafer", "sandal", "sneaker"].some(function(token) {
          return category.indexOf(token) !== -1;
        });
      }
      if (filter === "occasion") {
        return occasionFit.length > 0 && occasionFit !== "everyday";
      }
      return true;
    }

    function renderWardrobeInsights() {
      wardrobeCountStat.textContent = String(wardrobeItems.length || 0);
      wardrobeCountCopy.textContent = wardrobeItems.length
        ? "Your saved pieces are available for wardrobe-first dressing, pairing, and outfit-check flows."
        : "Load your saved wardrobe to inspect your current closet coverage.";
      wardrobeCompletenessStat.textContent = String((wardrobeSummary && wardrobeSummary.completeness_score_pct) || 0) + "%";
      const coverage = (wardrobeSummary && wardrobeSummary.occasion_coverage) || [];
      const gaps = (wardrobeSummary && ((wardrobeSummary.gap_items || []).concat(wardrobeSummary.missing_categories || []))) || [];
      wardrobeCoverageStat.textContent = String(coverage.filter(function(entry) { return Number(entry.item_count || 0) > 0; }).length);
      wardrobeGapStat.textContent = String(gaps.length || 0);
      wardrobeSummaryText.textContent = (wardrobeSummary && wardrobeSummary.summary)
        ? wardrobeSummary.summary
        : "Aura will summarize how complete your closet is once wardrobe data is available.";
      wardrobeGapList.innerHTML = gaps.length
        ? gaps.slice(0, 5).map(function(item) { return "<div>" + escapeHtml(item) + "</div>"; }).join("")
        : "<div>No immediate gaps detected yet.</div>";
      wardrobeCoverageList.innerHTML = coverage.length
        ? coverage.slice(0, 5).map(function(item) {
            return "<div>" + escapeHtml(item.label || item.key || "Occasion") + ": " + escapeHtml(String(item.item_count || 0)) + " piece(s)</div>";
          }).join("")
        : "<div>No occasion coverage data loaded yet.</div>";
      updateHeroStats();
    }

    function renderWardrobeCloset() {
      const filteredItems = wardrobeItems.filter(function(item) {
        return wardrobeFilterMatches(item, activeWardrobeFilter);
      });
      if (!filteredItems.length) {
        wardrobeClosetGrid.innerHTML = '<div class="wardrobe-empty" style="grid-column: 1 / -1;">No saved pieces match this filter yet.</div>';
        return;
      }
      wardrobeClosetGrid.innerHTML = filteredItems.slice(0, 9).map(function(item) {
        const imageUrl = wardrobeImageUrl(item);
        const tags = [item.garment_category, item.primary_color, item.occasion_fit].filter(Boolean).slice(0, 3);
        const title = item.title || "Wardrobe Item";
        const imageHtml = imageUrl
          ? '<img src="' + escapeHtml(imageUrl) + '" alt="' + escapeHtml(title) + '" loading="lazy" />'
          : '<div class="closet-placeholder">Saved Piece</div>';
        return '' +
          '<article class="closet-card">' +
            '<div class="closet-image">' + imageHtml + '</div>' +
            '<div class="closet-body">' +
              '<div>' +
                '<h3>' + escapeHtml(title) + '</h3>' +
                '<p>' + escapeHtml(item.description || "Saved in your wardrobe and ready to use as an outfit or pairing anchor.") + '</p>' +
              '</div>' +
              '<div class="tag-row">' +
                (tags.length ? tags.map(function(tag) { return '<span class="tag">' + escapeHtml(tag) + '</span>'; }).join("") : '<span class="tag">untagged</span>') +
              '</div>' +
              '<div class="closet-actions">' +
                '<button class="studio-btn" type="button" data-wardrobe-prompt="' + escapeHtml("Style my " + title + " from my wardrobe first.") + '">Style This</button>' +
                '<button class="studio-btn" type="button" data-wardrobe-prompt="' + escapeHtml("Build me an outfit around my " + title + " for the right occasion.") + '">Build A Look</button>' +
              '</div>' +
            '</div>' +
          '</article>';
      }).join("");
    }

    async function loadWardrobeStudio() {
      const userId = userIdEl.value.trim();
      if (!userId) {
        wardrobeStatusPill.textContent = "Waiting for user id";
        wardrobeItems = [];
        wardrobeSummary = null;
        renderWardrobeInsights();
        renderWardrobeCloset();
        return;
      }
      wardrobeStatusPill.textContent = "Loading closet";
      wardrobeClosetGrid.innerHTML = '<div class="skeleton-grid" style="grid-column:1/-1;">' +
        [0,1,2].map(function() {
          return '<div class="skeleton-closet-card"><div class="skeleton-closet-img"></div><div class="skeleton-closet-body"><div class="skeleton-line tall"></div><div class="skeleton-line medium"></div><div class="skeleton-line short"></div></div></div>';
        }).join("") + '</div>';
      try {
        const responses = await Promise.all([
          fetch("/v1/onboarding/wardrobe/" + encodeURIComponent(userId)),
          fetch("/v1/onboarding/wardrobe/" + encodeURIComponent(userId) + "/summary"),
        ]);
        if (!responses[0].ok || !responses[1].ok) {
          throw new Error("Unable to load wardrobe studio.");
        }
        const itemsPayload = await responses[0].json();
        const summaryPayload = await responses[1].json();
        wardrobeItems = itemsPayload.items || [];
        wardrobeSummary = summaryPayload || null;
        wardrobeStatusPill.textContent = wardrobeItems.length ? "Closet loaded" : "No saved pieces yet";
      } catch (error) {
        wardrobeItems = [];
        wardrobeSummary = null;
        wardrobeStatusPill.textContent = "Unable to load";
      }
      renderWardrobeInsights();
      renderWardrobeCloset();
    }

    function profileValue(entry) {
      if (entry && typeof entry === "object" && "value" in entry) {
        return String(entry.value || "").trim();
      }
      return String(entry || "").trim();
    }

    function paletteDotsForSeason(season) {
      const key = String(season || "").toLowerCase();
      if (key.indexOf("autumn") !== -1) return ["#a96a3f", "#6f5a39", "#c58a58"];
      if (key.indexOf("summer") !== -1) return ["#b7b8c7", "#d9c6d0", "#8aa0b6"];
      if (key.indexOf("winter") !== -1) return ["#1f2430", "#8c2f53", "#d8dbe7"];
      if (key.indexOf("spring") !== -1) return ["#f0b46b", "#d67a58", "#f1d68b"];
      return ["#e7d9c2", "#d8c2b1", "#b88b96"];
    }

    function buildStyleLeanList(data) {
      const items = [];
      if (data.primary) items.push(data.primary + " styling with " + (data.secondary ? data.secondary.toLowerCase() + " softness" : "clear polish"));
      if (data.seasonal) items.push(data.seasonal + " color direction with " + (data.contrast || "balanced") + " contrast handling");
      if (data.frame) items.push(data.frame + " lines and shapes that respect your frame");
      if (data.bodyShape) items.push("Silhouettes that work with a " + data.bodyShape + " shape");
      return items;
    }

    function buildStylePromptSuggestions(data) {
      const prompts = [];
      prompts.push("What collars suit my " + (data.frame ? data.frame.toLowerCase() : "profile") + "?");
      prompts.push("What colors work best for a " + (data.seasonal ? data.seasonal.toLowerCase() : "balanced palette") + " palette?");
      prompts.push("What silhouettes flatter my " + (data.bodyShape ? data.bodyShape.toLowerCase() : "shape") + "?");
      prompts.push("Show me outfits that feel " + (data.primary ? data.primary.toLowerCase() : "like me") + ".");
      return prompts;
    }

    function updateHeroStats() {
      const heroStyle = document.getElementById("heroStyleLabel");
      const heroStyleCopy = document.getElementById("heroStyleCopy");
      const heroWardrobe = document.getElementById("heroWardrobeLabel");
      const heroWardrobeCopy = document.getElementById("heroWardrobeCopy");
      if (heroStyle && styleCodeData) {
        heroStyle.textContent = styleCodeData.primary
          ? styleCodeData.primary + (styleCodeData.secondary ? " + " + styleCodeData.secondary : "")
          : "Profile in progress";
        heroStyleCopy.textContent = styleCodeData.seasonal
          ? styleCodeData.seasonal + " palette \u00b7 " + (styleCodeData.contrast || "Contrast pending") + " contrast"
          : "Use Aura to turn profile insight into daily outfit and pairing decisions.";
      }
      if (heroWardrobe && wardrobeSummary) {
        const pct = wardrobeSummary.completeness_score_pct || 0;
        const count = wardrobeItems.length;
        heroWardrobe.textContent = count + (count === 1 ? " piece" : " pieces") + " \u00b7 " + pct + "% ready";
        heroWardrobeCopy.textContent = pct >= 70
          ? "Strong coverage. Your wardrobe is a real styling asset."
          : pct >= 40
            ? "Growing nicely. A few more key pieces will unlock wardrobe-first answers."
            : "Just getting started. Add more pieces so Aura can style from what you own.";
      } else if (heroWardrobe && wardrobeItems.length > 0) {
        heroWardrobe.textContent = wardrobeItems.length + " pieces saved";
        heroWardrobeCopy.textContent = "Wardrobe summary loading.";
      }
    }

    function renderStyleCode() {
      if (!styleCodeData) {
        styleIdentityHeading.textContent = "Profile not loaded yet";
        styleIdentityCopy.textContent = "Load your user id to see Aura’s current view of your archetype blend, palette direction, and the lines that suit you.";
        styleCodeStatusPill.textContent = "Waiting for profile";
        stylePaletteRow.innerHTML = '<span class="palette-chip"><span class="palette-dot" style="background:#e7d9c2;"></span>Palette pending</span>';
        styleFactsGrid.innerHTML = '<div class="style-fact"><div class="section-title">Primary Archetype</div><strong>Pending</strong><p>Refresh your profile to reveal your current style-code summary.</p></div>';
        styleLeanList.innerHTML = "<div>No guidance available yet.</div>";
        stylePromptList.innerHTML = "<div>Ask Aura what collars, colors, or silhouettes suit you once your profile is loaded.</div>";
        return;
      }
      styleIdentityHeading.textContent = styleCodeData.primary
        ? styleCodeData.primary + (styleCodeData.secondary ? " + " + styleCodeData.secondary : "")
        : "Style profile in progress";
      styleIdentityCopy.textContent = styleCodeData.summary;
      styleCodeStatusPill.textContent = styleCodeData.ready ? "Profile loaded" : "Profile partial";
      stylePaletteRow.innerHTML = paletteDotsForSeason(styleCodeData.seasonal).map(function(color, index) {
        const labels = [styleCodeData.seasonal || "Palette", styleCodeData.contrast || "Contrast", styleCodeData.frame || "Frame"];
        return '<span class="palette-chip"><span class="palette-dot" style="background:' + color + ';"></span>' + escapeHtml(labels[index] || "Palette") + '</span>';
      }).join("");
      styleFactsGrid.innerHTML = [
        { label: "Primary Archetype", value: styleCodeData.primary || "Pending", copy: "The dominant style lens Aura is currently using." },
        { label: "Secondary Archetype", value: styleCodeData.secondary || "Not set", copy: "The softer secondary influence shaping your styling mix." },
        { label: "Seasonal Palette", value: styleCodeData.seasonal || "Pending", copy: "Color direction built from your analysis and draping results." },
        { label: "Silhouette Direction", value: styleCodeData.frame || "Pending", copy: "Frame and line direction used for collar and silhouette advice." },
        { label: "Contrast", value: styleCodeData.contrast || "Pending", copy: "How strong or soft your color and line contrast can go." },
        { label: "Body Shape", value: styleCodeData.bodyShape || "Pending", copy: "One input Aura uses when suggesting proportions and balance." },
      ].map(function(fact) {
        return '<div class="style-fact"><div class="section-title">' + escapeHtml(fact.label) + '</div><strong>' + escapeHtml(fact.value) + '</strong><p>' + escapeHtml(fact.copy) + '</p></div>';
      }).join("");
      styleLeanList.innerHTML = buildStyleLeanList(styleCodeData).map(function(item) {
        return "<div>" + escapeHtml(item) + "</div>";
      }).join("") || "<div>No guidance available yet.</div>";
      stylePromptList.innerHTML = buildStylePromptSuggestions(styleCodeData).map(function(item) {
        return '<div data-style-prompt="' + escapeHtml(item) + '">' + escapeHtml(item) + "</div>";
      }).join("");
      updateHeroStats();
    }

    async function loadStyleCode() {
      const userId = userIdEl.value.trim();
      if (!userId) {
        styleCodeData = null;
        renderStyleCode();
        return;
      }
      styleCodeStatusPill.textContent = "Loading profile";
      styleFactsGrid.innerHTML = [0,1,2,3].map(function() {
        return '<div class="skeleton-card"><div class="skeleton-line short"></div><div class="skeleton-line tall"></div><div class="skeleton-line medium"></div></div>';
      }).join("");
      styleLeanList.innerHTML = [0,1,2].map(function() {
        return '<div class="skeleton-line medium"></div>';
      }).join("");
      try {
        const responses = await Promise.all([
          fetch("/v1/onboarding/status/" + encodeURIComponent(userId)),
          fetch("/v1/onboarding/analysis/" + encodeURIComponent(userId)),
        ]);
        if (!responses[0].ok || !responses[1].ok) {
          throw new Error("Unable to load style code.");
        }
        const statusPayload = await responses[0].json();
        const analysisPayload = await responses[1].json();
        const profile = analysisPayload.profile || {};
        const stylePreference = profile.style_preference || {};
        const derived = analysisPayload.derived_interpretations || {};
        const attributes = analysisPayload.attributes || {};
        const primary = String(stylePreference.primaryArchetype || "").trim();
        const secondary = String(stylePreference.secondaryArchetype || "").trim();
        const seasonal = profileValue(derived.SeasonalColorGroup);
        const contrast = profileValue(derived.ContrastLevel);
        const frame = profileValue(derived.FrameStructure);
        const bodyShape = profileValue(attributes.BodyShape);
        const height = profileValue(derived.HeightCategory);
        styleCodeData = {
          ready: Boolean(statusPayload.style_preference_complete || primary || seasonal),
          primary: primary,
          secondary: secondary,
          seasonal: seasonal,
          contrast: contrast,
          frame: frame,
          bodyShape: bodyShape,
          height: height,
          summary: primary || seasonal
            ? "Aura sees you through a " + [primary, secondary].filter(Boolean).join(" + ") + " lens, grounded in " + (seasonal || "your evolving palette") + " color direction and " + (frame || "balanced") + " shape guidance."
            : "Your analysis is still incomplete, so Aura cannot yet build a full style-code summary.",
        };
      } catch (error) {
        styleCodeData = {
          ready: false,
          primary: "",
          secondary: "",
          seasonal: "",
          contrast: "",
          frame: "",
          bodyShape: "",
          height: "",
          summary: "Aura could not load your saved profile signals right now.",
        };
        styleCodeStatusPill.textContent = "Unable to load";
      }
      renderStyleCode();
    }

    function isOutfitCheckResult(result) {
      const metadata = result.metadata || {};
      const resolved = result.resolved_context || {};
      return String(metadata.primary_intent || "").toLowerCase() === "outfit_check"
        || String(metadata.answer_source || "").toLowerCase().indexOf("outfit_check") !== -1
        || String(resolved.style_goal || "").toLowerCase() === "outfit_check";
    }

    function isTripPlanningResult(result) {
      const metadata = result.metadata || {};
      const resolved = result.resolved_context || {};
      return String(metadata.answer_source || "").toLowerCase().indexOf("capsule") !== -1
        || String(metadata.primary_intent || "").toLowerCase() === "capsule_planning"
        || String(resolved.style_goal || "").toLowerCase().indexOf("capsule") !== -1
        || String(resolved.request_summary || "").toLowerCase().indexOf("trip") !== -1;
    }

    function updateJourneyStudios(result) {
      if (isOutfitCheckResult(result)) {
        outfitCheckStatusPill.textContent = "Latest critique";
        outfitCheckSummary.textContent = result.assistant_message || "Aura completed an outfit check.";
        const followups = (result.follow_up_suggestions || []).slice(0, 3);
        outfitCheckFollowups.innerHTML = followups.length
          ? followups.map(function(text) { return '<div data-flow-prompt="' + escapeHtml(text) + '">' + escapeHtml(text) + '</div>'; }).join("")
          : "<div>What would improve this look?</div>";
      }
      if (isTripPlanningResult(result)) {
        tripPlannerStatusPill.textContent = "Latest plan";
        const outfitCount = Array.isArray(result.outfits) ? result.outfits.length : 0;
        tripPlannerSummary.textContent = (result.assistant_message || "Aura built a trip plan.")
          + (outfitCount ? " " + outfitCount + " planned look(s) are currently attached." : "");
        const followups = (result.follow_up_suggestions || []).slice(0, 3);
        tripPlannerFollowups.innerHTML = followups.length
          ? followups.map(function(text) { return '<div data-flow-prompt="' + escapeHtml(text) + '">' + escapeHtml(text) + '</div>'; }).join("")
          : "<div>Build a shopping list</div>";
      }
    }

    function buildOutfitCard(outfit, conversationId, responseMetadata) {
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
      const outfitSource = inferOutfitSource(outfit, responseMetadata);
      const summaryText = buildStylistSummary(outfit);

      // Rank
      if (outfit.rank != null) {
        const rank = document.createElement("div");
        rank.className = "outfit-rank";
        rank.textContent = "#" + outfit.rank + " Recommendation";
        info.appendChild(rank);
      }

      const sourceRow = document.createElement("div");
      sourceRow.className = "outfit-source-row";
      const sourcePill = document.createElement("span");
      sourcePill.className = "source-pill " + sourceBadgeClass(outfitSource);
      sourcePill.textContent = sourceBadgeLabel(outfitSource);
      sourceRow.appendChild(sourcePill);
      if (outfit.tryon_image) {
        const tryOnPill = document.createElement("span");
        tryOnPill.className = "source-pill hybrid";
        tryOnPill.textContent = "Try-On Preview";
        sourceRow.appendChild(tryOnPill);
      }
      info.appendChild(sourceRow);

      // Title
      if (outfit.title) {
        const title = document.createElement("div");
        title.className = "outfit-title";
        title.textContent = outfit.title;
        info.appendChild(title);
      }

      const summaryCard = document.createElement("div");
      summaryCard.className = "outfit-summary";
      summaryCard.innerHTML =
        '<div class="outfit-summary-label">Stylist Summary</div>' +
        '<p class="outfit-summary-text">' + escapeHtml(summaryText) + '</p>';
      info.appendChild(summaryCard);

      // Per-product title + price + buy now
      for (const item of items) {
        const prod = document.createElement("div");
        prod.className = "outfit-product";
        const pTitle = item.title || item.product_id || "Untitled";
        const url = item.product_url || item.url || "";
        const itemSource = normalizeSourceToken(item.source) || outfitSource;
        let html = '<div class="product-header">' +
          '<span class="outfit-product-title">' + escapeHtml(pTitle) + '</span>';
        if (url) {
          html += '<a href="' + escapeHtml(url) + '" target="_blank" rel="noreferrer" class="btn-buy">Buy Now</a>';
        }
        html += '</div>';
        html += '<div class="outfit-item-source"><span class="source-mini-pill ' + escapeHtml(sourceBadgeClass(itemSource)) + '">' + escapeHtml(sourceBadgeLabel(itemSource)) + '</span>';
        if (item.role) {
          html += '<span class="chip">' + escapeHtml(item.role) + '</span>';
        }
        html += '</div>';
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
      canvas.setAttribute("role", "img");
      const radarAltParts = archetypes.map(function(a) {
        const v = Number(outfit.style_archetype_scores && outfit.style_archetype_scores[a.key]) || 0;
        return a.label + " " + v + "%";
      });
      canvas.setAttribute("aria-label", "Style archetype radar: " + radarAltParts.join(", "));
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

      // 8 evaluation criteria percentage bars
      const criteria = buildEvaluationCriteria(outfit, responseMetadata);
      const criteriaDiv = document.createElement("div");
      criteriaDiv.className = "outfit-criteria";
      for (const c of criteria) {
        const pct = outfit[c.key] || 0;
        const barColor = pct >= 80 ? "#2e7d32" : pct >= 60 ? "#f9a825" : "#c62828";
        const row = document.createElement("div");
        row.className = "criteria-row";
        row.innerHTML =
          '<span class="criteria-label">' + escapeHtml(c.label) + '</span>' +
          '<div class="criteria-track">' +
            '<div class="criteria-fill" style="width:' + pct + '%;background:' + barColor + ';"></div>' +
          '</div>' +
          '<span class="criteria-pct">' + pct + '%</span>';
        criteriaDiv.appendChild(row);
      }
      info.appendChild(criteriaDiv);

      const rationale = document.createElement("details");
      rationale.className = "outfit-rationale";
      const rationaleSummary = document.createElement("summary");
      rationaleSummary.textContent = "Why It Works";
      rationale.appendChild(rationaleSummary);
      const rationaleBody = document.createElement("div");
      rationaleBody.className = "outfit-rationale-body";
      [
        { label: "Body", value: outfit.body_note },
        { label: "Color", value: outfit.color_note },
        { label: "Style", value: outfit.style_note },
        { label: "Occasion", value: outfit.occasion_note },
      ].forEach(function(entry) {
        const value = String(entry.value || "").trim();
        if (!value) return;
        const note = document.createElement("div");
        note.className = "rationale-note";
        note.innerHTML =
          '<strong>' + escapeHtml(entry.label) + '</strong>' +
          '<p>' + escapeHtml(value) + '</p>';
        rationaleBody.appendChild(note);
      });
      if (!rationaleBody.children.length) {
        const note = document.createElement("div");
        note.className = "rationale-note";
        note.innerHTML =
          '<strong>Styling Direction</strong>' +
          '<p>' + escapeHtml(summaryText) + '</p>';
        rationaleBody.appendChild(note);
      }
      rationale.appendChild(rationaleBody);
      info.appendChild(rationale);

      // Feedback CTAs
      const fbWrap = document.createElement("div");
      fbWrap.className = "outfit-feedback";
      const likeBtn = document.createElement("button");
      likeBtn.className = "btn-like";
      likeBtn.textContent = "Like This";
      const saveBtn = document.createElement("button");
      saveBtn.className = "secondary";
      saveBtn.textContent = "Save Look";
      const dislikeBtn = document.createElement("button");
      dislikeBtn.className = "btn-dislike";
      dislikeBtn.textContent = "Didn't Like This";
      fbWrap.appendChild(likeBtn);
      fbWrap.appendChild(saveBtn);
      fbWrap.appendChild(dislikeBtn);
      info.appendChild(fbWrap);

      // Dislike form
      const dislikeForm = document.createElement("div");
      dislikeForm.className = "dislike-form";
      const reactionRow = document.createElement("div");
      reactionRow.className = "reaction-row";
      ["Too safe", "Too much", "Not me", "Weird pairing", "Show softer", "Show sharper"].forEach(function(label) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "reaction-chip";
        chip.textContent = label;
        chip.addEventListener("click", function() {
          ta.value = label;
          ta.focus();
          ta.setSelectionRange(ta.value.length, ta.value.length);
        });
        reactionRow.appendChild(chip);
      });
      dislikeForm.appendChild(reactionRow);
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
      saveBtn.addEventListener("click", function() {
        saveLook(outfit, responseMetadata || {});
        fbStatus.textContent = "Look saved for later.";
        fbStatus.className = "feedback-status success";
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
      wrap.className = "followup-groups";
      const grouped = {
        "Improve It": [],
        "Show Alternatives": [],
        "Explain Why": [],
        "Shop The Gap": [],
        "Save For Later": [],
      };
      function bucketFor(text) {
        const normalized = String(text || "").toLowerCase();
        if (normalized.indexOf("explain") !== -1 || normalized.indexOf("why") !== -1) return "Explain Why";
        if (normalized.indexOf("save") !== -1 || normalized.indexOf("later") !== -1) return "Save For Later";
        if (normalized.indexOf("catalog") !== -1 || normalized.indexOf("shop") !== -1 || normalized.indexOf("buy") !== -1) return "Shop The Gap";
        if (normalized.indexOf("more") !== -1 || normalized.indexOf("different") !== -1 || normalized.indexOf("alternative") !== -1) return "Show Alternatives";
        return "Improve It";
      }
      for (const text of suggestions) {
        grouped[bucketFor(text)].push(text);
      }
      Object.entries(grouped).forEach(function(entry) {
        const label = entry[0];
        const items = entry[1];
        if (!items.length) return;
        const section = document.createElement("div");
        section.className = "followup-group";
        const title = document.createElement("strong");
        title.textContent = label;
        const row = document.createElement("div");
        row.className = "followup-row";
        items.forEach(function(text) {
          const btn = document.createElement("button");
          btn.className = "secondary";
          btn.style.cssText = "font-size:13px;padding:6px 14px;border-radius:999px;";
          btn.textContent = text;
          btn.addEventListener("click", function() {
            messageEl.value = text;
            wrap.remove();
            send();
          });
          row.appendChild(btn);
        });
        section.appendChild(title);
        section.appendChild(row);
        wrap.appendChild(section);
      });
      feed.appendChild(wrap);
      feed.scrollTop = feed.scrollHeight;
    }

    function renderOutfits(outfits, conversationId, responseMetadata) {
      if (!outfits || !outfits.length) return;
      for (const outfit of outfits) {
        const card = buildOutfitCard(outfit, conversationId, responseMetadata || {});
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
      const res = await fetch("/v1/conversations/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userIdEl.value.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to resolve conversation");
      convIdEl.value = data.conversation_id;
      addMeta(data.reused_existing ? "conversation resumed" : "conversation created");
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
      let message = messageEl.value.trim();
      const productUrl = productUrlEl.value.trim();
      if (!userId) {
        err.textContent = "User ID is required.";
        return;
      }
      if (!message && !pendingImageData && !productUrl) {
        err.textContent = "Message is required.";
        return;
      }
      if (!message && pendingImageData && !productUrl) {
        message = "What goes with this? Show me pairing options.";
      }
      if (!message && productUrl) {
        message = "Should I buy this? " + productUrl;
      } else if (productUrl) {
        message = message + " " + productUrl;
      }
      const sourcePhrase = sourcePreferencePhrase(activeSourcePreference);
      if (sourcePhrase && message.toLowerCase().indexOf(sourcePhrase.toLowerCase()) === -1) {
        message = sourcePhrase + " " + message;
      }
      saveRecentThread(message);
      sendBtn.disabled = true;
      messageEl.disabled = true;
      try {
        const conversationId = await ensureConversation();
        const attachedImage = pendingImageData;
        addBubble(message, "user", attachedImage);
        messageEl.value = "";
        productUrlEl.value = "";
        clearImagePreview();
        const payload = { user_id: userId, message: message };
        if (attachedImage) payload.image_data = attachedImage;
        const res = await fetch("/v1/conversations/" + conversationId + "/turns/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const job = await res.json();
        if (!res.ok) throw new Error(job.detail || "Failed to start turn");
        const result = await pollJob(conversationId, job.job_id);
        addBubble(result.assistant_message || "", "assistant");
        if (result.response_type === "clarification") {
          renderQuickReplies(result.follow_up_suggestions || []);
        } else {
          renderOutfits(result.outfits || [], conversationId, result.metadata || {});
          renderQuickReplies(result.follow_up_suggestions || []);
        }
        updateJourneyStudios(result);
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
    function updateSourceSwitchVisibility() {
      const hasContent = messageEl.value.trim().length > 0 || pendingImageData;
      sourceSwitch.classList.toggle("visible", !!hasContent);
    }
    messageEl.addEventListener("input", updateSourceSwitchVisibility);
    addBubble(
      "Tell me what you want to wear, what you want to style, or what you want to understand about your profile. I can work wardrobe-first, catalog-only, or blend both.",
      "assistant"
    );
    configureHandoffBanner();
    renderRecentThreads();
    renderSavedLooks();
    renderWardrobeInsights();
    renderWardrobeCloset();
    renderStyleCode();
    if (userIdEl.value.trim()) {
      loadWardrobeStudio();
      loadStyleCode();
    }
  </script>
</body>
</html>
"""
    resolved_view = (active_view or "dashboard").strip().lower()
    if resolved_view not in {"dashboard", "chat", "wardrobe", "style", "trips"}:
      resolved_view = "dashboard"
    nav_parts = []
    if source:
      nav_parts.append(f"&source={escape(source)}")
    if focus:
      nav_parts.append(f"&focus={escape(focus)}")
    if conversation_id:
      nav_parts.append(f"&conversation_id={escape(conversation_id)}")
    return (
        html.replace("__USER_ID__", escape(user_id))
        .replace("__ACTIVE_VIEW__", escape(resolved_view))
        .replace("__NAV_PARAMS__", "".join(nav_parts))
    )
