from html import escape


def get_web_ui_html(
    user_id: str = "",
    active_view: str = "chat",
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
    /* ===== Design Tokens ===== */
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
      --header-h: 44px;
      --rail-w: 280px;
    }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; } }

    /* ===== Reset & Base ===== */
    *, *::before, *::after { box-sizing: border-box; margin: 0; }
    body {
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(184, 139, 150, 0.22), transparent 28%),
        radial-gradient(circle at 85% 12%, rgba(176, 138, 78, 0.14), transparent 24%),
        linear-gradient(180deg, #fbf6f1 0%, var(--bg) 42%, #f1e6da 100%);
      height: 100vh; overflow: hidden;
      display: flex; flex-direction: column;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }

    /* ===== View switching ===== */
    .page-view { display: none !important; }
    body.view-chat .page-chat { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow: hidden; }
    body.view-wardrobe .page-wardrobe { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body.view-results .page-results { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body.view-profile .page-profile { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body.view-edit-profile .page-profile { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body:not(.view-chat) .history-rail { display: none !important; }

    /* ===== App Header ===== */
    .app-header {
      height: var(--header-h); flex-shrink: 0;
      position: relative; z-index: 10;
      display: flex; align-items: center; gap: 16px;
      padding: 0 20px;
      background: rgba(255, 251, 246, 0.88);
      backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
      border-bottom: 1px solid var(--line);
    }
    .header-brand {
      font-family: "Cormorant Garamond", Georgia, serif;
      font-size: 20px; font-weight: 700; color: var(--accent);
      letter-spacing: -0.02em; cursor: pointer; white-space: nowrap;
    }
    .header-nav { display: flex; gap: 4px; margin-left: 12px; }
    .header-nav a {
      padding: 6px 16px; border-radius: 999px; font-size: 13px; font-weight: 600;
      color: var(--muted); transition: all 140ms ease; text-decoration: none;
    }
    .header-nav a:hover { background: rgba(111, 47, 69, 0.06); color: var(--ink); }
    .header-nav a.active { background: rgba(111, 47, 69, 0.10); color: var(--accent); }
    .header-actions { margin-left: auto; display: flex; align-items: center; gap: 10px; }
    .new-chat-btn {
      padding: 5px 14px; border-radius: 999px; border: 1px solid var(--line);
      background: var(--surface); font-size: 12px; font-weight: 600; color: var(--ink);
      cursor: pointer; transition: all 140ms ease;
    }
    .new-chat-btn:hover { border-color: var(--accent); color: var(--accent); }
    .avatar-menu { position: relative; }
    .avatar-btn {
      width: 30px; height: 30px; border-radius: 50%; border: 1.5px solid var(--line);
      background: var(--surface-alt); font-size: 14px; cursor: pointer;
      display: flex; align-items: center; justify-content: center; transition: border-color 140ms ease;
    }
    .avatar-btn:hover { border-color: var(--accent); }
    .avatar-dropdown {
      display: none; position: absolute; top: calc(100% + 6px); right: 0;
      min-width: 170px; background: var(--surface); border: 1px solid var(--line);
      border-radius: 12px; padding: 6px 0; box-shadow: var(--shadow); z-index: 200;
    }
    .avatar-dropdown.open { display: block; }
    .avatar-dropdown a, .avatar-dropdown button {
      display: block; width: 100%; text-align: left; padding: 10px 18px;
      font-size: 13px; font-weight: 500; color: var(--ink); background: none; border: none;
      cursor: pointer; text-decoration: none;
    }
    .avatar-dropdown a:hover, .avatar-dropdown button:hover { background: var(--surface-alt); }
    .avatar-dropdown .divider { height: 1px; background: var(--line); margin: 4px 0; }

    /* ===== App Body ===== */
    .app-body {
      flex: 1; display: flex; overflow: hidden; min-height: 0;
    }

    /* ===== Chat History Sidebar ===== */
    .history-rail {
      width: var(--rail-w); min-width: var(--rail-w); height: 100%;
      border-right: 1px solid var(--line);
      background: rgba(255, 251, 246, 0.65);
      display: flex; flex-direction: column; overflow: hidden;
    }
    .history-header {
      padding: 16px 18px 12px; display: flex; align-items: center; justify-content: space-between;
    }
    .history-header span { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }
    .history-list { flex: 1; overflow-y: auto; padding: 0 8px 12px; }
    .history-item {
      display: block; width: 100%; text-align: left; padding: 10px 12px;
      border-radius: 10px; border: none; background: none; cursor: pointer;
      font-size: 13px; color: var(--ink); transition: background 100ms ease;
      margin-bottom: 2px; position: relative;
    }
    .history-item:hover { background: rgba(111, 47, 69, 0.06); }
    .history-item.active { background: rgba(111, 47, 69, 0.10); font-weight: 600; }
    .history-item .preview { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-right: 44px; }
    .history-item .ts { display: block; font-size: 11px; color: var(--muted-soft); margin-top: 2px; }
    .history-actions {
      position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
      display: none; gap: 2px;
    }
    .history-item:hover .history-actions { display: flex; }
    .history-action-btn {
      width: 22px; height: 22px; border: none; background: none; cursor: pointer;
      border-radius: 6px; font-size: 12px; color: var(--muted); padding: 0;
      display: flex; align-items: center; justify-content: center;
    }
    .history-action-btn:hover { background: rgba(111, 47, 69, 0.12); color: var(--ink); }
    .history-rename-input {
      width: 100%; padding: 4px 8px; border: 1px solid var(--accent); border-radius: 6px;
      font-family: inherit; font-size: 13px; color: var(--ink); background: #fff; outline: none;
    }
    .history-empty { padding: 24px 18px; font-size: 13px; color: var(--muted); line-height: 1.5; }

    /* ===== Chat Main ===== */
    /* Chat internals */
    .chat-feed {
      flex: 1; overflow-y: auto; padding: 24px 24px 12px; max-width: 780px;
      margin: 0 auto; width: 100%;
    }

    /* Welcome screen */
    .feed-welcome { text-align: center; padding: 60px 16px 24px; }
    .feed-welcome .eyebrow {
      font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.16em;
      color: var(--accent-soft); margin-bottom: 10px;
    }
    .feed-welcome h2 {
      font-family: "Cormorant Garamond", Georgia, serif;
      font-size: 28px; font-weight: 600; line-height: 1.15; margin-bottom: 8px; color: var(--ink);
    }
    .feed-welcome p { font-size: 14px; color: var(--muted); max-width: 420px; margin: 0 auto 24px; line-height: 1.5; }
    /* Primary action — one dominant entry point for first-time users */
    .prompt-primary {
      display: inline-flex; align-items: center; justify-content: center;
      padding: 16px 28px; border-radius: 999px; border: 0;
      background: linear-gradient(135deg, var(--accent), var(--accent-soft));
      color: #fff; font-size: 15px; font-weight: 600; letter-spacing: 0.01em;
      cursor: pointer; box-shadow: 0 6px 22px rgba(111, 47, 69, 0.20);
      transition: transform 140ms ease, box-shadow 140ms ease;
    }
    .prompt-primary:hover { transform: translateY(-1px); box-shadow: 0 10px 26px rgba(111, 47, 69, 0.26); }
    .prompt-more-toggle {
      display: inline-block; margin-top: 14px; padding: 6px 10px;
      background: transparent; border: 0; cursor: pointer;
      font-size: 12px; color: var(--muted); letter-spacing: 0.04em;
    }
    .prompt-more-toggle:hover { color: var(--accent); }
    .prompt-more-toggle .chev { display: inline-block; transition: transform 160ms ease; }
    .prompt-more-toggle.open .chev { transform: rotate(180deg); }
    .prompt-grid {
      display: grid; grid-template-columns: 1fr 1fr; gap: 10px; max-width: 480px;
      margin: 12px auto 0;
      max-height: 0; overflow: hidden; opacity: 0;
      transition: max-height 220ms ease, opacity 200ms ease, margin 200ms ease;
    }
    .prompt-grid.open { max-height: 320px; opacity: 1; margin: 16px auto 0; }
    .prompt-card {
      padding: 14px 16px; border-radius: 14px; border: 1px solid var(--line);
      background: var(--surface); cursor: pointer; text-align: left;
      font-size: 13px; font-weight: 500; color: var(--ink); line-height: 1.4;
      transition: border-color 120ms ease, box-shadow 120ms ease;
    }
    .prompt-card:hover { border-color: var(--accent-soft); box-shadow: 0 2px 12px rgba(111, 47, 69, 0.08); }
    @media (prefers-reduced-motion: reduce) {
      .prompt-grid, .prompt-more-toggle .chev, .prompt-primary { transition: none; }
    }

    /* Bubbles */
    .bubble {
      max-width: 85%; padding: 12px 16px; border-radius: 18px;
      font-size: 14px; line-height: 1.55; margin-bottom: 8px; word-wrap: break-word;
    }
    /* Assistant bubble structured content (paragraphs + bullet lists)
       — used by renderAssistantMarkup() to render StyleAdvisor /
       explanation_request responses with proper semantic HTML. */
    .bubble p { margin: 0 0 8px 0; }
    .bubble p:last-child { margin-bottom: 0; }
    .bubble ul { margin: 0 0 8px 0; padding-left: 20px; }
    .bubble ul:last-child { margin-bottom: 0; }
    .bubble li { margin-bottom: 4px; }
    .bubble li:last-child { margin-bottom: 0; }
    .bubble.user {
      margin-left: auto;
      background: linear-gradient(135deg, rgba(111, 47, 69, 0.10), rgba(184, 139, 150, 0.16));
      border-bottom-right-radius: 6px;
    }
    .bubble.assistant {
      margin-right: auto;
      background: linear-gradient(135deg, var(--surface), var(--surface-alt));
      border: 1px solid var(--line);
      border-bottom-left-radius: 6px;
    }
    .bubble.agent {
      margin-right: auto; background: transparent; font-size: 12px;
      color: var(--muted); padding: 4px 16px;
      opacity: 1;
      transition: opacity 360ms ease;
    }
    .bubble.agent .dot {
      display: inline-block; width: 6px; height: 6px; border-radius: 50%;
      background: var(--accent); margin-right: 6px; vertical-align: middle;
      animation: pulse 1.2s infinite ease-in-out;
    }
    .bubble.agent.done .dot { animation: none; background: var(--wardrobe); }
    .bubble.agent.fading { opacity: 0; pointer-events: none; }
    @media (prefers-reduced-motion: reduce) {
      .bubble.agent { transition: none; }
    }
    .bubble.meta { font-size: 11px; color: var(--muted-soft); text-align: center; max-width: 100%; background: none; padding: 4px 0; }
    @keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }

    /* Follow-up suggestions */
    .followup-groups { margin: 12px 0; }
    .followup-group { margin-bottom: 10px; }
    .followup-group strong { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); display: block; margin-bottom: 6px; }
    .followup-row { display: flex; flex-wrap: wrap; gap: 6px; }

    /* Stage progress (subtle) */
    .stage-bar {
      padding: 0 24px; max-width: 780px; margin: 0 auto; width: 100%;
      font-size: 11px; color: var(--muted-soft); min-height: 18px;
    }
    .stage-bar:empty { display: none; }

    /* ===== Chat Composer ===== */
    .composer-wrap {
      padding: 8px 24px 16px; max-width: 780px; margin: 0 auto; width: 100%;
    }
    .composer-outer {
      background: var(--surface); border: 1.5px solid var(--line);
      border-radius: 24px;
      transition: border-color 140ms ease, box-shadow 140ms ease;
    }
    .composer-outer:focus-within { border-color: var(--accent-soft); box-shadow: 0 0 0 3px rgba(111, 47, 69, 0.06); }
    .composer-outer.dragover { border-color: var(--accent); background: rgba(111, 47, 69, 0.03); }
    .image-chip {
      display: none; align-items: center; gap: 8px;
      padding: 8px 12px 0; max-width: fit-content;
    }
    .image-chip.visible { display: flex; }
    .image-chip .chip-inner {
      display: flex; align-items: center; gap: 8px;
      padding: 4px 10px 4px 4px; border-radius: 10px;
      background: var(--surface-alt); border: 1px solid var(--line);
    }
    .image-chip img { height: 36px; border-radius: 6px; }
    .image-chip .name { font-size: 12px; color: var(--muted); max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .image-chip .remove {
      background: none; border: none; cursor: pointer;
      font-size: 14px; color: var(--muted); padding: 2px 4px;
    }
    .image-chip .remove:hover { color: var(--accent); }
    .composer {
      display: flex; align-items: flex-end; gap: 0;
      padding: 6px 8px 6px 6px;
    }
    .plus-menu { position: relative; flex-shrink: 0; align-self: flex-end; }
    .plus-btn {
      width: 32px; height: 32px; border-radius: 50%; border: none;
      background: transparent; color: var(--muted);
      font-size: 20px; cursor: pointer; display: flex; align-items: center; justify-content: center;
      transition: background 100ms ease, color 100ms ease;
    }
    .plus-btn:hover { background: rgba(111, 47, 69, 0.08); color: var(--accent); }
    .plus-popover {
      display: none; position: absolute; bottom: calc(100% + 8px); left: 0;
      min-width: 200px; background: var(--surface); border: 1px solid var(--line);
      border-radius: 12px; padding: 6px 0; box-shadow: var(--shadow); z-index: 50;
    }
    .plus-popover.open { display: block; }
    .plus-popover button {
      display: flex; align-items: center; gap: 10px; width: 100%; text-align: left;
      padding: 10px 16px; font-size: 13px; font-weight: 500; color: var(--ink);
      background: none; border: none; cursor: pointer;
    }
    .plus-popover button:hover { background: var(--surface-alt); }
    .plus-popover button .icon { font-size: 16px; width: 20px; text-align: center; }
    .composer textarea {
      flex: 1; border: none; outline: none; background: transparent;
      font-family: inherit; font-size: 14px; color: var(--ink);
      resize: none; min-height: 24px; max-height: 144px; line-height: 1.5;
      padding: 4px 8px;
    }
    .composer textarea::placeholder { color: var(--muted-soft); }
    .send-btn {
      width: 32px; height: 32px; border-radius: 50%; border: none;
      background: var(--accent); color: #fff; font-size: 15px;
      cursor: pointer; display: flex; align-items: center; justify-content: center;
      flex-shrink: 0; align-self: flex-end;
      transition: opacity 140ms ease, transform 80ms ease;
    }
    .send-btn:hover { opacity: 0.88; }
    .send-btn:active { transform: scale(0.94); }
    .send-btn:disabled { opacity: 0.35; cursor: default; }
    .send-btn .arrow { display: inline-block; transform: rotate(-90deg); }
    .composer-error { font-size: 12px; color: #c62828; margin-top: 4px; min-height: 16px; }

    /* ===== Wardrobe Picker Modal ===== */
    .modal-overlay {
      display: none; position: fixed; inset: 0; z-index: 300;
      background: rgba(32, 25, 21, 0.4); backdrop-filter: blur(4px);
      align-items: center; justify-content: center;
    }
    .modal-overlay.open { display: flex; }
    .modal-box {
      background: var(--surface); border-radius: 18px; padding: 24px;
      max-width: 560px; width: 92vw; max-height: 70vh; display: flex; flex-direction: column;
      box-shadow: 0 24px 80px rgba(32, 25, 21, 0.18);
    }
    .modal-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
    .modal-header h3 { font-size: 16px; font-weight: 700; }
    .modal-close { background: none; border: none; font-size: 20px; cursor: pointer; color: var(--muted); padding: 4px; }
    .modal-close:hover { color: var(--ink); }
    .modal-grid {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
      overflow-y: auto; flex: 1;
    }
    .modal-item {
      border: 2px solid var(--line); border-radius: 12px; overflow: hidden;
      cursor: pointer; transition: border-color 100ms ease;
    }
    .modal-item:hover { border-color: var(--accent-soft); }
    .modal-item img { width: 100%; aspect-ratio: 3/4; object-fit: cover; display: block; }
    .modal-item .label { padding: 6px 8px; font-size: 11px; font-weight: 600; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .modal-empty { grid-column: 1/-1; text-align: center; padding: 32px; color: var(--muted); font-size: 13px; }

    /* ===== Outfit Cards ===== */
    .outfit-card {
      display: grid; grid-template-columns: 80px 1fr 40%;
      grid-template-rows: auto 1fr;
      gap: 0; border-radius: 16px; border: 1px solid var(--line);
      background: var(--surface); overflow: hidden; margin-bottom: 16px;
      box-shadow: 0 4px 24px rgba(54, 32, 24, 0.06);
    }
    .outfit-header {
      grid-column: 1 / -1; padding: 16px 18px 10px;
      display: flex; flex-direction: column; gap: 4px;
      border-bottom: 1px solid var(--line);
    }
    .outfit-header-top {
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
    }
    .outfit-header-top .outfit-feedback { margin: 0; }
    .outfit-thumbs {
      display: flex; flex-direction: column; gap: 4px;
      padding: 10px 6px; overflow-y: auto; max-height: 480px;
    }
    .outfit-thumbs img {
      width: 64px; height: 64px; object-fit: cover; border-radius: 8px;
      border: 2px solid transparent; cursor: pointer; transition: border-color 120ms ease;
    }
    .outfit-thumbs img.active { border-color: var(--accent); }
    .outfit-thumbs img:hover { border-color: var(--accent-soft); }
    .outfit-main-img {
      display: flex; align-items: center; justify-content: center;
      background: var(--surface-alt); min-height: 200px; max-height: 720px; overflow: hidden;
    }
    .outfit-main-img img { max-width: 100%; max-height: 100%; object-fit: contain; }
    .outfit-info {
      padding: 16px 18px; overflow-y: auto; max-height: 720px;
      display: flex; flex-direction: column; gap: 10px;
    }
    .outfit-rank { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }
    .outfit-source-row { display: flex; gap: 6px; flex-wrap: wrap; }
    .source-pill {
      display: inline-block; padding: 3px 10px; border-radius: 999px;
      font-size: 11px; font-weight: 700; letter-spacing: 0.02em;
    }
    .source-pill.wardrobe { background: rgba(95, 106, 82, 0.12); color: var(--wardrobe); }
    .source-pill.catalog { background: rgba(111, 47, 69, 0.10); color: var(--accent); }
    .source-pill.hybrid { background: rgba(176, 138, 78, 0.12); color: var(--gold); }
    .source-mini-pill { font-size: 10px; padding: 2px 8px; border-radius: 999px; font-weight: 600; }
    .source-mini-pill.wardrobe { background: rgba(95, 106, 82, 0.10); color: var(--wardrobe); }
    .source-mini-pill.catalog { background: rgba(111, 47, 69, 0.08); color: var(--accent); }
    .source-mini-pill.hybrid { background: rgba(176, 138, 78, 0.10); color: var(--gold); }
    .outfit-title { font-family: "Cormorant Garamond", Georgia, serif; font-size: 20px; font-weight: 600; line-height: 1.2; }
    .outfit-summary { padding: 0; }
    .outfit-summary-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted-soft); margin-bottom: 4px; }
    .outfit-summary-text { font-size: 13px; color: var(--ink); line-height: 1.5; margin: 0; }
    .outfit-product { padding: 10px 0; border-bottom: 1px solid var(--line); }
    .outfit-product:last-of-type { border-bottom: none; }
    .outfit-product-title { font-weight: 600; font-size: 13px; display: block; margin-bottom: 2px; }
    .product-price { font-size: 13px; font-weight: 700; color: var(--accent); display: block; margin-bottom: 6px; }
    .product-cta { display: flex; gap: 6px; }
    .btn-buy, .btn-wishlist {
      padding: 6px 14px; border-radius: 8px; font-size: 11px; font-weight: 700;
      text-decoration: none; white-space: nowrap; cursor: pointer;
      border: 1px solid var(--line); text-align: center;
    }
    .btn-buy { background: var(--accent); color: #fff; border-color: var(--accent); }
    .btn-buy:hover { opacity: 0.88; text-decoration: none; }
    .btn-wishlist { background: var(--surface); color: var(--muted); }
    .btn-wishlist:hover { border-color: var(--accent-soft); color: var(--ink); }
    .btn-wishlist.wishlisted { color: var(--accent); border-color: var(--accent); }
    .outfit-item-source { display: flex; gap: 6px; align-items: center; margin-top: 4px; }
    .chip { font-size: 10px; padding: 2px 8px; border-radius: 999px; background: var(--surface-deep); color: var(--muted); font-weight: 600; }
    /* Split polar bar chart — sits at the bottom of the .outfit-info
       column (right column of the PDP card). The canvas is sized to
       fit the column's usable width (~280px after padding) and uses
       aspect-ratio + max-width: 100% so it scales DOWN proportionally
       on narrower viewports without squishing the rings into ellipses.
       Labels are arranged on a single circle (no staggering) for a
       cleaner, more orderly visual rhythm. */
    .outfit-radar {
      text-align: center;
      padding: 8px 0 4px;
      margin-top: 4px;
    }
    .outfit-radar canvas {
      display: block; margin: 0 auto;
      max-width: 100%; height: auto;
      aspect-ratio: 290 / 320;
    }
    .outfit-criteria { display: flex; flex-direction: column; gap: 6px; }
    .criteria-row { display: flex; align-items: center; gap: 8px; }
    .criteria-label { font-size: 11px; font-weight: 600; color: var(--muted); width: 100px; flex-shrink: 0; }
    .criteria-track { flex: 1; height: 6px; border-radius: 3px; background: var(--surface-deep); overflow: hidden; }
    .criteria-fill { height: 100%; border-radius: 3px; transition: width 300ms ease; }
    .criteria-pct { font-size: 11px; font-weight: 700; width: 34px; text-align: right; color: var(--ink); }
    .outfit-rationale { margin-top: 4px; }
    .outfit-rationale summary {
      font-size: 12px; font-weight: 700; color: var(--accent); cursor: pointer;
      list-style: none; padding: 6px 0;
    }
    .outfit-rationale summary::-webkit-details-marker { display: none; }
    .outfit-rationale summary::before { content: "\\25B6  "; font-size: 10px; }
    .outfit-rationale[open] summary::before { content: "\\25BC  "; }
    .outfit-rationale-body { padding: 8px 0; }
    .rationale-note { margin-bottom: 8px; font-size: 13px; line-height: 1.5; }
    .rationale-note strong { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin-bottom: 2px; }
    .rationale-note p { margin: 0; color: var(--ink); }
    .outfit-feedback { display: flex; gap: 8px; flex-wrap: wrap; padding-top: 4px; }
    .fb-icon-btn {
      border: none; background: none; cursor: pointer; font-size: 18px; line-height: 1;
      padding: 4px; filter: grayscale(1) opacity(0.5); transition: filter 120ms ease;
    }
    .fb-icon-btn:hover { filter: grayscale(0) opacity(1); }
    .outfit-feedback .secondary { background: var(--surface); color: var(--muted); }
    .outfit-feedback .secondary:hover { border-color: var(--accent-soft); color: var(--ink); }
    .dislike-form { display: none; padding: 10px 0; }
    .dislike-form.open { display: block; }
    .reaction-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
    .reaction-chip {
      padding: 5px 12px; border-radius: 999px; border: 1px solid var(--line);
      background: var(--surface); font-size: 12px; cursor: pointer; color: var(--ink);
    }
    .reaction-chip:hover { border-color: var(--accent-soft); }
    .dislike-form textarea {
      width: 100%; border: 1px solid var(--line); border-radius: 10px;
      padding: 10px 12px; font-family: inherit; font-size: 13px; resize: none;
      min-height: 60px; margin-bottom: 8px; outline: none; background: var(--surface);
    }
    .dislike-form textarea:focus { border-color: var(--accent-soft); }
    .dislike-actions { display: flex; gap: 8px; }
    .dislike-actions button {
      padding: 7px 18px; border-radius: 999px; font-size: 12px; font-weight: 700;
      cursor: pointer; border: 1px solid var(--line);
    }
    .dislike-actions button:first-child { background: var(--accent); color: #fff; border-color: var(--accent); }
    .dislike-actions button:first-child:hover { opacity: 0.88; }
    .dislike-actions .secondary { background: var(--surface); color: var(--muted); }
    .feedback-status { font-size: 12px; padding: 4px 0; min-height: 18px; }
    .feedback-status.success { color: var(--wardrobe); }
    .feedback-status.error { color: #c62828; }

    /* ===== Wardrobe Page ===== */
    .page-wardrobe {
      padding: 24px 32px; max-width: 960px; margin: 0 auto; width: 100%;
    }
    .wardrobe-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }
    .wardrobe-header h2 { font-family: "Cormorant Garamond", Georgia, serif; font-size: 24px; font-weight: 600; }
    .wardrobe-stats {
      display: flex; gap: 16px; align-items: center; font-size: 13px; color: var(--muted); margin-bottom: 16px;
    }
    .wardrobe-stats .stat-val { font-weight: 700; color: var(--ink); margin-right: 4px; }
    .wardrobe-filters { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 20px; }
    .filter-chip {
      padding: 6px 14px; border-radius: 999px; font-size: 12px; font-weight: 700;
      border: 1px solid var(--line); background: var(--surface); color: var(--ink);
      cursor: pointer; transition: all 100ms ease;
    }
    .filter-chip:hover { border-color: var(--wardrobe); color: var(--wardrobe); }
    .filter-chip.active { background: rgba(95, 106, 82, 0.12); color: var(--wardrobe); border-color: rgba(95, 106, 82, 0.3); }
    .closet-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .closet-card {
      border: 1px solid var(--line); border-radius: 14px; overflow: hidden;
      background: var(--surface); transition: box-shadow 120ms ease;
    }
    .closet-card:hover { box-shadow: 0 4px 20px rgba(54, 32, 24, 0.08); }
    .closet-image { aspect-ratio: 3/4; overflow: hidden; background: var(--surface-alt); }
    .closet-image img { width: 100%; height: 100%; object-fit: cover; }
    .closet-placeholder {
      width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
      font-size: 13px; color: var(--muted-soft);
    }
    .closet-body { padding: 12px; }
    .closet-body h3 { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
    .closet-body p { font-size: 12px; color: var(--muted); line-height: 1.4; margin-bottom: 8px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .tag-row { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px; }
    .tag { font-size: 10px; padding: 2px 8px; border-radius: 999px; background: var(--surface-deep); color: var(--muted); font-weight: 600; }
    .closet-actions { display: flex; gap: 6px; }
    .studio-btn {
      flex: 1; padding: 6px 0; border-radius: 999px; font-size: 11px; font-weight: 700;
      border: 1px solid var(--line); background: var(--surface); color: var(--ink);
      cursor: pointer; text-align: center;
    }
    .studio-btn:hover { border-color: var(--wardrobe); color: var(--wardrobe); }
    .studio-btn.danger { color: #9b2323; border-color: rgba(155,35,35,0.25); }
    .studio-btn.danger:hover { border-color: #9b2323; }
    .wardrobe-search {
      width: 100%; padding: 10px 14px; border: 1px solid var(--line); border-radius: 999px;
      font-family: inherit; font-size: 13px; color: var(--ink); background: var(--surface);
      margin-bottom: 12px; outline: none; transition: border-color 120ms ease;
    }
    .wardrobe-search:focus { border-color: var(--wardrobe); }
    .wardrobe-search::placeholder { color: var(--muted-soft); }
    .filter-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
    .wardrobe-empty { text-align: center; padding: 48px 24px; color: var(--muted); font-size: 14px; }
    .wardrobe-add-btn {
      padding: 8px 20px; border-radius: 999px; border: 1.5px dashed var(--line);
      background: none; font-size: 13px; font-weight: 600; color: var(--muted);
      cursor: pointer; transition: all 100ms ease;
    }
    .wardrobe-add-btn:hover { border-color: var(--wardrobe); color: var(--wardrobe); }

    /* ===== Results Page ===== */
    .page-results {
      padding: 24px 32px; max-width: 960px; margin: 0 auto; width: 100%;
    }
    .results-header { margin-bottom: 20px; }
    .results-header h2 { font-family: "Cormorant Garamond", Georgia, serif; font-size: 24px; font-weight: 600; margin-bottom: 4px; }
    .results-header p { font-size: 13px; color: var(--muted); }
    .results-tabs { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
    .results-tabs button {
      padding: 7px 16px; border-radius: 999px; font-size: 12px; font-weight: 700;
      border: 1px solid var(--line); background: var(--surface); color: var(--muted);
      cursor: pointer; transition: all 100ms ease;
    }
    .results-tabs button:hover { color: var(--ink); border-color: var(--accent-soft); }
    .results-tabs button.active { background: rgba(111, 47, 69, 0.10); color: var(--accent); border-color: rgba(111, 47, 69, 0.2); }
    .results-filters { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 20px; }
    .results-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
    .result-card {
      border: 1px solid var(--line); border-radius: 14px; overflow: hidden;
      background: var(--surface); cursor: pointer; transition: box-shadow 120ms ease;
    }
    .result-card:hover { box-shadow: 0 4px 20px rgba(54, 32, 24, 0.08); }
    .result-card .thumb { aspect-ratio: 4/3; background: var(--surface-alt); overflow: hidden; }
    .result-card .thumb img { width: 100%; height: 100%; object-fit: cover; }
    .result-card .thumb-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: var(--muted-soft); font-size: 13px; }
    .result-card .body { padding: 12px; }
    .result-card .body .msg { font-size: 13px; font-weight: 600; margin-bottom: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .result-card .body .meta-row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
    .result-card .body .meta-row .ts { font-size: 11px; color: var(--muted-soft); }
    .results-empty { text-align: center; padding: 48px; color: var(--muted); font-size: 14px; grid-column: 1/-1; }

    /* ===== Add Wardrobe Item Modal ===== */
    .modal-overlay {
      position: fixed; inset: 0; z-index: 9000; background: rgba(32, 25, 21, 0.45);
      display: flex; align-items: center; justify-content: center;
      opacity: 0; pointer-events: none; transition: opacity 160ms ease;
    }
    .modal-overlay.open { opacity: 1; pointer-events: auto; }
    .modal-box {
      background: var(--surface); border-radius: 20px; width: min(92vw, 480px);
      max-height: 88vh; overflow-y: auto; padding: 28px;
      box-shadow: 0 24px 80px rgba(32, 25, 21, 0.18);
    }
    .modal-box h2 { font-family: "Cormorant Garamond", Georgia, serif; font-size: 22px; font-weight: 600; margin-bottom: 20px; }
    .modal-field { margin-bottom: 14px; }
    .modal-field label { display: block; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin-bottom: 4px; }
    .modal-field input, .modal-field select {
      width: 100%; padding: 10px 14px; border: 1px solid var(--line); border-radius: 10px;
      font-family: inherit; font-size: 14px; color: var(--ink); background: #fff;
    }
    .modal-field input[type="file"] { padding: 8px; }
    .modal-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }
    .modal-actions .btn-cancel {
      padding: 10px 20px; border-radius: 999px; border: 1px solid var(--line);
      background: none; font-size: 13px; font-weight: 600; color: var(--muted);
      cursor: pointer;
    }
    .modal-error { color: #9b2323; font-size: 12px; margin-top: 8px; }
    .modal-preview { width: 80px; height: 100px; border-radius: 10px; object-fit: cover; margin-top: 8px; border: 1px solid var(--line); }

    /* ===== Profile Page (unified view + edit) ===== */
    .page-profile {
      padding: 32px; max-width: 720px; margin: 0 auto; width: 100%;
    }
    .profile-card {
      background: var(--surface); border: 1px solid var(--line); border-radius: 18px;
      padding: 28px; margin-bottom: 20px;
    }
    .profile-card-header {
      display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;
    }
    .profile-card-header h2 {
      font-family: "Cormorant Garamond", Georgia, serif;
      font-size: 24px; font-weight: 600; margin: 0;
    }
    .profile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .profile-field { }
    .profile-field .label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin-bottom: 4px; }
    .profile-field .value { font-size: 15px; font-weight: 500; }
    .profile-field input, .profile-field select {
      width: 100%; padding: 10px 14px; border: 1px solid var(--line); border-radius: 10px;
      font-family: inherit; font-size: 14px; color: var(--ink); background: #fff; outline: none;
      display: none;
    }
    .profile-field input:focus, .profile-field select:focus { border-color: var(--accent-soft); }
    .profile-field.editing .value { display: none; }
    .profile-field.editing input, .profile-field.editing select { display: block; }
    .profile-actions { display: flex; gap: 10px; margin-top: 20px; }
    .btn-primary {
      padding: 10px 24px; border-radius: 999px; border: none;
      background: var(--accent); color: #fff; font-size: 13px; font-weight: 700;
      cursor: pointer; transition: opacity 120ms ease;
    }
    .btn-primary:hover { opacity: 0.88; }
    .btn-secondary {
      padding: 10px 24px; border-radius: 999px; border: 1px solid var(--line);
      background: var(--surface); color: var(--muted); font-size: 13px; font-weight: 700;
      cursor: pointer; transition: all 120ms ease;
    }
    .btn-secondary:hover { border-color: var(--accent-soft); color: var(--ink); }
    .edit-status { font-size: 12px; margin-top: 10px; min-height: 18px; }
    .edit-status.success { color: var(--wardrobe); }
    .edit-status.error { color: #c62828; }
    .style-code-card {
      background: var(--surface); border: 1px solid var(--line); border-radius: 18px;
      padding: 28px; margin-bottom: 20px;
    }
    .style-code-card h3 { font-size: 18px; font-weight: 600; margin-bottom: 16px; font-family: "Cormorant Garamond", Georgia, serif; }
    .style-facts { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }
    .style-fact { background: var(--surface-alt); border-radius: 10px; padding: 12px 14px; }
    .style-fact .fact-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted-soft); margin-bottom: 2px; }
    .style-fact .fact-value { font-size: 14px; font-weight: 600; }
    .style-summary { font-size: 14px; color: var(--muted); line-height: 1.6; }
    /* ===== Analysis Status ===== */
    .analysis-card {
      background: var(--surface); border: 1px solid var(--line); border-radius: 18px;
      padding: 28px; margin-bottom: 20px;
    }
    .analysis-card h2 { font-family: "Cormorant Garamond", Georgia, serif; font-size: 24px; font-weight: 600; margin: 0; }
    .analysis-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
    .analysis-badge {
      padding: 6px 12px; border-radius: 999px; font-size: 11px; font-weight: 700;
      letter-spacing: 0.06em; text-transform: uppercase;
      background: var(--surface-alt); color: var(--muted);
    }
    .analysis-badge.completed { background: rgba(95, 106, 82, 0.12); color: var(--wardrobe); }
    .analysis-badge.running { background: rgba(111, 47, 69, 0.10); color: var(--accent); }
    .analysis-badge.failed { background: rgba(155, 35, 35, 0.10); color: #9b2323; }
    .analysis-progress { width: 100%; height: 8px; border-radius: 999px; background: var(--surface-deep); overflow: hidden; margin-bottom: 12px; }
    .analysis-progress-bar { width: 14%; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--accent), #b08a4e); transition: width 300ms ease; }
    .analysis-text { font-size: 13px; color: var(--muted); margin-bottom: 14px; }
    .analysis-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .analysis-error { display: none; padding: 10px 14px; border-radius: 12px; background: rgba(155,35,35,0.06); color: #9b2323; font-size: 12px; margin-bottom: 12px; }
    .analysis-error.show { display: block; }
    .agent-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-top: 16px; }
    .agent-card {
      border: 1px solid var(--line); border-radius: 14px; padding: 16px; background: #fff;
    }
    .agent-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
    .agent-card h4 { font-size: 13px; font-weight: 700; margin: 0; }
    .agent-card p { font-size: 12px; color: var(--muted); margin: 0; }
    .agent-rerun-btn {
      padding: 5px 10px; font-size: 11px; font-weight: 600; border-radius: 8px;
      border: 1px solid var(--line); background: var(--surface); color: var(--muted);
      cursor: pointer; display: none;
    }
    .agent-rerun-btn.show { display: inline-block; }
    .result-group { border: 1px solid var(--line); border-radius: 14px; overflow: hidden; background: #fff; margin-bottom: 14px; }
    .result-group-header {
      padding: 10px 16px; background: var(--surface-alt); border-bottom: 1px solid var(--line);
      font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); font-weight: 700;
    }
    .attr-row { display: grid; grid-template-columns: 160px 1fr 70px; gap: 10px; padding: 10px 16px; border-bottom: 1px solid var(--surface-deep); align-items: start; font-size: 13px; }
    .attr-row:last-child { border-bottom: none; }
    .attr-name { font-weight: 600; }
    .attr-value { line-height: 1.4; }
    .attr-value small { display: block; margin-top: 2px; color: var(--muted); font-size: 11px; }
    .attr-confidence {
      justify-self: end; padding: 4px 8px; border-radius: 999px;
      background: rgba(111, 47, 69, 0.08); color: var(--accent); font-size: 11px; font-weight: 700;
    }

    /* ===== Profile Images ===== */
    .profile-images-card {
      background: var(--surface); border: 1px solid var(--line); border-radius: 18px;
      padding: 28px; margin-bottom: 20px;
    }
    .profile-images-card h3 { font-family: "Cormorant Garamond", Georgia, serif; font-size: 18px; font-weight: 600; margin-bottom: 16px; }
    .profile-images-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .profile-image-slot { text-align: center; }
    .profile-image-slot .slot-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted-soft); margin-bottom: 8px; }
    .profile-image-slot img { width: 100%; max-width: 200px; border-radius: 14px; border: 1px solid var(--line); aspect-ratio: 2/3; object-fit: cover; }
    .profile-image-slot .slot-empty { width: 100%; max-width: 200px; aspect-ratio: 2/3; border-radius: 14px; border: 2px dashed var(--line); display: flex; align-items: center; justify-content: center; color: var(--muted-soft); font-size: 12px; margin: 0 auto; }
    .profile-image-slot .slot-update { margin-top: 8px; }
    .profile-image-slot .slot-update label {
      display: inline-block; padding: 5px 14px; border-radius: 999px; font-size: 11px; font-weight: 600;
      border: 1px solid var(--line); color: var(--muted); cursor: pointer; transition: all 100ms ease;
    }
    .profile-image-slot .slot-update label:hover { border-color: var(--accent-soft); color: var(--ink); }
    .profile-image-slot .slot-update input { display: none; }
    .analysis-confidence-pct { font-size: 13px; font-weight: 600; color: var(--accent); margin-left: 8px; }

    .color-palette-card {
      background: var(--surface); border: 1px solid var(--line); border-radius: 18px;
      padding: 28px;
    }
    .color-palette-card h3 { font-size: 18px; font-weight: 600; margin-bottom: 16px; font-family: "Cormorant Garamond", Georgia, serif; }
    .palette-section { margin-bottom: 14px; }
    .palette-section:last-child { margin-bottom: 0; }
    .palette-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted-soft); margin-bottom: 6px; }
    .palette-chips { display: flex; gap: 6px; flex-wrap: wrap; }
    .palette-chip {
      padding: 5px 12px; border-radius: 999px; font-size: 12px; font-weight: 600;
    }
    .palette-chip.base { background: var(--surface-alt); color: var(--ink); }
    .palette-chip.accent { background: rgba(111, 47, 69, 0.10); color: var(--accent); }
    .palette-chip.avoid { background: rgba(155, 35, 35, 0.08); color: #9b2323; }

    /* ===== Responsive ===== */
    @media (max-width: 900px) {
      .history-rail { width: 220px; min-width: 220px; }
      .outfit-card { grid-template-columns: 1fr; }
      .outfit-thumbs { flex-direction: row; overflow-x: auto; padding: 8px; }
      .outfit-thumbs img { width: 56px; height: 56px; }
      .outfit-main-img img { max-height: 320px; }
      .closet-grid { grid-template-columns: repeat(2, 1fr); }
      .results-grid { grid-template-columns: 1fr; }
      .profile-grid, .style-facts, .edit-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 600px) {
      .app-header { padding: 0 12px; gap: 8px; }
      .header-nav a { padding: 6px 10px; font-size: 12px; }
      .new-chat-btn { display: none; }
      .history-rail { display: none !important; }
      .hamburger-btn { display: flex !important; }
      .history-rail.mobile-open {
        display: flex !important; position: fixed; top: var(--header-h); left: 0; bottom: 0;
        width: 280px; z-index: 150; background: var(--surface);
        box-shadow: 4px 0 24px rgba(32, 25, 21, 0.12);
      }
      .chat-feed { padding: 16px 12px; }
      .composer-wrap { padding: 6px 12px 12px; }
      .prompt-grid { grid-template-columns: 1fr; }
      .page-wardrobe, .page-results, .page-profile { padding: 16px; }
      .closet-grid { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 430px) {
      .header-brand { font-size: 18px; }
      .closet-grid { grid-template-columns: 1fr; }
    }

    /* Hamburger (hidden on desktop) */
    .hamburger-btn {
      display: none; width: 30px; height: 30px; border-radius: 8px; border: 1px solid var(--line);
      background: var(--surface); align-items: center; justify-content: center; cursor: pointer;
      font-size: 16px; color: var(--muted);
    }
    .hamburger-btn:hover { border-color: var(--accent-soft); }

    /* Hidden file input */
    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }
  </style>
</head>
"""

    safe_user_id = escape(user_id or "", quote=True)
    safe_view = escape(active_view or "chat", quote=True)
    safe_conv_id = escape(conversation_id or "", quote=True)
    safe_source = escape(source or "", quote=True)

    html += f'<body class="view-{safe_view}">\n'

    # ── Header ──
    html += f"""
<header class="app-header">
  <button class="hamburger-btn" id="hamburgerBtn" aria-label="Toggle sidebar">&#9776;</button>
  <div class="header-brand" id="brandLink">Aura</div>
  <nav class="header-nav">
    <a href="/?user={safe_user_id}&view=chat" class="{'active' if active_view == 'chat' else ''}">Chat</a>
    <a href="/?user={safe_user_id}&view=wardrobe" class="{'active' if active_view == 'wardrobe' else ''}">Wardrobe</a>
    <a href="/?user={safe_user_id}&view=results" class="{'active' if active_view == 'results' else ''}">Results</a>
  </nav>
  <div class="header-actions">
    <button class="new-chat-btn" id="newChatBtn">+ New Chat</button>
    <div class="avatar-menu">
      <button class="avatar-btn" id="avatarBtn" aria-label="User menu">&#128100;</button>
      <div class="avatar-dropdown" id="avatarDropdown">
        <a href="/?user={safe_user_id}&view=profile">Profile</a>
        <!-- Edit is now inline on the profile page -->
        <div class="divider"></div>
        <button id="logoutBtn">Logout</button>
      </div>
    </div>
  </div>
</header>
"""

    # ── App Body ──
    html += '<div class="app-body">\n'

    # ── Chat History Sidebar ──
    html += f"""
<aside class="history-rail" id="historyRail">
  <div class="history-header">
    <span>Conversations</span>
  </div>
  <div class="history-list" id="historyList">
    <div class="history-empty">Start a conversation to see your history here.</div>
  </div>
</aside>
"""

    # ── Chat Page ──
    html += f"""
<div class="page-view page-chat">
  <div id="feed" class="chat-feed" role="region" aria-live="polite">
    <div class="feed-welcome" id="feedWelcome">
      <div class="eyebrow">Your Stylist Is Ready</div>
      <h2>What are we styling today?</h2>
      <p>Start with one ask. I'll style you from your wardrobe first, and pull from the catalog when there's a gap.</p>
      <button class="prompt-primary prompt-card" data-prompt="Dress me for tonight using my wardrobe.">Dress me for tonight</button>
      <div>
        <button type="button" class="prompt-more-toggle" id="promptMoreToggle" aria-expanded="false" aria-controls="promptMoreGrid">
          More ways to style <span class="chev">&#9662;</span>
        </button>
      </div>
      <div class="prompt-grid" id="promptMoreGrid">
        <button class="prompt-card" data-prompt="Find me a complete office look from the catalog.">Office look from catalog</button>
        <button class="prompt-card" data-prompt="What goes well with this?">Pair a garment I have</button>
        <button class="prompt-card" data-prompt="Plan my wardrobe for a 5-day beach vacation.">Plan a trip wardrobe</button>
        <button class="prompt-card" data-prompt="How does this outfit look on me?">Check an outfit I'm wearing</button>
      </div>
    </div>
  </div>
  <div class="stage-bar" id="stageBar"></div>
  <div class="composer-wrap">
    <div class="composer-outer" id="composerArea">
      <div class="image-chip" id="imageChip">
        <div class="chip-inner">
          <img id="imageChipImg" src="" alt="Attached" />
          <span class="name" id="imageChipName"></span>
          <button class="remove" id="imageChipRemove" aria-label="Remove image">&times;</button>
        </div>
      </div>
      <div class="composer">
        <div class="plus-menu">
          <button class="plus-btn" id="plusBtn" type="button" aria-label="Attach">+</button>
          <div class="plus-popover" id="plusPopover">
            <button type="button" id="uploadImageBtn"><span class="icon">&#128247;</span> Upload image</button>
            <button type="button" id="selectWardrobeBtn"><span class="icon">&#128090;</span> Select from wardrobe</button>
          </div>
        </div>
        <textarea id="messageInput" rows="1" placeholder="Message Aura..." aria-label="Message"></textarea>
        <button class="send-btn" id="sendBtn" type="button" aria-label="Send"><span class="arrow">&#10148;</span></button>
      </div>
    </div>
    <div class="composer-error" id="composerError"></div>
  </div>
</div>
"""

    # ── Wardrobe Page ──
    html += f"""
<div class="page-view page-wardrobe">
  <div class="wardrobe-header">
    <h2>Your Wardrobe</h2>
    <div style="display:flex;gap:8px;">
      <button class="wardrobe-add-btn" id="wardrobeAddBtn">+ Add Item</button>
      <button class="btn-secondary" id="wardrobeRefreshBtn">Refresh</button>
    </div>
  </div>
  <div class="wardrobe-stats" id="wardrobeStats">
    <div><span class="stat-val" id="wStatCount">0</span> pieces</div>
    <div><span class="stat-val" id="wStatComplete">0%</span> completeness</div>
    <div id="wStatusPill" style="margin-left:auto;font-size:11px;color:var(--muted-soft);"></div>
  </div>
  <input type="search" id="wardrobeSearch" class="wardrobe-search" placeholder="Search wardrobe by name, brand, or description..." />
  <div class="wardrobe-filters" id="wardrobeFilters">
    <button class="filter-chip active" data-filter="all">All</button>
    <button class="filter-chip" data-filter="tops">Tops</button>
    <button class="filter-chip" data-filter="bottoms">Bottoms</button>
    <button class="filter-chip" data-filter="shoes">Shoes</button>
    <button class="filter-chip" data-filter="dresses">Dresses</button>
    <button class="filter-chip" data-filter="outerwear">Outerwear</button>
    <button class="filter-chip" data-filter="accessories">Accessories</button>
    <button class="filter-chip" data-filter="occasion">Occasion-ready</button>
  </div>
  <div class="filter-row" id="wardrobeColorFilters">
    <button class="filter-chip active" data-color="all">All Colors</button>
    <button class="filter-chip" data-color="black">Black</button>
    <button class="filter-chip" data-color="white">White</button>
    <button class="filter-chip" data-color="blue">Blue</button>
    <button class="filter-chip" data-color="red">Red</button>
    <button class="filter-chip" data-color="green">Green</button>
    <button class="filter-chip" data-color="brown">Brown</button>
    <button class="filter-chip" data-color="navy">Navy</button>
    <button class="filter-chip" data-color="grey">Grey</button>
    <button class="filter-chip" data-color="beige">Beige</button>
    <button class="filter-chip" data-color="pink">Pink</button>
  </div>
  <div class="closet-grid" id="closetGrid">
    <div class="wardrobe-empty">Loading wardrobe...</div>
  </div>
</div>
"""

    # ── Add Wardrobe Item Modal ──
    html += """
<div class="modal-overlay" id="addItemModal">
  <div class="modal-box" style="text-align:center;">
    <h2 style="margin-bottom:8px;">Add to Wardrobe</h2>
    <p style="font-size:13px;color:var(--muted);margin-bottom:20px;">Upload a photo and Aura will analyse it automatically.</p>
    <form id="addItemForm">
      <label for="addItemFile" style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:32px 24px;border:2px dashed var(--line);border-radius:16px;cursor:pointer;transition:border-color 120ms ease;min-height:160px;" id="addItemDropzone">
        <img class="modal-preview" id="addItemPreview" style="display:none;max-height:180px;border-radius:10px;" alt="" />
        <span id="addItemPlaceholder" style="font-size:28px;">&#128248;</span>
        <span id="addItemLabel" style="font-size:13px;color:var(--muted);font-weight:500;">Tap to select or drag a photo here</span>
        <input type="file" id="addItemFile" accept="image/*" required style="display:none;" />
      </label>
      <div class="modal-error" id="addItemError" style="text-align:center;"></div>
      <div class="modal-actions" style="justify-content:center;">
        <button type="button" class="btn-cancel" id="addItemCancel">Cancel</button>
        <button type="submit" class="btn-primary" id="addItemSubmit">Add to Wardrobe</button>
      </div>
    </form>
  </div>
</div>
"""

    # ── Edit Wardrobe Item Modal ──
    html += """
<div class="modal-overlay" id="editItemModal">
  <div class="modal-box">
    <h2 style="margin-bottom:8px;">Edit Item</h2>
    <form id="editItemForm">
      <input type="hidden" id="editItemId" />
      <div id="editItemImgWrap" style="text-align:center;margin-bottom:16px;">
        <img id="editItemPreview" style="max-height:140px;border-radius:10px;border:1px solid var(--line);display:none;" alt="" />
      </div>
      <div class="modal-field">
        <label for="editTitle">Title</label>
        <input type="text" id="editTitle" maxlength="120" />
      </div>
      <div class="modal-field">
        <label for="editDescription">Description</label>
        <input type="text" id="editDescription" maxlength="300" />
      </div>
      <div class="modal-row">
        <div class="modal-field">
          <label for="editCategory">Category</label>
          <input type="text" id="editCategory" />
        </div>
        <div class="modal-field">
          <label for="editSubtype">Subtype</label>
          <input type="text" id="editSubtype" />
        </div>
      </div>
      <div class="modal-row">
        <div class="modal-field">
          <label for="editPrimaryColor">Primary Color</label>
          <input type="text" id="editPrimaryColor" />
        </div>
        <div class="modal-field">
          <label for="editSecondaryColor">Secondary Color</label>
          <input type="text" id="editSecondaryColor" />
        </div>
      </div>
      <div class="modal-row">
        <div class="modal-field">
          <label for="editPattern">Pattern</label>
          <input type="text" id="editPattern" />
        </div>
        <div class="modal-field">
          <label for="editFormality">Formality</label>
          <input type="text" id="editFormality" />
        </div>
      </div>
      <div class="modal-row">
        <div class="modal-field">
          <label for="editOccasion">Occasion Fit</label>
          <input type="text" id="editOccasion" />
        </div>
        <div class="modal-field">
          <label for="editBrand">Brand</label>
          <input type="text" id="editBrand" />
        </div>
      </div>
      <div class="modal-field">
        <label for="editNotes">Notes</label>
        <input type="text" id="editNotes" maxlength="500" />
      </div>
      <div class="modal-error" id="editItemError"></div>
      <div class="modal-actions">
        <button type="button" class="btn-cancel" id="editItemCancel">Cancel</button>
        <button type="submit" class="btn-primary" id="editItemSubmit">Save Changes</button>
      </div>
    </form>
  </div>
</div>
"""

    # ── Results Page ──
    html += """
<div class="page-view page-results">
  <div class="results-header">
    <h2>Previous Results</h2>
    <p>Your past styling recommendations, grouped by type.</p>
  </div>
  <div class="results-tabs" id="resultsTabs">
    <button class="active" data-tab="all">All</button>
    <button data-tab="occasion_recommendation">Outfit Picks</button>
    <button data-tab="outfit_check">Outfit Checks</button>
    <button data-tab="pairing_request">Pairings</button>
    <button data-tab="capsule_or_trip_planning">Capsules / Trips</button>
  </div>
  <div class="results-filters" id="resultsFilters">
    <button class="filter-chip active" data-source="all">All Sources</button>
    <button class="filter-chip" data-source="wardrobe">Wardrobe</button>
    <button class="filter-chip" data-source="catalog">Catalog</button>
  </div>
  <div class="results-grid" id="resultsGrid">
    <div class="results-empty">Loading results...</div>
  </div>
</div>
"""

    # ── Profile Page (unified: analysis + profile + style code + palette) ──
    html += """
<div class="page-view page-profile">
  <div class="analysis-card" id="analysisCard">
    <div class="analysis-header">
      <h2>Profile Analysis</h2>
      <div style="display:flex;align-items:center;gap:6px;">
        <span class="analysis-confidence-pct" id="analysisConfidence"></span>
        <div class="analysis-badge" id="analysisBadge">Loading</div>
      </div>
    </div>
    <div class="analysis-progress" id="analysisProgressWrap"><div class="analysis-progress-bar" id="analysisProgressBar"></div></div>
    <div class="analysis-text" id="analysisText">Checking analysis status...</div>
    <div class="analysis-error" id="analysisError"></div>
    <div class="analysis-actions" id="analysisActions">
      <button class="btn-secondary" id="analysisRerunBtn" style="display:none;">Re-Run Analysis</button>
      <button class="btn-secondary" id="analysisRetryBtn" style="display:none;">Retry</button>
    </div>
    <div class="agent-grid" id="analysisAgentGrid">
      <div class="agent-card"><div class="agent-card-head"><h4>Body Type</h4><button class="agent-rerun-btn" data-agent="body_type_analysis">Re-Run</button></div><p id="agentStatus-body_type_analysis">—</p></div>
      <div class="agent-card"><div class="agent-card-head"><h4>Color Analysis</h4><button class="agent-rerun-btn" data-agent="color_analysis_headshot">Re-Run</button></div><p id="agentStatus-color_analysis_headshot">—</p></div>
      <div class="agent-card"><div class="agent-card-head"><h4>Other Details</h4><button class="agent-rerun-btn" data-agent="other_details_analysis">Re-Run</button></div><p id="agentStatus-other_details_analysis">—</p></div>
    </div>
  </div>
  <div class="profile-images-card">
    <h3>Your Photos</h3>
    <div class="profile-images-grid">
      <div class="profile-image-slot">
        <div class="slot-label">Full Body</div>
        <div id="imgSlotFullBody"><div class="slot-empty">Not uploaded</div></div>
        <div class="slot-update"><label>Update<input type="file" accept="image/*" id="updateFullBody" /></label></div>
      </div>
      <div class="profile-image-slot">
        <div class="slot-label">Headshot</div>
        <div id="imgSlotHeadshot"><div class="slot-empty">Not uploaded</div></div>
        <div class="slot-update"><label>Update<input type="file" accept="image/*" id="updateHeadshot" /></label></div>
      </div>
    </div>
  </div>
  <div id="analysisResultsWrap"></div>
  <div class="profile-card" id="profileCard">
    <div class="profile-card-header">
      <h2>Your Profile</h2>
      <button class="btn-secondary" id="editToggleBtn">Edit</button>
    </div>
    <div class="profile-grid" id="profileGrid"></div>
    <div class="profile-actions" id="profileEditActions" style="display:none;">
      <button class="btn-primary" id="editSaveBtn">Save Changes</button>
      <button class="btn-secondary" id="editCancelBtn">Cancel</button>
    </div>
    <div class="edit-status" id="editStatus"></div>
  </div>
  <div class="style-code-card" id="styleCodeCard">
    <h3>Your Style Code</h3>
    <div class="style-facts" id="styleFacts"></div>
    <div class="style-summary" id="styleSummary"></div>
  </div>
  <div class="color-palette-card" id="colorPaletteCard">
    <h3>Your Color Palette</h3>
    <div id="colorPaletteContent"></div>
  </div>
</div>
"""

    # ── Wardrobe Picker Modal ──
    html += """
<div class="modal-overlay" id="wardrobePickerModal">
  <div class="modal-box">
    <div class="modal-header">
      <h3>Select from Wardrobe</h3>
      <button class="modal-close" id="wardrobePickerClose">&times;</button>
    </div>
    <div class="modal-grid" id="wardrobePickerGrid">
      <div class="modal-empty">Loading wardrobe items...</div>
    </div>
  </div>
</div>
"""

    # ── Hidden file input ──
    html += '<input type="file" id="chatImageFile" accept="image/*" class="sr-only" />\n'

    html += '</div><!-- /app-body -->\n'

    # ══════════════════════════════════════════════════════════════
    # JAVASCRIPT
    # ══════════════════════════════════════════════════════════════
    html += f"""
<script>
(function() {{
  "use strict";

  // ── Config ──
  var USER_ID = "{safe_user_id}";
  var ACTIVE_VIEW = "{safe_view}";
  var INIT_CONV_ID = "{safe_conv_id}";

  // ── State ──
  var pendingImageData = "";
  var wardrobeItems = [];
  var wardrobeSummary = null;
  var activeWardrobeFilter = "all";
  var activeWardrobeColor = "all";
  var wardrobeSearchQuery = "";
  var wardrobeItemsById = {{}};
  var styleCodeData = null;
  var conversationId = INIT_CONV_ID;
  var userAnalysisConfidencePct = 70;
  var allResults = [];
  var activeResultTab = "all";
  var activeResultSource = "all";

  // ── Session persistence ──
  if (USER_ID) {{
    try {{ localStorage.setItem("aura_user_id", USER_ID); }} catch(_) {{}}
  }}

  // ── DOM refs ──
  var feed = document.getElementById("feed");
  var feedWelcome = document.getElementById("feedWelcome");
  var stageBar = document.getElementById("stageBar");
  var messageEl = document.getElementById("messageInput");
  var sendBtn = document.getElementById("sendBtn");
  var err = document.getElementById("composerError");
  var composerArea = document.getElementById("composerArea");
  var chatImageFileEl = document.getElementById("chatImageFile");
  var imageChip = document.getElementById("imageChip");
  var imageChipImg = document.getElementById("imageChipImg");
  var imageChipName = document.getElementById("imageChipName");
  var imageChipRemove = document.getElementById("imageChipRemove");
  var plusBtn = document.getElementById("plusBtn");
  var plusPopover = document.getElementById("plusPopover");
  var uploadImageBtn = document.getElementById("uploadImageBtn");
  var selectWardrobeBtn = document.getElementById("selectWardrobeBtn");
  var historyList = document.getElementById("historyList");
  var historyRail = document.getElementById("historyRail");
  var hamburgerBtn = document.getElementById("hamburgerBtn");
  var newChatBtn = document.getElementById("newChatBtn");
  var avatarBtn = document.getElementById("avatarBtn");
  var avatarDropdown = document.getElementById("avatarDropdown");
  var brandLink = document.getElementById("brandLink");
  var logoutBtn = document.getElementById("logoutBtn");
  // Wardrobe
  var closetGrid = document.getElementById("closetGrid");
  var wardrobeFilters = document.getElementById("wardrobeFilters");
  var wardrobeColorFilters = document.getElementById("wardrobeColorFilters");
  var wardrobeSearchInput = document.getElementById("wardrobeSearch");
  var wStatusPill = document.getElementById("wStatusPill");
  var wStatCount = document.getElementById("wStatCount");
  var wStatComplete = document.getElementById("wStatComplete");
  // Results
  var resultsGrid = document.getElementById("resultsGrid");
  var resultsTabs = document.getElementById("resultsTabs");
  var resultsFilters = document.getElementById("resultsFilters");
  // Profile
  var profileGrid = document.getElementById("profileGrid");
  var styleFacts = document.getElementById("styleFacts");
  var styleSummary = document.getElementById("styleSummary");
  // Wardrobe picker modal
  var wardrobePickerModal = document.getElementById("wardrobePickerModal");
  var wardrobePickerGrid = document.getElementById("wardrobePickerGrid");
  var wardrobePickerClose = document.getElementById("wardrobePickerClose");

  // ══════════════════════════════════════════════
  // UTILITY HELPERS
  // ══════════════════════════════════════════════

  function escapeHtml(value) {{
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }}

  function firstImageUrl(item) {{
    return item.image_url || item.primary_image_url || item.images__0__src || item.images_0_src || "";
  }}

  function normalizeSourceToken(value) {{
    var n = String(value || "").toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
    if (!n) return "";
    if (n.indexOf("wardrobe") !== -1) return "wardrobe";
    if (n.indexOf("catalog") !== -1) return "catalog";
    if (n.indexOf("hybrid") !== -1) return "hybrid";
    return n;
  }}

  function sourceBadgeLabel(source) {{
    if (source === "wardrobe") return "From Your Wardrobe";
    if (source === "catalog") return "Catalog Pick";
    if (source === "hybrid") return "Wardrobe + Catalog";
    return "Styled Look";
  }}

  function sourceBadgeClass(source) {{
    if (source === "wardrobe" || source === "catalog" || source === "hybrid") return source;
    return "catalog";
  }}

  function inferOutfitSource(outfit, responseMetadata) {{
    var answerSource = normalizeSourceToken(responseMetadata && responseMetadata.answer_source);
    if (answerSource === "wardrobe") return "wardrobe";
    if (answerSource === "catalog") return "catalog";
    if (answerSource === "hybrid") return "hybrid";
    var itemSources = Array.from(new Set((outfit.items || []).map(function(item) {{
      return normalizeSourceToken(item && item.source);
    }}).filter(Boolean)));
    if (itemSources.includes("wardrobe") && itemSources.includes("catalog")) return "hybrid";
    if (itemSources.includes("wardrobe")) return "wardrobe";
    if (itemSources.includes("catalog")) return "catalog";
    return answerSource || "catalog";
  }}

  function buildStylistSummary(outfit) {{
    var summary = String(outfit.reasoning || "").trim();
    if (summary) return summary;
    var notes = [outfit.body_note, outfit.color_note, outfit.style_note, outfit.occasion_note]
      .map(function(v) {{ return String(v || "").trim(); }}).filter(Boolean);
    if (notes.length) return notes[0];
    return "A balanced look assembled to work as a complete styling direction.";
  }}

  function buildEvaluationCriteria(outfit, responseMetadata) {{
    // style_fit_pct is intentionally absent from this list. The top
    // semicircle of the split polar bar chart already shows the 8
    // archetype scores, which are the OUTFIT'S aesthetic profile —
    // putting "Style" on the bottom semicircle as a single axis would
    // double-count that dimension. The backend still scores
    // style_fit_pct (it informs the holistic match_score and is used
    // in the purchase verdict), it just doesn't appear as a Fit
    // profile axis here.
    var isOutfitCheck = String(responseMetadata && responseMetadata.primary_intent || "").toLowerCase() === "outfit_check"
      || String(responseMetadata && responseMetadata.answer_source || "").toLowerCase().indexOf("outfit_check") !== -1;
    if (isOutfitCheck) {{
      return [
        {{ key: "body_harmony_pct", label: "Body" }},
        {{ key: "color_suitability_pct", label: "Color" }},
        {{ key: "pairing_coherence_pct", label: "Pairing" }},
        {{ key: "occasion_pct", label: "Occasion" }},
      ];
    }}
    return [
      {{ key: "body_harmony_pct", label: "Body" }},
      {{ key: "color_suitability_pct", label: "Color" }},
      {{ key: "risk_tolerance_pct", label: "Risk" }},
      {{ key: "comfort_boundary_pct", label: "Comfort" }},
      {{ key: "occasion_pct", label: "Occasion" }},
      {{ key: "specific_needs_pct", label: "Needs" }},
      {{ key: "pairing_coherence_pct", label: "Pairing" }},
    ];
  }}

  function wardrobeImageUrl(item) {{
    if (item.image_url) return item.image_url;
    var p = item.image_path || "";
    if (!p) return "";
    if (p.startsWith("http://") || p.startsWith("https://")) return p;
    return "/v1/onboarding/images/local?path=" + encodeURIComponent(p);
  }}

  function profileValue(obj) {{
    if (!obj) return "";
    if (typeof obj === "string") return obj;
    return String(obj.value || obj.label || "").trim();
  }}

  function relativeTime(isoStr) {{
    if (!isoStr) return "";
    try {{
      var d = new Date(isoStr);
      var now = new Date();
      var diff = Math.floor((now - d) / 1000);
      if (diff < 60) return "just now";
      if (diff < 3600) return Math.floor(diff / 60) + "m ago";
      if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
      if (diff < 604800) return Math.floor(diff / 86400) + "d ago";
      return d.toLocaleDateString();
    }} catch(_) {{ return ""; }}
  }}

  // ══════════════════════════════════════════════
  // CHAT BUBBLES
  // ══════════════════════════════════════════════

  function dismissFeedWelcome() {{
    if (feedWelcome) {{ feedWelcome.style.display = "none"; }}
  }}

  // Parse assistant text into paragraphs + bullet lists. Bullets are
  // recognized by lines starting with •, -, or *. Paragraph breaks are
  // blank lines (\n\n). The result is a DocumentFragment of <p> and
  // <ul><li> nodes, all created via textContent so user-provided text
  // is escaped automatically (no XSS risk).
  //
  // The StyleAdvisor and explanation_request handlers return a flat
  // string of the form:
  //   "Prose answer...\n\n• bullet 1\n• bullet 2\n• bullet 3"
  // Without this parser the chat bubble's default white-space: normal
  // collapses the newlines and the bullets read as a single concatenated
  // sentence. With the parser we get a semantic <p> + <ul> tree.
  function renderAssistantMarkup(text) {{
    var frag = document.createDocumentFragment();
    if (!text) return frag;
    var normalized = String(text).replace(/\r\n/g, "\n");
    var blocks = normalized.split(/\n\n+/);
    for (var bi = 0; bi < blocks.length; bi++) {{
      var block = blocks[bi].trim();
      if (!block) continue;
      var lines = block.split("\n");
      var isBulletList = lines.length > 0 && lines.every(function(line) {{
        return /^\s*[•\-*]\s+/.test(line);
      }});
      if (isBulletList) {{
        var ul = document.createElement("ul");
        for (var li = 0; li < lines.length; li++) {{
          var item = document.createElement("li");
          item.textContent = lines[li].replace(/^\s*[•\-*]\s+/, "").trim();
          ul.appendChild(item);
        }}
        frag.appendChild(ul);
      }} else {{
        var p = document.createElement("p");
        // Single newlines inside a paragraph become spaces (not <br>)
        // so wrapped sentences read naturally.
        p.textContent = lines.map(function(l) {{ return l.trim(); }}).join(" ");
        frag.appendChild(p);
      }}
    }}
    return frag;
  }}

  function addBubble(text, kind, imageDataUrl) {{
    dismissFeedWelcome();
    var div = document.createElement("div");
    div.className = "bubble " + kind;
    if (imageDataUrl) {{
      var img = document.createElement("img");
      img.src = imageDataUrl;
      img.style.cssText = "max-height:120px;border-radius:8px;display:block;margin-bottom:6px;";
      img.onerror = function() {{ this.style.display = "none"; }};
      div.appendChild(img);
    }}
    if (kind === "assistant" && text) {{
      // Render assistant messages with paragraph + bullet structure so
      // StyleAdvisor / explanation_request responses display as proper
      // bulleted lists instead of a wall of text with inline • chars.
      div.appendChild(renderAssistantMarkup(text));
    }} else {{
      div.appendChild(document.createTextNode(text));
    }}
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
    return div;
  }}

  function addAgentBubble(text) {{
    var div = document.createElement("div");
    div.className = "bubble agent";
    var dot = document.createElement("span");
    dot.className = "dot";
    div.appendChild(dot);
    div.appendChild(document.createTextNode(text));
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
    return div;
  }}

  function addMeta(text) {{
    var div = document.createElement("div");
    div.className = "bubble meta";
    div.textContent = text;
    feed.appendChild(div);
  }}

  // ══════════════════════════════════════════════
  // IMAGE HANDLING
  // ══════════════════════════════════════════════

  function setImagePreview(dataUrl, fileName) {{
    pendingImageData = dataUrl;
    imageChipImg.src = dataUrl;
    imageChipImg.onerror = function() {{ this.style.display = "none"; }};
    imageChipImg.style.display = "";
    imageChipName.textContent = fileName || "Pasted image";
    imageChip.classList.add("visible");
  }}

  function clearImagePreview() {{
    pendingImageData = "";
    imageChipImg.src = "";
    imageChipName.textContent = "";
    imageChip.classList.remove("visible");
    chatImageFileEl.value = "";
  }}

  function handleImageFile(file) {{
    if (!file) return;
    var isImage = (file.type && file.type.indexOf("image") !== -1) || /\.(jpe?g|png|gif|webp|heic|heif|bmp|tiff?)$/i.test(file.name);
    if (!isImage) return;
    if (file.size > 10 * 1024 * 1024) {{ err.textContent = "Image must be under 10 MB."; return; }}
    var reader = new FileReader();
    reader.onload = function(e) {{
      var dataUrl = e.target.result;
      var isHeic = /\.(heic|heif)$/i.test(file.name) || file.type === "image/heic" || file.type === "image/heif";
      if (isHeic) {{
        imageChipName.textContent = "Converting " + (file.name || "image") + "...";
        imageChipImg.style.display = "none";
        imageChip.classList.add("visible");
        fetch("/v1/images/convert", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ image_data: dataUrl }}),
        }}).then(function(r) {{ return r.json(); }}).then(function(d) {{
          setImagePreview(d.image_data, file.name.replace(/\.(heic|heif)$/i, ".jpg"));
        }}).catch(function() {{
          setImagePreview(dataUrl, file.name);
        }});
      }} else {{
        setImagePreview(dataUrl, file.name);
      }}
    }};
    reader.readAsDataURL(file);
  }}

  if (chatImageFileEl) {{
    chatImageFileEl.addEventListener("change", function() {{
      if (this.files && this.files[0]) handleImageFile(this.files[0]);
    }});
  }}

  if (imageChipRemove) {{ imageChipRemove.addEventListener("click", clearImagePreview); }}

  // Paste
  if (messageEl) {{
    messageEl.addEventListener("paste", function(e) {{
      var items = (e.clipboardData || {{}}).items || [];
      for (var i = 0; i < items.length; i++) {{
        if (items[i].type.indexOf("image") !== -1) {{
          e.preventDefault();
          handleImageFile(items[i].getAsFile());
          return;
        }}
      }}
    }});
  }}

  // Drag-drop
  if (composerArea) {{
    composerArea.addEventListener("dragenter", function(e) {{ e.preventDefault(); composerArea.classList.add("dragover"); }});
    composerArea.addEventListener("dragover", function(e) {{ e.preventDefault(); composerArea.classList.add("dragover"); }});
    composerArea.addEventListener("dragleave", function(e) {{ e.preventDefault(); composerArea.classList.remove("dragover"); }});
    composerArea.addEventListener("drop", function(e) {{
      e.preventDefault();
      composerArea.classList.remove("dragover");
      var file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      handleImageFile(file);
    }});
  }}

  // ══════════════════════════════════════════════
  // PLUS MENU & WARDROBE PICKER
  // ══════════════════════════════════════════════

  if (plusBtn && plusPopover) {{
    plusBtn.addEventListener("click", function(e) {{
      e.stopPropagation();
      plusPopover.classList.toggle("open");
    }});
    document.addEventListener("click", function() {{ plusPopover.classList.remove("open"); }});
    plusPopover.addEventListener("click", function(e) {{ e.stopPropagation(); }});
  }}

  if (uploadImageBtn) {{
    uploadImageBtn.addEventListener("click", function() {{
      plusPopover.classList.remove("open");
      chatImageFileEl.click();
    }});
  }}

  if (selectWardrobeBtn) {{
    selectWardrobeBtn.addEventListener("click", function() {{
      plusPopover.classList.remove("open");
      openWardrobePicker();
    }});
  }}

  function openWardrobePicker() {{
    if (wardrobePickerModal) {{
      wardrobePickerModal.classList.add("open");
      loadWardrobePickerItems();
    }}
  }}
  if (wardrobePickerClose) {{
    wardrobePickerClose.addEventListener("click", function() {{ wardrobePickerModal.classList.remove("open"); }});
  }}
  if (wardrobePickerModal) {{
    wardrobePickerModal.addEventListener("click", function(e) {{
      if (e.target === wardrobePickerModal) wardrobePickerModal.classList.remove("open");
    }});
  }}

  function loadWardrobePickerItems() {{
    if (!USER_ID) {{ wardrobePickerGrid.innerHTML = '<div class="modal-empty">No user ID.</div>'; return; }}
    wardrobePickerGrid.innerHTML = '<div class="modal-empty">Loading...</div>';
    fetch("/v1/onboarding/wardrobe/" + encodeURIComponent(USER_ID))
      .then(function(r) {{ return r.json(); }})
      .then(function(data) {{
        var items = data.items || [];
        if (!items.length) {{
          wardrobePickerGrid.innerHTML = '<div class="modal-empty">No wardrobe items yet. Add items in the Wardrobe tab.</div>';
          return;
        }}
        wardrobePickerGrid.innerHTML = "";
        items.forEach(function(item) {{
          var imgUrl = wardrobeImageUrl(item);
          var el = document.createElement("div");
          el.className = "modal-item";
          el.innerHTML = (imgUrl ? '<img src="' + escapeHtml(imgUrl) + '" alt="' + escapeHtml(item.title || "Item") + '" loading="lazy" />' : '<div style="aspect-ratio:3/4;background:var(--surface-alt);display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:12px;">No image</div>') +
            '<div class="label">' + escapeHtml(item.title || "Wardrobe Item") + '</div>';
          el.addEventListener("click", function() {{
            if (imgUrl) {{
              // Fetch the image to get base64
              fetch(imgUrl).then(function(r) {{ return r.blob(); }}).then(function(blob) {{
                var reader = new FileReader();
                reader.onload = function(e) {{ setImagePreview(e.target.result, item.title || "Wardrobe item"); }};
                reader.readAsDataURL(blob);
              }}).catch(function() {{
                // Fallback: seed a prompt mentioning the item
                messageEl.value = "Style my " + (item.title || "wardrobe item") + " from my wardrobe.";
              }});
            }} else {{
              messageEl.value = "Style my " + (item.title || "wardrobe item") + " from my wardrobe.";
            }}
            wardrobePickerModal.classList.remove("open");
            messageEl.focus();
          }});
          wardrobePickerGrid.appendChild(el);
        }});
      }})
      .catch(function() {{
        wardrobePickerGrid.innerHTML = '<div class="modal-empty">Failed to load wardrobe.</div>';
      }});
  }}

  // ══════════════════════════════════════════════
  // AUTO-EXPANDING TEXTAREA
  // ══════════════════════════════════════════════

  messageEl.addEventListener("input", function() {{
    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 144) + "px";
  }});

  messageEl.addEventListener("keydown", function(e) {{
    if (e.key === "Enter" && !e.shiftKey) {{
      e.preventDefault();
      send();
    }}
  }});

  // ══════════════════════════════════════════════
  // OUTFIT CARD BUILDER (preserved from original)
  // ══════════════════════════════════════════════

  function buildOutfitCard(outfit, convId, responseMetadata) {{
    var card = document.createElement("div");
    card.className = "outfit-card";

    // Col 1: Thumbnails
    var thumbs = document.createElement("div");
    thumbs.className = "outfit-thumbs";
    var images = [];
    var items = outfit.items || [];
    for (var ii = 0; ii < items.length; ii++) {{
      var src = firstImageUrl(items[ii]);
      if (src) images.push({{ src: src, label: items[ii].title || items[ii].garment_category || "Product" }});
    }}
    if (outfit.tryon_image) images.push({{ src: outfit.tryon_image, label: "Virtual Try-On" }});
    var defaultIdx = outfit.tryon_image ? images.length - 1 : 0;

    // Col 2: Hero image
    var heroWrap = document.createElement("div");
    heroWrap.className = "outfit-main-img";
    var heroImg = document.createElement("img");
    heroImg.alt = outfit.title || "Outfit";
    heroImg.loading = "lazy";
    if (images.length > 0) heroImg.src = images[defaultIdx].src;
    heroWrap.appendChild(heroImg);

    images.forEach(function(img, idx) {{
      var thumb = document.createElement("img");
      thumb.src = img.src; thumb.alt = img.label; thumb.loading = "lazy";
      if (idx === defaultIdx) thumb.className = "active";
      thumb.addEventListener("click", function() {{
        heroImg.src = img.src;
        thumbs.querySelectorAll("img").forEach(function(t) {{ t.classList.remove("active"); }});
        thumb.classList.add("active");
      }});
      thumbs.appendChild(thumb);
    }});

    // ── Card header (full-width row above the 3 columns) ──
    var outfitSource = inferOutfitSource(outfit, responseMetadata);
    var summaryText = buildStylistSummary(outfit);
    var profileConfPct = userAnalysisConfidencePct || 70;

    var header = document.createElement("div");
    header.className = "outfit-header";

    // Top row: title on left, feedback icons on right
    var headerTop = document.createElement("div");
    headerTop.className = "outfit-header-top";
    var titleEl = document.createElement("div");
    titleEl.className = "outfit-title";
    titleEl.textContent = outfit.title || "Styled Look";
    headerTop.appendChild(titleEl);

    // Feedback icons in header
    var fbWrap = document.createElement("div");
    fbWrap.className = "outfit-feedback";
    var likeBtn = document.createElement("button"); likeBtn.className = "fb-icon-btn fb-like"; likeBtn.innerHTML = "&#128077;"; likeBtn.title = "Like This";
    var dislikeBtn = document.createElement("button"); dislikeBtn.className = "fb-icon-btn fb-dislike"; dislikeBtn.innerHTML = "&#128078;"; dislikeBtn.title = "Didn't Like This";
    fbWrap.appendChild(likeBtn); fbWrap.appendChild(dislikeBtn);
    headerTop.appendChild(fbWrap);
    header.appendChild(headerTop);

    // Summary row
    var trimmedSummary = summaryText.length > 200 ? summaryText.substring(0, 197) + "..." : summaryText;
    var summaryCard = document.createElement("div");
    summaryCard.className = "outfit-summary";
    summaryCard.innerHTML = '<p class="outfit-summary-text">' + escapeHtml(trimmedSummary) + '</p>';
    header.appendChild(summaryCard);

    // ── Col 3: Info panel (products + radars only) ──
    var info = document.createElement("div");
    info.className = "outfit-info";

    // Product specifications (3-row layout: title, price, CTAs)
    for (var pi = 0; pi < items.length; pi++) {{
      var item = items[pi];
      var prod = document.createElement("div");
      prod.className = "outfit-product";
      var pTitle = item.title || item.product_id || "Untitled";
      var url = item.product_url || item.url || "";
      var priceStr = String(item.price || "").trim();
      var hasPrice = priceStr && priceStr !== "0" && priceStr.toLowerCase() !== "n/a";
      var hasBuyLink = !!url;
      var itemSource = normalizeSourceToken(item.source);
      var isWardrobe = itemSource === "wardrobe";
      var html = '<span class="outfit-product-title">' + escapeHtml(pTitle) + '</span>';
      if (isWardrobe) {{
        html += '<span class="product-price" style="color:var(--wardrobe);">From your wardrobe</span>';
      }} else if (hasPrice) {{
        html += '<span class="product-price">Rs. ' + escapeHtml(priceStr.replace(/^Rs\.?\s*/i, "")) + '</span>';
      }}
      var productId = item.product_id || "";
      if (!isWardrobe) {{
        html += '<div class="product-cta">';
        if (hasBuyLink) html += '<a href="' + escapeHtml(url) + '" target="_blank" rel="noreferrer" class="btn-buy">Buy Now</a>';
        html += '<button type="button" class="btn-wishlist" data-product-id="' + escapeHtml(productId) + '" title="Add to Wishlist">&#9825;</button>';
        html += '</div>';
      }}
      prod.innerHTML = html;
      info.appendChild(prod);
    }}

    // Wishlist button handler (event delegation)
    info.addEventListener("click", function(e) {{
      var wishBtn = e.target.closest(".btn-wishlist");
      if (!wishBtn || wishBtn.classList.contains("wishlisted")) return;
      var pid = wishBtn.getAttribute("data-product-id") || "";
      if (!pid) return;
      wishBtn.disabled = true;
      fetch("/v1/products/" + encodeURIComponent(pid) + "/wishlist?user_id=" + encodeURIComponent(USER_ID) + "&conversation_id=" + encodeURIComponent(conversationId || ""), {{ method: "POST" }})
        .then(function(r) {{
          if (!r.ok) throw new Error("Failed");
          wishBtn.innerHTML = "&#9829;";
          wishBtn.classList.add("wishlisted");
          wishBtn.title = "Wishlisted";
        }})
        .catch(function() {{
          wishBtn.disabled = false;
        }});
    }});

    // 4. Split polar bar chart — Nightingale-style merge of the
    // archetype radar and the evaluation criteria radar.
    //
    // Top semicircle (9 → 12 → 3 o'clock): style archetype profile,
    // always 8 axes, purple. Bottom semicircle (3 → 6 → 9 o'clock): fit /
    // evaluation profile, dynamic 5-9 axes after the context-gated filter,
    // burgundy. A dashed horizontal line through the centre separates
    // them. Both profiles share the same 0-100 grid rings.
    //
    // Phase 12B follow-ups (April 9 2026) preserved here:
    //   - drop dimensions whose value is null or undefined
    //   - drop dimensions where the value is exactly 0 IF the key is
    //     one of the 4 context-gated dimensions (pairing_coherence_pct,
    //     occasion_pct, weather_time_pct, specific_needs_pct). The 5
    //     always-evaluated dimensions are NOT subject to the zero-drop —
    //     a genuine 0 there is a meaningful signal worth showing.
    //
    // The bottom-semicircle values are still multiplied by
    // profileConfPct / 100 to preserve the Phase 12B confidence scaling.
    // The top-semicircle archetype values are NOT confidence-scaled —
    // archetypes describe the OUTFIT's aesthetic profile, not how
    // confident we are about the user's profile.
    var CONTEXT_GATED_KEYS = {{
      "pairing_coherence_pct": true,
      "occasion_pct": true,
      "weather_time_pct": true,
      "specific_needs_pct": true,
    }};

    // ── Top semicircle data: archetypes (always 8) ──
    var archetypes = [
      {{ key: "classic_pct", label: "Classic" }}, {{ key: "dramatic_pct", label: "Dramatic" }},
      {{ key: "romantic_pct", label: "Romantic" }}, {{ key: "natural_pct", label: "Natural" }},
      {{ key: "minimalist_pct", label: "Minimalist" }}, {{ key: "creative_pct", label: "Creative" }},
      {{ key: "sporty_pct", label: "Sporty" }}, {{ key: "edgy_pct", label: "Edgy" }},
    ];
    var archetypeValues = archetypes.map(function(a) {{ return outfit[a.key] || 0; }});

    // ── Bottom semicircle data: filtered evaluation criteria (5-9) ──
    var criteria = buildEvaluationCriteria(outfit, responseMetadata).filter(function(c) {{
      var v = outfit[c.key];
      if (v === null || v === undefined) return false;
      if (CONTEXT_GATED_KEYS[c.key] && v === 0) return false;
      return true;
    }});
    var confFactor = profileConfPct / 100;
    var criteriaValues = criteria.map(function(c) {{
      return Math.round((outfit[c.key] || 0) * confFactor);
    }});
    var hasCriteriaData = criteria.length > 0 && criteriaValues.some(function(v) {{ return v > 0; }});

    // ── Canvas setup ──
    // Width 290 × Height 320: the chart lives at the bottom of the
    // .outfit-info column (40% right column of the PDP card). 290px
    // is slightly wider than the column's ~280px usable width so the
    // canvas CSS-scales down by ~5% via aspect-ratio: 290/320 +
    // max-width: 100% — proportional scaling that keeps the rings
    // perfectly circular. The wider native canvas + the taller height
    // give the labels enough horizontal space to sit on a SINGLE ring
    // without colliding, while the polygon stays prominent.
    var radarDiv = document.createElement("div");
    radarDiv.className = "outfit-radar";
    var polarCanvas = document.createElement("canvas");
    polarCanvas.setAttribute("role", "img");
    polarCanvas.setAttribute("aria-label", "Style + fit profile chart");
    var W = 290, H = 320, dpr = window.devicePixelRatio || 1;
    polarCanvas.width = W * dpr; polarCanvas.height = H * dpr;
    polarCanvas.style.width = W + "px"; polarCanvas.style.height = H + "px";
    radarDiv.appendChild(polarCanvas);
    info.appendChild(radarDiv);
    var pCtx = polarCanvas.getContext("2d");
    pCtx.scale(dpr, dpr);

    // ── Layout constants ──
    // pMaxR=85 polygon radius. pLabelR=115 single-ring label radius —
    // labels for ALL axes sit at this exact distance from the centre,
    // forming a clean circular orbit. The previous staggered double-
    // ring pattern was visually noisy; the single ring reads as a
    // proper radar chart. With 8 archetype labels in 180°, the two
    // centermost labels (Natural at i=3, Minimalist at i=4) have
    // ~45px horizontal separation at this radius, just enough to fit
    // their bounding boxes side by side at the 9px font size.
    var pCx = W / 2, pCy = H / 2;
    var pMaxR = 85;      // outer ring radius
    var pLabelR = 115;   // single-ring axis label radius (no staggering)
    var pMaxValue = 100;

    // ── Grid rings (4 concentric circles at 25/50/75/100) ──
    pCtx.strokeStyle = "rgba(0, 0, 0, 0.08)";
    pCtx.lineWidth = 0.5;
    for (var pRing = 1; pRing <= 4; pRing++) {{
      pCtx.beginPath();
      pCtx.arc(pCx, pCy, (pRing / 4) * pMaxR, 0, 2 * Math.PI);
      pCtx.stroke();
    }}

    // ── Dashed horizontal divider through the centre ──
    pCtx.save();
    pCtx.beginPath();
    pCtx.moveTo(pCx - pMaxR - 10, pCy);
    pCtx.lineTo(pCx + pMaxR + 10, pCy);
    pCtx.strokeStyle = "rgba(0, 0, 0, 0.14)";
    pCtx.lineWidth = 0.75;
    pCtx.setLineDash([4, 4]);
    pCtx.stroke();
    pCtx.restore();

    // ── drawProfile: one filled arc sector per axis ──
    // axes = [{{key, label}}, ...], values = [int, ...] aligned to axes
    //
    // All labels sit on a SINGLE circular ring at pLabelR. The previous
    // staggered double-ring pattern was visually noisy — the eye read
    // it as random rather than orderly. The single-ring layout looks
    // like a proper radar chart and reads as a clean circular orbit.
    function drawProfile(axes, values, color, fillColor, startAngle, span) {{
      var n = axes.length;
      if (n === 0) return;
      var sector = span / n;
      var gap = Math.min(0.09, sector * 0.15);
      for (var i = 0; i < n; i++) {{
        var midAngle = startAngle + (i + 0.5) * sector;
        var arcRadius = Math.max((values[i] / pMaxValue) * pMaxR, 4);

        // Arc sector (filled wedge from centre)
        pCtx.beginPath();
        pCtx.moveTo(pCx, pCy);
        pCtx.arc(pCx, pCy, arcRadius, midAngle - sector / 2 + gap / 2, midAngle + sector / 2 - gap / 2);
        pCtx.closePath();
        pCtx.fillStyle = fillColor;
        pCtx.fill();
        pCtx.strokeStyle = color;
        pCtx.lineWidth = 1.5;
        pCtx.stroke();

        // Tip dot at the arc midpoint
        pCtx.beginPath();
        pCtx.arc(pCx + Math.cos(midAngle) * arcRadius, pCy + Math.sin(midAngle) * arcRadius, 2.5, 0, 2 * Math.PI);
        pCtx.fillStyle = color;
        pCtx.fill();

        // Axis label — all labels on a single circle at pLabelR for
        // a clean, orderly orbit around the chart.
        //
        // Centermost-label nudge: when two labels straddle the vertical
        // centre of a semicircle (e.g. Natural at i=3 and Minimalist at
        // i=4 in the 8-axis top semicircle), their natural trig
        // positions sit only ~45px apart at pLabelR=115 — enough that
        // their bounding boxes barely have a 1px gap and they read as a
        // single concatenated phrase. The nudge pushes them ~9px
        // further apart in the direction of their cos sign, giving
        // ~18px of additional horizontal breathing room without
        // resizing the canvas or affecting any other label. The check
        // `0 < |ca| < 0.28` only fires for the two centermost labels in
        // a semicircle; labels exactly at 12/6 o'clock (`ca === 0`,
        // which happens with odd-axis-count semicircles) get no nudge.
        var ca = Math.cos(midAngle);
        var sa = Math.sin(midAngle);
        var labelXNudge = 0;
        if (Math.abs(ca) > 0 && Math.abs(ca) < 0.28) {{
          labelXNudge = ca > 0 ? 9 : -9;
        }}
        var lx = pCx + ca * pLabelR + labelXNudge;
        var ly = pCy + sa * pLabelR;
        pCtx.textAlign = Math.abs(ca) < 0.28 ? "center" : (ca > 0 ? "left" : "right");
        pCtx.textBaseline = Math.abs(sa) < 0.28 ? "middle" : (sa > 0 ? "top" : "bottom");
        pCtx.font = "600 9px system-ui, sans-serif";
        pCtx.fillStyle = color;
        pCtx.fillText(axes[i].label, lx, ly);
      }}
    }}

    // ── Top semicircle: style archetypes (always 8 axes) ──
    drawProfile(
      archetypes,
      archetypeValues,
      "#7F77DD",                       // stroke + label colour
      "rgba(127, 119, 221, 0.38)",     // fill
      Math.PI,                         // start at 9 o'clock
      Math.PI                          // span the top semicircle
    );

    // ── Bottom semicircle: filtered evaluation criteria ──
    if (hasCriteriaData) {{
      drawProfile(
        criteria,
        criteriaValues,
        "#8B3055",
        "rgba(139, 48, 85, 0.35)",
        0,                             // start at 3 o'clock
        Math.PI                        // span the bottom semicircle
      );
    }}

    // No legend — the axis labels are already color-coded (purple
    // archetypes on top, burgundy fit dimensions on bottom) so a
    // separate caption underneath would be redundant. Removing it
    // also frees a few pixels of vertical room inside the
    // .outfit-info column.

    // Dislike form (stays in info panel, expands when thumbs-down clicked)
    var dislikeForm = document.createElement("div");
    dislikeForm.className = "dislike-form";
    var reactionRow = document.createElement("div");
    reactionRow.className = "reaction-row";
    var ta = document.createElement("textarea");
    ta.placeholder = "What's missing or what would you prefer?";
    ["Too safe", "Too much", "Not me", "Weird pairing", "Show softer", "Show sharper"].forEach(function(label) {{
      var chip = document.createElement("button"); chip.type = "button"; chip.className = "reaction-chip"; chip.textContent = label;
      chip.addEventListener("click", function() {{ ta.value = label; ta.focus(); }});
      reactionRow.appendChild(chip);
    }});
    dislikeForm.appendChild(reactionRow);
    dislikeForm.appendChild(ta);
    var dislikeActions = document.createElement("div");
    dislikeActions.className = "dislike-actions";
    var submitBtn = document.createElement("button"); submitBtn.textContent = "Submit";
    var cancelBtn = document.createElement("button"); cancelBtn.className = "secondary"; cancelBtn.textContent = "Cancel";
    dislikeActions.appendChild(submitBtn); dislikeActions.appendChild(cancelBtn);
    dislikeForm.appendChild(dislikeActions);
    info.appendChild(dislikeForm);

    var fbStatus = document.createElement("div");
    fbStatus.className = "feedback-status";
    info.appendChild(fbStatus);

    var outfitRank = outfit.rank || 0;
    var itemIds = items.map(function(i) {{ return i.product_id || ""; }}).filter(Boolean);
    likeBtn.addEventListener("click", function() {{ sendFeedback(convId, outfitRank, "like", "", itemIds, fbStatus, fbWrap, dislikeForm); }});
    dislikeBtn.addEventListener("click", function() {{ dislikeForm.classList.add("open"); }});
    cancelBtn.addEventListener("click", function() {{ dislikeForm.classList.remove("open"); ta.value = ""; }});
    submitBtn.addEventListener("click", function() {{ sendFeedback(convId, outfitRank, "dislike", ta.value.trim(), itemIds, fbStatus, fbWrap, dislikeForm); }});

    card.appendChild(header); card.appendChild(thumbs); card.appendChild(heroWrap); card.appendChild(info);
    return card;
  }}

  // ══════════════════════════════════════════════
  // FEEDBACK
  // ══════════════════════════════════════════════

  async function sendFeedback(convId, outfitRank, eventType, notes, itemIds, statusEl, fbWrap, dislikeForm) {{
    statusEl.textContent = "Sending...";
    statusEl.className = "feedback-status";
    try {{
      var res = await fetch("/v1/conversations/" + convId + "/feedback", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ outfit_rank: outfitRank, event_type: eventType, notes: notes, item_ids: itemIds }}),
      }});
      var data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Feedback failed");
      statusEl.textContent = eventType === "like" ? "Thanks for your feedback!" : "Feedback submitted. Thank you!";
      statusEl.className = "feedback-status success";
      fbWrap.style.display = "none";
      dislikeForm.classList.remove("open");
    }} catch (e) {{
      statusEl.textContent = "Error: " + (e.message || String(e));
      statusEl.className = "feedback-status error";
    }}
  }}

  // ══════════════════════════════════════════════
  // RENDER HELPERS
  // ══════════════════════════════════════════════

  function renderOutfits(outfits, convId, responseMetadata) {{
    if (!outfits || !outfits.length) return;
    for (var i = 0; i < outfits.length; i++) {{
      var card = buildOutfitCard(outfits[i], convId, responseMetadata || {{}});
      feed.appendChild(card);
    }}
    feed.scrollTop = feed.scrollHeight;
  }}

  function renderQuickReplies(suggestions, structuredGroups) {{
    if ((!suggestions || !suggestions.length) && (!structuredGroups || !structuredGroups.length)) return;
    var wrap = document.createElement("div");
    wrap.className = "followup-groups";

    // Prefer structured groups emitted by the response_formatter (label + suggestions).
    // Fall back to the legacy substring bucketing only when no structured payload exists.
    var groupsToRender = [];
    if (structuredGroups && structuredGroups.length) {{
      structuredGroups.forEach(function(g) {{
        var items = (g && g.suggestions) || [];
        if (items.length) groupsToRender.push({{ label: g.label || "Suggestions", items: items }});
      }});
    }} else {{
      var grouped = {{ "Improve It": [], "Show Alternatives": [], "Explain Why": [], "Shop The Gap": [], "Save For Later": [] }};
      function bucketFor(text) {{
        var n = String(text || "").toLowerCase();
        if (n.indexOf("explain") !== -1 || n.indexOf("why") !== -1) return "Explain Why";
        if (n.indexOf("save") !== -1 || n.indexOf("later") !== -1) return "Save For Later";
        if (n.indexOf("catalog") !== -1 || n.indexOf("shop") !== -1 || n.indexOf("buy") !== -1) return "Shop The Gap";
        if (n.indexOf("more") !== -1 || n.indexOf("different") !== -1 || n.indexOf("alternative") !== -1) return "Show Alternatives";
        return "Improve It";
      }}
      for (var i = 0; i < suggestions.length; i++) grouped[bucketFor(suggestions[i])].push(suggestions[i]);
      Object.entries(grouped).forEach(function(entry) {{
        if (entry[1].length) groupsToRender.push({{ label: entry[0], items: entry[1] }});
      }});
    }}

    groupsToRender.forEach(function(g) {{
      var section = document.createElement("div"); section.className = "followup-group";
      var title = document.createElement("strong"); title.textContent = g.label;
      var row = document.createElement("div"); row.className = "followup-row";
      g.items.forEach(function(text) {{
        var btn = document.createElement("button");
        btn.className = "secondary";
        btn.style.cssText = "font-size:13px;padding:6px 14px;border-radius:999px;";
        btn.textContent = text;
        btn.addEventListener("click", function() {{ messageEl.value = text; wrap.remove(); send(); }});
        row.appendChild(btn);
      }});
      section.appendChild(title); section.appendChild(row); wrap.appendChild(section);
    }});
    feed.appendChild(wrap);
    feed.scrollTop = feed.scrollHeight;
  }}

  // Return the most recent stage that has a non-empty, human-facing
  // message. Deliberately ignores stages whose template resolved to an
  // empty string — those are intent-signalled "don't show this" events
  // (e.g. user_context_completed, outfit_assembly_completed).
  function latestVisibleStage(stages) {{
    if (!stages || !stages.length) return null;
    for (var i = stages.length - 1; i >= 0; i--) {{
      var s = stages[i];
      var msg = s && s.message;
      if (msg && String(msg).trim()) return s;
    }}
    return null;
  }}

  function renderStages(stages) {{
    var latest = latestVisibleStage(stages);
    stageBar.textContent = latest ? latest.message : "";
  }}

  // ══════════════════════════════════════════════
  // CONVERSATION & SENDING
  // ══════════════════════════════════════════════

  async function ensureConversation() {{
    if (conversationId) return conversationId;
    var res = await fetch("/v1/conversations", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ user_id: USER_ID }}),
    }});
    var data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to create conversation");
    conversationId = data.conversation_id;
    loadConversationHistory();
    return conversationId;
  }}

  // Fade out and remove a thinking bubble. Safe to call with null.
  function fadeOutThinkingBubble(bubble) {{
    if (!bubble) return;
    bubble.classList.add("fading");
    // Match the 360ms opacity transition in the .bubble.agent CSS rule.
    setTimeout(function() {{ if (bubble.parentNode) bubble.parentNode.removeChild(bubble); }}, 400);
  }}

  async function pollJob(convId, jobId) {{
    // Single in-place "thinking" bubble per turn. Updates its text as new
    // stages arrive, fades out on completion/failure. Matches modern
    // chatbot UX (ChatGPT, Claude, Gemini) instead of stacking one bubble
    // per stage. The subtle .stage-bar at the bottom remains as a
    // secondary progress indicator for users who have scrolled up.
    var thinkingBubble = null;
    var lastStageText = "";
    try {{
      while (true) {{
        var res = await fetch("/v1/conversations/" + convId + "/turns/" + jobId + "/status");
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Polling failed");
        var stages = data.stages || [];
        renderStages(stages);
        // Update or create the single thinking bubble from the latest
        // *visible* stage (skipping the deliberately-silent ones).
        var latest = latestVisibleStage(stages);
        var latestMsg = latest ? latest.message : "";
        if (latestMsg && latestMsg !== lastStageText) {{
          if (!thinkingBubble) {{
            thinkingBubble = addAgentBubble(latestMsg);
          }} else {{
            // The bubble contains [dot, textNode]. Update the text node only.
            if (thinkingBubble.lastChild) {{
              thinkingBubble.lastChild.textContent = latestMsg;
            }} else {{
              thinkingBubble.appendChild(document.createTextNode(latestMsg));
            }}
            // Keep it in view when new stages arrive.
            feed.scrollTop = feed.scrollHeight;
          }}
          lastStageText = latestMsg;
        }}
        if (data.status === "completed") {{
          fadeOutThinkingBubble(thinkingBubble);
          stageBar.textContent = "";
          return data.result;
        }}
        if (data.status === "failed") throw new Error(data.error || "Turn failed");
        await new Promise(function(resolve) {{ setTimeout(resolve, 800); }});
      }}
    }} catch (exc) {{
      fadeOutThinkingBubble(thinkingBubble);
      stageBar.textContent = "";
      throw exc;
    }}
  }}

  async function send() {{
    err.textContent = "";
    var message = messageEl.value.trim();
    if (!USER_ID) {{ err.textContent = "No user session. Please log in."; return; }}
    if (!message && !pendingImageData) {{ return; }}
    if (!message && pendingImageData) {{ message = "What goes with this? Show me pairing options."; }}

    sendBtn.disabled = true;
    messageEl.disabled = true;
    try {{
      var convId = await ensureConversation();
      var attachedImage = pendingImageData;
      addBubble(message, "user", attachedImage);
      messageEl.value = "";
      messageEl.style.height = "auto";
      clearImagePreview();
      var payload = {{ user_id: USER_ID, message: message }};
      if (attachedImage) payload.image_data = attachedImage;
      var res = await fetch("/v1/conversations/" + convId + "/turns/start", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload),
      }});
      var job = await res.json();
      if (!res.ok) throw new Error(job.detail || "Failed to start turn");
      var result = await pollJob(convId, job.job_id);
      addBubble(result.assistant_message || "", "assistant");
      var __md = result.metadata || {{}};
      var __groups = (__md && __md.follow_up_groups) || [];
      if (result.response_type === "clarification") {{
        renderQuickReplies(result.follow_up_suggestions || [], __groups);
      }} else {{
        renderOutfits(result.outfits || [], convId, __md);
        renderQuickReplies(result.follow_up_suggestions || [], __groups);
      }}
      // Refresh sidebar
      loadConversationHistory();
    }} catch (e) {{
      err.textContent = e.message || String(e);
    }} finally {{
      sendBtn.disabled = false;
      messageEl.disabled = false;
      messageEl.focus();
    }}
  }}

  sendBtn.addEventListener("click", send);

  // Prompt cards
  document.querySelectorAll(".prompt-card").forEach(function(card) {{
    card.addEventListener("click", function() {{
      messageEl.value = card.getAttribute("data-prompt") || card.textContent;
      messageEl.focus();
      send();
    }});
  }});

  // Progressive disclosure: "More ways to style" reveals secondary prompts
  var promptMoreToggle = document.getElementById("promptMoreToggle");
  var promptMoreGrid = document.getElementById("promptMoreGrid");
  if (promptMoreToggle && promptMoreGrid) {{
    promptMoreToggle.addEventListener("click", function() {{
      var isOpen = promptMoreGrid.classList.toggle("open");
      promptMoreToggle.classList.toggle("open", isOpen);
      promptMoreToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }});
  }}

  // ══════════════════════════════════════════════
  // CHAT HISTORY SIDEBAR
  // ══════════════════════════════════════════════

  async function loadConversationHistory() {{
    if (!USER_ID) return;
    try {{
      var res = await fetch("/v1/users/" + encodeURIComponent(USER_ID) + "/conversations");
      var data = await res.json();
      if (!res.ok) return;
      var convs = data.conversations || [];
      if (!convs.length) {{
        historyList.innerHTML = '<div class="history-empty">Start a conversation to see your history here.</div>';
        return;
      }}
      historyList.innerHTML = "";
      convs.forEach(function(c) {{
        var btn = document.createElement("button");
        btn.className = "history-item" + (c.conversation_id === conversationId ? " active" : "");
        var label = c.title || c.preview || "Conversation";
        btn.innerHTML = '<span class="preview">' + escapeHtml(label) + '</span>' +
          '<span class="ts">' + escapeHtml(relativeTime(c.updated_at || c.created_at)) + '</span>' +
          '<span class="history-actions">' +
            '<span class="history-action-btn" data-hist-action="rename" data-conv-id="' + escapeHtml(c.conversation_id) + '" data-conv-label="' + escapeHtml(label) + '" title="Rename">&#9998;</span>' +
            '<span class="history-action-btn" data-hist-action="delete" data-conv-id="' + escapeHtml(c.conversation_id) + '" title="Delete">&#128465;</span>' +
          '</span>';
        btn.addEventListener("click", function(e) {{
          if (e.target.closest("[data-hist-action]")) return;
          loadConversation(c.conversation_id);
        }});
        historyList.appendChild(btn);
      }});
    }} catch (_) {{}}
  }}

  // Chat history rename/delete actions
  if (historyList) {{
    historyList.addEventListener("click", async function(e) {{
      var actionEl = e.target.closest("[data-hist-action]");
      if (!actionEl) return;
      e.stopPropagation();
      var action = actionEl.getAttribute("data-hist-action");
      var convId = actionEl.getAttribute("data-conv-id");

      if (action === "delete") {{
        if (!confirm("Delete this conversation?")) return;
        // Immediately remove from sidebar for instant feedback
        var histItem = actionEl.closest(".history-item");
        if (histItem) histItem.remove();
        if (conversationId === convId) {{
          conversationId = null;
          feed.innerHTML = "";
          stageBar.textContent = "";
        }}
        try {{
          var res = await fetch("/v1/conversations/" + encodeURIComponent(convId), {{ method: "DELETE" }});
          if (!res.ok) {{ var err = await res.json(); throw new Error(err.detail || "Delete failed"); }}
          loadConversationHistory();
        }} catch(ex) {{
          // Restore sidebar if delete failed
          loadConversationHistory();
          alert(ex.message || "Failed to delete conversation.");
        }}
      }}

      if (action === "rename") {{
        var histItem = actionEl.closest(".history-item");
        if (!histItem) return;
        var previewSpan = histItem.querySelector(".preview");
        if (!previewSpan) return;
        var currentLabel = actionEl.getAttribute("data-conv-label") || previewSpan.textContent || "";
        var input = document.createElement("input");
        input.type = "text";
        input.className = "history-rename-input";
        input.value = currentLabel;
        previewSpan.textContent = "";
        previewSpan.appendChild(input);
        input.focus();
        input.select();

        async function commitRename() {{
          var newTitle = input.value.trim();
          if (!newTitle || newTitle === currentLabel) {{
            previewSpan.textContent = currentLabel;
            return;
          }}
          try {{
            var res = await fetch("/v1/conversations/" + encodeURIComponent(convId), {{
              method: "PATCH",
              headers: {{ "Content-Type": "application/json" }},
              body: JSON.stringify({{ title: newTitle }})
            }});
            if (!res.ok) {{ var err = await res.json(); throw new Error(err.detail || "Rename failed"); }}
            loadConversationHistory();
          }} catch(ex) {{
            previewSpan.textContent = currentLabel;
            alert(ex.message || "Failed to rename.");
          }}
        }}

        var committed = false;
        input.addEventListener("keydown", function(ke) {{
          if (ke.key === "Enter") {{ ke.preventDefault(); if (!committed) {{ committed = true; commitRename(); }} }}
          if (ke.key === "Escape") {{ previewSpan.textContent = currentLabel; }}
        }});
        input.addEventListener("blur", function() {{
          if (!committed) {{ committed = true; commitRename(); }}
        }});
      }}
    }});
  }}

  async function loadConversation(convId) {{
    conversationId = convId;
    feed.innerHTML = "";
    stageBar.textContent = "";
    // Highlight in sidebar
    historyList.querySelectorAll(".history-item").forEach(function(el) {{ el.classList.remove("active"); }});
    var items = historyList.querySelectorAll(".history-item");
    // Re-highlight active
    loadConversationHistory();
    try {{
      var res = await fetch("/v1/conversations/" + convId + "/turns");
      var data = await res.json();
      if (!res.ok) return;
      var turns = data.turns || [];
      for (var i = 0; i < turns.length; i++) {{
        var t = turns[i];
        if (t.user_message) addBubble(t.user_message, "user");
        if (t.assistant_message) {{
          addBubble(t.assistant_message, "assistant");
          // Render outfits from resolved context
          var ctx = t.resolved_context || {{}};
          var outfits = ctx.outfits || [];
          if (outfits.length) {{
            renderOutfits(outfits, convId, ctx);
          }}
        }}
      }}
    }} catch (_) {{}}
  }}

  // New chat — creates a fresh conversation
  if (newChatBtn) {{
    newChatBtn.addEventListener("click", async function() {{
      if (ACTIVE_VIEW !== "chat") {{
        window.location.href = "/?user=" + encodeURIComponent(USER_ID) + "&view=chat&new=1";
        return;
      }}
      // Create a new conversation immediately
      try {{
        var res = await fetch("/v1/conversations", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ user_id: USER_ID }}),
        }});
        var data = await res.json();
        if (res.ok && data.conversation_id) {{
          conversationId = data.conversation_id;
        }} else {{
          conversationId = "";
        }}
      }} catch (_) {{
        conversationId = "";
      }}
      feed.innerHTML = "";
      stageBar.textContent = "";
      if (feedWelcome) {{
        feedWelcome.style.display = "";
        feed.appendChild(feedWelcome);
      }}
      loadConversationHistory();
      if (messageEl) messageEl.focus();
    }});
  }}

  if (brandLink) {{
    brandLink.addEventListener("click", function() {{
      window.location.href = "/?user=" + encodeURIComponent(USER_ID) + "&view=chat";
    }});
  }}

  // Hamburger (mobile)
  if (hamburgerBtn) {{
    hamburgerBtn.addEventListener("click", function() {{
      if (historyRail) historyRail.classList.toggle("mobile-open");
    }});
  }}

  // Avatar dropdown
  if (avatarBtn && avatarDropdown) {{
    avatarBtn.addEventListener("click", function(e) {{
      e.stopPropagation();
      avatarDropdown.classList.toggle("open");
    }});
    document.addEventListener("click", function() {{ avatarDropdown.classList.remove("open"); }});
  }}

  // Logout
  if (logoutBtn) {{
    logoutBtn.addEventListener("click", function() {{
      try {{ localStorage.removeItem("aura_user_id"); }} catch(_) {{}}
      window.location.href = "/";
    }});
  }}

  // ══════════════════════════════════════════════
  // WARDROBE VIEW
  // ══════════════════════════════════════════════

  // Recognized occasion tags from catalog enrichment metadata. Used by the
  // "Occasion-ready" filter so we match against the structured field instead
  // of doing keyword scans against item titles.
  var OCCASION_READY_TAGS = [
    "wedding", "cocktail_party", "cocktail", "date_night",
    "office", "work_meeting", "business", "interview",
    "semi_formal", "formal", "evening", "party",
    "festive", "ceremony", "gala"
  ];
  var OCCASION_READY_FORMALITY = [
    "smart_casual", "business_casual", "semi_formal", "formal", "ultra_formal"
  ];

  function wardrobeFilterMatches(item, filter) {{
    if (filter === "all") return true;
    var category = String(item.garment_category || "").toLowerCase();
    if (filter === "tops") return ["top", "shirt", "blouse", "tee", "tshirt", "sweater", "knit"].some(function(t) {{ return category.indexOf(t) !== -1; }});
    if (filter === "bottoms") return ["pant", "trouser", "jean", "skirt", "short"].some(function(t) {{ return category.indexOf(t) !== -1; }});
    if (filter === "shoes") return ["shoe", "heel", "boot", "loafer", "sandal", "sneaker"].some(function(t) {{ return category.indexOf(t) !== -1; }});
    if (filter === "dresses") return ["dress", "gown", "romper", "jumpsuit"].some(function(t) {{ return category.indexOf(t) !== -1; }});
    if (filter === "outerwear") return ["jacket", "blazer", "coat", "parka", "hoodie", "cardigan"].some(function(t) {{ return category.indexOf(t) !== -1; }});
    if (filter === "accessories") return ["bag", "belt", "scarf", "watch", "jewelry", "hat", "accessory", "sunglasses", "tie", "bracelet", "necklace", "earring", "ring"].some(function(t) {{ return category.indexOf(t) !== -1; }});
    if (filter === "occasion") {{
      // Occasion-ready uses the enrichment metadata fields (occasion_fit and
      // formality_level), matched against a recognized tag set, instead of
      // brittle "non-empty / not everyday" string checks against item names.
      var occasionFit = String(item.occasion_fit || "").toLowerCase().trim().replace(/[\\s]+/g, "_");
      var formalityLevel = String(item.formality_level || "").toLowerCase().trim().replace(/[\\s]+/g, "_");
      if (!occasionFit && !formalityLevel) return false;
      var occasionMatch = OCCASION_READY_TAGS.some(function(tag) {{ return occasionFit.indexOf(tag) !== -1; }});
      var formalityMatch = OCCASION_READY_FORMALITY.indexOf(formalityLevel) !== -1;
      return occasionMatch || formalityMatch;
    }}
    return true;
  }}

  function wardrobeColorMatches(item, color) {{
    if (color === "all") return true;
    var primary = String(item.primary_color || "").toLowerCase();
    var secondary = String(item.secondary_color || "").toLowerCase();
    return primary.indexOf(color) !== -1 || secondary.indexOf(color) !== -1;
  }}

  function wardrobeSearchMatches(item, query) {{
    if (!query) return true;
    var hay = (String(item.title || "") + " " + String(item.description || "") + " " + String(item.brand || "") + " " + String(item.garment_category || "")).toLowerCase();
    return hay.indexOf(query) !== -1;
  }}

  function renderWardrobeCloset() {{
    var filtered = wardrobeItems.filter(function(item) {{
      return wardrobeFilterMatches(item, activeWardrobeFilter)
        && wardrobeColorMatches(item, activeWardrobeColor)
        && wardrobeSearchMatches(item, wardrobeSearchQuery);
    }});
    if (!filtered.length) {{
      closetGrid.innerHTML = '<div class="wardrobe-empty">No saved pieces match this filter yet.</div>';
      return;
    }}
    closetGrid.innerHTML = filtered.map(function(item) {{
      var imageUrl = wardrobeImageUrl(item);
      var tags = [item.garment_category, item.primary_color, item.occasion_fit].filter(Boolean).slice(0, 3);
      var title = item.title || "Wardrobe Item";
      var imageHtml = imageUrl
        ? '<img src="' + escapeHtml(imageUrl) + '" alt="' + escapeHtml(title) + '" loading="lazy" />'
        : '<div class="closet-placeholder">Saved Piece</div>';
      return '<article class="closet-card">' +
        '<div class="closet-image">' + imageHtml + '</div>' +
        '<div class="closet-body">' +
          '<h3>' + escapeHtml(title) + '</h3>' +
          '<p>' + escapeHtml(item.description || "Saved in your wardrobe.") + '</p>' +
          '<div class="tag-row">' + (tags.length ? tags.map(function(tag) {{ return '<span class="tag">' + escapeHtml(tag) + '</span>'; }}).join("") : '<span class="tag">untagged</span>') + '</div>' +
          '<div class="closet-actions">' +
            '<button class="studio-btn" type="button" data-wardrobe-prompt="' + escapeHtml("Style my " + title + " from my wardrobe.") + '" data-wardrobe-img="' + escapeHtml(imageUrl || "") + '">Style This</button>' +
            '<button class="studio-btn" type="button" data-wardrobe-prompt="' + escapeHtml("Build me an outfit around my " + title + " for the right occasion.") + '" data-wardrobe-img="' + escapeHtml(imageUrl || "") + '">Build A Look</button>' +
            '<button class="studio-btn" type="button" data-action="edit" data-item-id="' + escapeHtml(item.id) + '">Edit</button>' +
            '<button class="studio-btn danger" type="button" data-action="delete" data-item-id="' + escapeHtml(item.id) + '">Delete</button>' +
          '</div>' +
        '</div></article>';
    }}).join("");
  }}

  async function loadWardrobeStudio() {{
    if (!USER_ID) {{ wStatusPill.textContent = "No user"; return; }}
    wStatusPill.textContent = "Loading...";
    try {{
      var responses = await Promise.all([
        fetch("/v1/onboarding/wardrobe/" + encodeURIComponent(USER_ID)),
        fetch("/v1/onboarding/wardrobe/" + encodeURIComponent(USER_ID) + "/summary"),
      ]);
      if (!responses[0].ok || !responses[1].ok) throw new Error("Load failed");
      var itemsPayload = await responses[0].json();
      var summaryPayload = await responses[1].json();
      wardrobeItems = itemsPayload.items || [];
      wardrobeSummary = summaryPayload || null;
      wardrobeItemsById = {{}};
      wardrobeItems.forEach(function(item) {{ wardrobeItemsById[item.id] = item; }});
      wStatCount.textContent = String(wardrobeItems.length);
      wStatComplete.textContent = String((wardrobeSummary && wardrobeSummary.completeness_score_pct) || 0) + "%";
      wStatusPill.textContent = wardrobeItems.length ? "Loaded" : "No pieces yet";
      // Restore persisted filters
      try {{
        var saved = JSON.parse(localStorage.getItem("aura_wardrobe_filters") || "null");
        if (saved) {{
          if (saved.category) {{ activeWardrobeFilter = saved.category; }}
          if (saved.color) {{ activeWardrobeColor = saved.color; }}
          if (saved.search) {{ wardrobeSearchQuery = saved.search; if (wardrobeSearchInput) wardrobeSearchInput.value = saved.search; }}
          // Sync chip active states
          if (wardrobeFilters) wardrobeFilters.querySelectorAll(".filter-chip").forEach(function(c) {{ c.classList.toggle("active", (c.getAttribute("data-filter") || "all") === activeWardrobeFilter); }});
          if (wardrobeColorFilters) wardrobeColorFilters.querySelectorAll(".filter-chip").forEach(function(c) {{ c.classList.toggle("active", (c.getAttribute("data-color") || "all") === activeWardrobeColor); }});
        }}
      }} catch(_) {{}}
    }} catch (_) {{
      wardrobeItems = []; wardrobeSummary = null;
      wStatusPill.textContent = "Unable to load";
    }}
    renderWardrobeCloset();
  }}

  // Persist wardrobe filter state
  function saveWardrobeFilterState() {{
    try {{
      localStorage.setItem("aura_wardrobe_filters", JSON.stringify({{
        category: activeWardrobeFilter, color: activeWardrobeColor, search: wardrobeSearchQuery
      }}));
    }} catch(_) {{}}
  }}

  // Wardrobe category filter chips
  if (wardrobeFilters) {{
    wardrobeFilters.addEventListener("click", function(e) {{
      var chip = e.target.closest(".filter-chip");
      if (!chip) return;
      activeWardrobeFilter = chip.getAttribute("data-filter") || "all";
      wardrobeFilters.querySelectorAll(".filter-chip").forEach(function(c) {{ c.classList.remove("active"); }});
      chip.classList.add("active");
      saveWardrobeFilterState();
      renderWardrobeCloset();
    }});
  }}

  // Wardrobe color filter chips
  if (wardrobeColorFilters) {{
    wardrobeColorFilters.addEventListener("click", function(e) {{
      var chip = e.target.closest(".filter-chip");
      if (!chip) return;
      activeWardrobeColor = chip.getAttribute("data-color") || "all";
      wardrobeColorFilters.querySelectorAll(".filter-chip").forEach(function(c) {{ c.classList.remove("active"); }});
      chip.classList.add("active");
      saveWardrobeFilterState();
      renderWardrobeCloset();
    }});
  }}

  // Wardrobe search
  if (wardrobeSearchInput) {{
    wardrobeSearchInput.addEventListener("input", function(e) {{
      wardrobeSearchQuery = (e.target.value || "").toLowerCase().trim();
      saveWardrobeFilterState();
      renderWardrobeCloset();
    }});
  }}

  // Wardrobe card actions (Style This, Build A Look, Edit, Delete)
  if (closetGrid) {{
    closetGrid.addEventListener("click", async function(e) {{
      // Edit action
      var editBtn = e.target.closest("[data-action='edit']");
      if (editBtn) {{
        var itemId = editBtn.getAttribute("data-item-id");
        var item = wardrobeItemsById[itemId];
        if (!item) return;
        var modal = document.getElementById("editItemModal");
        if (!modal) return;
        document.getElementById("editItemId").value = item.id;
        document.getElementById("editTitle").value = item.title || "";
        document.getElementById("editDescription").value = item.description || "";
        document.getElementById("editCategory").value = item.garment_category || "";
        document.getElementById("editSubtype").value = item.garment_subtype || "";
        document.getElementById("editPrimaryColor").value = item.primary_color || "";
        document.getElementById("editSecondaryColor").value = item.secondary_color || "";
        document.getElementById("editPattern").value = item.pattern_type || "";
        document.getElementById("editFormality").value = item.formality_level || "";
        document.getElementById("editOccasion").value = item.occasion_fit || "";
        document.getElementById("editBrand").value = item.brand || "";
        document.getElementById("editNotes").value = item.notes || "";
        var imgPreview = document.getElementById("editItemPreview");
        var imgUrl = wardrobeImageUrl(item);
        if (imgUrl) {{ imgPreview.src = imgUrl; imgPreview.style.display = "inline-block"; }}
        else {{ imgPreview.style.display = "none"; }}
        document.getElementById("editItemError").textContent = "";
        modal.classList.add("open");
        return;
      }}
      // Delete action
      var delBtn = e.target.closest("[data-action='delete']");
      if (delBtn) {{
        var itemId = delBtn.getAttribute("data-item-id");
        var item = wardrobeItemsById[itemId];
        var name = (item && item.title) || "this item";
        if (!confirm("Remove " + name + " from your wardrobe?")) return;
        try {{
          var res = await fetch("/v1/onboarding/wardrobe/items/" + encodeURIComponent(itemId) + "?user_id=" + encodeURIComponent(USER_ID), {{ method: "DELETE" }});
          if (!res.ok) {{ var err = await res.json(); throw new Error(err.detail || "Delete failed"); }}
          loadWardrobeStudio();
        }} catch(ex) {{
          alert(ex.message || "Failed to delete item.");
        }}
        return;
      }}
      // Style This / Build A Look (existing)
      var btn = e.target.closest("[data-wardrobe-prompt]");
      if (!btn) return;
      var prompt = btn.getAttribute("data-wardrobe-prompt") || "";
      var imgUrl = btn.getAttribute("data-wardrobe-img") || "";
      var chatUrl = "/?user=" + encodeURIComponent(USER_ID) + "&view=chat&prompt=" + encodeURIComponent(prompt);
      if (imgUrl) chatUrl += "&wardrobe_img=" + encodeURIComponent(imgUrl);
      window.location.href = chatUrl;
    }});
  }}

  // Refresh button
  if (document.getElementById("wardrobeRefreshBtn")) {{
    document.getElementById("wardrobeRefreshBtn").addEventListener("click", loadWardrobeStudio);
  }}

  // Add Item modal
  (function() {{
    var modal = document.getElementById("addItemModal");
    var form = document.getElementById("addItemForm");
    var fileInput = document.getElementById("addItemFile");
    var preview = document.getElementById("addItemPreview");
    var errorEl = document.getElementById("addItemError");
    var addBtn = document.getElementById("wardrobeAddBtn");
    var cancelBtn = document.getElementById("addItemCancel");
    if (!modal || !form || !addBtn) return;

    var placeholder = document.getElementById("addItemPlaceholder");
    var dropLabel = document.getElementById("addItemLabel");
    var dropzone = document.getElementById("addItemDropzone");

    function resetModal() {{ form.reset(); preview.style.display = "none"; errorEl.textContent = ""; if (placeholder) placeholder.style.display = ""; if (dropLabel) dropLabel.style.display = ""; }}

    addBtn.addEventListener("click", function() {{ modal.classList.add("open"); }});
    cancelBtn.addEventListener("click", function() {{ modal.classList.remove("open"); resetModal(); }});
    modal.addEventListener("click", function(e) {{ if (e.target === modal) {{ modal.classList.remove("open"); resetModal(); }} }});

    fileInput.addEventListener("change", function() {{
      if (fileInput.files && fileInput.files[0]) {{
        var reader = new FileReader();
        reader.onload = function(e) {{ preview.src = e.target.result; preview.style.display = "block"; if (placeholder) placeholder.style.display = "none"; if (dropLabel) dropLabel.style.display = "none"; }};
        reader.readAsDataURL(fileInput.files[0]);
      }}
    }});

    if (dropzone) {{
      dropzone.addEventListener("dragover", function(e) {{ e.preventDefault(); dropzone.style.borderColor = "var(--accent)"; }});
      dropzone.addEventListener("dragleave", function() {{ dropzone.style.borderColor = ""; }});
      dropzone.addEventListener("drop", function(e) {{ e.preventDefault(); dropzone.style.borderColor = ""; if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {{ fileInput.files = e.dataTransfer.files; fileInput.dispatchEvent(new Event("change")); }} }});
    }}

    form.addEventListener("submit", async function(e) {{
      e.preventDefault();
      if (!fileInput.files || !fileInput.files[0]) {{ errorEl.textContent = "Please select a photo."; return; }}
      var submitBtn = document.getElementById("addItemSubmit");
      submitBtn.disabled = true; submitBtn.textContent = "Analysing...";
      errorEl.textContent = "";
      var fd = new FormData();
      fd.append("user_id", USER_ID);
      fd.append("file", fileInput.files[0]);
      try {{
        var res = await fetch("/v1/onboarding/wardrobe/items", {{ method: "POST", body: fd }});
        if (!res.ok) {{ var err = await res.json(); throw new Error(err.detail || "Failed to save"); }}
        modal.classList.remove("open"); resetModal();
        loadWardrobeStudio();
      }} catch (ex) {{
        errorEl.textContent = ex.message || "Failed to save item.";
      }} finally {{
        submitBtn.disabled = false; submitBtn.textContent = "Add to Wardrobe";
      }}
    }});
  }}());

  // Edit Item modal
  (function() {{
    var modal = document.getElementById("editItemModal");
    var form = document.getElementById("editItemForm");
    var cancelBtn = document.getElementById("editItemCancel");
    var errorEl = document.getElementById("editItemError");
    if (!modal || !form) return;

    if (cancelBtn) cancelBtn.addEventListener("click", function() {{ modal.classList.remove("open"); }});
    modal.addEventListener("click", function(e) {{ if (e.target === modal) modal.classList.remove("open"); }});

    form.addEventListener("submit", async function(e) {{
      e.preventDefault();
      var itemId = document.getElementById("editItemId").value;
      if (!itemId) return;
      var submitBtn = document.getElementById("editItemSubmit");
      submitBtn.disabled = true; submitBtn.textContent = "Saving...";
      errorEl.textContent = "";
      var payload = {{
        user_id: USER_ID,
        title: document.getElementById("editTitle").value.trim(),
        description: document.getElementById("editDescription").value.trim(),
        garment_category: document.getElementById("editCategory").value.trim(),
        garment_subtype: document.getElementById("editSubtype").value.trim(),
        primary_color: document.getElementById("editPrimaryColor").value.trim(),
        secondary_color: document.getElementById("editSecondaryColor").value.trim(),
        pattern_type: document.getElementById("editPattern").value.trim(),
        formality_level: document.getElementById("editFormality").value.trim(),
        occasion_fit: document.getElementById("editOccasion").value.trim(),
        brand: document.getElementById("editBrand").value.trim(),
        notes: document.getElementById("editNotes").value.trim()
      }};
      try {{
        var res = await fetch("/v1/onboarding/wardrobe/items/" + encodeURIComponent(itemId), {{
          method: "PATCH",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});
        if (!res.ok) {{ var err = await res.json(); throw new Error(err.detail || "Update failed"); }}
        modal.classList.remove("open");
        loadWardrobeStudio();
      }} catch(ex) {{
        errorEl.textContent = ex.message || "Failed to update item.";
      }} finally {{
        submitBtn.disabled = false; submitBtn.textContent = "Save Changes";
      }}
    }});
  }}())

  // ══════════════════════════════════════════════
  // RESULTS VIEW
  // ══════════════════════════════════════════════

  async function loadResults() {{
    if (!USER_ID) return;
    resultsGrid.innerHTML = '<div class="results-empty">Loading...</div>';
    try {{
      var res = await fetch("/v1/users/" + encodeURIComponent(USER_ID) + "/results");
      var data = await res.json();
      if (!res.ok) throw new Error("Failed");
      allResults = data.results || [];
      renderResults();
    }} catch (_) {{
      resultsGrid.innerHTML = '<div class="results-empty">Unable to load results.</div>';
    }}
  }}

  function renderResults() {{
    var filtered = allResults.filter(function(r) {{
      if (activeResultTab !== "all" && r.intent !== activeResultTab) return false;
      if (activeResultSource !== "all" && r.source && r.source.indexOf(activeResultSource) === -1) return false;
      return true;
    }});
    if (!filtered.length) {{
      resultsGrid.innerHTML = '<div class="results-empty">No results match the current filters.</div>';
      return;
    }}
    resultsGrid.innerHTML = filtered.map(function(r) {{
      var thumbHtml = r.first_outfit_image
        ? '<img src="' + escapeHtml(r.first_outfit_image) + '" alt="" loading="lazy" />'
        : '<div class="thumb-placeholder">No preview</div>';
      return '<div class="result-card" data-conv="' + escapeHtml(r.conversation_id) + '">' +
        '<div class="thumb">' + thumbHtml + '</div>' +
        '<div class="body">' +
          '<div class="msg">' + escapeHtml(r.user_message || "Styling request") + '</div>' +
          '<div class="meta-row">' +
            (r.occasion ? '<span class="chip">' + escapeHtml(r.occasion) + '</span>' : '') +
            (r.intent ? '<span class="source-mini-pill catalog">' + escapeHtml(r.intent.replace(/_/g, " ")) + '</span>' : '') +
            '<span class="ts">' + escapeHtml(relativeTime(r.created_at)) + '</span>' +
          '</div>' +
        '</div></div>';
    }}).join("");
  }}

  // Result tabs
  if (resultsTabs) {{
    resultsTabs.addEventListener("click", function(e) {{
      var btn = e.target.closest("button");
      if (!btn) return;
      activeResultTab = btn.getAttribute("data-tab") || "all";
      resultsTabs.querySelectorAll("button").forEach(function(b) {{ b.classList.remove("active"); }});
      btn.classList.add("active");
      renderResults();
    }});
  }}

  // Result source filters
  if (resultsFilters) {{
    resultsFilters.addEventListener("click", function(e) {{
      var chip = e.target.closest(".filter-chip");
      if (!chip) return;
      activeResultSource = chip.getAttribute("data-source") || "all";
      resultsFilters.querySelectorAll(".filter-chip").forEach(function(c) {{ c.classList.remove("active"); }});
      chip.classList.add("active");
      renderResults();
    }});
  }}

  // Click result card -> open conversation
  if (resultsGrid) {{
    resultsGrid.addEventListener("click", function(e) {{
      var card = e.target.closest(".result-card");
      if (!card) return;
      var convId = card.getAttribute("data-conv");
      if (convId) {{
        window.location.href = "/?user=" + encodeURIComponent(USER_ID) + "&view=chat&conversation_id=" + encodeURIComponent(convId);
      }}
    }});
  }}

  // ══════════════════════════════════════════════
  // PROFILE VIEW (unified view + inline edit)
  // ══════════════════════════════════════════════

  var profileEditing = false;
  var profileData = {{}};
  var editToggleBtn = document.getElementById("editToggleBtn");
  var editSaveBtn = document.getElementById("editSaveBtn");
  var editCancelBtn = document.getElementById("editCancelBtn");
  var editActions = document.getElementById("profileEditActions");
  var editStatus = document.getElementById("editStatus");
  var colorPaletteContent = document.getElementById("colorPaletteContent");

  var genderOptions = '<option value="">Select</option><option value="male">Male</option><option value="female">Female</option><option value="non_binary">Non-binary</option><option value="prefer_not_to_say">Prefer not to say</option>';
  var professionOptions = '<option value="">Select</option><option value="software_engineer">Software Engineer</option><option value="doctor">Doctor</option><option value="lawyer">Lawyer</option><option value="teacher">Teacher</option><option value="designer">Designer</option><option value="architect">Architect</option><option value="business_finance">Business / Finance</option><option value="marketing">Marketing</option><option value="artist">Artist</option><option value="student">Student</option><option value="entrepreneur">Entrepreneur</option><option value="homemaker">Homemaker</option><option value="other">Other</option>';

  function renderProfileGrid(profile, editing) {{
    var fields = [
      {{ key: "name", label: "Name", value: profile.name || "", type: "text" }},
      {{ key: "gender", label: "Gender", value: profile.gender || "", type: "select", options: genderOptions }},
      {{ key: "date_of_birth", label: "Date of Birth", value: profile.date_of_birth || "", type: "date" }},
      {{ key: "profession", label: "Profession", value: profile.profession || "", type: "select", options: professionOptions }},
      {{ key: "height_cm", label: "Height (cm)", value: profile.height_cm || "", type: "number" }},
      {{ key: "waist_cm", label: "Waist (cm)", value: profile.waist_cm || "", type: "number" }},
    ];
    profileGrid.innerHTML = fields.map(function(f) {{
      var displayVal = f.key === "height_cm" || f.key === "waist_cm"
        ? (f.value ? f.value + " cm" : "Not set")
        : (f.value || "Not set");
      var inputHtml = "";
      if (f.type === "select") {{
        inputHtml = '<select id="edit_' + f.key + '" style="' + (editing ? "display:block" : "display:none") + '">' + f.options + '</select>';
      }} else {{
        inputHtml = '<input id="edit_' + f.key + '" type="' + f.type + '" value="' + escapeHtml(String(f.value)) + '" style="' + (editing ? "display:block" : "display:none") + '" />';
      }}
      return '<div class="profile-field' + (editing ? " editing" : "") + '"><div class="label">' + escapeHtml(f.label) + '</div><div class="value">' + escapeHtml(displayVal) + '</div>' + inputHtml + '</div>';
    }}).join("");
    // Set select values after rendering
    if (editing) {{
      var genderSel = document.getElementById("edit_gender");
      var profSel = document.getElementById("edit_profession");
      if (genderSel) genderSel.value = profile.gender || "";
      if (profSel) profSel.value = profile.profession || "";
    }}
  }}

  function renderColorPalette(derived) {{
    if (!colorPaletteContent) return;
    var base = profileListValue(derived.BaseColors);
    var accent = profileListValue(derived.AccentColors);
    var avoid = profileListValue(derived.AvoidColors);
    if (!base.length && !accent.length && !avoid.length) {{
      colorPaletteContent.innerHTML = '<div style="color:var(--muted);font-size:13px;">Complete your analysis to see your personalized color palette.</div>';
      return;
    }}
    function chips(arr, cls) {{ return arr.map(function(c) {{ return '<span class="palette-chip ' + cls + '">' + escapeHtml(c) + '</span>'; }}).join(""); }}
    colorPaletteContent.innerHTML =
      '<div class="palette-section"><div class="palette-label">Base Colors</div><div class="palette-chips">' + chips(base, "base") + '</div></div>' +
      '<div class="palette-section"><div class="palette-label">Accent Colors</div><div class="palette-chips">' + chips(accent, "accent") + '</div></div>' +
      '<div class="palette-section"><div class="palette-label">Colors to Avoid</div><div class="palette-chips">' + chips(avoid, "avoid") + '</div></div>';
  }}

  function profileListValue(entry) {{
    if (!entry) return [];
    var v = entry.value || entry;
    return Array.isArray(v) ? v : [];
  }}

  // ── Analysis status + polling ──
  var analysisBadge = document.getElementById("analysisBadge");
  var analysisProgressBar = document.getElementById("analysisProgressBar");
  var analysisProgressWrap = document.getElementById("analysisProgressWrap");
  var analysisText = document.getElementById("analysisText");
  var analysisError = document.getElementById("analysisError");
  var analysisRerunBtn = document.getElementById("analysisRerunBtn");
  var analysisRetryBtn = document.getElementById("analysisRetryBtn");
  var analysisResultsWrap = document.getElementById("analysisResultsWrap");
  var agentRerunBtns = document.querySelectorAll(".agent-rerun-btn");

  var AGENT_LABELS = {{ body_type_analysis: "Body Type", color_analysis_headshot: "Color Analysis", other_details_analysis: "Other Details" }};

  function setAnalysisStatus(state, text) {{
    if (analysisBadge) {{ analysisBadge.textContent = state.replace(/_/g, " "); analysisBadge.className = "analysis-badge " + state; }}
    if (analysisText) analysisText.textContent = text;
  }}

  function showAnalysisError(msg) {{ if (analysisError) {{ analysisError.textContent = msg; analysisError.classList.add("show"); }} }}
  function hideAnalysisError() {{ if (analysisError) {{ analysisError.textContent = ""; analysisError.classList.remove("show"); }} }}

  function renderAnalysisResults(grouped, derivedInterps) {{
    if (!analysisResultsWrap) return;
    var html = "";
    var derivedNames = Object.keys(derivedInterps || {{}});
    if (derivedNames.length) {{
      html += '<div class="result-group"><div class="result-group-header">Derived Interpretations</div>';
      derivedNames.forEach(function(name) {{
        var item = derivedInterps[name];
        var val = Array.isArray(item.value) ? item.value.join(", ") : (item.value || "");
        html += '<div class="attr-row"><div class="attr-name">' + escapeHtml(name) + '</div><div class="attr-value">' + escapeHtml(val) + '<small>' + escapeHtml(item.evidence_note || "") + '</small></div><div class="attr-confidence">' + Math.round((item.confidence || 0) * 100) + '%</div></div>';
      }});
      html += '</div>';
    }}
    Object.keys(AGENT_LABELS).forEach(function(agentName) {{
      var values = grouped[agentName] || {{}};
      var names = Object.keys(values);
      if (!names.length) return;
      html += '<div class="result-group"><div class="result-group-header">' + escapeHtml(AGENT_LABELS[agentName]) + '</div>';
      names.forEach(function(name) {{
        var item = values[name];
        html += '<div class="attr-row"><div class="attr-name">' + escapeHtml(name) + '</div><div class="attr-value">' + escapeHtml(item.value || "") + '<small>' + escapeHtml(item.evidence_note || "") + '</small></div><div class="attr-confidence">' + Math.round((item.confidence || 0) * 100) + '%</div></div>';
      }});
      html += '</div>';
    }});
    analysisResultsWrap.innerHTML = html;
  }}

  function renderAnalysisState(analysis) {{
    var state = analysis.status || "not_started";
    var grouped = analysis.grouped_attributes || {{}};
    setAnalysisStatus(state, state === "completed" ? "All analysis agents completed successfully." : state === "failed" ? "Analysis failed. You can retry." : "Analysis is running...");

    var progressMap = {{ not_started: 14, pending: 24, running: 68, completed: 100, failed: 100 }};
    if (analysisProgressBar) analysisProgressBar.style.width = (progressMap[state] || 18) + "%";
    if (analysisProgressWrap) analysisProgressWrap.style.display = state === "completed" ? "none" : "";

    if (analysisRerunBtn) analysisRerunBtn.style.display = state === "completed" ? "" : "none";
    if (analysisRetryBtn) analysisRetryBtn.style.display = state === "failed" ? "" : "none";

    agentRerunBtns.forEach(function(btn) {{ btn.classList.toggle("show", state === "completed" || state === "failed"); }});

    Object.keys(AGENT_LABELS).forEach(function(agentName) {{
      var el = document.getElementById("agentStatus-" + agentName);
      if (!el) return;
      var count = Object.keys(grouped[agentName] || {{}}).length;
      el.textContent = state === "completed" ? (count ? count + " attributes" : "Done") : (count ? count + " prepared" : "Waiting...");
    }});

    if (state === "completed") {{
      renderAnalysisResults(grouped, analysis.derived_interpretations || {{}});
      var pct = computeAnalysisConfidence(grouped, analysis.derived_interpretations || {{}});
      if (analysisConfidenceEl) analysisConfidenceEl.textContent = pct + "% confidence";
      hideAnalysisError();
    }} else {{
      if (analysisConfidenceEl) analysisConfidenceEl.textContent = "";
    }}
    if (state === "failed") {{
      showAnalysisError(analysis.error_message || "Analysis failed.");
    }}
  }}

  async function fetchAnalysisStatus() {{
    var res = await fetch("/v1/onboarding/analysis/" + encodeURIComponent(USER_ID));
    if (!res.ok) throw new Error("Unable to load analysis");
    return await res.json();
  }}

  async function pollAnalysis() {{
    while (true) {{
      var analysis = await fetchAnalysisStatus();
      renderAnalysisState(analysis);
      renderStyleAndPalette(analysis);
      if (analysis.status === "completed" || analysis.status === "failed") return;
      await new Promise(function(r) {{ setTimeout(r, 1500); }});
    }}
  }}

  function renderStyleAndPalette(analysis) {{
    var derived = analysis.derived_interpretations || {{}};
    var attributes = analysis.attributes || {{}};
    var stylePref = (analysis.profile || {{}}).style_preference || {{}};
    var primary = String(stylePref.primaryArchetype || "").trim();
    var secondary = String(stylePref.secondaryArchetype || "").trim();
    var seasonal = profileValue(derived.SeasonalColorGroup);
    var contrast = profileValue(derived.ContrastLevel);
    var frame = profileValue(derived.FrameStructure);
    var bodyShape = profileValue(attributes.BodyShape);
    var facts = [
      {{ label: "Primary Archetype", value: primary }},
      {{ label: "Secondary Archetype", value: secondary }},
      {{ label: "Seasonal Palette", value: seasonal }},
      {{ label: "Contrast Level", value: contrast }},
      {{ label: "Frame Structure", value: frame }},
      {{ label: "Body Shape", value: bodyShape }},
    ].filter(function(f) {{ return f.value; }});
    if (styleFacts) {{
      styleFacts.innerHTML = facts.map(function(f) {{
        return '<div class="style-fact"><div class="fact-label">' + escapeHtml(f.label) + '</div><div class="fact-value">' + escapeHtml(f.value) + '</div></div>';
      }}).join("");
    }}
    if (styleSummary) {{
      styleSummary.textContent = primary || seasonal
        ? "Aura sees you through a " + [primary, secondary].filter(Boolean).join(" + ") + " lens, grounded in " + (seasonal || "your evolving palette") + " color direction and " + (frame || "balanced") + " shape guidance."
        : "Complete your analysis to unlock your full style code.";
    }}
    renderColorPalette(derived);
  }}

  // Image previews
  function renderProfileImages(imagePaths) {{
    var categories = {{ full_body: "imgSlotFullBody", headshot: "imgSlotHeadshot" }};
    Object.keys(categories).forEach(function(cat) {{
      var slot = document.getElementById(categories[cat]);
      var path = imagePaths[cat] || "";
      if (slot && path) {{
        slot.innerHTML = '<img src="/v1/onboarding/images/local?path=' + encodeURIComponent(path) + '" alt="' + escapeHtml(cat) + '" loading="lazy" />';
      }}
    }});
  }}

  // Image update handlers
  ["updateFullBody", "updateHeadshot"].forEach(function(inputId) {{
    var input = document.getElementById(inputId);
    if (!input) return;
    var category = inputId === "updateFullBody" ? "full_body" : "headshot";
    input.addEventListener("change", async function() {{
      if (!input.files || !input.files[0]) return;
      var fd = new FormData();
      fd.append("user_id", USER_ID);
      fd.append("file", input.files[0]);
      try {{
        var res = await fetch("/v1/onboarding/images/" + category, {{ method: "POST", body: fd }});
        if (!res.ok) {{ var err = await res.json(); alert(err.detail || "Upload failed"); return; }}
        loadProfile();
      }} catch (ex) {{ alert("Upload failed: " + ex.message); }}
    }});
  }});

  // Confidence calculation
  var analysisConfidenceEl = document.getElementById("analysisConfidence");
  function computeAnalysisConfidence(grouped, derived) {{
    var total = 0, count = 0;
    // Derived interpretations
    Object.keys(derived || {{}}).forEach(function(k) {{
      var c = (derived[k] || {{}}).confidence;
      if (typeof c === "number") {{ total += c; count++; }}
    }});
    // Agent attributes
    Object.keys(grouped || {{}}).forEach(function(agent) {{
      Object.keys(grouped[agent] || {{}}).forEach(function(attr) {{
        var c = (grouped[agent][attr] || {{}}).confidence;
        if (typeof c === "number") {{ total += c; count++; }}
      }});
    }});
    return count > 0 ? Math.round((total / count) * 100) : 0;
  }}

  async function loadProfile() {{
    if (!USER_ID || !profileGrid) return;
    try {{
      var statusRes = await fetch("/v1/onboarding/status/" + encodeURIComponent(USER_ID));
      profileData = statusRes.ok ? await statusRes.json() : {{}};
      renderProfileImages(profileData.image_paths || {{}});
      var analysis = await fetchAnalysisStatus();
      renderProfileGrid(profileData, profileEditing);
      renderAnalysisState(analysis);
      renderStyleAndPalette(analysis);

      // Poll if not yet complete
      if (analysis.status && analysis.status !== "completed" && analysis.status !== "failed") {{
        // Ensure analysis is started
        try {{ await fetch("/v1/onboarding/analysis/start", {{ method: "POST", headers: {{"Content-Type": "application/json"}}, body: JSON.stringify({{ user_id: USER_ID }}) }}); }} catch(_) {{}}
        await pollAnalysis();
      }}
    }} catch (_) {{}}
  }}

  // Re-run analysis
  if (analysisRerunBtn) {{
    analysisRerunBtn.addEventListener("click", async function() {{
      analysisRerunBtn.disabled = true;
      setAnalysisStatus("running", "Re-running profile analysis...");
      if (analysisProgressWrap) analysisProgressWrap.style.display = "";
      if (analysisProgressBar) analysisProgressBar.style.width = "24%";
      hideAnalysisError();
      try {{
        await fetch("/v1/onboarding/analysis/rerun", {{ method: "POST", headers: {{"Content-Type": "application/json"}}, body: JSON.stringify({{ user_id: USER_ID }}) }});
        await pollAnalysis();
      }} catch (e) {{ showAnalysisError(e.message || "Re-run failed"); }}
      analysisRerunBtn.disabled = false;
    }});
  }}

  // Retry analysis
  if (analysisRetryBtn) {{
    analysisRetryBtn.addEventListener("click", async function() {{
      analysisRetryBtn.disabled = true;
      hideAnalysisError();
      try {{
        await fetch("/v1/onboarding/analysis/start", {{ method: "POST", headers: {{"Content-Type": "application/json"}}, body: JSON.stringify({{ user_id: USER_ID }}) }});
        await pollAnalysis();
      }} catch (e) {{ showAnalysisError(e.message || "Retry failed"); }}
      analysisRetryBtn.disabled = false;
    }});
  }}

  // Agent-level re-run
  agentRerunBtns.forEach(function(btn) {{
    btn.addEventListener("click", async function() {{
      var agentName = btn.getAttribute("data-agent");
      if (!agentName) return;
      btn.disabled = true;
      setAnalysisStatus("running", "Re-running " + (AGENT_LABELS[agentName] || "agent") + "...");
      if (analysisProgressWrap) analysisProgressWrap.style.display = "";
      if (analysisProgressBar) analysisProgressBar.style.width = "24%";
      hideAnalysisError();
      try {{
        await fetch("/v1/onboarding/analysis/rerun-agent", {{ method: "POST", headers: {{"Content-Type": "application/json"}}, body: JSON.stringify({{ user_id: USER_ID, agent_name: agentName }}) }});
        await pollAnalysis();
      }} catch (e) {{ showAnalysisError(e.message || "Re-run failed"); }}
      btn.disabled = false;
    }});
  }})

  // Toggle edit mode
  if (editToggleBtn) {{
    editToggleBtn.addEventListener("click", function() {{
      profileEditing = true;
      renderProfileGrid(profileData, true);
      editToggleBtn.style.display = "none";
      editActions.style.display = "flex";
      editStatus.textContent = "";
    }});
  }}

  // Cancel edit
  if (editCancelBtn) {{
    editCancelBtn.addEventListener("click", function() {{
      profileEditing = false;
      renderProfileGrid(profileData, false);
      editToggleBtn.style.display = "";
      editActions.style.display = "none";
      editStatus.textContent = "";
    }});
  }}

  // Save profile edits
  if (editSaveBtn) {{
    editSaveBtn.addEventListener("click", async function() {{
      editStatus.textContent = "Saving...";
      editStatus.className = "edit-status";
      try {{
        var payload = {{
          user_id: USER_ID,
          name: (document.getElementById("edit_name") || {{}}).value || "",
          date_of_birth: (document.getElementById("edit_date_of_birth") || {{}}).value || "",
          gender: (document.getElementById("edit_gender") || {{}}).value || "",
          height_cm: parseInt((document.getElementById("edit_height_cm") || {{}}).value) || 0,
          waist_cm: parseInt((document.getElementById("edit_waist_cm") || {{}}).value) || 0,
          profession: (document.getElementById("edit_profession") || {{}}).value || "",
        }};
        var res = await fetch("/v1/onboarding/profile", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload),
        }});
        if (!res.ok) {{
          var data = await res.json();
          throw new Error(data.detail || "Save failed");
        }}
        editStatus.textContent = "Profile updated.";
        editStatus.className = "edit-status success";
        profileEditing = false;
        editToggleBtn.style.display = "";
        editActions.style.display = "none";
        loadProfile();
      }} catch (e) {{
        editStatus.textContent = "Error: " + (e.message || String(e));
        editStatus.className = "edit-status error";
      }}
    }});
  }}

  // ══════════════════════════════════════════════
  // INIT
  // ══════════════════════════════════════════════

  // Fetch user analysis confidence (used to scale evaluation radar charts)
  if (USER_ID) {{
    fetch("/v1/onboarding/analysis/" + encodeURIComponent(USER_ID))
      .then(function(r) {{ return r.ok ? r.json() : null; }})
      .then(function(data) {{
        if (!data) return;
        var grouped = {{}};
        ["body_type_analysis", "color_analysis_headshot", "other_details_analysis"].forEach(function(agent) {{
          var raw = data[agent] || data["profile"] && data["profile"][agent] || {{}};
          if (typeof raw === "object") grouped[agent] = raw;
        }});
        // Flatten attributes if they come as a flat dict
        var attrs = data.attributes || {{}};
        if (Object.keys(grouped).length === 0 && Object.keys(attrs).length > 0) {{
          grouped["_flat"] = attrs;
        }}
        var derived = data.derived_interpretations || {{}};
        userAnalysisConfidencePct = computeAnalysisConfidence(grouped, derived);
      }})
      .catch(function() {{}});
  }}

  // Load conversation history
  if (ACTIVE_VIEW === "chat") {{
    var urlParams = new URLSearchParams(window.location.search);

    // Handle +New Chat from another view
    if (urlParams.get("new") === "1") {{
      window.history.replaceState(null, "", "/?user=" + encodeURIComponent(USER_ID) + "&view=chat");
      fetch("/v1/conversations", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ user_id: USER_ID }}),
      }}).then(function(r) {{ return r.json(); }}).then(function(d) {{
        if (d.conversation_id) conversationId = d.conversation_id;
        loadConversationHistory();
      }}).catch(function() {{ loadConversationHistory(); }});
    }} else {{
      loadConversationHistory();
      if (INIT_CONV_ID) {{
        loadConversation(INIT_CONV_ID);
      }}
    }}
    var seedPrompt = urlParams.get("prompt") || "";
    var seedImg = urlParams.get("wardrobe_img") || "";
    if (seedPrompt) {{
      // Clean URL without reloading
      var cleanUrl = "/?user=" + encodeURIComponent(USER_ID) + "&view=chat";
      window.history.replaceState(null, "", cleanUrl);

      if (seedImg) {{
        fetch(seedImg)
          .then(function(r) {{ return r.blob(); }})
          .then(function(blob) {{
            var reader = new FileReader();
            reader.onload = function(ev) {{
              setImagePreview(ev.target.result, "Wardrobe item");
              messageEl.value = seedPrompt;
              send();
            }};
            reader.readAsDataURL(blob);
          }})
          .catch(function() {{
            messageEl.value = seedPrompt;
            send();
          }});
      }} else {{
        messageEl.value = seedPrompt;
        send();
      }}
    }}
  }}

  // Load wardrobe view
  if (ACTIVE_VIEW === "wardrobe") {{
    loadWardrobeStudio();
  }}

  // Load results view
  if (ACTIVE_VIEW === "results") {{
    loadResults();
  }}

  // Load profile
  if (ACTIVE_VIEW === "profile" || ACTIVE_VIEW === "edit-profile") {{
    loadProfile();
  }}

}})();
</script>
"""
    html += "</body>\n</html>"
    return html
