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
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,400;1,9..144,500&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet" />
  <script>(function(){try{var t=localStorage.getItem("aura_theme");if(!t){t=(window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches)?"dark":"light";}document.documentElement.setAttribute("data-theme",t);}catch(e){}}());</script>
  <title>Sigma Aura</title>
  <style>
    /* ===== Design Tokens — Confident Luxe (see docs/DESIGN.md § Brand Direction) ===== */
    :root {
      /* Canvas & surfaces — warm ivory base */
      --canvas: #F7F3EC;
      --canvas-rgb: 247, 243, 236;
      --surface: #FDFBF6;
      --surface-sunk: #EEE8DD;
      --bg: #F7F3EC;              /* legacy alias */
      --bg-soft: #EEE8DD;          /* legacy alias */
      --surface-alt: #EEE8DD;      /* legacy alias */
      --surface-deep: #EEE8DD;     /* legacy alias */

      /* Ink — espresso-black */
      --ink: #16110E;
      --ink-2: #2E2824;
      --ink-3: #6B635C;
      --ink-4: #A69C92;
      --ink-rgb: 22, 17, 14;
      --muted: #6B635C;            /* legacy alias -> ink-3 */
      --muted-soft: #A69C92;       /* legacy alias -> ink-4 */

      /* Lines — hairline-first */
      --line: #E1D8C9;
      --line-strong: #C9BCA8;

      /* Accent — oxblood */
      --accent: #5C1A1B;
      --accent-soft: #7A2A2C;
      --accent-rgb: 92, 26, 27;
      --accent-soft-rgb: 122, 42, 44;

      /* Signal — champagne, personal cues ONLY */
      --signal: #C6A15B;
      --signal-rgb: 198, 161, 91;
      --gold: #C6A15B;             /* legacy alias -> signal */

      /* Retired moss/wardrobe color remapped to neutral ink-2 (source labels now carry the wardrobe/catalog distinction, not color) */
      --wardrobe: #2E2824;
      --wardrobe-rgb: 46, 40, 36;

      /* Text on accent */
      --on-accent: #FDFBF6;

      /* Semantic */
      --danger: #8A2A2A;
      --danger-rgb: 138, 42, 42;
      --positive: #4A6B3A;

      /* Shadow channel — warm ink in light, black in dark */
      --shadow-rgb: 22, 17, 14;

      /* Radii */
      --radius-sm: 4px;
      --radius-md: 8px;
      --radius-lg: 14px;
      --radius-full: 999px;

      /* Elevation — hairline-first; shadows reserved for floating surfaces */
      --shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.04), 0 8px 24px rgba(var(--shadow-rgb), 0.06);
      --shadow-pop: 0 1px 2px rgba(var(--shadow-rgb), 0.04), 0 8px 24px rgba(var(--shadow-rgb), 0.06);
      --shadow-modal: 0 24px 80px rgba(var(--shadow-rgb), 0.18);

      /* Motion — single easing curve */
      --ease: cubic-bezier(.2, .7, .1, 1);
      --dur-1: 120ms;
      --dur-2: 240ms;
      --dur-3: 480ms;

      /* Layout */
      --header-h: 56px;
      --rail-w: 280px;
    }

    [data-theme="dark"] {
      --canvas: #0E0B09;
      --canvas-rgb: 14, 11, 9;
      --surface: #15110E;
      --surface-sunk: #0A0806;
      --bg: #0E0B09;
      --bg-soft: #0A0806;
      --surface-alt: #0A0806;
      --surface-deep: #0A0806;

      --ink: #F4EFE5;
      --ink-2: #D8D1C3;
      --ink-3: #8A8176;
      --ink-4: #544D45;
      --ink-rgb: 244, 239, 229;
      --muted: #8A8176;
      --muted-soft: #544D45;

      --line: #2A231D;
      --line-strong: #3A312A;

      --accent: #B34548;
      --accent-soft: #C95A5D;
      --accent-rgb: 179, 69, 72;
      --accent-soft-rgb: 201, 90, 93;

      --signal: #D6B373;
      --signal-rgb: 214, 179, 115;
      --gold: #D6B373;

      --wardrobe: #D8D1C3;
      --wardrobe-rgb: 216, 209, 195;

      --on-accent: #F4EFE5;
      --danger: #B3544F;
      --danger-rgb: 179, 84, 79;
      --positive: #6F9356;

      --shadow-rgb: 0, 0, 0;
      --shadow: 0 1px 2px rgba(0,0,0,0.4), 0 8px 24px rgba(0,0,0,0.5);
      --shadow-pop: 0 1px 2px rgba(0,0,0,0.4), 0 8px 24px rgba(0,0,0,0.5);
      --shadow-modal: 0 24px 80px rgba(0,0,0,0.65);
    }

    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; } }

    /* ===== Reset & Base ===== */
    *, *::before, *::after { box-sizing: border-box; margin: 0; }
    body {
      font-family: "Inter", -apple-system, "Helvetica Neue", "Segoe UI", sans-serif;
      font-size: 15px;
      line-height: 1.6;
      color: var(--ink);
      background: var(--canvas);
      height: 100vh; overflow: hidden;
      display: flex; flex-direction: column;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }

    /* ===== View switching ===== */
    .page-view { display: none !important; }
    body.view-home .page-home { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body.view-chat .page-home { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body.view-wardrobe .page-wardrobe { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body.view-outfits .page-outfits { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body.view-checks .page-checks { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body.view-results .page-results { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body.view-wishlist .page-wishlist { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body.view-trialroom .page-trialroom { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body.view-profile .page-profile { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    body.view-edit-profile .page-profile { display: flex !important; flex: 1; flex-direction: column; height: 100%; overflow-y: auto; }
    .history-rail { display: none !important; }

    /* ===== View-transition fade+rise — Confident Luxe motion § 3 ===== */
    @keyframes aura-view-enter {
      from { opacity: 0; transform: translateY(8px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    body.view-home .page-home,
    body.view-chat .page-home,
    body.view-wardrobe .page-wardrobe,
    body.view-outfits .page-outfits,
    body.view-checks .page-checks,
    body.view-results .page-results,
    body.view-wishlist .page-wishlist,
    body.view-trialroom .page-trialroom,
    body.view-profile .page-profile {
      animation: aura-view-enter var(--dur-3) var(--ease) both;
    }

    /* ===== Runway label track-in — the single motion detail per view ===== */
    /* Applied to ONE header-level label per view. Labels slide in from 6px */
    /* left and fade to full opacity. 360ms on the standard curve. */
    @keyframes aura-track-in {
      from { opacity: 0; transform: translateX(-6px); }
      to   { opacity: 1; transform: translateX(0); }
    }
    .wardrobe-title-block .wardrobe-count,
    .results-header p,
    .dossier-hero .dossier-statement {
      animation: aura-track-in var(--dur-3) var(--ease) both;
      animation-delay: 120ms;
    }

    /* ===== Staggered entrance — Looks grid only, 60ms stagger ===== */
    @keyframes aura-card-rise {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .results-grid .result-card {
      animation: aura-card-rise var(--dur-2) var(--ease) both;
    }
    .results-grid .result-card:nth-child(1)  { animation-delay:   0ms; }
    .results-grid .result-card:nth-child(2)  { animation-delay:  60ms; }
    .results-grid .result-card:nth-child(3)  { animation-delay: 120ms; }
    .results-grid .result-card:nth-child(4)  { animation-delay: 180ms; }
    .results-grid .result-card:nth-child(5)  { animation-delay: 240ms; }
    .results-grid .result-card:nth-child(6)  { animation-delay: 300ms; }
    .results-grid .result-card:nth-child(7)  { animation-delay: 360ms; }
    .results-grid .result-card:nth-child(8)  { animation-delay: 420ms; }
    .results-grid .result-card:nth-child(9)  { animation-delay: 480ms; }
    .results-grid .result-card:nth-child(n+10) { animation-delay: 540ms; }

    /* ===== Reduced-motion override — strip all entrance motion ===== */
    @media (prefers-reduced-motion: reduce) {
      body.view-chat .page-chat,
      body.view-wardrobe .page-wardrobe,
      body.view-results .page-results,
      body.view-wishlist .page-wishlist,
      body.view-trialroom .page-trialroom,
      body.view-profile .page-profile,
      .wardrobe-title-block .wardrobe-count,
      .results-header p,
      .dossier-hero .dossier-statement,
      .results-grid .result-card { animation: none !important; }
    }
    /* History rail collapse (⌘K / Ctrl+K) */
    body.rail-collapsed .history-rail { width: 0 !important; min-width: 0 !important; border-right: 0 !important; overflow: hidden !important; }
    @media (prefers-reduced-motion: no-preference) {
      .history-rail { transition: width var(--dur-2) var(--ease), min-width var(--dur-2) var(--ease); }
    }

    /* ===== App Header ===== */
    .app-header {
      height: var(--header-h); flex-shrink: 0;
      position: relative; z-index: 10;
      display: flex; align-items: center; gap: 20px;
      padding: 0 32px;
      background: rgba(var(--canvas-rgb), 0.88);
      backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
      border-bottom: 1px solid var(--line);
    }
    .header-brand {
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-size: 22px; font-weight: 500;
      color: var(--ink);
      letter-spacing: 0.02em;
      text-transform: uppercase;
      cursor: pointer; white-space: nowrap;
    }
    .header-nav { display: flex; gap: 24px; margin-left: 32px; }
    .header-nav a {
      padding: 4px 0;
      border-bottom: 1px solid transparent;
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
      text-decoration: none;
      transition: color var(--dur-1) var(--ease), border-color var(--dur-1) var(--ease);
    }
    .header-nav a:hover { color: var(--ink-2); }
    .header-nav a.active { color: var(--ink); border-bottom-color: var(--ink); }
    .header-actions { margin-left: auto; display: flex; align-items: center; gap: 16px; }
    .new-chat-btn {
      padding: 6px 14px;
      border-radius: var(--radius-md);
      border: 1px solid var(--line-strong);
      background: transparent;
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-2);
      cursor: pointer;
      transition: border-color var(--dur-1) var(--ease), color var(--dur-1) var(--ease);
    }
    .new-chat-btn:hover { border-color: var(--ink); color: var(--ink); }
    .avatar-menu { position: relative; }
    .avatar-btn {
      width: 32px; height: 32px; border-radius: 50%;
      border: 1px solid var(--line-strong);
      background: var(--surface-sunk);
      font-size: 14px; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      transition: border-color var(--dur-1) var(--ease);
    }
    .avatar-btn:hover { border-color: var(--ink); }
    .avatar-dropdown {
      display: none; position: absolute; top: calc(100% + 8px); right: 0;
      min-width: 180px; background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      padding: 6px 0;
      box-shadow: var(--shadow-pop);
      z-index: 200;
    }
    .avatar-dropdown.open { display: block; }
    .avatar-dropdown a, .avatar-dropdown button {
      display: block; width: 100%; text-align: left;
      padding: 10px 18px;
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-2);
      background: none; border: none;
      cursor: pointer; text-decoration: none;
      transition: color var(--dur-1) var(--ease);
    }
    .avatar-dropdown a:hover, .avatar-dropdown button:hover { color: var(--ink); }
    .avatar-dropdown .divider { height: 1px; background: var(--line); margin: 4px 0; }

    /* ===== App Body ===== */
    .app-body {
      flex: 1; display: flex; overflow: hidden; min-height: 0;
    }

    /* ===== Chat History Sidebar — Confident Luxe: hairline, no fills ===== */
    .history-rail {
      width: var(--rail-w); min-width: var(--rail-w); height: 100%;
      border-right: 1px solid var(--line);
      background: var(--canvas);
      display: flex; flex-direction: column; overflow: hidden;
    }
    .history-header {
      padding: 20px 20px 12px; display: flex; align-items: center; justify-content: space-between;
    }
    .history-header span {
      font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.12em;
      color: var(--ink-3);
    }
    .history-list { flex: 1; overflow-y: auto; padding: 0 12px 16px; }
    .history-item {
      display: block; width: 100%; text-align: left; padding: 12px 14px 12px 16px;
      border-radius: 0; border: none; border-left: 2px solid transparent;
      background: none; cursor: pointer;
      font-size: 13px; color: var(--ink-2);
      transition: border-color var(--dur-1) var(--ease), color var(--dur-1) var(--ease);
      margin-bottom: 2px; position: relative;
    }
    .history-item:hover { color: var(--ink); border-left-color: var(--line-strong); }
    .history-item.active { color: var(--ink); border-left-color: var(--accent); font-weight: 600; }
    .history-item .preview { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-right: 44px; }
    .history-item .ts {
      display: block; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--ink-4); margin-top: 4px;
    }
    .history-actions {
      position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
      display: none; gap: 2px;
    }
    .history-item:hover .history-actions { display: flex; }
    .history-action-btn {
      width: 24px; height: 24px; border: none; background: none; cursor: pointer;
      border-radius: var(--radius-sm); font-size: 12px; color: var(--ink-4); padding: 0;
      display: flex; align-items: center; justify-content: center;
      transition: color var(--dur-1) var(--ease);
    }
    .history-action-btn:hover { color: var(--ink); }
    .history-rename-input {
      width: 100%; padding: 4px 8px; border: 0; border-bottom: 1px solid var(--ink);
      border-radius: 0;
      font-family: inherit; font-size: 13px; color: var(--ink); background: transparent; outline: none;
    }
    .history-empty {
      padding: 24px 20px; font-size: 13px; color: var(--ink-3); line-height: 1.55;
      font-style: italic;
    }

    /* ===== Discovery Surface (Home) — Phase 15 ===== */
    .page-home {
      padding: 0;
      width: 100%;
    }
    /* Top section: headline + input */
    .discovery-top {
      padding: 12vh 32px 40px;
      max-width: 800px;
      margin: 0 auto;
      width: 100%;
      text-align: center;
      flex-shrink: 0;
    }
    .discovery-top.has-result {
      padding: 32px 32px 24px;
    }
    .discovery-top.has-result .welcome-headline { font-size: 28px; margin-bottom: 12px; }
    .discovery-top.has-result .welcome-sub { display: none; }
    .discovery-top.has-result .welcome-prompts { display: none; }
    .discovery-input-wrap {
      max-width: 680px;
      margin: 0 auto;
      position: relative;
    }
    .discovery-input {
      width: 100%;
      padding: 14px 52px 14px 20px;
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      background: var(--surface);
      font-family: inherit;
      font-size: 15px;
      color: var(--ink);
      outline: none;
      transition: border-color var(--dur-1) var(--ease), box-shadow var(--dur-1) var(--ease);
    }
    .discovery-input:focus { border-color: var(--line-strong); box-shadow: var(--shadow-pop); }
    .discovery-input::placeholder { color: var(--ink-4); font-style: italic; }
    .discovery-send {
      position: absolute;
      right: 8px; top: 50%; transform: translateY(-50%);
      width: 36px; height: 36px;
      border-radius: 50%; border: none;
      background: var(--accent);
      color: var(--on-accent);
      font-size: 15px;
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      transition: opacity var(--dur-1) var(--ease);
    }
    .discovery-send:hover { opacity: 0.88; }
    .discovery-send:disabled { opacity: 0.3; cursor: default; }
    .discovery-send .arrow { display: inline-block; transform: rotate(-90deg); }

    /* Thinking indicator below input */
    .discovery-thinking {
      max-width: 680px;
      margin: 8px auto 0;
      font-size: 12px;
      font-style: italic;
      color: var(--ink-3);
      min-height: 18px;
      text-align: left;
      padding: 0 4px;
    }
    .discovery-thinking:empty { display: none; }

    /* Active result area */
    .discovery-result {
      max-width: 1080px;
      margin: 0 auto;
      padding: 0 32px 32px;
      width: 100%;
    }
    .discovery-result:empty { display: none; }
    /* Context summary above the carousel */
    .result-context {
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--ink-4);
      margin-bottom: 16px;
      padding: 0 4px;
    }
    /* PDP carousel — one card rendered at a time, rebuilt on navigation */
    .pdp-carousel {
      position: relative;
      max-width: 880px;
      margin: 0 auto;
    }
    /* Carousel header: turn summary (left) + counter + arrows (right) — one line */
    .carousel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 0 4px 10px;
      max-width: 880px;
      margin: 0 auto;
    }
    .carousel-header .turn-summary {
      flex: 1;
      font-size: 13px;
      font-style: italic;
      color: var(--ink-3);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .carousel-counter {
      font-family: "JetBrains Mono", ui-monospace, monospace;
      font-size: 10px; font-weight: 500;
      color: var(--ink-4);
      letter-spacing: 0.06em;
      flex-shrink: 0;
    }
    .carousel-nav { display: flex; gap: 6px; flex-shrink: 0; }
    .carousel-nav button {
      appearance: none;
      width: 26px; height: 26px;
      border-radius: 50%;
      border: 1px solid var(--line);
      background: transparent;
      color: var(--ink-3);
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      font-size: 13px;
      transition: border-color var(--dur-1) var(--ease), color var(--dur-1) var(--ease);
    }
    .carousel-nav button:hover { border-color: var(--ink); color: var(--ink); }

    /* Follow-up chips below the carousel */
    .discovery-followups {
      max-width: 1080px;
      margin: 0 auto;
      padding: 0 36px 24px;
    }

    /* Recent intent groups */
    .recent-intents {
      max-width: 1080px;
      margin: 0 auto;
      padding: 32px 32px 64px;
      border-top: 1px solid var(--line);
    }
    .recent-intents:empty { display: none; }
    .recent-intents-label {
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
      margin-bottom: 20px;
    }
    .recent-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 20px;
    }
    .recent-card {
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      overflow: hidden;
      cursor: pointer;
      transition: border-color var(--dur-1) var(--ease);
      background: var(--surface);
    }
    .recent-card:hover { border-color: var(--line-strong); }
    .recent-card-img {
      aspect-ratio: 4/3;
      background: var(--surface-sunk);
      overflow: hidden;
    }
    .recent-card-img img { width: 100%; height: 100%; object-fit: cover; }
    .recent-card-body { padding: 14px 16px; }
    .recent-card-body .rc-context {
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
      margin-bottom: 4px;
    }
    .recent-card-body .rc-summary {
      font-size: 13px; color: var(--ink);
      display: -webkit-box; -webkit-line-clamp: 2;
      -webkit-box-orient: vertical; overflow: hidden;
    }
    .recent-card-body .rc-meta {
      font-size: 9px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
      margin-top: 8px;
    }

    /* ===== Chat Feed (legacy — kept for loadConversation replay) ===== */
    .chat-feed {
      flex: 1; overflow-y: auto; padding: 32px 32px 12px; max-width: 960px;
      margin: 0 auto; width: 100%;
    }

    /* Welcome — Confident Luxe empty state (see docs/DESIGN.md § Tonal Moments) */
    .feed-welcome {
      text-align: center;
      padding: 18vh 24px 48px;
      max-width: 760px;
      margin: 0 auto;
    }
    .welcome-headline {
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-style: italic;
      font-weight: 400;
      font-size: clamp(40px, 7vw, 72px);
      line-height: 1.06;
      letter-spacing: -0.01em;
      color: var(--ink);
      margin: 0 0 18px 0;
    }
    .welcome-headline .welcome-dot { font-style: normal; color: var(--accent); }
    .welcome-sub {
      font-size: 14px;
      color: var(--ink-3);
      line-height: 1.55;
      margin: 0 auto 40px;
      max-width: 440px;
    }
    .welcome-prompts {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 28px;
      max-width: 620px;
      margin: 0 auto;
    }
    .welcome-prompt {
      appearance: none;
      background: transparent;
      border: 0;
      border-bottom: 1px solid var(--line);
      padding: 8px 2px;
      font-family: inherit;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--ink-3);
      cursor: pointer;
      transition: color var(--dur-1) var(--ease), border-color var(--dur-1) var(--ease);
    }
    .welcome-prompt:hover,
    .welcome-prompt:focus-visible {
      color: var(--ink);
      border-bottom-color: var(--ink);
      outline: none;
    }
    @media (prefers-reduced-motion: reduce) {
      .welcome-prompt { transition: none; }
    }
    @media (max-width: 640px) {
      .feed-welcome { padding: 12vh 20px 32px; }
      .welcome-prompts { gap: 18px 24px; }
    }

    /* Bubbles — Confident Luxe: agent as flowing editorial copy, user as quiet sunk pill */
    .bubble {
      max-width: 82%;
      font-size: 15px;
      line-height: 1.65;
      margin-bottom: 16px;
      word-wrap: break-word;
    }
    .bubble p { margin: 0 0 10px 0; }
    .bubble p:last-child { margin-bottom: 0; }
    .bubble ul { margin: 0 0 10px 0; padding-left: 20px; }
    .bubble ul:last-child { margin-bottom: 0; }
    .bubble li { margin-bottom: 6px; }
    .bubble li:last-child { margin-bottom: 0; }
    /* User message — right-aligned, sunk fill, no shadow */
    .bubble.user {
      margin-left: auto;
      padding: 10px 16px;
      background: var(--surface-sunk);
      color: var(--ink);
      border-radius: var(--radius-md);
    }
    /* Assistant / stylist copy — no background, no border, 2px ink avatar rule on left */
    .bubble.assistant {
      margin-right: auto;
      padding: 2px 0 2px 20px;
      color: var(--ink);
      border-left: 2px solid var(--ink);
      background: transparent;
      max-width: 100%;
    }
    /* Agent stage / "thinking" bubble — small stylist-voice line, no chrome */
    .bubble.agent {
      margin-right: auto; background: transparent; font-size: 12px;
      color: var(--ink-3); padding: 4px 0 4px 20px;
      border-left: 2px solid var(--line-strong);
      opacity: 1;
      transition: opacity var(--dur-3) var(--ease);
      font-style: italic;
    }
    .bubble.agent .dot { display: none; }
    .bubble.agent.done { border-left-color: var(--positive); }
    .bubble.agent.fading { opacity: 0; pointer-events: none; }
    @media (prefers-reduced-motion: reduce) {
      .bubble.agent { transition: none; }
    }
    .bubble.meta {
      font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--ink-4); text-align: center; max-width: 100%;
      background: none; padding: 8px 0; margin-bottom: 12px;
    }

    /* Follow-up suggestions — Confident Luxe: uppercase bucket headers, hairline chips */
    .followup-groups { margin: 20px 0 8px; padding-left: 22px; }
    .followup-group { margin-bottom: 14px; }
    .followup-group:last-child { margin-bottom: 0; }
    .followup-group strong {
      font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4); display: block; margin-bottom: 10px;
    }
    .followup-row { display: flex; flex-wrap: wrap; gap: 8px; }
    .followup-chip {
      appearance: none;
      background: transparent;
      border: 1px solid var(--line);
      border-radius: var(--radius-full);
      padding: 7px 14px;
      font-family: inherit;
      font-size: 12px;
      font-weight: 500;
      color: var(--ink-2);
      cursor: pointer;
      transition: border-color var(--dur-1) var(--ease), color var(--dur-1) var(--ease);
    }
    .followup-chip:hover { border-color: var(--ink); color: var(--ink); }

    /* Stage progress — stylist voice, italic, quiet */
    .stage-bar {
      padding: 0 32px; max-width: 960px; margin: 0 auto; width: 100%;
      font-size: 12px; color: var(--ink-3); min-height: 18px;
      font-style: italic;
    }
    .stage-bar:empty { display: none; }

    /* ===== Chat Composer — Confident Luxe: hairline, focus-only elevation ===== */
    .composer-wrap {
      padding: 8px 32px 20px; max-width: 960px; margin: 0 auto; width: 100%;
    }
    .composer-outer {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      transition: border-color var(--dur-1) var(--ease), box-shadow var(--dur-1) var(--ease);
    }
    .composer-outer:focus-within { border-color: var(--line-strong); box-shadow: var(--shadow-pop); }
    .composer-outer.dragover { border-color: var(--accent); }
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
    .plus-btn:hover { background: rgba(var(--accent-rgb), 0.08); color: var(--accent); }
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
      background: var(--accent); color: var(--on-accent); font-size: 15px;
      cursor: pointer; display: flex; align-items: center; justify-content: center;
      flex-shrink: 0; align-self: flex-end;
      transition: opacity 140ms ease, transform 80ms ease;
    }
    .send-btn:hover { opacity: 0.88; }
    .send-btn:active { transform: scale(0.94); }
    .send-btn:disabled { opacity: 0.35; cursor: default; }
    .send-btn .arrow { display: inline-block; transform: rotate(-90deg); }
    .composer-error { font-size: 12px; color: var(--danger); margin-top: 4px; min-height: 16px; }

    /* ===== Wardrobe Picker Modal — Confident Luxe ===== */
    .modal-overlay {
      display: none; position: fixed; inset: 0; z-index: 300;
      background: rgba(var(--shadow-rgb), 0.5);
      backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
      align-items: center; justify-content: center;
    }
    .modal-overlay.open { display: flex; }
    .modal-box {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      padding: 32px;
      max-width: 560px; width: 92vw; max-height: 80vh;
      display: flex; flex-direction: column;
      box-shadow: var(--shadow-modal);
    }
    .modal-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
    .modal-header h3 {
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-size: 24px; font-weight: 400; color: var(--ink); margin: 0;
    }
    .modal-close {
      background: none; border: none; font-family: inherit;
      font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-3); padding: 4px 8px; cursor: pointer;
      transition: color var(--dur-1) var(--ease);
    }
    .modal-close:hover { color: var(--ink); }
    .modal-grid {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;
      overflow-y: auto; flex: 1; padding: 2px;
    }
    .modal-item {
      border: 0; border-radius: var(--radius-sm); overflow: hidden;
      cursor: pointer;
      background: transparent;
      transition: opacity var(--dur-1) var(--ease);
    }
    .modal-item:hover { opacity: 0.88; }
    .modal-item img { width: 100%; aspect-ratio: 3/4; object-fit: cover; display: block; border-radius: var(--radius-sm); }
    .modal-item .label {
      padding: 8px 2px 0;
      font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--ink-3);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .modal-empty {
      grid-column: 1/-1; text-align: center; padding: 48px 24px;
      color: var(--ink-3);
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-style: italic; font-size: 20px;
    }

    /* ===== Outfit PDP Card — 3-column: thumbs | hero | info ===== */
    .outfit-card {
      display: grid;
      grid-template-columns: 100px 1fr 44%;
      grid-template-rows: auto 1fr;
      gap: 0;
      border-radius: var(--radius-md);
      border: 1px solid var(--line);
      background: var(--surface);
      overflow: hidden;
      margin-bottom: 0;
      max-width: 880px;
    }
    @media (max-width: 900px) {
      .outfit-card { grid-template-columns: 1fr; max-height: none; max-width: 100%; }
      .outfit-thumbs { display: none; }
    }
    /* Header spans full width — compact */
    .outfit-header {
      grid-column: 1 / -1;
      padding: 16px 22px 12px;
      display: flex; flex-direction: column; gap: 4px;
      border-bottom: 1px solid var(--line);
    }
    .outfit-header-top {
      display: flex; align-items: baseline; justify-content: space-between; gap: 16px;
    }
    .outfit-header-top .outfit-feedback {
      display: flex; gap: 12px; flex-shrink: 0; align-items: center;
    }
    /* Feedback strip — legacy, hidden (replaced by header icons + modal) */
    .feedback-strip { display: none; }
    .fb-icon-btn {
      appearance: none;
      background: transparent;
      border: 0;
      padding: 4px;
      color: var(--ink-4);
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      border-radius: var(--radius-sm);
      flex-shrink: 0;
      transition: color var(--dur-1) var(--ease);
    }
    .fb-icon-btn svg { display: block; }
    .fb-icon-btn:hover { color: var(--ink); }
    .fb-icon-btn.fb-like:hover { color: var(--accent); }
    .feedback-prompt {
      appearance: none;
      background: transparent;
      border: 0;
      padding: 0;
      font-family: inherit;
      font-size: 13px;
      font-style: italic;
      color: var(--ink-4);
      cursor: pointer;
      text-align: left;
      transition: color var(--dur-1) var(--ease);
    }
    .feedback-prompt:hover { color: var(--ink-2); }
    /* Textarea + submit hidden until .fb-open toggled */
    .feedback-strip .feedback-textarea,
    .feedback-strip .dislike-submit { display: none; }
    .feedback-strip.fb-open .feedback-prompt { display: none; }
    .feedback-strip.fb-open .feedback-textarea {
      display: block;
      flex: 1;
      border: 0;
      border-bottom: 1px solid var(--line-strong);
      border-radius: 0;
      padding: 4px 0;
      font-family: inherit; font-size: 13px; font-style: italic;
      color: var(--ink); background: transparent;
      resize: none; outline: none;
      min-height: 22px;
      transition: border-color var(--dur-1) var(--ease);
    }
    .feedback-strip.fb-open .feedback-textarea::placeholder { color: var(--ink-4); }
    .feedback-strip.fb-open .feedback-textarea:focus { border-bottom-color: var(--ink); }
    .feedback-strip.fb-open .dislike-submit {
      display: block;
      flex-shrink: 0;
    }
    /* Hero image — contain (never crops). Background matches card so gaps are invisible. */
    .outfit-main-img {
      position: relative;
      background: var(--surface);
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 0;
    }
    .outfit-main-img img {
      display: block;
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
    }
    /* Thumbnails — vertical strip in the first grid column */
    .outfit-thumbs {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 8px 8px;
      overflow-y: auto;
      background: var(--surface);
    }
    .outfit-thumbs img {
      width: 60px; aspect-ratio: 2/3; height: auto;
      object-fit: cover;
      border-radius: var(--radius-sm);
      border: 1px solid transparent;
      cursor: pointer;
      opacity: 0.6;
      flex-shrink: 0;
      transition: opacity var(--dur-1) var(--ease), border-color var(--dur-1) var(--ease);
    }
    .outfit-thumbs img.active { border-color: var(--ink); opacity: 1; }
    .outfit-thumbs img:hover { opacity: 1; }
    .outfit-info {
      padding: 16px 20px; overflow: visible;
      display: flex; flex-direction: column; gap: 8px;
    }
    .outfit-rank {
      font-size: 9px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
    }
    .outfit-source-row { display: flex; gap: 6px; flex-wrap: wrap; }
    /* Source labels — uppercase tracked, no fill. Confident Luxe § Voice & Microcopy. */
    .source-pill {
      display: inline-block;
      padding: 4px 0;
      border: 0;
      background: transparent;
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-3);
    }
    .source-pill.wardrobe,
    .source-pill.catalog { color: var(--ink-3); }
    .source-pill.hybrid { color: var(--ink-3); }
    .source-mini-pill {
      display: inline-block;
      padding: 2px 0;
      background: transparent;
      font-family: inherit;
      font-size: 9px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
    }
    .source-mini-pill.wardrobe,
    .source-mini-pill.catalog,
    .source-mini-pill.hybrid { color: var(--ink-4); }
    /* Outfit title — Fraunces italic (compact) */
    .outfit-title {
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-size: 18px;
      font-weight: 400;
      font-style: italic;
      line-height: 1.15;
      color: var(--ink);
    }
    /* Summary — stylist caption, compact */
    .outfit-summary { padding: 0; }
    .outfit-summary-label {
      font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4); margin-bottom: 4px;
    }
    .outfit-summary-text {
      font-size: 12px; font-style: italic;
      color: var(--ink-3); line-height: 1.5; margin: 0;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    }
    /* Per-item source label injected above each product title */
    .product-source-label {
      display: block;
      font-size: 9px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.16em;
      color: var(--ink-4);
      margin-bottom: 3px;
    }
    .outfit-product { padding: 10px 0; border-bottom: 1px solid var(--line); }
    .outfit-product:last-of-type { border-bottom: none; }
    .outfit-product-title { font-weight: 500; font-size: 14px; display: block; margin-bottom: 3px; color: var(--ink); }
    .product-price {
      font-family: "JetBrains Mono", ui-monospace, monospace;
      font-size: 10px; font-weight: 500;
      color: var(--ink-3);
      display: block; margin-bottom: 6px;
    }
    .product-cta { display: flex; gap: 14px; align-items: center; }
    .btn-buy, .btn-wishlist {
      appearance: none;
      padding: 4px 0;
      background: transparent;
      border: 0;
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      text-decoration: none; white-space: nowrap; cursor: pointer;
      text-align: left;
      transition: color var(--dur-1) var(--ease);
    }
    .btn-buy {
      color: var(--ink);
      border-bottom: 1px solid var(--ink);
    }
    .btn-buy:hover { color: var(--accent); border-bottom-color: var(--accent); text-decoration: none; }
    .btn-wishlist { color: var(--ink-4); }
    .btn-wishlist:hover { color: var(--ink); }
    .btn-wishlist.wishlisted { color: var(--accent); }
    .outfit-item-source { display: flex; gap: 10px; align-items: center; margin-top: 6px; }
    .chip {
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      padding: 0; background: transparent;
      color: var(--ink-4);
    }
    /* Polar chart — always visible */
    .outfit-radar {
      text-align: center;
      padding: 8px 0 4px;
      margin-top: 8px;
    }
    .outfit-radar canvas {
      display: block; margin: 0 auto;
      max-width: 100%; height: auto;
      aspect-ratio: 280 / 300;
    }
    .radar-toggle { display: none; }
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
    .outfit-feedback { display: flex; gap: 12px; flex-wrap: wrap; padding-top: 0; align-items: center; }
    /* Feedback modal — full-screen overlay for dislike feedback */
    .feedback-modal-overlay {
      position: fixed; inset: 0; z-index: 9500;
      background: rgba(var(--shadow-rgb), 0.5);
      backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
      display: flex; align-items: center; justify-content: center;
      opacity: 0; pointer-events: none;
      transition: opacity var(--dur-2) var(--ease);
    }
    .feedback-modal-overlay.open { opacity: 1; pointer-events: auto; }
    .feedback-modal {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      padding: 36px 32px 28px;
      width: min(92vw, 480px);
      box-shadow: var(--shadow-modal);
    }
    .feedback-modal h3 {
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-size: 24px; font-weight: 400; font-style: italic;
      color: var(--ink); margin: 0 0 24px;
    }
    .feedback-modal .reaction-row {
      display: flex; flex-wrap: wrap; gap: 10px;
      margin-bottom: 20px;
    }
    .feedback-modal .reaction-chip {
      appearance: none;
      padding: 8px 18px;
      border-radius: var(--radius-full);
      border: 1px solid var(--line);
      background: transparent;
      font-family: inherit;
      font-size: 13px; font-weight: 500;
      color: var(--ink-2);
      cursor: pointer;
      transition: border-color var(--dur-1) var(--ease), color var(--dur-1) var(--ease);
    }
    .feedback-modal .reaction-chip:hover { border-color: var(--ink); color: var(--ink); }
    .feedback-modal .reaction-chip.selected { border-color: var(--ink); color: var(--ink); font-weight: 600; }
    .feedback-modal textarea {
      width: 100%;
      border: 0;
      border-bottom: 1px solid var(--line-strong);
      border-radius: 0;
      padding: 10px 0;
      font-family: inherit; font-size: 14px; font-style: italic;
      color: var(--ink); background: transparent;
      resize: none; outline: none;
      min-height: 48px;
      margin-bottom: 24px;
      transition: border-color var(--dur-1) var(--ease);
    }
    .feedback-modal textarea::placeholder { color: var(--ink-4); }
    .feedback-modal textarea:focus { border-bottom-color: var(--ink); }
    .feedback-modal .dislike-actions {
      display: flex; gap: 12px; align-items: center;
    }
    .feedback-modal .dislike-actions button {
      appearance: none;
      padding: 10px 22px;
      border-radius: var(--radius-md);
      font-family: inherit;
      font-size: 11px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      cursor: pointer;
    }
    .feedback-modal .dislike-actions button:first-child {
      background: var(--ink); color: var(--canvas); border: 1px solid var(--ink);
      transition: background-color var(--dur-1) var(--ease);
    }
    .feedback-modal .dislike-actions button:first-child:hover { background: var(--ink-2); border-color: var(--ink-2); }
    .feedback-modal .dislike-actions .secondary {
      background: transparent; color: var(--ink-3);
      border: 1px solid var(--line-strong);
      transition: border-color var(--dur-1) var(--ease), color var(--dur-1) var(--ease);
    }
    .feedback-modal .dislike-actions .secondary:hover { border-color: var(--ink); color: var(--ink); }
    .feedback-modal .feedback-status {
      font-size: 12px; font-style: italic;
      padding: 8px 0 0;
      min-height: 18px;
    }
    .reaction-row { display: none; flex-wrap: wrap; gap: 8px; padding: 8px 0 4px; }
    .reaction-row.open { display: flex; }
    .reaction-chip {
      appearance: none;
      padding: 6px 14px;
      border-radius: var(--radius-full);
      border: 1px solid var(--line);
      background: transparent;
      font-family: inherit;
      font-size: 11px; font-weight: 500;
      color: var(--ink-2);
      cursor: pointer;
      transition: border-color var(--dur-1) var(--ease), color var(--dur-1) var(--ease);
    }
    .reaction-chip:hover { border-color: var(--ink); color: var(--ink); }
    .reaction-chip.selected { border-color: var(--ink); color: var(--ink); font-weight: 600; }
    /* Textarea + submit on the same row */
    .dislike-input-row {
      display: flex;
      align-items: flex-end;
      gap: 12px;
    }
    .dislike-form textarea {
      flex: 1;
      border: 0;
      border-bottom: 1px solid var(--line-strong);
      border-radius: 0;
      padding: 8px 0;
      font-family: inherit; font-size: 13px;
      color: var(--ink); background: transparent;
      resize: none;
      min-height: 28px; outline: none;
      transition: border-color var(--dur-1) var(--ease);
    }
    .dislike-form textarea::placeholder { color: var(--ink-4); font-style: italic; }
    .dislike-form textarea:focus { border-bottom-color: var(--ink); }
    .dislike-submit {
      appearance: none;
      flex-shrink: 0;
      padding: 6px 16px;
      border-radius: var(--radius-md);
      border: 1px solid var(--ink);
      background: var(--ink);
      color: var(--canvas);
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      cursor: pointer;
      transition: background-color var(--dur-1) var(--ease);
    }
    .dislike-submit:hover { background: var(--ink-2); border-color: var(--ink-2); }
    .feedback-status { font-size: 12px; font-style: italic; padding: 6px 0; min-height: 18px; }
    .feedback-status.success { color: var(--positive); }
    .feedback-status.error { color: var(--danger); }

    /* ===== Wardrobe Page ===== */
    /* ===== Wardrobe — Confident Luxe closet ===== */
    .page-wardrobe {
      padding: 48px 48px 64px; max-width: 1440px; margin: 0 auto; width: 100%;
    }
    .wardrobe-header {
      display: flex; align-items: flex-start; justify-content: space-between;
      margin-bottom: 32px; gap: 24px; flex-wrap: wrap;
    }
    .wardrobe-title-block { display: flex; align-items: baseline; gap: 24px; flex-wrap: wrap; }
    .wardrobe-header h2 {
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-size: clamp(36px, 5vw, 48px);
      font-weight: 400;
      line-height: 1.05;
      color: var(--ink);
      margin: 0;
    }
    .wardrobe-count {
      font-family: "JetBrains Mono", ui-monospace, monospace;
      font-size: 11px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--ink-3);
    }
    .wardrobe-count .num { color: var(--ink); font-weight: 600; }
    .wardrobe-header-actions { display: flex; align-items: center; gap: 12px; }
    .wardrobe-stats { display: none; }  /* legacy stats row retired */
    .wardrobe-filters {
      display: flex; gap: 20px 24px; flex-wrap: wrap; margin-bottom: 14px;
      padding-bottom: 14px; border-bottom: 1px solid var(--line);
    }
    .filter-chip {
      appearance: none;
      padding: 6px 0;
      border: 0;
      border-bottom: 1px solid transparent;
      background: none;
      font-family: inherit;
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--ink-4);
      cursor: pointer;
      transition: color var(--dur-1) var(--ease), border-color var(--dur-1) var(--ease);
    }
    .filter-chip:hover { color: var(--ink-2); }
    .filter-chip.active { color: var(--ink); border-bottom-color: var(--ink); }
    .filter-row {
      display: flex; gap: 20px 24px; flex-wrap: wrap; margin-bottom: 20px;
      padding-bottom: 14px; border-bottom: 1px solid var(--line);
    }
    .wardrobe-search {
      flex: 0 0 auto;
      min-width: 220px;
      padding: 6px 0;
      border: 0;
      border-bottom: 1px solid var(--line-strong);
      border-radius: 0;
      font-family: inherit;
      font-size: 13px;
      color: var(--ink);
      background: transparent;
      outline: none;
      transition: border-color var(--dur-1) var(--ease);
    }
    .wardrobe-search:focus { border-bottom-color: var(--ink); }
    .wardrobe-search::placeholder { color: var(--ink-4); }
    .closet-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 40px 28px;
      margin-top: 32px;
    }
    /* Closet card — no border, no shadow, no background. Just photo + metadata below. */
    .closet-card {
      background: transparent;
      border: 0;
      border-radius: 0;
      overflow: visible;
      transition: none;
      display: flex;
      flex-direction: column;
    }
    .closet-card:hover { border-color: transparent; }
    .closet-image {
      aspect-ratio: 4/5;
      overflow: hidden;
      background: var(--surface-sunk);
      border-radius: var(--radius-sm);
    }
    .closet-image img {
      width: 100%; height: 100%;
      object-fit: cover;
      object-position: center 20%;
      display: block;
      transition: opacity var(--dur-2) var(--ease);
    }
    .closet-card:hover .closet-image img { opacity: 0.92; }
    .closet-placeholder {
      width: 100%; height: 100%;
      display: flex; align-items: center; justify-content: center;
      font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
    }
    .closet-body {
      padding: 14px 0 0;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .closet-body h3 {
      font-size: 13px;
      font-weight: 500;
      margin: 0;
      line-height: 1.35;
      color: var(--ink);
      transition: text-decoration var(--dur-1) var(--ease);
    }
    .closet-card:hover .closet-body h3 { text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 3px; }
    .closet-body p {
      font-size: 11px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--ink-3);
      line-height: 1.4;
      margin: 0;
      display: -webkit-box;
      -webkit-line-clamp: 1;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .tag-row { display: none; }  /* legacy pill tags retired — metadata lives in the UPPERCASE caption */
    .closet-actions {
      display: flex;
      gap: 8px;
      margin-top: 10px;
      opacity: 0;
      transition: opacity var(--dur-1) var(--ease);
    }
    .closet-card:hover .closet-actions,
    .closet-card:focus-within .closet-actions { opacity: 1; }
    @media (prefers-reduced-motion: reduce) {
      .closet-actions { opacity: 1; }
    }
    .studio-btn {
      appearance: none;
      padding: 4px 0;
      border: 0;
      background: none;
      font-family: inherit;
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--ink-3);
      cursor: pointer;
      transition: color var(--dur-1) var(--ease);
    }
    .studio-btn:hover { color: var(--ink); }
    .studio-btn.primary { color: var(--accent); }
    .studio-btn.primary:hover { color: var(--accent-soft); }
    .studio-btn.icon-only { padding: 4px 6px; }
    .studio-btn.danger { color: var(--ink-4); }
    .studio-btn.danger:hover { color: var(--danger); }
    .wardrobe-empty {
      grid-column: 1 / -1;
      text-align: center;
      padding: 80px 24px;
      color: var(--ink-3);
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-style: italic;
      font-size: 28px;
      line-height: 1.3;
    }
    .wardrobe-add-btn {
      appearance: none;
      padding: 10px 22px;
      border-radius: var(--radius-md);
      border: 1px solid var(--ink);
      background: var(--ink);
      color: var(--canvas);
      font-family: inherit;
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      cursor: pointer;
      transition: background-color var(--dur-1) var(--ease), border-color var(--dur-1) var(--ease);
    }
    .wardrobe-add-btn:hover { background: var(--ink-2); border-color: var(--ink-2); }

    /* ===== Looks (Results) Page — Confident Luxe lookbook ===== */
    .page-results {
      padding: 48px 48px 64px; max-width: 1440px; margin: 0 auto; width: 100%;
    }
    .results-header {
      display: flex; align-items: flex-start; justify-content: space-between;
      gap: 24px; flex-wrap: wrap; margin-bottom: 32px;
    }
    .results-header h2 {
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-size: clamp(36px, 5vw, 48px);
      font-weight: 400;
      line-height: 1.05;
      color: var(--ink);
      margin: 0;
    }
    .results-header p {
      font-size: 13px;
      color: var(--ink-3);
      font-style: italic;
      line-height: 1.5;
      margin: 8px 0 0;
      max-width: 480px;
    }
    .results-tabs {
      display: flex; gap: 20px 24px; flex-wrap: wrap;
      margin-bottom: 14px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }
    .results-tabs button {
      appearance: none;
      padding: 6px 0;
      border: 0;
      border-bottom: 1px solid transparent;
      background: none;
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
      cursor: pointer;
      transition: color var(--dur-1) var(--ease), border-color var(--dur-1) var(--ease);
    }
    .results-tabs button:hover { color: var(--ink-2); }
    .results-tabs button.active { color: var(--ink); border-bottom-color: var(--ink); }
    .results-filters {
      display: flex; gap: 20px 24px; flex-wrap: wrap;
      margin-bottom: 28px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }
    .results-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 40px 28px;
    }
    /* Lookbook card — full-bleed image, display title overlay */
    .result-card {
      position: relative;
      border: 0;
      border-radius: var(--radius-sm);
      overflow: hidden;
      background: var(--surface-sunk);
      cursor: pointer;
      aspect-ratio: 4/5;
    }
    .result-card:hover { border-color: transparent; }
    .result-card .thumb {
      position: absolute; inset: 0;
      background: var(--surface-sunk);
      overflow: hidden;
    }
    .result-card .thumb img {
      width: 100%; height: 100%;
      object-fit: cover;
      transition: opacity var(--dur-2) var(--ease);
    }
    .result-card:hover .thumb img { opacity: 0.88; }
    .result-card .thumb-placeholder {
      width: 100%; height: 100%;
      display: flex; align-items: center; justify-content: center;
      color: var(--ink-4);
      font-size: 11px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
    }
    /* Top-right source label. Text sits over dark image gradient — always light ivory, regardless of theme. */
    .result-card .body .meta-row .source-mini-pill {
      position: absolute;
      top: 14px; right: 16px;
      color: var(--on-accent);
      text-shadow: 0 1px 2px rgba(0,0,0,0.4);
    }
    /* Bottom-left title block with dark gradient overlay */
    .result-card .body {
      position: absolute;
      left: 0; right: 0; bottom: 0;
      padding: 20px 18px 18px;
      background: linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.35) 60%, rgba(0,0,0,0.6) 100%);
      color: var(--on-accent);
    }
    .result-card .body .msg {
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-size: 20px; font-weight: 400;
      font-style: italic;
      line-height: 1.15;
      margin-bottom: 8px;
      color: var(--on-accent);
      display: -webkit-box;
      -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
      text-shadow: 0 1px 3px rgba(0,0,0,0.35);
    }
    .result-card .body .meta-row {
      display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
    }
    .result-card .body .meta-row .ts {
      font-size: 9px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--on-accent);
      opacity: 0.75;
    }
    /* Reposition intent chip at top-left */
    .result-card .body .meta-row .source-mini-pill.catalog {
      position: absolute;
      top: 14px; left: 16px; right: auto;
      color: var(--on-accent);
      text-shadow: 0 1px 2px rgba(0,0,0,0.4);
    }
    .results-empty {
      grid-column: 1 / -1;
      text-align: center;
      padding: 80px 24px;
      color: var(--ink-3);
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-style: italic;
      font-size: 28px;
      line-height: 1.3;
    }

    /* ===== Add / Edit Wardrobe Item Modal — Confident Luxe ===== */
    /* NOTE: this block intentionally re-declares .modal-overlay and .modal-box
       because #addItemModal and #editItemModal are loaded after the picker modal
       CSS and need different behaviour (fade + drawer variant). */
    .modal-overlay {
      position: fixed; inset: 0; z-index: 9000;
      background: rgba(var(--shadow-rgb), 0.5);
      backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
      display: flex; align-items: center; justify-content: center;
      opacity: 0; pointer-events: none;
      transition: opacity var(--dur-2) var(--ease);
    }
    .modal-overlay.open { opacity: 1; pointer-events: auto; }
    .modal-box {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      width: min(92vw, 520px);
      max-height: 88vh;
      overflow-y: auto;
      padding: 36px 32px;
      box-shadow: var(--shadow-modal);
    }
    /* Drawer variant — right-edge slide, used by #addItemModal via .drawer-right on box */
    .modal-overlay.drawer-right { justify-content: flex-end; align-items: stretch; }
    .modal-overlay.drawer-right .modal-box {
      width: min(100vw, 480px);
      max-height: 100vh;
      height: 100%;
      border-radius: 0;
      border-left: 1px solid var(--line);
      border-right: 0; border-top: 0; border-bottom: 0;
      transform: translateX(24px);
      transition: transform var(--dur-2) var(--ease);
      padding: 48px 36px 36px;
    }
    .modal-overlay.drawer-right.open .modal-box { transform: translateX(0); }
    @media (max-width: 640px) {
      .modal-overlay.drawer-right .modal-box { width: 100vw; }
    }
    .modal-box h2 {
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-size: 32px; font-weight: 400; line-height: 1.15;
      color: var(--ink);
      margin-bottom: 8px;
    }
    .modal-field { margin-bottom: 20px; }
    .modal-field label {
      display: block;
      font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4); margin-bottom: 8px;
    }
    .modal-field input, .modal-field select {
      width: 100%;
      padding: 8px 0;
      border: 0;
      border-bottom: 1px solid var(--line-strong);
      border-radius: 0;
      font-family: inherit; font-size: 14px;
      color: var(--ink); background: transparent;
      outline: none;
      transition: border-color var(--dur-1) var(--ease);
    }
    .modal-field input:focus, .modal-field select:focus { border-bottom-color: var(--ink); }
    .modal-field input[type="file"] { padding: 8px; border: 1px dashed var(--line); border-radius: var(--radius-md); }
    .modal-row { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    .modal-actions {
      display: flex; gap: 8px; justify-content: flex-end;
      margin-top: 28px; padding-top: 20px;
      border-top: 1px solid var(--line);
    }
    .modal-actions .btn-cancel {
      padding: 10px 18px;
      border-radius: var(--radius-md);
      border: 1px solid var(--line);
      background: transparent;
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-3);
      cursor: pointer;
      transition: border-color var(--dur-1) var(--ease), color var(--dur-1) var(--ease);
    }
    .modal-actions .btn-cancel:hover { border-color: var(--ink); color: var(--ink); }
    .modal-error { color: var(--danger); font-size: 12px; margin-top: 8px; font-style: italic; }
    .modal-preview {
      width: 80px; height: 100px;
      border-radius: var(--radius-sm);
      object-fit: cover;
      margin-top: 8px;
      border: 1px solid var(--line);
    }

    /* ===== Profile — Style Dossier (Confident Luxe) ===== */
    .page-profile {
      padding: 48px 48px 80px;
      max-width: 1040px; margin: 0 auto; width: 100%;
    }
    /* Dossier hero — name in display-xl, one-line stylist statement */
    .dossier-hero {
      padding: 32px 0 40px;
      margin-bottom: 40px;
      border-bottom: 1px solid var(--line);
    }
    .dossier-hero h1 {
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-size: clamp(48px, 7vw, 72px);
      font-weight: 400;
      line-height: 1.02;
      letter-spacing: -0.02em;
      color: var(--ink);
      margin: 0 0 14px;
    }
    .dossier-hero .dossier-statement {
      font-size: 14px;
      font-style: italic;
      line-height: 1.55;
      color: var(--ink-3);
      max-width: 560px;
      margin: 0;
    }
    .dossier-hero .dossier-controls {
      display: flex;
      align-items: center;
      gap: 24px;
      margin-top: 24px;
    }
    /* Unified dossier card — all cards share one quiet treatment */
    .profile-card,
    .style-code-card,
    .color-palette-card,
    .analysis-card,
    .profile-images-card {
      background: transparent;
      border: 0;
      border-top: 1px solid var(--line);
      border-radius: 0;
      padding: 32px 0 40px;
      margin-bottom: 0;
    }
    .profile-card-header {
      display: flex; align-items: baseline; justify-content: space-between;
      margin-bottom: 24px;
    }
    .profile-card-header h2,
    .profile-card-header h3,
    .style-code-card > h3,
    .color-palette-card > h3,
    .profile-images-card > h3,
    .analysis-card h2 {
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-size: 28px;
      font-weight: 400;
      line-height: 1.15;
      color: var(--ink);
      margin: 0 0 20px;
    }
    .profile-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 28px 32px; }
    .profile-field { }
    .profile-field .label {
      display: block;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4); margin-bottom: 8px;
    }
    .profile-field .value {
      font-size: 15px; font-weight: 500;
      color: var(--ink);
    }
    .profile-field .value:empty::before {
      content: "—"; color: var(--ink-4);
    }
    .profile-field input, .profile-field select {
      width: 100%;
      padding: 6px 0;
      border: 0;
      border-bottom: 1px solid var(--line-strong);
      border-radius: 0;
      font-family: inherit; font-size: 14px;
      color: var(--ink); background: transparent;
      outline: none;
      display: none;
      transition: border-color var(--dur-1) var(--ease);
    }
    .profile-field input:focus, .profile-field select:focus { border-bottom-color: var(--ink); }
    .profile-field.editing .value { display: none; }
    .profile-field.editing input, .profile-field.editing select { display: block; }
    .profile-actions { display: flex; gap: 10px; margin-top: 24px; }
    .btn-primary {
      padding: 10px 20px;
      border-radius: var(--radius-md);
      border: 1px solid var(--ink);
      background: var(--ink);
      color: var(--canvas);
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      cursor: pointer;
      transition: background-color var(--dur-1) var(--ease), border-color var(--dur-1) var(--ease);
    }
    .btn-primary:hover { background: var(--ink-2); border-color: var(--ink-2); }
    .btn-secondary {
      padding: 10px 20px;
      border-radius: var(--radius-md);
      border: 1px solid var(--line-strong);
      background: transparent;
      color: var(--ink-3);
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      cursor: pointer;
      transition: border-color var(--dur-1) var(--ease), color var(--dur-1) var(--ease);
    }
    .btn-secondary:hover { border-color: var(--ink); color: var(--ink); }
    .edit-status { font-size: 12px; margin-top: 10px; min-height: 18px; font-style: italic; }
    .edit-status.success { color: var(--positive); }
    .edit-status.error { color: var(--danger); }
    /* Style code — adjectives as display-italic quote blocks */
    .style-facts {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-bottom: 28px;
    }
    .style-fact {
      background: transparent;
      border: 0;
      border-radius: 0;
      padding: 0;
    }
    .style-fact .fact-label {
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
      margin-bottom: 2px;
      display: none;  /* hide in dossier view — the adjective is the label */
    }
    .style-fact .fact-value {
      font-family: "Fraunces", "Cormorant Garamond", Georgia, serif;
      font-style: italic;
      font-size: clamp(28px, 4vw, 44px);
      font-weight: 400;
      line-height: 1.1;
      color: var(--ink);
    }
    .style-summary {
      font-size: 14px;
      font-style: italic;
      color: var(--ink-3);
      line-height: 1.6;
      max-width: 520px;
      margin-top: 20px;
      padding-top: 20px;
      border-top: 1px solid var(--line);
    }
    /* ===== Analysis Status — hairline Confident Luxe ===== */
    .analysis-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
    .analysis-badge {
      padding: 0;
      background: transparent;
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
    }
    .analysis-badge.completed { color: var(--positive); }
    .analysis-badge.running { color: var(--accent); }
    .analysis-badge.failed { color: var(--danger); }
    .analysis-progress {
      width: 100%; height: 2px;
      border-radius: 0;
      background: var(--line);
      overflow: hidden;
      margin-bottom: 16px;
    }
    .analysis-progress-bar {
      width: 14%; height: 100%;
      border-radius: inherit;
      background: var(--ink);
      transition: width var(--dur-3) var(--ease);
    }
    .analysis-text { font-size: 13px; color: var(--ink-3); font-style: italic; margin-bottom: 16px; }
    .analysis-actions { display: flex; gap: 10px; flex-wrap: wrap; }
    .analysis-error {
      display: none; padding: 12px 16px;
      border-left: 2px solid var(--danger);
      background: transparent;
      color: var(--danger);
      font-size: 12px; font-style: italic;
      margin-bottom: 14px;
    }
    .analysis-error.show { display: block; }
    .agent-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 20px; }
    .agent-card {
      border: 0;
      border-top: 1px solid var(--line);
      border-radius: 0;
      padding: 16px 0 0;
      background: transparent;
    }
    .agent-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
    .agent-card h4 {
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-3);
      margin: 0;
    }
    .agent-card p { font-size: 13px; color: var(--ink-2); margin: 0; }
    .agent-rerun-btn {
      padding: 4px 0;
      background: transparent; border: 0;
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
      cursor: pointer;
      display: none;
      transition: color var(--dur-1) var(--ease);
    }
    .agent-rerun-btn:hover { color: var(--ink); }
    .agent-rerun-btn.show { display: inline-block; }
    .result-group {
      border: 0;
      border-top: 1px solid var(--line);
      border-radius: 0;
      background: transparent;
      margin-bottom: 24px;
    }
    .result-group-header {
      padding: 12px 0 16px;
      background: transparent;
      border-bottom: 1px solid var(--line);
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
    }
    .attr-row { display: grid; grid-template-columns: 160px 1fr 70px; gap: 10px; padding: 14px 0; border-bottom: 1px solid var(--line); align-items: start; font-size: 13px; }
    .attr-row:last-child { border-bottom: none; }
    .attr-name {
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-3);
    }
    .attr-value { line-height: 1.5; color: var(--ink); }
    .attr-value small { display: block; margin-top: 4px; color: var(--ink-4); font-size: 11px; font-style: italic; }
    .attr-confidence {
      justify-self: end;
      padding: 0;
      background: transparent;
      font-family: "JetBrains Mono", ui-monospace, monospace;
      font-size: 11px; font-weight: 500;
      color: var(--ink-3);
    }

    /* ===== Profile Images ===== */
    .profile-images-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; max-width: 520px; }
    .profile-image-slot { }
    .profile-image-slot .slot-label {
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
      margin-bottom: 10px;
    }
    .profile-image-slot img {
      width: 100%;
      border-radius: var(--radius-sm);
      border: 0;
      aspect-ratio: 2/3;
      object-fit: cover;
      background: var(--surface-sunk);
    }
    .profile-image-slot .slot-empty {
      width: 100%;
      aspect-ratio: 2/3;
      border-radius: var(--radius-sm);
      border: 1px dashed var(--line-strong);
      background: var(--surface-sunk);
      display: flex; align-items: center; justify-content: center;
      color: var(--ink-4);
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
    }
    .profile-image-slot .slot-update { margin-top: 12px; }
    .profile-image-slot .slot-update label {
      display: inline-block;
      padding: 4px 0;
      background: transparent;
      border: 0;
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
      cursor: pointer;
      transition: color var(--dur-1) var(--ease);
    }
    .profile-image-slot .slot-update label:hover { color: var(--ink); }
    .profile-image-slot .slot-update input { display: none; }
    .analysis-confidence-pct {
      font-family: "JetBrains Mono", ui-monospace, monospace;
      font-size: 11px; font-weight: 500;
      color: var(--ink-3);
      margin-left: 12px;
    }

    /* Color palette — hairline swatch strip, champagne signal rule */
    .color-palette-card {
      position: relative;
    }
    .color-palette-card::before {
      content: "";
      position: absolute;
      top: 32px; bottom: 40px; left: -14px;
      width: 1px;
      background: var(--signal);
    }
    .palette-section { margin-bottom: 20px; }
    .palette-section:last-child { margin-bottom: 0; }
    .palette-label {
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-4);
      margin-bottom: 10px;
    }
    .palette-chips { display: flex; gap: 18px; flex-wrap: wrap; }
    .palette-chip {
      padding: 0 0 6px;
      background: transparent;
      border: 0;
      border-bottom: 1px solid var(--line);
      font-family: inherit;
      font-size: 11px; font-weight: 500;
      text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--ink-2);
    }
    .palette-chip.base { color: var(--ink); border-bottom-color: var(--line-strong); }
    .palette-chip.accent { color: var(--accent); border-bottom-color: var(--accent); }
    .palette-chip.avoid { color: var(--ink-4); text-decoration: line-through; border-bottom-color: transparent; }

    /* Theme toggle — lives in the dossier hero */
    .theme-toggle {
      appearance: none;
      padding: 4px 0;
      background: transparent;
      border: 0;
      border-bottom: 1px solid var(--line);
      font-family: inherit;
      font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--ink-3);
      cursor: pointer;
      transition: color var(--dur-1) var(--ease), border-color var(--dur-1) var(--ease);
    }
    .theme-toggle:hover { color: var(--ink); border-bottom-color: var(--ink); }

    /* ===== Responsive ===== */
    @media (max-width: 1200px) {
      .closet-grid { grid-template-columns: repeat(4, 1fr); gap: 32px 24px; }
    }
    @media (max-width: 900px) {
      .history-rail { width: 220px; min-width: 220px; }
      .outfit-card { grid-template-columns: 1fr; }
      .outfit-thumbs { flex-direction: row; overflow-x: auto; padding: 8px; }
      .outfit-thumbs img { width: 56px; height: 56px; }
      .outfit-main-img img { max-height: 320px; }
      .closet-grid { grid-template-columns: repeat(3, 1fr); gap: 28px 20px; }
      .results-grid { grid-template-columns: 1fr; }
      .profile-grid, .style-facts, .edit-grid { grid-template-columns: 1fr; }
      .page-wardrobe { padding: 32px 24px; }
    }
    @media (max-width: 600px) {
      .app-header { padding: 0 12px; gap: 8px; }
      .header-nav a { padding: 6px 10px; font-size: 12px; }
      .new-chat-btn { display: none; }
      .history-rail { display: none !important; }
      .hamburger-btn { display: flex !important; }
      .history-rail.mobile-open {
        display: flex !important; position: fixed; top: var(--header-h); left: 0; bottom: 0;
        width: 280px; z-index: 150; background: var(--canvas);
        box-shadow: var(--shadow-modal);
      }
      .chat-feed { padding: 16px 12px; }
      .composer-wrap { padding: 6px 12px 12px; }
      .page-wardrobe { padding: 24px 16px; }
      .page-results, .page-profile { padding: 16px; }
      .closet-grid { grid-template-columns: repeat(2, 1fr); gap: 24px 16px; }
      .wardrobe-search { margin-left: 0 !important; width: 100%; }
    }
    @media (max-width: 430px) {
      .header-brand { font-size: 18px; }
      .closet-grid { gap: 20px 14px; }
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
    <a href="/?user={safe_user_id}&view=home" class="{'active' if active_view in ('home', 'chat') else ''}">Home</a>
    <a href="/?user={safe_user_id}&view=outfits" class="{'active' if active_view == 'outfits' else ''}">Outfits</a>
    <a href="/?user={safe_user_id}&view=checks" class="{'active' if active_view == 'checks' else ''}">Checks</a>
    <a href="/?user={safe_user_id}&view=wardrobe" class="{'active' if active_view == 'wardrobe' else ''}">Wardrobe</a>
    <a href="/?user={safe_user_id}&view=wishlist" class="{'active' if active_view == 'wishlist' else ''}">Saved</a>
  </nav>
  <div class="header-actions">
    <button class="new-chat-btn" id="newChatBtn" style="display:none;">New chat</button>
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

    # ── Discovery Surface (Home) — Phase 15 ──
    html += f"""
<div class="page-view page-home">
  <div class="discovery-top" id="discoveryTop">
    <h1 class="welcome-headline">What are we wearing<span class="welcome-dot">.</span></h1>
    <p class="welcome-sub">From your wardrobe first. Catalog when there's a gap.</p>
    <div class="discovery-input-wrap">
      <input type="text" class="discovery-input" id="discoveryInput" placeholder="Describe what you need..." aria-label="Describe what you need" />
      <button class="discovery-send" id="discoverySend" type="button" aria-label="Send"><span class="arrow">&#10148;</span></button>
    </div>
    <div class="discovery-thinking" id="discoveryThinking"></div>
    <div class="welcome-prompts" id="welcomePrompts">
      <button class="welcome-prompt" data-prompt="Dress me for tonight using my wardrobe.">Build a look</button>
      <button class="welcome-prompt" data-prompt="What goes well with this?">Pair a garment</button>
      <button class="welcome-prompt" data-prompt="Plan my wardrobe for a 5-day trip.">Plan a trip</button>
      <button class="welcome-prompt" data-prompt="Is this worth buying?">Is it worth it</button>
    </div>
    <div class="image-chip" id="imageChip">
      <div class="chip-inner">
        <img id="imageChipImg" src="" alt="Attached" />
        <span class="name" id="imageChipName"></span>
        <button class="remove" id="imageChipRemove" aria-label="Remove image">&times;</button>
      </div>
    </div>
  </div>
  <div id="discoveryResultArea" class="discovery-result"></div>
  <div id="discoveryFollowups" class="discovery-followups"></div>
  <div id="recentIntents" class="recent-intents"></div>
  <!-- Hidden legacy feed for loadConversation replay -->
  <div id="feed" class="chat-feed" style="display:none;" role="region"></div>
  <div class="composer-error" id="composerError" style="max-width:680px;margin:0 auto;padding:0 32px;"></div>
</div>
"""

    # ── Outfits Tab (Phase 15C — intent-organized history) ──
    html += """
<div class="page-view page-outfits" style="padding: 48px 32px;">
  <div class="results-header"><div><h2>Outfits</h2><p>Everything we've styled, grouped by what you asked for.</p></div></div>
  <div id="outfitsContent" class="recent-intents" style="border-top:0;padding-top:0;">
    <div class="results-empty">Loading.</div>
  </div>
</div>
"""

    # ── Checks Tab (Phase 15D) ──
    html += """
<div class="page-view page-checks" style="padding: 48px 32px;">
  <div class="results-header"><div><h2>Checks</h2><p>Outfit checks you've run.</p></div></div>
  <div id="checksContent" style="max-width:960px;margin:0 auto;">
    <div class="results-empty">Loading.</div>
  </div>
</div>
"""

    # ── Wardrobe Page ──
    html += f"""
<div class="page-view page-wardrobe">
  <div class="wardrobe-header">
    <div class="wardrobe-title-block">
      <h2>Wardrobe</h2>
      <div class="wardrobe-count"><span class="num" id="wStatCount">0</span> pieces</div>
    </div>
    <div class="wardrobe-header-actions">
      <button class="wardrobe-add-btn" id="wardrobeAddBtn">Add piece</button>
    </div>
  </div>
  <div class="wardrobe-filters" id="wardrobeFilters" role="tablist" aria-label="Category">
    <button class="filter-chip active" data-filter="all">All</button>
    <button class="filter-chip" data-filter="tops">Tops</button>
    <button class="filter-chip" data-filter="bottoms">Bottoms</button>
    <button class="filter-chip" data-filter="shoes">Shoes</button>
    <button class="filter-chip" data-filter="dresses">Dresses</button>
    <button class="filter-chip" data-filter="outerwear">Outerwear</button>
    <button class="filter-chip" data-filter="accessories">Accessories</button>
    <button class="filter-chip" data-filter="occasion">Occasion-ready</button>
  </div>
  <div class="filter-row" id="wardrobeColorFilters" role="tablist" aria-label="Color">
    <button class="filter-chip active" data-color="all">All colors</button>
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
    <input type="search" id="wardrobeSearch" class="wardrobe-search" placeholder="Search your closet…" style="margin-left:auto;" />
  </div>
  <div class="closet-grid" id="closetGrid">
    <div class="wardrobe-empty">Your closet is empty.</div>
  </div>
</div>
"""

    # ── Add Wardrobe Item Drawer (right-edge slide) ──
    html += """
<div class="modal-overlay drawer-right" id="addItemModal">
  <div class="modal-box">
    <h2>Add a piece</h2>
    <p style="font-size:13px;color:var(--ink-3);margin-bottom:28px;font-style:italic;">Upload a photo. I'll read it automatically.</p>
    <form id="addItemForm">
      <label for="addItemFile" style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:48px 24px;border:1px dashed var(--line-strong);border-radius:var(--radius-md);cursor:pointer;transition:border-color var(--dur-1) var(--ease);min-height:240px;background:var(--surface-sunk);" id="addItemDropzone">
        <img class="modal-preview" id="addItemPreview" style="display:none;max-height:200px;border-radius:var(--radius-sm);" alt="" />
        <span id="addItemPlaceholder" style="font-size:32px;opacity:0.4;">&#128248;</span>
        <span id="addItemLabel" style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.14em;color:var(--ink-3);">Tap to upload or drag a photo</span>
        <input type="file" id="addItemFile" accept="image/*" required style="display:none;" />
      </label>
      <div class="modal-error" id="addItemError" style="text-align:center;"></div>
      <div class="modal-actions">
        <button type="button" class="btn-cancel" id="addItemCancel">Cancel</button>
        <button type="submit" class="btn-primary" id="addItemSubmit">Add to closet</button>
      </div>
    </form>
  </div>
</div>
"""

    # ── Edit Wardrobe Item Modal (center) ──
    html += """
<div class="modal-overlay" id="editItemModal">
  <div class="modal-box">
    <h2>Edit piece</h2>
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

    # ── Looks (Results) Page ──
    html += """
<div class="page-view page-results">
  <div class="results-header">
    <div>
      <h2>Looks</h2>
      <p>Everything we've styled, in one place.</p>
    </div>
  </div>
  <div class="results-tabs" id="resultsTabs" role="tablist" aria-label="Look type">
    <button class="active" data-tab="all">All</button>
    <button data-tab="occasion_recommendation">Outfits</button>
    <button data-tab="outfit_check">Checks</button>
    <button data-tab="pairing_request">Pairings</button>
    <button data-tab="capsule_or_trip_planning">Trips</button>
  </div>
  <div class="results-filters" id="resultsFilters" role="tablist" aria-label="Source">
    <button class="filter-chip active" data-source="all">All sources</button>
    <button class="filter-chip" data-source="wardrobe">Yours</button>
    <button class="filter-chip" data-source="catalog">Shop</button>
  </div>
  <div class="results-grid" id="resultsGrid">
    <div class="results-empty">Loading.</div>
  </div>
</div>
"""

    # ── Wishlist Page ──
    html += """
<div class="page-view page-wishlist" style="padding: 24px;">
  <div class="results-header">
    <h2>My Wishlist</h2>
    <p>Garments you saved from your styling sessions.</p>
  </div>
  <div class="closet-grid" id="wishlistGrid" style="gap: 18px; margin-top: 16px;">
    <div class="results-empty">Loading wishlist...</div>
  </div>
</div>
"""

    # ── Trial Room Page ──
    html += """
<div class="page-view page-trialroom" style="padding: 24px;">
  <div class="results-header">
    <h2>Trial Room</h2>
    <p>See how outfits look on you — your virtual try-on gallery.</p>
  </div>
  <div class="closet-grid" id="tryonGalleryGrid" style="gap: 18px; margin-top: 16px;">
    <div class="results-empty">Loading try-on gallery...</div>
  </div>
</div>
"""

    # ── Profile Page — Style Dossier (Confident Luxe) ──
    html += """
<div class="page-view page-profile">
  <div class="dossier-hero">
    <h1 id="dossierName">Your dossier</h1>
    <p class="dossier-statement" id="dossierStatement">A record of what we've learned about how you dress.</p>
    <div class="dossier-controls">
      <button class="theme-toggle" id="themeToggle" type="button" aria-label="Toggle light and dark theme">Flip to dark</button>
    </div>
  </div>
  <div class="style-code-card" id="styleCodeCard">
    <div class="profile-card-header">
      <h3>Style code</h3>
    </div>
    <div class="style-facts" id="styleFacts"></div>
    <div class="style-summary" id="styleSummary"></div>
  </div>
  <div class="color-palette-card" id="colorPaletteCard">
    <div class="profile-card-header">
      <h3>Palette</h3>
    </div>
    <div id="colorPaletteContent"></div>
  </div>
  <div class="profile-card" id="profileCard">
    <div class="profile-card-header">
      <h3>Profile</h3>
      <button class="btn-secondary" id="editToggleBtn">Edit</button>
    </div>
    <div class="profile-grid" id="profileGrid"></div>
    <div class="profile-actions" id="profileEditActions" style="display:none;">
      <button class="btn-primary" id="editSaveBtn">Save changes</button>
      <button class="btn-secondary" id="editCancelBtn">Cancel</button>
    </div>
    <div class="edit-status" id="editStatus"></div>
  </div>
  <div class="profile-images-card">
    <div class="profile-card-header">
      <h3>Photos</h3>
    </div>
    <div class="profile-images-grid">
      <div class="profile-image-slot">
        <div class="slot-label">Full body</div>
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
  <div class="analysis-card" id="analysisCard">
    <div class="profile-card-header">
      <h3>Analysis</h3>
      <div style="display:flex;align-items:center;gap:12px;">
        <span class="analysis-confidence-pct" id="analysisConfidence"></span>
        <div class="analysis-badge" id="analysisBadge">Loading</div>
      </div>
    </div>
    <div class="analysis-progress" id="analysisProgressWrap"><div class="analysis-progress-bar" id="analysisProgressBar"></div></div>
    <div class="analysis-text" id="analysisText">Checking analysis status.</div>
    <div class="analysis-error" id="analysisError"></div>
    <div class="analysis-actions" id="analysisActions">
      <button class="btn-secondary" id="analysisRerunBtn" style="display:none;">Re-run analysis</button>
      <button class="btn-secondary" id="analysisRetryBtn" style="display:none;">Retry</button>
    </div>
    <div class="agent-grid" id="analysisAgentGrid">
      <div class="agent-card"><div class="agent-card-head"><h4>Body</h4><button class="agent-rerun-btn" data-agent="body_type_analysis">Re-run</button></div><p id="agentStatus-body_type_analysis">—</p></div>
      <div class="agent-card"><div class="agent-card-head"><h4>Color</h4><button class="agent-rerun-btn" data-agent="color_analysis_headshot">Re-run</button></div><p id="agentStatus-color_analysis_headshot">—</p></div>
      <div class="agent-card"><div class="agent-card-head"><h4>Other details</h4><button class="agent-rerun-btn" data-agent="other_details_analysis">Re-run</button></div><p id="agentStatus-other_details_analysis">—</p></div>
    </div>
  </div>
  <div id="analysisResultsWrap"></div>
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
  var pendingWardrobeItemId = "";      // set by "Select from wardrobe" picker
  var pendingWardrobeImageUrl = "";    // wardrobe item image for the chat bubble
  var pendingWishlistProductId = "";   // set by "Select from wishlist" picker
  var pendingWishlistImageUrl = "";    // wishlist item image for the chat bubble
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
  // Discovery surface elements (Phase 15)
  var discoveryInput = document.getElementById("discoveryInput");
  var discoverySend = document.getElementById("discoverySend");
  var discoveryTop = document.getElementById("discoveryTop");
  var discoveryThinking = document.getElementById("discoveryThinking");
  var discoveryResultArea = document.getElementById("discoveryResultArea");
  var discoveryFollowups = document.getElementById("discoveryFollowups");
  var recentIntentsArea = document.getElementById("recentIntents");
  var feedWelcome = document.getElementById("feedWelcome");
  var stageBar = discoveryThinking;
  var messageEl = discoveryInput;
  var sendBtn = discoverySend;
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
  var wStatCount = document.getElementById("wStatCount");
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
    if (source === "wardrobe") return "YOURS";
    if (source === "catalog") return "SHOP";
    if (source === "hybrid") return "HYBRID";
    return "FOR YOU";
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
  // recognized by lines starting with bullet glyphs. Paragraph breaks
  // are blank lines (double newline). The result is a DocumentFragment
  // of paragraph and unordered-list nodes, all created via textContent
  // so user-provided text is escaped automatically (no XSS risk).
  //
  // The StyleAdvisor and explanation_request handlers return a flat
  // string with prose then a blank line then bulleted lines. Without
  // this parser the chat bubble default white-space rule collapses the
  // newlines and the bullets read as a single concatenated sentence.
  // With the parser we get a semantic p and ul tree.
  function renderAssistantMarkup(text) {{
    var frag = document.createDocumentFragment();
    if (!text) return frag;
    var normalized = String(text).replace(/\\r\\n/g, "\\n");
    var blocks = normalized.split(/\\n\\n+/);
    for (var bi = 0; bi < blocks.length; bi++) {{
      var block = blocks[bi].trim();
      if (!block) continue;
      var lines = block.split("\\n");
      var isBulletList = lines.length > 0 && lines.every(function(line) {{
        return /^\\s*[•\\-*]\\s+/.test(line);
      }});
      if (isBulletList) {{
        var ul = document.createElement("ul");
        for (var li = 0; li < lines.length; li++) {{
          var item = document.createElement("li");
          item.textContent = lines[li].replace(/^\\s*[•\\-*]\\s+/, "").trim();
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
    pendingWardrobeItemId = "";
    pendingWardrobeImageUrl = "";
    pendingWishlistProductId = "";
    pendingWishlistImageUrl = "";
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
            // Send the wardrobe_item_id to the backend instead of re-
            // fetching the image as base64. The backend loads the existing
            // item directly — no re-enrichment, no duplicate wardrobe row.
            pendingWardrobeItemId = item.id || "";
            pendingWardrobeImageUrl = imgUrl || "";
            console.log("[AURA] Wardrobe picker: id =", pendingWardrobeItemId, "img =", pendingWardrobeImageUrl, "title =", item.title);
            // Show the wardrobe item's image as a preview chip so the
            // user sees what they selected, but DON'T set pendingImageData
            // (that would trigger a full re-upload on the backend).
            if (imgUrl) {{
              imageChipImg.src = imgUrl;
              imageChipImg.onerror = function() {{ this.style.display = "none"; }};
              imageChipImg.style.display = "";
              imageChipName.textContent = item.title || "Wardrobe item";
              imageChip.classList.add("visible");
            }}
            // Only set the default message if the user hasn't typed
            // anything yet. Don't overwrite their custom query.
            if (!messageEl.value.trim()) {{
              messageEl.value = "What goes with my " + (item.title || "wardrobe item") + "?";
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

  // ── Wishlist picker (same pattern as wardrobe picker) ──
  var selectWishlistBtn = document.getElementById("selectWishlistBtn");
  if (selectWishlistBtn) {{
    selectWishlistBtn.addEventListener("click", function() {{
      plusPopover.classList.remove("open");
      openWishlistPicker();
    }});
  }}

  function openWishlistPicker() {{
    // Reuse the wardrobe picker modal structure for the wishlist picker.
    // Swap the title and load wishlist items instead.
    if (wardrobePickerModal) {{
      wardrobePickerModal.classList.add("open");
      loadWishlistPickerItems();
    }}
  }}

  function loadWishlistPickerItems() {{
    if (!USER_ID) {{ wardrobePickerGrid.innerHTML = '<div class="modal-empty">No user ID.</div>'; return; }}
    wardrobePickerGrid.innerHTML = '<div class="modal-empty">Loading wishlist...</div>';
    fetch("/v1/users/" + encodeURIComponent(USER_ID) + "/wishlist")
      .then(function(r) {{ return r.json(); }})
      .then(function(data) {{
        var items = data.items || [];
        if (!items.length) {{
          wardrobePickerGrid.innerHTML = '<div class="modal-empty">No wishlisted items yet. Tap the heart on outfit cards to save items.</div>';
          return;
        }}
        wardrobePickerGrid.innerHTML = "";
        items.forEach(function(item) {{
          var imgUrl = item.image_url || "";
          var el = document.createElement("div");
          el.className = "modal-item";
          el.innerHTML = (imgUrl ? '<img src="' + escapeHtml(imgUrl) + '" alt="' + escapeHtml(item.title || "Item") + '" loading="lazy" />' : '<div style="aspect-ratio:3/4;background:var(--surface-alt);display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:12px;">No image</div>') +
            '<div class="label">' + escapeHtml(item.title || "Wishlist Item") + '</div>' +
            (item.price ? '<div class="label" style="color:var(--accent);font-weight:700;">Rs. ' + escapeHtml(item.price) + '</div>' : '');
          el.addEventListener("click", function() {{
            pendingWishlistProductId = item.product_id || "";
            pendingWishlistImageUrl = imgUrl || "";
            console.log("[AURA] Wishlist picker: product_id =", pendingWishlistProductId, "title =", item.title);
            if (imgUrl) {{
              imageChipImg.src = imgUrl;
              imageChipImg.onerror = function() {{ this.style.display = "none"; }};
              imageChipImg.style.display = "";
              imageChipName.textContent = item.title || "Wishlist item";
              imageChip.classList.add("visible");
            }}
            if (!messageEl.value.trim()) {{
              messageEl.value = "Should I buy this " + (item.title || "item") + "?";
            }}
            wardrobePickerModal.classList.remove("open");
            messageEl.focus();
          }});
          wardrobePickerGrid.appendChild(el);
        }});
      }})
      .catch(function() {{
        wardrobePickerGrid.innerHTML = '<div class="modal-empty">Failed to load wishlist.</div>';
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

    // Top row: title (left) + like/dislike icons (right)
    var headerTop = document.createElement("div");
    headerTop.className = "outfit-header-top";
    var titleEl = document.createElement("div");
    titleEl.className = "outfit-title";
    titleEl.textContent = outfit.title || "Styled Look";
    headerTop.appendChild(titleEl);
    var fbWrap = document.createElement("div");
    fbWrap.className = "outfit-feedback";
    var isLiked = !!outfit._liked;
    var likeBtn = document.createElement("button"); likeBtn.className = "fb-icon-btn fb-like"; likeBtn.title = "Like";
    if (isLiked) {{
      likeBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="var(--accent)" stroke="var(--accent)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z"/></svg>';
      likeBtn.style.color = "var(--accent)";
    }} else {{
      likeBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z"/></svg>';
    }}
    var dislikeBtn = document.createElement("button"); dislikeBtn.className = "fb-icon-btn fb-dislike"; dislikeBtn.title = "Hide this";
    dislikeBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/><path d="M14.12 14.12a3 3 0 11-4.24-4.24"/></svg>';
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
      var html = '';
      html += '<span class="outfit-product-title">' + escapeHtml(pTitle) + '</span>';
      if (isWardrobe) {{
        // no price row for wardrobe items
      }} else if (hasPrice) {{
        // Clean price: strip "Rs." prefix, remove trailing ".0", add comma separator
        var cleanPrice = priceStr.replace(/^Rs\.?\s*/i, "").replace(/\.0+$/, "");
        cleanPrice = cleanPrice.replace(/\B(?=(\d{{3}})+(?!\d))/g, ",");
        html += '<span class="product-price">Rs. ' + escapeHtml(cleanPrice) + '</span>';
      }}
      var productId = item.product_id || "";
      if (!isWardrobe) {{
        html += '<div class="product-cta">';
        if (hasBuyLink) html += '<a href="' + escapeHtml(url) + '" target="_blank" rel="noreferrer" class="btn-buy">Buy now</a>';
        html += '<button type="button" class="btn-wishlist" data-product-id="' + escapeHtml(productId) + '" title="Save">Save</button>';
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
    var W = 280, H = 300, dpr = window.devicePixelRatio || 1;
    polarCanvas.width = W * dpr; polarCanvas.height = H * dpr;
    polarCanvas.style.width = W + "px"; polarCanvas.style.height = H + "px";
    radarDiv.appendChild(polarCanvas);
    // Toggle button — "See profile" / "Hide profile"
    var radarToggle = document.createElement("button");
    radarToggle.className = "radar-toggle";
    radarToggle.type = "button";
    radarToggle.textContent = "See profile";
    radarToggle.addEventListener("click", function() {{
      var isOpen = radarDiv.classList.toggle("open");
      radarToggle.textContent = isOpen ? "Hide profile" : "See profile";
    }});
    info.appendChild(radarToggle);
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
    var pMaxR = 62;      // outer ring radius (compact)
    var pLabelR = 86;    // single-ring axis label radius
    var pMaxValue = 100;

    // Read Confident Luxe tokens for archetype (champagne) + criteria (oxblood)
    // and the grid ink channel. Using live CSS vars so light/dark mode flip
    // automatically without re-rendering. Declared BEFORE first use to avoid
    // var-hoisting undefined reads (the grid ring code below uses --ink-rgb
    // and the drawProfile calls below use --signal-rgb / --accent-rgb).
    var rootStyle = getComputedStyle(document.documentElement);
    var gridInkRgb = (rootStyle.getPropertyValue("--ink-rgb") || "22, 17, 14").trim();
    var signalRgb = (rootStyle.getPropertyValue("--signal-rgb") || "198, 161, 91").trim();
    var accentRgb = (rootStyle.getPropertyValue("--accent-rgb") || "92, 26, 27").trim();
    var signalStroke = "rgb(" + signalRgb + ")";
    var signalFill = "rgba(" + signalRgb + ", 0.28)";
    var accentStroke = "rgb(" + accentRgb + ")";
    var accentFill = "rgba(" + accentRgb + ", 0.22)";

    // ── Grid rings (4 concentric circles at 25/50/75/100) ──
    pCtx.strokeStyle = "rgba(" + gridInkRgb + ", 0.14)";
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
    pCtx.strokeStyle = "rgba(" + gridInkRgb + ", 0.22)";
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

    // (Champagne / oxblood stroke + fill values were resolved above, before
    // the grid rings, so drawProfile below can use them directly.)

    // ── Top semicircle: style archetypes (always 8 axes) — champagne ──
    drawProfile(
      archetypes,
      archetypeValues,
      signalStroke,                    // stroke + label colour (--signal)
      signalFill,                      // fill
      Math.PI,                         // start at 9 o'clock
      Math.PI                          // span the top semicircle
    );

    // ── Bottom semicircle: filtered evaluation criteria — oxblood ──
    if (hasCriteriaData) {{
      drawProfile(
        criteria,
        criteriaValues,
        accentStroke,                  // stroke + label colour (--accent)
        accentFill,                    // fill
        0,                             // start at 3 o'clock
        Math.PI                        // span the bottom semicircle
      );
    }}

    // No legend — the axis labels are already color-coded (purple
    // archetypes on top, burgundy fit dimensions on bottom) so a
    // separate caption underneath would be redundant. Removing it
    // also frees a few pixels of vertical room inside the
    // .outfit-info column.

    // ── Feedback: like in header, dislike opens a modal overlay ──
    var outfitRank = outfit.rank || 0;
    var itemIds = items.map(function(i) {{ return i.product_id || ""; }}).filter(Boolean);

    // Build the dislike feedback modal (appended to document.body)
    var fbOverlay = document.createElement("div");
    fbOverlay.className = "feedback-modal-overlay";
    var fbModal = document.createElement("div");
    fbModal.className = "feedback-modal";
    fbModal.innerHTML = '<h3>What would you change?</h3>';
    var reactionRow = document.createElement("div");
    reactionRow.className = "reaction-row";
    reactionRow.style.display = "flex";
    var ta = document.createElement("textarea");
    ta.placeholder = "Tell me what felt off.";
    ["Too much", "Not me", "Weird pairing"].forEach(function(label) {{
      var chip = document.createElement("button"); chip.type = "button"; chip.className = "reaction-chip"; chip.textContent = label;
      chip.addEventListener("click", function() {{
        chip.classList.toggle("selected");
        var selected = [];
        reactionRow.querySelectorAll(".reaction-chip.selected").forEach(function(c) {{ selected.push(c.textContent); }});
        ta.value = selected.join(", ");
      }});
      reactionRow.appendChild(chip);
    }});
    fbModal.appendChild(reactionRow);
    fbModal.appendChild(ta);
    var fbActions = document.createElement("div");
    fbActions.className = "dislike-actions";
    var submitBtn = document.createElement("button"); submitBtn.textContent = "Submit";
    var cancelBtn = document.createElement("button"); cancelBtn.className = "secondary"; cancelBtn.textContent = "Cancel";
    fbActions.appendChild(submitBtn); fbActions.appendChild(cancelBtn);
    fbModal.appendChild(fbActions);
    var fbStatus = document.createElement("div");
    fbStatus.className = "feedback-status";
    fbModal.appendChild(fbStatus);
    fbOverlay.appendChild(fbModal);
    document.body.appendChild(fbOverlay);

    // Close on backdrop click
    fbOverlay.addEventListener("click", function(e) {{
      if (e.target === fbOverlay) {{ fbOverlay.classList.remove("open"); }}
    }});

    // Wire buttons
    var outfitTurnId = outfit._turn_id || "";
    var outfitConvId = outfit._conv_id || convId;
    likeBtn.onclick = function(e) {{
      e.stopPropagation();
      likeBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="var(--accent)" stroke="var(--accent)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z"/></svg>';
      likeBtn.style.color = "var(--accent)";
      sendFeedback(outfitConvId, outfitRank, "like", "", itemIds, fbStatus, fbWrap, fbOverlay, outfitTurnId);
    }};
    dislikeBtn.onclick = function(e) {{
      e.stopPropagation();
      console.log("[AURA] dislike clicked, opening modal");
      fbOverlay.classList.add("open");
    }};
    cancelBtn.addEventListener("click", function() {{
      fbOverlay.classList.remove("open");
      ta.value = "";
      reactionRow.querySelectorAll(".selected").forEach(function(c) {{ c.classList.remove("selected"); }});
    }});
    submitBtn.addEventListener("click", function() {{
      sendFeedback(outfitConvId, outfitRank, "dislike", ta.value.trim(), itemIds, fbStatus, fbWrap, fbOverlay, outfitTurnId);
      setTimeout(function() {{
        fbOverlay.classList.remove("open");
        // Remove this outfit from the carousel and advance
        var slot = card.parentNode;
        if (slot && slot._outfits && slot._showIdx) {{
          // Find and remove from the outfits array
          for (var ri = 0; ri < slot._outfits.length; ri++) {{
            if (slot._outfits[ri].rank === outfit.rank && slot._outfits[ri].title === outfit.title) {{
              slot._outfits.splice(ri, 1);
              break;
            }}
          }}
          // Update the counter
          var ctr = slot.parentNode ? slot.parentNode.querySelector(".carousel-counter") : null;
          if (slot._outfits.length > 0) {{
            // Show next, or last if we were at the end
            var cur = ctr ? parseInt(ctr.textContent) - 1 : 0;
            var nextIdx = cur < slot._outfits.length ? cur : slot._outfits.length - 1;
            slot._showIdx(nextIdx, true);
          }} else {{
            // All outfits hidden — remove the entire section
            var sectionEl = slot.parentNode;
            while (sectionEl && !sectionEl.hasAttribute("data-intent-section")) sectionEl = sectionEl.parentNode;
            if (sectionEl) sectionEl.remove();
          }}
        }}
      }}, 600);
    }});

    // 3-column grid: header spans all, then thumbs | hero | info
    card.appendChild(header);
    card.appendChild(thumbs);
    card.appendChild(heroWrap);
    card.appendChild(info);
    return card;
  }}

  // ══════════════════════════════════════════════
  // FEEDBACK
  // ══════════════════════════════════════════════

  async function sendFeedback(convId, outfitRank, eventType, notes, itemIds, statusEl, fbWrap, dislikeForm, turnId) {{
    statusEl.textContent = "Sending...";
    statusEl.className = "feedback-status";
    try {{
      var payload = {{ outfit_rank: outfitRank, event_type: eventType, notes: notes, item_ids: itemIds }};
      if (turnId) payload.turn_id = turnId;
      var res = await fetch("/v1/conversations/" + convId + "/feedback", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload),
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
      var title = document.createElement("strong");
      title.textContent = String(g.label || "").toUpperCase();
      var row = document.createElement("div"); row.className = "followup-row";
      g.items.forEach(function(text) {{
        var btn = document.createElement("button");
        btn.className = "followup-chip";
        btn.type = "button";
        btn.textContent = text;
        btn.addEventListener("click", function() {{ messageEl.value = text; wrap.remove(); send(); }});
        row.appendChild(btn);
      }});
      section.appendChild(title); section.appendChild(row); wrap.appendChild(section);
    }});
    feed.appendChild(wrap);
    feed.scrollTop = feed.scrollHeight;
  }}

  // Return all stages that have a non-empty, human-facing message.
  // Deliberately filters out stages whose template resolved to an empty
  // string — those are intent-signalled "don't show this" events
  // (e.g. user_context_completed, outfit_assembly_completed).
  function visibleStages(stages) {{
    if (!stages || !stages.length) return [];
    var out = [];
    for (var i = 0; i < stages.length; i++) {{
      var s = stages[i];
      var msg = s && s.message;
      if (msg && String(msg).trim()) out.push(s);
    }}
    return out;
  }}

  function renderStages(stages) {{
    var visible = visibleStages(stages);
    var latest = visible.length ? visible[visible.length - 1] : null;
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
    // Single in-place "thinking" bubble per turn. Advances through stages
    // ONE AT A TIME so the user sees every step — not just the long-running
    // outfit_architect call, which previously dominated the screen because
    // it's the only stage still running when polls fire. Each visible stage
    // gets at least one poll-tick of dwell time (400ms).
    var thinkingBubble = null;
    var lastStageText = "";
    var shownIdx = -1;      // index in visibleStages() we're currently showing
    var POLL_INTERVAL = 400;
    try {{
      while (true) {{
        var res = await fetch("/v1/conversations/" + convId + "/turns/" + jobId + "/status");
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Polling failed");
        var stages = data.stages || [];
        var visible = visibleStages(stages);
        // Advance one step per poll so earlier stages always get a tick.
        // If new stages have arrived, we catch up by one; if we've caught
        // up to the end, we stay on the latest.
        if (visible.length > 0) {{
          if (shownIdx < visible.length - 1) shownIdx += 1;
          var target = visible[shownIdx];
          var targetMsg = target ? target.message : "";
          stageBar.textContent = targetMsg;
          if (targetMsg && targetMsg !== lastStageText) {{
            if (!thinkingBubble) {{
              thinkingBubble = addAgentBubble(targetMsg);
            }} else if (thinkingBubble.lastChild) {{
              // The bubble contains [dot, textNode]. Update the text node only.
              thinkingBubble.lastChild.textContent = targetMsg;
              feed.scrollTop = feed.scrollHeight;
            }} else {{
              thinkingBubble.appendChild(document.createTextNode(targetMsg));
              feed.scrollTop = feed.scrollHeight;
            }}
            lastStageText = targetMsg;
          }}
        }}
        if (data.status === "completed") {{
          // Flush any remaining stages the user hasn't seen yet before
          // fading the bubble — one quick burst so the final lines flash.
          if (visible.length > 0 && shownIdx < visible.length - 1) {{
            var finalMsg = visible[visible.length - 1].message;
            if (finalMsg && finalMsg !== lastStageText && thinkingBubble && thinkingBubble.lastChild) {{
              thinkingBubble.lastChild.textContent = finalMsg;
              lastStageText = finalMsg;
            }}
          }}
          fadeOutThinkingBubble(thinkingBubble);
          stageBar.textContent = "";
          return data.result;
        }}
        if (data.status === "failed") throw new Error(data.error || "Turn failed");
        await new Promise(function(resolve) {{ setTimeout(resolve, POLL_INTERVAL); }});
      }}
    }} catch (exc) {{
      fadeOutThinkingBubble(thinkingBubble);
      stageBar.textContent = "";
      throw exc;
    }}
  }}

  // ══════════════════════════════════════════════
  // PDP CAROUSEL RENDERER (Phase 15)
  // ══════════════════════════════════════════════

  function renderPdpCarousel(outfits, convId, responseMetadata, container, onSlideChange) {{
    if (!outfits || !outfits.length) return;
    container.innerHTML = "";

    var currentIdx = 0;

    // Carousel header: turn summary (left) + counter + arrows (right)
    var headerRow = document.createElement("div");
    headerRow.className = "carousel-header";
    var summarySpan = document.createElement("span");
    summarySpan.className = "turn-summary";
    summarySpan.textContent = (outfits[0] && outfits[0]._turn_context) || "";
    headerRow.appendChild(summarySpan);

    var counter = null;
    var prevBtn = null;
    var nextBtn = null;
    if (outfits.length > 1) {{
      counter = document.createElement("span");
      counter.className = "carousel-counter";
      counter.textContent = "1 / " + outfits.length;
      headerRow.appendChild(counter);
      var nav = document.createElement("div");
      nav.className = "carousel-nav";
      prevBtn = document.createElement("button"); prevBtn.innerHTML = "&#8592;"; prevBtn.title = "Previous";
      nextBtn = document.createElement("button"); nextBtn.innerHTML = "&#8594;"; nextBtn.title = "Next";
      nav.appendChild(prevBtn); nav.appendChild(nextBtn);
      headerRow.appendChild(nav);
    }}
    container.appendChild(headerRow);

    var carouselSlot = document.createElement("div");
    carouselSlot.className = "pdp-carousel";
    container.appendChild(carouselSlot);

    var _myOverlay = null;
    // Build and show only one card at a time — avoids canvas/display:none issues
    function showIdx(idx, isNav) {{
      // Only clean up THIS carousel's overlay on navigation, not all overlays on the page
      if (isNav && _myOverlay && _myOverlay.parentNode) {{ _myOverlay.remove(); _myOverlay = null; }}
      carouselSlot.innerHTML = "";
      var card = buildOutfitCard(outfits[idx], convId, responseMetadata || {{}});
      carouselSlot.appendChild(card);
      // Track the modal overlay so we can clean up only ours on nav
      var overlay = document.body.querySelector(".feedback-modal-overlay:last-child");
      if (overlay) _myOverlay = overlay;
      currentIdx = idx;
      if (counter) counter.textContent = (idx + 1) + " / " + outfits.length;
      summarySpan.textContent = (outfits[idx] && outfits[idx]._turn_context) || summarySpan.textContent;
      if (typeof onSlideChange === "function") onSlideChange(idx);
    }}

    // Attach to the slot element so buildOutfitCard can access them
    carouselSlot._outfits = outfits;
    carouselSlot._showIdx = showIdx;
    showIdx(0, false);

    if (outfits.length > 1) {{
      prevBtn.addEventListener("click", function() {{ if (currentIdx > 0) showIdx(currentIdx - 1, true); }});
      nextBtn.addEventListener("click", function() {{ if (currentIdx < outfits.length - 1) showIdx(currentIdx + 1, true); }});
    }}
  }}

  function renderDiscoveryFollowups(suggestions, structuredGroups, container) {{
    container.innerHTML = "";
    if ((!suggestions || !suggestions.length) && (!structuredGroups || !structuredGroups.length)) return;
    var wrap = document.createElement("div");
    wrap.className = "followup-groups";
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
      var title = document.createElement("strong");
      title.textContent = String(g.label || "").toUpperCase();
      var row = document.createElement("div"); row.className = "followup-row";
      g.items.forEach(function(text) {{
        var btn = document.createElement("button");
        btn.className = "followup-chip";
        btn.type = "button";
        btn.textContent = text;
        btn.addEventListener("click", function() {{ messageEl.value = text; container.innerHTML = ""; send(); }});
        row.appendChild(btn);
      }});
      section.appendChild(title); section.appendChild(row); wrap.appendChild(section);
    }});
    container.appendChild(wrap);
  }}

  // ══════════════════════════════════════════════
  // RECENT INTENT GROUPS (Home page bottom)
  // ══════════════════════════════════════════════

  async function loadRecentIntents() {{
    if (!USER_ID || !recentIntentsArea) return;
    try {{
      var res = await fetch("/v1/users/" + encodeURIComponent(USER_ID) + "/intent-history");
      var data = await res.json();
      if (!res.ok || !data.groups || !data.groups.length) {{
        recentIntentsArea.innerHTML = "";
        return;
      }}
      var html = '<div class="recent-intents-label">Recent</div><div class="recent-grid">';
      data.groups.forEach(function(g) {{
        var img = g.first_image
          ? '<img src="' + escapeHtml(g.first_image) + '" alt="" loading="lazy" />'
          : "";
        var intentLabel = (g.intent || "styled look").replace(/_/g, " ").toUpperCase();
        var summary = g.turns && g.turns.length ? g.turns[0].user_message : "";
        html += '<div class="recent-card" data-conv="' + escapeHtml(g.conversation_id) + '">' +
          '<div class="recent-card-img">' + img + '</div>' +
          '<div class="recent-card-body">' +
            '<div class="rc-context">' + escapeHtml(g.context_summary || intentLabel) + '</div>' +
            '<div class="rc-summary">' + escapeHtml(summary) + '</div>' +
            '<div class="rc-meta">' + escapeHtml(g.turn_count + (g.turn_count === 1 ? " look" : " looks") + " · " + relativeTime(g.updated_at)) + '</div>' +
          '</div></div>';
      }});
      html += '</div>';
      recentIntentsArea.innerHTML = html;
      // Click a recent card → navigate to Outfits tab
      recentIntentsArea.querySelectorAll(".recent-card").forEach(function(card) {{
        card.addEventListener("click", function() {{
          window.location.href = "/?user=" + encodeURIComponent(USER_ID) + "&view=outfits";
        }});
      }});
    }} catch (_) {{
      recentIntentsArea.innerHTML = "";
    }}
  }}

  // ══════════════════════════════════════════════
  // SEND — Discovery surface flow (Phase 15)
  // ══════════════════════════════════════════════

  async function send() {{
    err.textContent = "";
    var message = messageEl.value.trim();
    if (!USER_ID) {{ err.textContent = "No user session. Please log in."; return; }}
    if (!message && !pendingImageData && !pendingWardrobeItemId && !pendingWishlistProductId) {{ return; }}
    if (!message && pendingImageData) {{ message = "What goes with this? Show me pairing options."; }}
    if (!message && pendingWardrobeItemId) {{ message = "What goes with this wardrobe item?"; }}
    if (!message && pendingWishlistProductId) {{ message = "Should I buy this?"; }}

    sendBtn.disabled = true;
    messageEl.disabled = true;
    // Collapse the discovery top to make room for results
    if (discoveryTop) discoveryTop.classList.add("has-result");
    if (discoveryResultArea) discoveryResultArea.innerHTML = "";
    if (discoveryFollowups) discoveryFollowups.innerHTML = "";

    try {{
      var convId = await ensureConversation();
      var attachedImage = pendingImageData;
      var attachedWardrobeItemId = pendingWardrobeItemId;
      var attachedWishlistProductId = pendingWishlistProductId;
      console.log("[AURA] Send: image =", !!attachedImage, "wardrobe =", attachedWardrobeItemId, "wishlist =", attachedWishlistProductId);
      messageEl.value = "";
      clearImagePreview();
      var payload = {{ user_id: USER_ID, message: message }};
      if (attachedImage) payload.image_data = attachedImage;
      if (attachedWardrobeItemId && !attachedImage) payload.wardrobe_item_id = attachedWardrobeItemId;
      if (attachedWishlistProductId && !attachedImage && !attachedWardrobeItemId) payload.wishlist_product_id = attachedWishlistProductId;

      var res = await fetch("/v1/conversations/" + convId + "/turns/start", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload),
      }});
      var job = await res.json();
      if (!res.ok) throw new Error(job.detail || "Failed to start turn");
      var result = await pollJob(convId, job.job_id);

      // Render the result as a PDP carousel (not chat bubbles)
      var outfits = result.outfits || [];
      var __md = result.metadata || {{}};
      var __groups = (__md && __md.follow_up_groups) || [];

      if (outfits.length && discoveryResultArea) {{
        // Context summary
        var occasion = __md.occasion || "";
        var source = __md.answer_source || "";
        var contextParts = [];
        if (occasion) contextParts.push(occasion.replace(/_/g, " "));
        if (source) contextParts.push(source.replace(/_/g, " "));
        contextParts.push(outfits.length + (outfits.length === 1 ? " look" : " looks"));
        var ctxEl = document.createElement("div");
        ctxEl.className = "result-context";
        ctxEl.textContent = contextParts.join(" · ");
        discoveryResultArea.appendChild(ctxEl);

        renderPdpCarousel(outfits, convId, __md, discoveryResultArea);
      }} else if (result.assistant_message) {{
        // No outfits — show the text response (clarification, direct answer)
        var textBlock = document.createElement("div");
        textBlock.style.cssText = "max-width:680px;margin:0 auto;padding:16px 4px;font-size:15px;line-height:1.65;color:var(--ink);";
        textBlock.appendChild(renderAssistantMarkup(result.assistant_message));
        discoveryResultArea.appendChild(textBlock);
      }}

      // Follow-up chips
      if (discoveryFollowups) {{
        renderDiscoveryFollowups(result.follow_up_suggestions || [], __groups, discoveryFollowups);
      }}

      // Refresh recent intents
      loadRecentIntents();

    }} catch (e) {{
      err.textContent = e.message || String(e);
    }} finally {{
      sendBtn.disabled = false;
      messageEl.disabled = false;
      messageEl.focus();
    }}
  }}

  // Wire the discovery send button + Enter key
  if (discoverySend) discoverySend.addEventListener("click", send);
  if (discoveryInput) {{
    discoveryInput.addEventListener("keydown", function(e) {{
      if (e.key === "Enter" && !e.shiftKey) {{
        e.preventDefault();
        send();
      }}
    }});
  }}

  // Welcome prompts
  document.querySelectorAll(".welcome-prompt").forEach(function(btn) {{
    btn.addEventListener("click", function() {{
      messageEl.value = btn.getAttribute("data-prompt") || btn.textContent;
      messageEl.focus();
      send();
    }});
  }});

  // Theme toggle — lives in the profile dossier, persists to localStorage
  function currentTheme() {{
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }}
  function syncThemeToggleLabel() {{
    var btn = document.getElementById("themeToggle");
    if (!btn) return;
    btn.textContent = currentTheme() === "dark" ? "Flip to light" : "Flip to dark";
  }}
  var themeToggleBtn = document.getElementById("themeToggle");
  if (themeToggleBtn) {{
    syncThemeToggleLabel();
    themeToggleBtn.addEventListener("click", function() {{
      var next = currentTheme() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try {{ localStorage.setItem("aura_theme", next); }} catch (_) {{}}
      syncThemeToggleLabel();
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
      if (!res.ok) {{
        console.warn("[AURA] loadConversation: fetch failed", res.status, data);
        return;
      }}
      var turns = data.turns || [];
      console.log("[AURA] loadConversation", {{ convId: convId, turn_count: turns.length }});
      for (var i = 0; i < turns.length; i++) {{
        var t = turns[i];
        if (t.user_message) addBubble(t.user_message, "user");
        if (t.assistant_message) {{
          addBubble(t.assistant_message, "assistant");
          // Render outfits from resolved context
          var ctx = t.resolved_context || {{}};
          var outfits = ctx.outfits || [];
          console.log("[AURA] turn " + i, {{
            has_resolved_context: !!t.resolved_context,
            resolved_context_keys: t.resolved_context ? Object.keys(t.resolved_context) : [],
            outfit_count: outfits.length,
            first_outfit_title: outfits[0] && outfits[0].title,
          }});
          if (outfits.length) {{
            try {{
              renderOutfits(outfits, convId, ctx);
            }} catch (exc) {{
              console.error("[AURA] renderOutfits threw for turn " + i, exc);
            }}
          }}
        }}
      }}
    }} catch (exc) {{
      console.error("[AURA] loadConversation threw", exc);
    }}
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
      var rawTags = [item.garment_category, item.primary_color, item.formality_level || item.occasion_fit].filter(Boolean).slice(0, 3);
      var tags = rawTags.map(function(t) {{ return String(t).replace(/_/g, " "); }});
      var title = item.title || "Wardrobe Item";
      var imageHtml = imageUrl
        ? '<img src="' + escapeHtml(imageUrl) + '" alt="' + escapeHtml(title) + '" loading="lazy" />'
        : '<div class="closet-placeholder">Saved Piece</div>';
      return '<article class="closet-card">' +
        '<div class="closet-image">' + imageHtml + '</div>' +
        '<div class="closet-body">' +
          '<h3>' + escapeHtml(title) + '</h3>' +
          '<div class="tag-row">' + (tags.length ? tags.map(function(tag) {{ return '<span class="tag">' + escapeHtml(tag) + '</span>'; }}).join("") : '') + '</div>' +
          '<div class="closet-actions">' +
            '<button class="studio-btn primary" type="button" data-wardrobe-prompt="' + escapeHtml("Style my " + title + " from my wardrobe.") + '" data-wardrobe-img="' + escapeHtml(imageUrl || "") + '">Style This</button>' +
            '<button class="studio-btn" type="button" data-action="edit" data-item-id="' + escapeHtml(item.id) + '">Edit</button>' +
            '<button class="studio-btn danger icon-only" type="button" data-action="delete" data-item-id="' + escapeHtml(item.id) + '">&#128465;</button>' +
          '</div>' +
        '</div></article>';
    }}).join("");
  }}

  async function loadWardrobeStudio() {{
    if (!USER_ID) {{ return; }}
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
      if (wStatCount) wStatCount.textContent = String(wardrobeItems.length);
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
    resultsGrid.innerHTML = '<div class="results-empty">Loading.</div>';
    try {{
      var res = await fetch("/v1/users/" + encodeURIComponent(USER_ID) + "/results");
      var data = await res.json();
      if (!res.ok) throw new Error("Failed");
      allResults = data.results || [];
      renderResults();
    }} catch (_) {{
      resultsGrid.innerHTML = '<div class="results-empty">Couldn\\'t load your lookbook.</div>';
    }}
  }}

  var INTENT_LABEL = {{
    "occasion_recommendation": "Outfit",
    "outfit_check": "Check",
    "pairing_request": "Pairing",
    "capsule_or_trip_planning": "Trip",
    "shopping_decision": "Verdict",
    "style_advice": "Advice"
  }};

  function sourceForResult(r) {{
    var s = (r && r.source) || "";
    if (s.indexOf("wardrobe") !== -1 && s.indexOf("catalog") !== -1) return "hybrid";
    if (s.indexOf("wardrobe") !== -1) return "wardrobe";
    if (s.indexOf("catalog") !== -1) return "catalog";
    return "";
  }}

  function renderResults() {{
    var filtered = allResults.filter(function(r) {{
      if (activeResultTab !== "all" && r.intent !== activeResultTab) return false;
      if (activeResultSource !== "all" && r.source && r.source.indexOf(activeResultSource) === -1) return false;
      return true;
    }});
    if (!filtered.length) {{
      resultsGrid.innerHTML = '<div class="results-empty">Nothing saved yet. Let\\'s find something.</div>';
      return;
    }}
    resultsGrid.innerHTML = filtered.map(function(r) {{
      var thumbHtml = r.first_outfit_image
        ? '<img src="' + escapeHtml(r.first_outfit_image) + '" alt="" loading="lazy" />'
        : '<div class="thumb-placeholder">No preview</div>';
      var sourceKey = sourceForResult(r);
      var sourceLabel = sourceBadgeLabel(sourceKey);
      var intentKey = r.intent || "";
      var intentLabel = (INTENT_LABEL[intentKey] || intentKey.replace(/_/g, " ")).toUpperCase();
      return '<div class="result-card" data-conv="' + escapeHtml(r.conversation_id) + '">' +
        '<div class="thumb">' + thumbHtml + '</div>' +
        '<div class="body">' +
          (intentKey ? '<span class="source-mini-pill catalog">' + escapeHtml(intentLabel) + '</span>' : '') +
          (sourceKey ? '<span class="source-mini-pill ' + sourceKey + '">' + escapeHtml(sourceLabel) + '</span>' : '') +
          '<div class="msg">' + escapeHtml(r.user_message || "A styled look") + '</div>' +
          '<div class="meta-row">' +
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
      colorPaletteContent.innerHTML = '<div style="color:var(--ink-3);font-size:13px;font-style:italic;">Finish your analysis to see your colours.</div>';
      return;
    }}
    function chips(arr, cls) {{ return arr.map(function(c) {{ return '<span class="palette-chip ' + cls + '">' + escapeHtml(c) + '</span>'; }}).join(""); }}
    var html = "";
    if (base.length) html += '<div class="palette-section"><div class="palette-label">Base</div><div class="palette-chips">' + chips(base, "base") + '</div></div>';
    if (accent.length) html += '<div class="palette-section"><div class="palette-label">Accent</div><div class="palette-chips">' + chips(accent, "accent") + '</div></div>';
    if (avoid.length) html += '<div class="palette-section"><div class="palette-label">Avoid</div><div class="palette-chips">' + chips(avoid, "avoid") + '</div></div>';
    colorPaletteContent.innerHTML = html;
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

    // Style dossier adjective list — each value becomes an oversized
    // italic display line, one per row. Ordered by importance so the
    // strongest signals read first.
    var facts = [
      {{ label: "Primary Archetype", value: primary }},
      {{ label: "Secondary Archetype", value: secondary }},
      {{ label: "Seasonal Palette", value: seasonal }},
      {{ label: "Contrast Level", value: contrast }},
      {{ label: "Frame Structure", value: frame }},
      {{ label: "Body Shape", value: bodyShape }},
    ].filter(function(f) {{ return f.value; }});
    if (styleFacts) {{
      if (!facts.length) {{
        styleFacts.innerHTML = '<div class="style-fact"><div class="fact-value" style="font-size:22px;color:var(--ink-3);">Finish your analysis to unlock your style code.</div></div>';
      }} else {{
        styleFacts.innerHTML = facts.map(function(f) {{
          return '<div class="style-fact"><div class="fact-label">' + escapeHtml(f.label) + '</div><div class="fact-value">' + escapeHtml(f.value) + '</div></div>';
        }}).join("");
      }}
    }}
    // Short stylist-voice summary under the adjective list.
    if (styleSummary) {{
      if (primary || seasonal) {{
        var lensParts = [primary, secondary].filter(Boolean);
        var lens = lensParts.join(" meets ").toLowerCase();
        var seasonLine = seasonal ? ("Your palette lives in " + String(seasonal).toLowerCase() + ".") : "";
        var frameLine = frame ? (" Your frame reads " + String(frame).toLowerCase() + ".") : "";
        styleSummary.textContent = "I see you through a " + lens + " lens." + (seasonLine ? " " + seasonLine : "") + frameLine;
      }} else {{
        styleSummary.textContent = "Finish your analysis to unlock your full style code.";
      }}
    }}

    // Dossier hero — name + one-line style statement
    var nameEl = document.getElementById("dossierName");
    var statementEl = document.getElementById("dossierStatement");
    if (nameEl) {{
      var displayName = (profileData && (profileData.name || profileData.first_name)) || "";
      nameEl.textContent = displayName ? displayName : "Your dossier";
    }}
    if (statementEl) {{
      if (primary) {{
        statementEl.textContent = "A " + String(primary).toLowerCase() + " with " + String(seasonal || "an evolving").toLowerCase() + " colouring.";
      }} else {{
        statementEl.textContent = "A record of what we've learned about how you dress.";
      }}
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

  // Discovery surface — load recent intents on Home/Chat view
  if (ACTIVE_VIEW === "chat" || ACTIVE_VIEW === "home") {{
    loadRecentIntents();
    var urlParams = new URLSearchParams(window.location.search);
    var seedPrompt = urlParams.get("prompt") || "";
    if (seedPrompt) {{
      var cleanUrl = "/?user=" + encodeURIComponent(USER_ID) + "&view=home";
      window.history.replaceState(null, "", cleanUrl);
      messageEl.value = seedPrompt;
      send();
    }}
  }}

  // Outfits tab — intent-organized history
  if (ACTIVE_VIEW === "outfits") {{
    (async function() {{
      var area = document.getElementById("outfitsContent");
      if (!area) return;
      try {{
        var res = await fetch("/v1/users/" + encodeURIComponent(USER_ID) + "/intent-history?types=occasion_recommendation,pairing_request,capsule_or_trip_planning");
        var data = await res.json();
        if (!res.ok || !data.groups || !data.groups.length) {{
          area.innerHTML = '<div class="results-empty">Nothing styled yet.</div>';
          return;
        }}
        area.innerHTML = "";
        data.groups.forEach(function(g) {{
          var section = document.createElement("div");
          section.setAttribute("data-intent-section", "1");
          section.style.cssText = "margin-bottom:56px;";
          // Context header
          var header = document.createElement("div");
          header.style.cssText = "margin-bottom:20px;";
          var sectionTitle = document.createElement("h3");
          sectionTitle.style.cssText = "font-family:'Fraunces','Cormorant Garamond',Georgia,serif;font-size:28px;font-weight:400;font-style:italic;color:var(--ink);margin:0 0 4px;";
          var occasion = (g.occasion || g.intent || "styled look").replace(/_/g, " ");
          sectionTitle.textContent = occasion.charAt(0).toUpperCase() + occasion.slice(1);
          var sectionMeta = document.createElement("div");
          sectionMeta.style.cssText = "font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.14em;color:var(--ink-4);";
          sectionMeta.textContent = relativeTime(g.updated_at).toUpperCase();
          header.appendChild(sectionTitle);
          header.appendChild(sectionMeta);
          section.appendChild(header);
          // Flatten all turns' outfits into one carousel with per-card context
          var allOutfits = [];
          var outfitContexts = [];
          (g.turns || []).forEach(function(turn) {{
            (turn.outfits || []).forEach(function(outfit) {{
              outfit._turn_context = turn.user_message || "";
              outfit._turn_id = turn.turn_id || "";
              outfit._conv_id = turn.conversation_id || "";
              allOutfits.push(outfit);
              outfitContexts.push(turn.user_message || "");
            }});
          }});
          if (!allOutfits.length) return;
          var carouselWrap = document.createElement("div");
          carouselWrap.className = "discovery-result";
          carouselWrap.style.padding = "0 0 16px";
          renderPdpCarousel(allOutfits, g.conversation_id, {{}}, carouselWrap);
          section.appendChild(carouselWrap);
          area.appendChild(section);
        }});
      }} catch (_) {{
        area.innerHTML = '<div class="results-empty">Couldn\\'t load your outfits.</div>';
      }}
    }})();
  }}

  // Checks tab
  if (ACTIVE_VIEW === "checks") {{
    (async function() {{
      var area = document.getElementById("checksContent");
      if (!area) return;
      try {{
        var res = await fetch("/v1/users/" + encodeURIComponent(USER_ID) + "/intent-history?types=outfit_check");
        var data = await res.json();
        if (!res.ok || !data.groups || !data.groups.length) {{
          area.innerHTML = '<div class="results-empty">No outfit checks yet.</div>';
          return;
        }}
        area.innerHTML = "";
        data.groups.forEach(function(g) {{
          (g.turns || []).forEach(function(turn) {{
            var card = document.createElement("div");
            card.style.cssText = "border:1px solid var(--line);border-radius:var(--radius-md);padding:24px;margin-bottom:20px;background:var(--surface);";
            card.innerHTML = '<div style="font-size:13px;font-style:italic;color:var(--ink-3);margin-bottom:8px;">' + escapeHtml(turn.user_message || "Outfit check") + '</div>' +
              '<div style="font-size:15px;color:var(--ink);line-height:1.6;">' + escapeHtml(turn.assistant_summary || "") + '</div>' +
              '<div style="font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:0.14em;color:var(--ink-4);margin-top:12px;">' + escapeHtml(relativeTime(turn.created_at)) + '</div>';
            area.appendChild(card);
          }});
        }});
      }} catch (_) {{
        area.innerHTML = '<div class="results-empty">Couldn\\'t load checks.</div>';
      }}
    }})();
  }}

  // Load wardrobe view
  if (ACTIVE_VIEW === "wardrobe") {{
    loadWardrobeStudio();
  }}

  // Load results view (legacy — kept for backward compat with ?view=results URLs)
  if (ACTIVE_VIEW === "results") {{
    loadResults();
  }}

  // ── Wishlist page ──
  async function loadWishlist() {{
    var grid = document.getElementById("wishlistGrid");
    if (!grid) return;
    grid.innerHTML = '<div class="results-empty">Loading wishlist...</div>';
    try {{
      var res = await fetch("/v1/users/" + encodeURIComponent(USER_ID) + "/wishlist");
      var data = await res.json();
      var items = data.items || [];
      if (!items.length) {{
        grid.innerHTML = '<div class="results-empty">No wishlisted items yet. Tap the heart &#9825; on outfit cards to save garments you like.</div>';
        return;
      }}
      grid.innerHTML = "";
      items.forEach(function(item) {{
        var card = document.createElement("div");
        card.className = "closet-card";
        card.style.cssText = "border-radius:var(--radius-md); border:1px solid var(--line); overflow:hidden; background:var(--surface);";
        var imgUrl = item.image_url || "";
        var priceStr = item.price ? String(item.price).replace(/\\.0$/, "") : "";
        card.innerHTML = '<div class="closet-image" style="aspect-ratio:3/4; overflow:hidden; background:var(--surface-alt);">' +
          (imgUrl ? '<img src="' + escapeHtml(imgUrl) + '" alt="' + escapeHtml(item.title || "Item") + '" loading="lazy" style="width:100%; height:100%; object-fit:cover;" />' : '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:12px;">No image</div>') +
        '</div>' +
        '<div style="padding:12px 14px 14px; display:flex; flex-direction:column; gap:4px;">' +
          '<div style="font-size:13px; font-weight:600; color:var(--ink); line-height:1.35;">' + escapeHtml(item.title || "Untitled") + '</div>' +
          (priceStr ? '<div style="color:var(--accent); font-weight:700; font-size:14px;">Rs. ' + escapeHtml(priceStr) + '</div>' : '') +
          (item.garment_category ? '<div style="font-size:11px; color:var(--muted); text-transform:capitalize;">' + escapeHtml(item.garment_category.replace(/_/g, " ")) + (item.primary_color ? ' &middot; ' + escapeHtml(item.primary_color.replace(/_/g, " ")) : '') + '</div>' : '') +
          (item.product_url ? '<a href="' + escapeHtml(item.product_url) + '" target="_blank" style="display:inline-block; margin-top:6px; padding:6px 16px; font-size:12px; font-weight:600; color:var(--surface); background:var(--ink); border-radius:8px; text-decoration:none; text-align:center;">Buy Now</a>' : '') +
        '</div>';
        grid.appendChild(card);
      }});
    }} catch (_) {{
      grid.innerHTML = '<div class="results-empty">Failed to load wishlist.</div>';
    }}
  }}

  if (ACTIVE_VIEW === "wishlist") {{
    loadWishlist();
  }}

  // ── Trial Room page ──
  async function loadTryonGallery() {{
    var grid = document.getElementById("tryonGalleryGrid");
    if (!grid) return;
    grid.innerHTML = '<div class="results-empty">Loading trial room...</div>';
    try {{
      var res = await fetch("/v1/users/" + encodeURIComponent(USER_ID) + "/tryon-gallery");
      var data = await res.json();
      var items = data.items || [];
      if (!items.length) {{
        grid.innerHTML = '<div class="results-empty">No try-on renders yet. Chat with Aura and ask to try something on!</div>';
        return;
      }}
      grid.innerHTML = "";
      items.forEach(function(item) {{
        var card = document.createElement("div");
        card.className = "closet-card";
        card.style.cssText = "border-radius:var(--radius-md); border:1px solid var(--line); overflow:hidden; background:var(--surface); cursor:pointer; transition:border-color var(--dur-1) var(--ease);";
        var imgUrl = item.image_url || "";
        card.innerHTML = '<div style="aspect-ratio:2/3; overflow:hidden; background:var(--surface-alt); position:relative;">' +
          (imgUrl ? '<img src="' + escapeHtml(imgUrl) + '" alt="Try-on" loading="lazy" style="width:100%; height:100%; object-fit:cover; display:block;" />' : '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:12px;">No render</div>') +
          '<div style="position:absolute; bottom:0; left:0; right:0; padding:8px 12px; background:linear-gradient(transparent, rgba(0,0,0,0.5)); color:var(--on-accent); font-size:11px; font-weight:500;">' + relativeTime(item.created_at) + '</div>' +
        '</div>';
        card.addEventListener("mouseenter", function() {{ card.style.borderColor = "var(--line-strong)"; }});
        card.addEventListener("mouseleave", function() {{ card.style.borderColor = "var(--line)"; }});
        card.addEventListener("click", function() {{
          if (imgUrl) window.open(imgUrl, "_blank");
        }});
        grid.appendChild(card);
      }});
    }} catch (_) {{
      grid.innerHTML = '<div class="results-empty">Failed to load trial room.</div>';
    }}
  }}

  if (ACTIVE_VIEW === "trialroom") {{
    loadTryonGallery();
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
