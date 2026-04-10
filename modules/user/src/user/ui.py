from html import escape


def get_onboarding_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet" />
  <title>Sigma Aura Onboarding</title>
  <style>
    :root {
      --bg: #f6f0ea;
      --surface: rgba(255, 250, 245, 0.94);
      --surface-strong: #fffaf5;
      --ink: #201915;
      --muted: #6e655f;
      --line: #dfd1c4;
      --line-strong: #c8b8a6;
      --accent: #6f2f45;
      --accent-soft: #f3e6ea;
      --accent-warm: #b08a4e;
      --danger: #9b2323;
      --danger-bg: #fceeee;
      --shadow: 0 22px 60px rgba(54, 32, 24, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      height: 100vh;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
      overflow: hidden;
    }
    .shell {
      display: grid;
      grid-template-columns: 1fr 2fr;
      height: 100vh;
    }
    .sidebar {
      padding: 48px 36px;
      background:
        linear-gradient(180deg, rgba(111, 47, 69, 0.96) 0%, rgba(80, 30, 48, 0.98) 100%);
      color: #f6f2eb;
      display: flex;
      flex-direction: column;
      gap: 28px;
      overflow-y: auto;
    }
    .eyebrow {
      font-size: 12px;
      letter-spacing: 0.24em;
      text-transform: uppercase;
      opacity: 0.74;
    }
    .sidebar h1 {
      margin: 0;
      font-family: "Cormorant Garamond", serif;
      font-size: 42px;
      font-weight: 600;
      line-height: 1.06;
      letter-spacing: 0.01em;
    }
    .sidebar p {
      margin: 0;
      color: rgba(246, 242, 235, 0.84);
      line-height: 1.6;
      font-size: 14px;
    }
    .sidebar-tagline {
      font-family: "Cormorant Garamond", serif;
      font-size: 18px;
      font-style: italic;
      color: rgba(246, 242, 235, 0.72);
      line-height: 1.4;
      margin: 0;
    }
    .status-card {
      padding: 18px;
      border: 1px solid rgba(255, 255, 255, 0.16);
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.08);
    }
    .status-card strong,
    .checklist strong {
      display: block;
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-bottom: 10px;
      color: rgba(255, 255, 255, 0.72);
    }
    .otp-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.12);
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0.08em;
    }
    .checklist {
      display: grid;
      gap: 10px;
    }
    .checklist-item {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      color: rgba(255, 255, 255, 0.86);
    }
    .check-icon {
      width: 22px;
      height: 22px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 50%;
      border: 1px solid rgba(255, 255, 255, 0.22);
      background: rgba(255, 255, 255, 0.08);
      font-size: 12px;
      flex: 0 0 auto;
    }
    .main {
      padding: 40px 48px;
      background:
        radial-gradient(circle at top left, rgba(184, 139, 150, 0.12), transparent 28%),
        radial-gradient(circle at 85% 12%, rgba(176, 138, 78, 0.08), transparent 24%),
        linear-gradient(180deg, #fbf6f1 0%, var(--bg) 42%, #f1e6da 100%);
      display: flex;
      flex-direction: column;
      gap: 18px;
      overflow-y: auto;
    }
    .topline {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }
    .step-meta {
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .progress {
      display: grid;
      grid-template-columns: repeat(10, minmax(0, 1fr));
      gap: 6px;
      width: min(100%, 340px);
    }
    .progress-bar {
      height: 6px;
      border-radius: 999px;
      background: rgba(216, 206, 193, 0.72);
      transition: transform 160ms ease, background 160ms ease;
      transform-origin: center;
    }
    .progress-bar.active {
      background: var(--accent);
      transform: scaleY(1.2);
    }
    .progress-bar.done {
      background: #b08a4e;
    }
    .panel {
      border: none;
      border-radius: 0;
      padding: 0;
      background: transparent;
      min-height: 480px;
      display: flex;
      flex-direction: column;
    }
    .step {
      display: none;
      flex: 1;
    }
    .step.active {
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    .step-title {
      margin: 0;
      font-size: 30px;
      line-height: 1.05;
      letter-spacing: -0.02em;
    }
    .step-desc {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
      max-width: 560px;
    }
    .field {
      display: grid;
      gap: 8px;
    }
    .field label {
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .field input,
    .field select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px 18px;
      background: #fff;
      color: var(--ink);
      font-size: 16px;
      outline: none;
      transition: border-color 140ms ease, box-shadow 140ms ease;
    }
    .field input:focus,
    .field select:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 4px rgba(31, 111, 95, 0.08);
    }
    .caption {
      font-size: 12px;
      color: var(--muted);
      line-height: 1.45;
    }
    .grid-2 {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .choice-grid {
      display: grid;
      gap: 12px;
    }
    .choice-grid.cols-2 {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .choice-card {
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
      background: #fff;
      cursor: pointer;
      transition: border-color 140ms ease, transform 140ms ease, background 140ms ease;
    }
    .choice-card:hover {
      border-color: var(--line-strong);
      transform: translateY(-1px);
    }
    .choice-card.selected {
      border-color: var(--accent);
      background: var(--accent-soft);
    }
    .choice-card strong {
      display: block;
      font-size: 15px;
      margin-bottom: 4px;
    }
    .choice-card span {
      display: block;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.45;
    }
    .image-card {
      display: grid;
      gap: 16px;
      margin-top: 4px;
    }
    .uploader {
      border: 1px dashed var(--line-strong);
      border-radius: 22px;
      padding: 20px;
      background:
        linear-gradient(180deg, rgba(245, 239, 232, 0.68) 0%, rgba(255, 255, 255, 0.96) 100%);
    }
    .dropzone {
      display: grid;
      place-items: center;
      aspect-ratio: 2 / 3;
      border: 1px dashed rgba(188, 172, 151, 0.9);
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.8);
      text-align: center;
      padding: 24px;
      cursor: pointer;
    }
    .dropzone strong {
      display: block;
      font-size: 16px;
      margin-bottom: 6px;
    }
    .crop-shell {
      display: none;
      gap: 14px;
    }
    .crop-shell.ready {
      display: grid;
    }
    .crop-stage {
      position: relative;
      width: 100%;
      max-width: 640px;
      aspect-ratio: 2 / 3;
      border-radius: 22px;
      overflow: hidden;
      background:
        linear-gradient(135deg, #221f1c 0%, #111 100%);
      border: 1px solid rgba(255, 255, 255, 0.08);
      touch-action: none;
    }
    .crop-canvas {
      width: 100%;
      height: 100%;
      display: block;
      cursor: grab;
    }
    .crop-canvas:active {
      cursor: grabbing;
    }
    .crop-overlay {
      position: absolute;
      inset: 0;
      pointer-events: none;
      border: 2px solid rgba(255, 255, 255, 0.82);
      border-radius: 22px;
      box-shadow: inset 0 0 0 999px rgba(17, 17, 17, 0.16);
    }
    .ratio-badge {
      position: absolute;
      top: 14px;
      left: 14px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.12);
      color: #fff;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      backdrop-filter: blur(10px);
    }
    .crop-controls {
      display: grid;
      gap: 12px;
    }
    .zoom-row {
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 12px;
      align-items: center;
    }
    .zoom-row span {
      font-size: 12px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
    }
    input[type="range"] {
      width: 100%;
      accent-color: var(--accent);
    }
    .crop-actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    .btn {
      border: none;
      border-radius: 16px;
      padding: 14px 18px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      transition: opacity 140ms ease, transform 140ms ease;
    }
    .btn:hover {
      transform: translateY(-1px);
    }
    .btn.primary {
      background: var(--accent);
      color: #fff;
    }
    .btn.secondary {
      background: #fff;
      color: var(--ink);
      border: 1px solid var(--line);
    }
    .btn.ghost {
      background: transparent;
      color: var(--muted);
      border: 1px solid rgba(216, 206, 193, 0.72);
    }
    .btn:disabled {
      opacity: 0.52;
      cursor: not-allowed;
      transform: none;
    }
    .actions {
      margin-top: auto;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }
    .actions .btn.primary {
      min-width: 180px;
    }
    .error {
      display: none;
      padding: 12px 14px;
      border-radius: 14px;
      background: var(--danger-bg);
      color: var(--danger);
      font-size: 13px;
      line-height: 1.45;
    }
    .error.show {
      display: block;
    }
    .success-card {
      flex: 1;
      display: grid;
      place-items: center;
      text-align: center;
      gap: 16px;
      padding: 20px 0;
    }
    .success-mark {
      width: 82px;
      height: 82px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 38px;
      font-weight: 700;
    }
    .fineprint {
      font-size: 12px;
      color: var(--muted);
      line-height: 1.5;
    }
    .style-shell {
      display: grid;
      gap: 18px;
    }
    .style-counter {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      width: fit-content;
      padding: 8px 12px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .style-layer {
      display: grid;
      gap: 12px;
    }
    .style-layer.hidden {
      display: none;
    }
    .style-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }
    .style-card {
      position: relative;
      border: 1px solid var(--line);
      border-radius: 18px;
      overflow: hidden;
      background: #f7f1ea;
      cursor: pointer;
      transition: transform 140ms ease, border-color 140ms ease, box-shadow 140ms ease;
      min-height: 208px;
    }
    .style-card:hover {
      transform: translateY(-1px);
      border-color: var(--line-strong);
    }
    .style-card.selected {
      border-color: var(--accent);
      box-shadow: 0 0 0 4px rgba(31, 111, 95, 0.12);
    }
    .style-card img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
      aspect-ratio: 4 / 5;
      background: #efe7dd;
    }
    .style-badge {
      position: absolute;
      top: 10px;
      right: 10px;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: rgba(17, 17, 17, 0.52);
      color: #fff;
      display: grid;
      place-items: center;
      font-size: 13px;
      font-weight: 700;
      opacity: 0;
      transition: opacity 140ms ease, background 140ms ease;
    }
    .style-card.selected .style-badge {
      opacity: 1;
      background: var(--accent);
    }
    .style-separator {
      display: flex;
      align-items: center;
      gap: 12px;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    .style-separator::before,
    .style-separator::after {
      content: "";
      height: 1px;
      flex: 1;
      background: rgba(188, 172, 151, 0.72);
    }
    @media (max-width: 900px) {
      body { height: auto; overflow: auto; }
      .shell {
        grid-template-columns: 1fr;
        height: auto;
      }
      .sidebar {
        padding: 28px 22px 20px;
      }
      .main {
        padding: 24px 20px;
        overflow: visible;
      }
      .panel {
        min-height: 0;
      }
      .grid-2,
      .choice-grid.cols-2,
      .zoom-row {
        grid-template-columns: 1fr;
      }
      .crop-stage {
        max-width: 100%;
      }
      .style-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div>
        <div class="eyebrow">Sigma Aura</div>
        <h1>Your personal fashion stylist.</h1>
      </div>
      <p class="sidebar-tagline">Know what to wear. Know what to buy. Know what suits you.</p>
      <p>Aura learns your body, your colors, and your style — then helps you make better dressing and shopping decisions every day.</p>
      <div class="checklist">
        <strong>What Aura does for you</strong>
        <div class="checklist-item"><span class="check-icon">&#10024;</span><span>Outfit recommendations for any occasion</span></div>
        <div class="checklist-item"><span class="check-icon">&#127912;</span><span>Color and style analysis based on your photos</span></div>
        <div class="checklist-item"><span class="check-icon">&#128090;</span><span>Wardrobe management — use what you own first</span></div>
        <div class="checklist-item"><span class="check-icon">&#128717;</span><span>Shopping guidance — buy only what you need</span></div>
        <div class="checklist-item"><span class="check-icon">&#9992;</span><span>Trip and capsule wardrobe planning</span></div>
      </div>
      <div class="status-card">
        <strong>To get started</strong>
        <p style="margin:0;font-size:13px;color:rgba(246,242,235,0.8);">Complete a quick profile setup so Aura can personalise recommendations to your body, coloring, and taste.</p>
      </div>
    </aside>

    <main class="main">
      <div class="topline">
        <div class="step-meta" id="stepMeta">Step 1 of 9</div>
        <div class="progress" id="progressBar"></div>
      </div>

      <section class="panel">
        <div class="step active" id="step-mobile">
          <h2 class="step-title">Start with your mobile number.</h2>
          <p class="step-desc">This is the first gate before the conversational platform. Use your mobile number here, then verify with the current fixed OTP.</p>
          <div class="field">
            <label for="mobileInput">Mobile Number</label>
            <input id="mobileInput" type="tel" inputmode="tel" placeholder="+91 9876543210" maxlength="15" />
          </div>
          <div class="caption">Numbers only with an optional leading <code>+</code> are accepted.</div>
          <div class="error" id="mobileErr"></div>
          <div class="actions">
            <button class="btn primary" id="sendOtpBtn">Send OTP</button>
          </div>
        </div>

        <div class="step" id="step-otp">
          <h2 class="step-title">Verify the fixed OTP.</h2>
          <p class="step-desc">For this implementation the OTP is fixed. Enter <strong>123456</strong> to continue.</p>
          <div class="field">
            <label for="otpInput">OTP</label>
            <input id="otpInput" type="text" inputmode="numeric" placeholder="123456" maxlength="6" />
          </div>
          <div class="error" id="otpErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="0">Back</button>
            <button class="btn primary" id="verifyOtpBtn">Verify OTP</button>
          </div>
        </div>

        <div class="step" id="step-name">
          <h2 class="step-title">What should we call you?</h2>
          <p class="step-desc">We will use this name throughout the experience.</p>
          <div class="field">
            <label for="nameInput">Full Name</label>
            <input id="nameInput" type="text" placeholder="Your name" maxlength="100" />
          </div>
          <div class="error" id="nameErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="1">Back</button>
            <button class="btn primary" id="nameNextBtn">Continue</button>
          </div>
        </div>

        <div class="step" id="step-gender">
          <h2 class="step-title">Select gender.</h2>
          <p class="step-desc">This helps us tailor recommendations to your body and style profile.</p>
          <div class="choice-grid cols-2" id="genderGrid"></div>
          <input id="genderInput" type="hidden" />
          <div class="error" id="genderErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="2">Back</button>
            <button class="btn primary" id="genderNextBtn">Continue</button>
          </div>
        </div>

        <div class="step" id="step-images">
          <h2 class="step-title">Upload your photos.</h2>
          <p class="step-desc">We need a full-body and a headshot to analyze your body proportions, coloring, and features. Position each photo inside the 2:3 frame before uploading.</p>
          <div class="grid-2">
            <div class="image-card">
              <div class="uploader">
                <div class="dropzone" id="dropzone-fullbody">
                  <div>
                    <strong>Full body</strong>
                    <div class="caption">Standing pose, head to toe.</div>
                  </div>
                </div>
                <input id="input-fullbody" type="file" accept="image/*" hidden />
                <div class="crop-shell" id="crop-shell-fullbody">
                  <div class="crop-stage">
                    <canvas class="crop-canvas" id="canvas-fullbody" width="800" height="1200"></canvas>
                    <div class="crop-overlay"></div>
                    <div class="ratio-badge">2:3</div>
                  </div>
                  <div class="crop-controls">
                    <div class="zoom-row">
                      <span>Zoom</span>
                      <input id="zoom-fullbody" type="range" min="1" max="4" step="0.01" value="1" />
                      <button class="btn ghost" type="button" id="change-fullbody">Change</button>
                    </div>
                  </div>
                </div>
                <div class="upload-status" id="status-fullbody"></div>
              </div>
            </div>
            <div class="image-card">
              <div class="uploader">
                <div class="dropzone" id="dropzone-headshot">
                  <div>
                    <strong>Headshot</strong>
                    <div class="caption">Clear face, even lighting.</div>
                  </div>
                </div>
                <input id="input-headshot" type="file" accept="image/*" hidden />
                <div class="crop-shell" id="crop-shell-headshot">
                  <div class="crop-stage">
                    <canvas class="crop-canvas" id="canvas-headshot" width="800" height="1200"></canvas>
                    <div class="crop-overlay"></div>
                    <div class="ratio-badge">2:3</div>
                  </div>
                  <div class="crop-controls">
                    <div class="zoom-row">
                      <span>Zoom</span>
                      <input id="zoom-headshot" type="range" min="1" max="4" step="0.01" value="1" />
                      <button class="btn ghost" type="button" id="change-headshot">Change</button>
                    </div>
                  </div>
                </div>
                <div class="upload-status" id="status-headshot"></div>
              </div>
            </div>
          </div>
          <div class="error" id="imagesErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="3">Back</button>
            <button class="btn primary" id="uploadBothBtn">Upload Photos and Continue</button>
          </div>
        </div>

        <div class="step" id="step-dob">
          <h2 class="step-title">Add your date of birth.</h2>
          <p class="step-desc">This helps us calibrate age-appropriate style recommendations.</p>
          <div class="field">
            <label for="dobInput">Date of Birth</label>
            <input id="dobInput" type="date" />
          </div>
          <div class="error" id="dobErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="4">Back</button>
            <button class="btn primary" id="dobNextBtn">Continue</button>
          </div>
        </div>

        <div class="step" id="step-body">
          <h2 class="step-title">Your measurements.</h2>
          <p class="step-desc">These help us recommend the right silhouettes and fits for your frame.</p>
          <div class="grid-2">
            <div class="field">
              <label>Height</label>
              <div class="grid-2">
                <div class="field">
                  <input id="heightFtInput" type="number" min="3" max="7" step="1" placeholder="5" />
                  <div class="caption">feet</div>
                </div>
                <div class="field">
                  <input id="heightInInput" type="number" min="0" max="11" step="1" placeholder="8" />
                  <div class="caption">inches</div>
                </div>
              </div>
            </div>
            <div class="field">
              <label for="waistInInput">Waist</label>
              <input id="waistInInput" type="number" min="20" max="60" step="0.5" placeholder="32" />
              <div class="caption">inches</div>
            </div>
          </div>
          <input id="heightInput" type="hidden" />
          <input id="waistInput" type="hidden" />
          <div class="error" id="bodyErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="5">Back</button>
            <button class="btn primary" id="bodyNextBtn">Continue</button>
          </div>
        </div>

        <div class="step" id="step-profession">
          <h2 class="step-title">Choose your profession.</h2>
          <p class="step-desc">This helps us understand your daily dress code context.</p>
          <div class="choice-grid cols-2" id="professionGrid"></div>
          <input id="professionInput" type="hidden" />
          <div class="error" id="professionErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="6">Back</button>
            <button class="btn primary" id="professionNextBtn">Save Profile</button>
          </div>
        </div>

        <div class="step" id="step-style">
          <h2 class="step-title">Select the outfits that feel like you.</h2>
          <p class="step-desc">Choose between 3 and 5 images. More options will appear progressively as soon as your first and second choices sharpen the direction.</p>
          <div class="style-shell">
            <div class="style-counter" id="styleCounter">0 of 3-5 selected</div>
            <div class="style-layer">
              <div class="style-grid" id="styleLayer1"></div>
            </div>
            <div class="style-layer hidden" id="styleLayer2Block">
              <div class="style-separator">More in this direction</div>
              <div class="style-grid" id="styleLayer2"></div>
            </div>
            <div class="style-layer hidden" id="styleLayer3Block">
              <div class="style-separator">Push the signal further</div>
              <div class="style-grid" id="styleLayer3"></div>
            </div>
          </div>
          <div class="error" id="styleErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="7">Back</button>
            <button class="btn primary" id="saveStyleBtn" disabled>Continue to Profile Processing</button>
          </div>
        </div>

        <div class="step" id="step-done">
          <div class="success-card">
            <div class="success-mark">✓</div>
            <div>
              <h2 class="step-title">Onboarding complete.</h2>
              <p class="step-desc">Your profile record and image metadata are saved locally. You can now enter the conversational platform.</p>
            </div>
            <button class="btn primary" id="goToPlatformBtn">Open Aura</button>
            <div class="fineprint">Images are stored with encrypted titles derived from user id, image type, and timestamp.</div>
          </div>
        </div>
      </section>
    </main>
  </div>

  <script>
    // Auto-redirect returning users who have a stored session
    (function() {
      try {
        var params = new URLSearchParams(window.location.search);
        if (!params.get("user")) {
          var storedUser = localStorage.getItem("aura_user_id");
          if (storedUser) {
            window.location.href = "/?user=" + encodeURIComponent(storedUser) + "&view=chat";
            return;
          }
        }
      } catch(_) {}
    })();

    const STEP_ORDER = [
      "mobile",
      "otp",
      "name",
      "gender",
      "images",
      "dob",
      "body",
      "profession",
      "style",
      "done"
    ];

    const GENDER_OPTIONS = [
      { value: "male", label: "Male", hint: "Masculine profile mapping" },
      { value: "female", label: "Female", hint: "Feminine profile mapping" },
      { value: "non_binary", label: "Non-binary", hint: "Non-binary profile mapping" },
      { value: "prefer_not_to_say", label: "Prefer not to say", hint: "Stored without explicit gender preference" }
    ];

    const PROFESSION_OPTIONS = [
      { value: "software_engineer", label: "Software Engineer", hint: "Tech and product roles" },
      { value: "doctor", label: "Doctor", hint: "Clinical and medical practice" },
      { value: "lawyer", label: "Lawyer", hint: "Legal practice and advisory" },
      { value: "teacher", label: "Teacher", hint: "Education and instruction" },
      { value: "designer", label: "Designer", hint: "Creative design work" },
      { value: "architect", label: "Architect", hint: "Architecture and planning" },
      { value: "business_finance", label: "Business / Finance", hint: "Operations, strategy or finance" },
      { value: "marketing", label: "Marketing", hint: "Brand, growth and media" },
      { value: "artist", label: "Artist", hint: "Artistic practice and performance" },
      { value: "student", label: "Student", hint: "Academic track" },
      { value: "entrepreneur", label: "Entrepreneur", hint: "Founder or builder role" },
      { value: "homemaker", label: "Homemaker", hint: "Home-focused role" },
      { value: "other", label: "Other", hint: "Anything outside the current fixed set" }
    ];

    const IMAGE_STEPS = {
      fullbody: {
        category: "full_body",
        errorId: "imagesErr"
      },
      headshot: {
        category: "headshot",
        errorId: "imagesErr"
      }
    };
    const REQUIRED_IMAGE_CATEGORIES = ["full_body", "headshot"];

    const state = {
      currentStep: 0,
      userId: "",
      cropper: {
        fullbody: createCropState("fullbody"),
        headshot: createCropState("headshot")
      },
      style: {
        gender: "male",
        pool: [],
        layer1: [],
        layer2: [],
        layer3: [],
        layer2Triggered: false,
        layer3Triggered: false,
        selectedEvents: [],
        shownImages: [],
        loaded: false
      }
    };

    function createCropState(key) {
      return {
        key,
        image: null,
        input: document.getElementById("input-" + key),
        dropzone: document.getElementById("dropzone-" + key),
        shell: document.getElementById("crop-shell-" + key),
        canvas: document.getElementById("canvas-" + key),
        slider: document.getElementById("zoom-" + key),
        changeBtn: document.getElementById("change-" + key),
        ctx: null,
        naturalWidth: 0,
        naturalHeight: 0,
        baseScale: 1,
        scale: 1,
        minScale: 1,
        maxScale: 4,
        x: 0,
        y: 0,
        dragging: false,
        dragStartX: 0,
        dragStartY: 0,
        originX: 0,
        originY: 0
      };
    }

    const progressBar = document.getElementById("progressBar");
    const stepMeta = document.getElementById("stepMeta");
    const styleCounter = document.getElementById("styleCounter");
    const styleLayer1 = document.getElementById("styleLayer1");
    const styleLayer2 = document.getElementById("styleLayer2");
    const styleLayer3 = document.getElementById("styleLayer3");
    const styleLayer2Block = document.getElementById("styleLayer2Block");
    const styleLayer3Block = document.getElementById("styleLayer3Block");

    function initProgress() {
      progressBar.innerHTML = "";
      for (let i = 0; i < STEP_ORDER.length - 1; i++) {
        const bar = document.createElement("div");
        bar.className = "progress-bar";
        progressBar.appendChild(bar);
      }
    }

    function setStep(index) {
      state.currentStep = index;
      STEP_ORDER.forEach((key, stepIndex) => {
        document.getElementById("step-" + key).classList.toggle("active", stepIndex === index);
      });

      const visibleStepCount = STEP_ORDER.length - 1;
      const bars = progressBar.querySelectorAll(".progress-bar");
      bars.forEach((bar, barIndex) => {
        bar.classList.toggle("done", barIndex < Math.min(index, visibleStepCount));
        bar.classList.toggle("active", barIndex === Math.min(index, visibleStepCount - 1));
      });

      stepMeta.textContent = index >= visibleStepCount
        ? "Ready for the platform"
        : "Step " + (index + 1) + " of " + visibleStepCount;

      if (STEP_ORDER[index] === "style") {
        ensureStyleSession();
      }
    }

    function showError(id, message) {
      const el = document.getElementById(id);
      el.textContent = message;
      el.classList.add("show");
    }

    function hideError(id) {
      const el = document.getElementById(id);
      el.textContent = "";
      el.classList.remove("show");
    }

    function extractError(data, fallback) {
      if (!data) return fallback;
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail)) return data.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
      return data.message || fallback;
    }

    function renderChoiceGrid(containerId, inputId, options) {
      const container = document.getElementById(containerId);
      const input = document.getElementById(inputId);
      container.innerHTML = "";
      options.forEach((option) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "choice-card";
        button.dataset.value = option.value;
        button.innerHTML = "<strong>" + option.label + "</strong><span>" + option.hint + "</span>";
        button.addEventListener("click", () => {
          Array.from(container.children).forEach((node) => node.classList.remove("selected"));
          button.classList.add("selected");
          input.value = option.value;
        });
        container.appendChild(button);
      });
    }

    function bindBackButtons() {
      document.querySelectorAll("[data-back]").forEach((button) => {
        button.addEventListener("click", () => setStep(parseInt(button.dataset.back, 10)));
      });
    }

    async function postJson(url, payload, fallback) {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(extractError(data, fallback));
      }
      return data;
    }

    async function patchJson(url, payload) {
      const response = await fetch(url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(extractError(data, "Update failed"));
      return data;
    }

    function isHeicLikeFile(file) {
      const name = (file && file.name ? file.name : "").toLowerCase();
      const type = (file && file.type ? file.type : "").toLowerCase();
      return name.endsWith(".heic") || name.endsWith(".heif") || type === "image/heic" || type === "image/heif";
    }

    async function readFileAsDataUrl(file) {
      return await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error("Unable to read image"));
        reader.readAsDataURL(file);
      });
    }

    async function normalizeImageForPreview(file) {
      const formData = new FormData();
      formData.append("file", file, file.name || "image.heic");
      const response = await fetch("/v1/onboarding/images/normalize", {
        method: "POST",
        body: formData
      });
      if (!response.ok) {
        let message = "Unable to normalize image";
        try {
          const data = await response.json();
          message = extractError(data, message);
        } catch (_) {
          // Ignore JSON parse errors for binary responses.
        }
        throw new Error(message);
      }
      const blob = await response.blob();
      return await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error("Unable to read normalized image"));
        reader.readAsDataURL(blob);
      });
    }

    function validateMobile(value) {
      return /^\+?\d{10,15}$/.test(value);
    }

    function stylePoolFind(matchFn, excludeIds) {
      return state.style.pool.find((image) => !excludeIds.has(image.id) && matchFn(image)) || null;
    }

    function findBlendImage(arch1, arch2, excludeIds) {
      return stylePoolFind((image) => image.imageType === "blend" && (
        (image.primaryArchetype === arch1 && image.secondaryArchetype === arch2) ||
        (image.primaryArchetype === arch2 && image.secondaryArchetype === arch1)
      ), excludeIds);
    }

    function styleFallback(baseArchetype, excludeIds, preferred) {
      for (const query of preferred) {
        const match = stylePoolFind((image) => {
          if (query.imageType && image.imageType !== query.imageType) return false;
          if (query.primaryArchetype && image.primaryArchetype !== query.primaryArchetype) return false;
          if (query.secondaryArchetype !== undefined && image.secondaryArchetype !== query.secondaryArchetype) return false;
          if (query.intensity && image.intensity !== query.intensity) return false;
          if (query.context && image.context !== query.context) return false;
          return true;
        }, excludeIds);
        if (match) return match;
      }
      return stylePoolFind(() => true, excludeIds);
    }

    function renderStyleGrid(container, images, layerNumber) {
      container.innerHTML = "";
      images.forEach((image) => {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "style-card";
        card.dataset.imageId = image.id;
        card.innerHTML = '<img alt="" loading="lazy" src="' + image.imageUrl + '" /><span class="style-badge"></span>';
        card.addEventListener("click", () => toggleStyleSelection(image, layerNumber));
        container.appendChild(card);
      });
      syncStyleSelectionUI();
    }

    function syncStyleSelectionUI() {
      const selectedIds = new Map(state.style.selectedEvents.map((event, index) => [event.image.id, index + 1]));
      document.querySelectorAll(".style-card").forEach((card) => {
        const order = selectedIds.get(card.dataset.imageId);
        card.classList.toggle("selected", Boolean(order));
        const badge = card.querySelector(".style-badge");
        badge.textContent = order ? String(order) : "";
      });
      styleCounter.textContent = state.style.selectedEvents.length + " of 3-5 selected";
      document.getElementById("saveStyleBtn").disabled = !(state.style.selectedEvents.length >= 3 && state.style.selectedEvents.length <= 5);
    }

    function currentShownImages() {
      return [...state.style.layer1, ...state.style.layer2, ...state.style.layer3];
    }

    function createSelectionEvent(image, layerNumber) {
      return {
        image,
        layer: layerNumber,
        position: image.position || null,
        selectionOrder: state.style.selectedEvents.length + 1
      };
    }

    function toggleStyleSelection(image, layerNumber) {
      hideError("styleErr");
      const existingIndex = state.style.selectedEvents.findIndex((event) => event.image.id === image.id);
      if (existingIndex >= 0) {
        state.style.selectedEvents.splice(existingIndex, 1);
        state.style.selectedEvents.forEach((event, index) => {
          event.selectionOrder = index + 1;
        });
        syncStyleSelectionUI();
        return;
      }
      if (state.style.selectedEvents.length >= 5) {
        showError("styleErr", "You can select up to 5 images.");
        return;
      }
      state.style.selectedEvents.push(createSelectionEvent(image, layerNumber));
      if (layerNumber === 1 && !state.style.layer2Triggered) {
        generateLayer2(image);
      }
      if (layerNumber === 2 && !state.style.layer3Triggered) {
        generateLayer3(image);
      }
      syncStyleSelectionUI();
    }

    function generateLayer2(triggerImage) {
      const adjacency = state.style.adjacency[triggerImage.primaryArchetype];
      const usedIds = new Set(currentShownImages().map((image) => image.id));
      const candidates = [
        stylePoolFind((image) => image.primaryArchetype === triggerImage.primaryArchetype && image.imageType === "pure" && !image.secondaryArchetype && image.intensity === "bold", usedIds),
        findBlendImage(triggerImage.primaryArchetype, adjacency.near, usedIds),
        findBlendImage(triggerImage.primaryArchetype, adjacency.far, usedIds),
        stylePoolFind((image) => image.primaryArchetype === triggerImage.primaryArchetype && image.imageType === "pure" && !image.secondaryArchetype && image.intensity === "restrained", usedIds)
      ];
      const next = [];
      candidates.forEach((candidate, idx) => {
        const image = candidate || styleFallback(triggerImage.primaryArchetype, usedIds, [
          { primaryArchetype: triggerImage.primaryArchetype, secondaryArchetype: null, imageType: "pure", intensity: "moderate" },
          { primaryArchetype: triggerImage.primaryArchetype, secondaryArchetype: null, imageType: "context", context: "casual" },
          { primaryArchetype: triggerImage.primaryArchetype, secondaryArchetype: adjacency.third, imageType: "blend" },
          { primaryArchetype: adjacency.near, secondaryArchetype: null, imageType: "pure", intensity: "moderate" }
        ]);
        usedIds.add(image.id);
        next.push({ ...image, position: idx + 1 });
      });
      state.style.layer2 = next;
      state.style.layer2Triggered = true;
      styleLayer2Block.classList.remove("hidden");
      renderStyleGrid(styleLayer2, next, 2);
    }

    function generateLayer3(triggerImage) {
      const baseTrigger = state.style.selectedEvents.find((event) => event.layer === 1);
      if (!baseTrigger) return;
      const baseArchetype = baseTrigger.image.primaryArchetype;
      const adjacency = state.style.adjacency[baseArchetype];
      const usedIds = new Set(currentShownImages().map((image) => image.id));
      let queries = [];
      if (triggerImage.position === 1) {
        queries = [
          { primaryArchetype: baseArchetype, secondaryArchetype: null, imageType: "context", context: "casual" },
          { primaryArchetype: baseArchetype, secondaryArchetype: null, imageType: "context", context: "elevated" },
          { primaryArchetype: baseArchetype, secondaryArchetype: adjacency.third, imageType: "blend" },
          { primaryArchetype: adjacency.near, secondaryArchetype: null, imageType: "pure", intensity: "moderate" }
        ];
      } else if (triggerImage.position === 2) {
        const blendArchetype = triggerImage.secondaryArchetype || triggerImage.primaryArchetype;
        const blendAdjacency = state.style.adjacency[blendArchetype];
        queries = [
          { primaryArchetype: blendArchetype, secondaryArchetype: null, imageType: "pure", intensity: "moderate" },
          { primaryArchetype: blendArchetype, secondaryArchetype: null, imageType: "pure", intensity: "bold" },
          { primaryArchetype: baseArchetype, secondaryArchetype: null, imageType: "context", context: "casual" },
          { primaryArchetype: blendArchetype, secondaryArchetype: blendAdjacency.near, imageType: "blend" }
        ];
      } else if (triggerImage.position === 3) {
        const farArchetype = triggerImage.secondaryArchetype || triggerImage.primaryArchetype;
        queries = [
          { primaryArchetype: farArchetype, secondaryArchetype: null, imageType: "pure", intensity: "moderate" },
          { primaryArchetype: farArchetype, secondaryArchetype: null, imageType: "pure", intensity: "restrained" },
          { primaryArchetype: baseArchetype, secondaryArchetype: null, imageType: "context", context: "elevated" },
          { primaryArchetype: farArchetype, secondaryArchetype: state.style.adjacency[farArchetype].near, imageType: "blend" }
        ];
      } else {
        queries = [
          { primaryArchetype: baseArchetype, secondaryArchetype: null, imageType: "context", context: "casual" },
          { primaryArchetype: adjacency.near, secondaryArchetype: null, imageType: "pure", intensity: "restrained" },
          { primaryArchetype: adjacency.far, secondaryArchetype: null, imageType: "pure", intensity: "restrained" },
          { primaryArchetype: baseArchetype, secondaryArchetype: null, imageType: "context", context: "elevated" }
        ];
      }
      const next = [];
      queries.forEach((query, idx) => {
        const image = (
          query.imageType === "blend" && query.secondaryArchetype
            ? findBlendImage(query.primaryArchetype, query.secondaryArchetype, usedIds)
            : stylePoolFind((candidate) => {
                if (candidate.primaryArchetype !== query.primaryArchetype) return false;
                if ((query.secondaryArchetype || null) !== (candidate.secondaryArchetype || null)) return false;
                if (candidate.imageType !== query.imageType) return false;
                if (query.intensity && candidate.intensity !== query.intensity) return false;
                if (query.context && candidate.context !== query.context) return false;
                return true;
              }, usedIds)
        ) || styleFallback(baseArchetype, usedIds, [
          query,
          { primaryArchetype: baseArchetype, secondaryArchetype: null, imageType: "context", context: "casual" },
          { primaryArchetype: baseArchetype, secondaryArchetype: null, imageType: "context", context: "elevated" },
          { primaryArchetype: adjacency.third, secondaryArchetype: null, imageType: "pure", intensity: "moderate" }
        ]);
        usedIds.add(image.id);
        next.push({ ...image, position: idx + 1 });
      });
      state.style.layer3 = next;
      state.style.layer3Triggered = true;
      styleLayer3Block.classList.remove("hidden");
      renderStyleGrid(styleLayer3, next, 3);
    }

    async function ensureStyleSession() {
      if (!state.userId || state.style.loaded) return;
      hideError("styleErr");
      const response = await fetch("/v1/onboarding/style/session/" + encodeURIComponent(state.userId));
      const data = await response.json();
      if (!response.ok) {
        showError("styleErr", extractError(data, "Unable to load style archetype images"));
        return;
      }
      state.style.gender = data.gender;
      state.style.pool = data.pool || [];
      state.style.layer1 = data.layer1 || [];
      state.style.adjacency = data.adjacency || {};
      state.style.layer2 = [];
      state.style.layer3 = [];
      state.style.selectedEvents = [];
      state.style.layer2Triggered = false;
      state.style.layer3Triggered = false;
      state.style.loaded = true;
      styleLayer2Block.classList.add("hidden");
      styleLayer3Block.classList.add("hidden");
      renderStyleGrid(styleLayer1, state.style.layer1, 1);
      styleLayer2.innerHTML = "";
      styleLayer3.innerHTML = "";
      syncStyleSelectionUI();
    }

    function prefillFromStatus(status) {
      // Pre-fill form fields from existing profile data
      if (status.name) document.getElementById("nameInput").value = status.name;
      if (status.gender) {
        document.getElementById("genderInput").value = status.gender;
        // Highlight the selected gender chip
        document.querySelectorAll("#genderGrid .choice-btn").forEach(btn => {
          btn.classList.toggle("selected", btn.dataset.value === status.gender);
        });
      }
      if (status.date_of_birth) document.getElementById("dobInput").value = status.date_of_birth;
      if (status.height_cm) {
        const totalInches = Math.round(status.height_cm / 2.54);
        document.getElementById("heightFtInput").value = Math.floor(totalInches / 12);
        document.getElementById("heightInInput").value = totalInches % 12;
        document.getElementById("heightInput").value = status.height_cm;
      }
      if (status.waist_cm) {
        document.getElementById("waistInInput").value = Math.round(status.waist_cm / 2.54 * 2) / 2;
        document.getElementById("waistInput").value = status.waist_cm;
      }
      if (status.profession) {
        document.getElementById("professionInput").value = status.profession;
        document.querySelectorAll("#professionGrid .choice-btn").forEach(btn => {
          btn.classList.toggle("selected", btn.dataset.value === status.profession);
        });
      }
      // Set gender in style state for session filtering
      if (status.gender) state.style.gender = (status.gender === "female") ? "female" : "male";
    }

    function determineResumeDestination(status) {
      const uploaded = Array.isArray(status.images_uploaded) ? status.images_uploaded : [];
      const hasAllImages = REQUIRED_IMAGE_CATEGORIES.every((c) => uploaded.includes(c));

      // New step order: mobile(0), otp(1), name(2), gender(3), images(4), dob(5), body(6), profession(7), style(8), done(9)
      if (status.onboarding_complete) return { type: "processing" };
      if (!status.name) return { type: "step", index: 2 };
      if (!status.gender) return { type: "step", index: 3 };
      if (!hasAllImages) return { type: "step", index: 4 };
      if (!status.date_of_birth) return { type: "step", index: 5 };
      if (!status.height_cm || !status.waist_cm) return { type: "step", index: 6 };
      if (!status.profession) return { type: "step", index: 7 };
      if (!status.style_preference_complete) return { type: "step", index: 8 };
      return { type: "processing" };
    }

    function clampCrop(crop) {
      const scaledWidth = crop.naturalWidth * crop.scale;
      const scaledHeight = crop.naturalHeight * crop.scale;
      const canvasWidth = crop.canvas.width;
      const canvasHeight = crop.canvas.height;

      if (scaledWidth <= canvasWidth) {
        crop.x = (canvasWidth - scaledWidth) / 2;
      } else {
        crop.x = Math.min(0, Math.max(canvasWidth - scaledWidth, crop.x));
      }

      if (scaledHeight <= canvasHeight) {
        crop.y = (canvasHeight - scaledHeight) / 2;
      } else {
        crop.y = Math.min(0, Math.max(canvasHeight - scaledHeight, crop.y));
      }
    }

    function drawCrop(crop) {
      if (!crop.image || !crop.ctx) return;
      crop.ctx.clearRect(0, 0, crop.canvas.width, crop.canvas.height);
      crop.ctx.fillStyle = "#111";
      crop.ctx.fillRect(0, 0, crop.canvas.width, crop.canvas.height);
      crop.ctx.drawImage(
        crop.image,
        crop.x,
        crop.y,
        crop.naturalWidth * crop.scale,
        crop.naturalHeight * crop.scale
      );
    }

    function resetCropper(crop) {
      crop.image = null;
      crop.naturalWidth = 0;
      crop.naturalHeight = 0;
      crop.scale = 1;
      crop.x = 0;
      crop.y = 0;
      crop.shell.classList.remove("ready");
      crop.dropzone.style.display = "grid";
      crop.input.value = "";
      crop.slider.value = "1";
    }

    function applyZoom(crop, nextScale, focusX, focusY) {
      const previousScale = crop.scale;
      crop.scale = Math.max(crop.minScale, Math.min(crop.maxScale, nextScale));
      const ratio = crop.scale / previousScale;
      crop.x = focusX - (focusX - crop.x) * ratio;
      crop.y = focusY - (focusY - crop.y) * ratio;
      clampCrop(crop);
      drawCrop(crop);
      crop.slider.value = (crop.scale / crop.baseScale).toFixed(2);
    }

    function loadCropImage(crop, dataUrl) {
      return new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = () => {
          crop.image = image;
          crop.ctx = crop.canvas.getContext("2d");
          crop.naturalWidth = image.naturalWidth;
          crop.naturalHeight = image.naturalHeight;
          crop.baseScale = Math.max(crop.canvas.width / crop.naturalWidth, crop.canvas.height / crop.naturalHeight);
          crop.minScale = crop.baseScale;
          crop.maxScale = crop.baseScale * 4;
          crop.scale = crop.baseScale;
          crop.x = (crop.canvas.width - crop.naturalWidth * crop.scale) / 2;
          crop.y = (crop.canvas.height - crop.naturalHeight * crop.scale) / 2;
          clampCrop(crop);
          drawCrop(crop);
          crop.slider.min = "1";
          crop.slider.max = "4";
          crop.slider.value = "1";
          crop.dropzone.style.display = "none";
          crop.shell.classList.add("ready");
          resolve();
        };
        image.onerror = () => reject(new Error("Invalid image file"));
        image.src = dataUrl;
      });
    }

    function bindCropper(crop) {
      crop.dropzone.addEventListener("click", () => crop.input.click());

      crop.input.addEventListener("change", async () => {
        const file = crop.input.files && crop.input.files[0];
        if (!file) return;
        try {
          const dataUrl = isHeicLikeFile(file)
            ? await normalizeImageForPreview(file)
            : await readFileAsDataUrl(file);
          await loadCropImage(crop, dataUrl);
        } catch (error) {
          resetCropper(crop);
          showError(IMAGE_STEPS[crop.key].errorId, String(error.message || error));
        }
      });

      crop.changeBtn.addEventListener("click", () => {
        hideError(IMAGE_STEPS[crop.key].errorId);
        resetCropper(crop);
      });

      crop.slider.addEventListener("input", () => {
        if (!crop.image) return;
        const scaleFactor = parseFloat(crop.slider.value);
        applyZoom(crop, crop.baseScale * scaleFactor, crop.canvas.width / 2, crop.canvas.height / 2);
      });

      crop.canvas.addEventListener("pointerdown", (event) => {
        if (!crop.image) return;
        crop.dragging = true;
        crop.dragStartX = event.clientX;
        crop.dragStartY = event.clientY;
        crop.originX = crop.x;
        crop.originY = crop.y;
        crop.canvas.setPointerCapture(event.pointerId);
      });

      crop.canvas.addEventListener("pointermove", (event) => {
        if (!crop.dragging) return;
        crop.x = crop.originX + (event.clientX - crop.dragStartX);
        crop.y = crop.originY + (event.clientY - crop.dragStartY);
        clampCrop(crop);
        drawCrop(crop);
      });

      function endDrag() {
        crop.dragging = false;
      }

      crop.canvas.addEventListener("pointerup", endDrag);
      crop.canvas.addEventListener("pointercancel", endDrag);
      crop.canvas.addEventListener("wheel", (event) => {
        if (!crop.image) return;
        event.preventDefault();
        const factor = event.deltaY < 0 ? 1.06 : 0.94;
        const rect = crop.canvas.getBoundingClientRect();
        const focusX = (event.clientX - rect.left) * (crop.canvas.width / rect.width);
        const focusY = (event.clientY - rect.top) * (crop.canvas.height / rect.height);
        applyZoom(crop, crop.scale * factor, focusX, focusY);
      }, { passive: false });
    }

    function exportCrop(crop) {
      return new Promise((resolve, reject) => {
        if (!crop.image) {
          reject(new Error("Please select and position an image before uploading"));
          return;
        }
        const outputCanvas = document.createElement("canvas");
        outputCanvas.width = crop.canvas.width;
        outputCanvas.height = crop.canvas.height;
        const outputCtx = outputCanvas.getContext("2d");
        const sourceX = -crop.x / crop.scale;
        const sourceY = -crop.y / crop.scale;
        const sourceWidth = crop.canvas.width / crop.scale;
        const sourceHeight = crop.canvas.height / crop.scale;
        outputCtx.drawImage(crop.image, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, outputCanvas.width, outputCanvas.height);
        outputCanvas.toBlob((blob) => {
          if (!blob) {
            reject(new Error("Unable to prepare cropped image"));
            return;
          }
          resolve(blob);
        }, "image/jpeg", 0.92);
      });
    }

    async function uploadImage(key, buttonId, nextLabel) {
      const details = IMAGE_STEPS[key];
      const crop = state.cropper[key];
      const errorId = details.errorId;
      hideError(errorId);
      const button = document.getElementById(buttonId);
      button.disabled = true;
      button.textContent = "Uploading...";
      try {
        const blob = await exportCrop(crop);
        const formData = new FormData();
        formData.append("user_id", state.userId);
        formData.append("file", blob, details.category + ".jpg");
        const response = await fetch("/v1/onboarding/images/" + details.category, {
          method: "POST",
          body: formData
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(extractError(data, "Image upload failed"));
        }
        setStep(details.nextStep);
      } catch (error) {
        showError(errorId, String(error.message || error));
      } finally {
        button.disabled = false;
        button.textContent = nextLabel;
      }
    }

    async function uploadImageAsync(key) {
      const details = IMAGE_STEPS[key];
      const crop = state.cropper[key];
      const blob = await exportCrop(crop);
      const formData = new FormData();
      formData.append("user_id", state.userId);
      formData.append("file", blob, details.category + ".jpg");
      const response = await fetch("/v1/onboarding/images/" + details.category, {
        method: "POST",
        body: formData
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(extractError(data, "Image upload failed for " + key));
      }
      return data;
    }

    function profilePayload() {
      return {
        user_id: state.userId,
        name: document.getElementById("nameInput").value.trim(),
        date_of_birth: document.getElementById("dobInput").value,
        gender: document.getElementById("genderInput").value,
        height_cm: parseFloat(document.getElementById("heightInput").value),
        waist_cm: parseFloat(document.getElementById("waistInput").value),
        profession: document.getElementById("professionInput").value
      };
    }

    function bindFormActions() {
      document.getElementById("sendOtpBtn").addEventListener("click", async () => {
        hideError("mobileErr");
        const mobile = document.getElementById("mobileInput").value.trim().replace(/\s+/g, "");
        if (!validateMobile(mobile)) {
          showError("mobileErr", "Enter a valid mobile number.");
          return;
        }
        const button = document.getElementById("sendOtpBtn");
        button.disabled = true;
        button.textContent = "Sending...";
        try {
          await postJson("/v1/onboarding/send-otp", { mobile }, "Failed to send OTP");
          setStep(1);
        } catch (error) {
          showError("mobileErr", String(error.message || error));
        } finally {
          button.disabled = false;
          button.textContent = "Send OTP";
        }
      });

      document.getElementById("verifyOtpBtn").addEventListener("click", async () => {
        hideError("otpErr");
        const mobile = document.getElementById("mobileInput").value.trim().replace(/\s+/g, "");
        const otp = document.getElementById("otpInput").value.trim();
        if (!validateMobile(mobile)) {
          showError("otpErr", "Mobile number is invalid.");
          return;
        }
        if (!/^\d{6}$/.test(otp)) {
          showError("otpErr", "Enter the 6-digit OTP.");
          return;
        }
        const button = document.getElementById("verifyOtpBtn");
        button.disabled = true;
        button.textContent = "Verifying...";
        try {
          const data = await postJson("/v1/onboarding/verify-otp", { mobile, otp }, "OTP verification failed");
          state.userId = data.user_id;
          try { localStorage.setItem("aura_user_id", state.userId); } catch(_) {}
          const statusResponse = await fetch("/v1/onboarding/status/" + encodeURIComponent(state.userId));
          const status = await statusResponse.json();
          if (!statusResponse.ok) {
            throw new Error(extractError(status, "Unable to load onboarding status"));
          }
          prefillFromStatus(status);
          const destination = determineResumeDestination(status);
          if (destination.type === "processing") {
            window.location.href = "/?user=" + encodeURIComponent(state.userId) + "&view=profile";
            return;
          }
          setStep(destination.index);
        } catch (error) {
          showError("otpErr", String(error.message || error));
        } finally {
          button.disabled = false;
          button.textContent = "Verify OTP";
        }
      });

      document.getElementById("nameNextBtn").addEventListener("click", async () => {
        hideError("nameErr");
        const name = document.getElementById("nameInput").value.trim();
        if (!name) {
          showError("nameErr", "Name is required.");
          return;
        }
        // Incremental save
        try { await patchJson("/v1/onboarding/profile/partial", { user_id: state.userId, name }); } catch(_) {}
        setStep(3);
      });

      document.getElementById("genderNextBtn").addEventListener("click", async () => {
        hideError("genderErr");
        const gender = document.getElementById("genderInput").value;
        if (!gender) {
          showError("genderErr", "Select a gender option.");
          return;
        }
        state.style.gender = (gender === "female") ? "female" : "male";
        // Incremental save
        try { await patchJson("/v1/onboarding/profile/partial", { user_id: state.userId, gender }); } catch(_) {}
        setStep(4); // → images
      });

      document.getElementById("dobNextBtn").addEventListener("click", async () => {
        hideError("dobErr");
        const dob = document.getElementById("dobInput").value;
        if (!dob) {
          showError("dobErr", "Date of birth is required.");
          return;
        }
        // Incremental save
        try { await patchJson("/v1/onboarding/profile/partial", { user_id: state.userId, date_of_birth: dob }); } catch(_) {}
        // Phase 2: start other_details analysis (needs gender + age + both images)
        try {
          await postJson("/v1/onboarding/analysis/start-phase2", { user_id: state.userId }, "");
        } catch (_) { /* best-effort */ }
        setStep(6); // → body
      });

      document.getElementById("bodyNextBtn").addEventListener("click", async () => {
        hideError("bodyErr");
        const ft = parseInt(document.getElementById("heightFtInput").value, 10);
        const inches = parseInt(document.getElementById("heightInInput").value, 10) || 0;
        const waistIn = parseFloat(document.getElementById("waistInInput").value);
        if (!Number.isFinite(ft) || ft < 3 || ft > 7) {
          showError("bodyErr", "Enter height in feet (3-7).");
          return;
        }
        if (inches < 0 || inches > 11) {
          showError("bodyErr", "Inches must be 0-11.");
          return;
        }
        if (!Number.isFinite(waistIn) || waistIn < 20 || waistIn > 60) {
          showError("bodyErr", "Enter waist in inches (20-60).");
          return;
        }
        // Convert to cm for the API
        const heightCm = Math.round(((ft * 12) + inches) * 2.54 * 10) / 10;
        const waistCm = Math.round(waistIn * 2.54 * 10) / 10;
        document.getElementById("heightInput").value = heightCm;
        document.getElementById("waistInput").value = waistCm;
        // Incremental save
        try { await patchJson("/v1/onboarding/profile/partial", { user_id: state.userId, height_cm: heightCm, waist_cm: waistCm }); } catch(_) {}
        setStep(7); // → profession
      });

      document.getElementById("professionNextBtn").addEventListener("click", async () => {
        hideError("professionErr");
        if (!document.getElementById("professionInput").value) {
          showError("professionErr", "Select a profession option.");
          return;
        }
        const button = document.getElementById("professionNextBtn");
        button.disabled = true;
        button.textContent = "Saving...";
        try {
          await postJson("/v1/onboarding/profile", profilePayload(), "Failed to save profile");
          setStep(8); // → style
        } catch (error) {
          showError("professionErr", String(error.message || error));
        } finally {
          button.disabled = false;
          button.textContent = "Save Profile";
        }
      });

      document.getElementById("uploadBothBtn").addEventListener("click", async () => {
        hideError("imagesErr");
        const button = document.getElementById("uploadBothBtn");
        // Check that both images have been selected (cropper has an image loaded)
        if (!state.cropper.fullbody.image) {
          showError("imagesErr", "Please select a full-body photo.");
          return;
        }
        if (!state.cropper.headshot.image) {
          showError("imagesErr", "Please select a headshot photo.");
          return;
        }
        button.disabled = true;
        button.textContent = "Uploading...";
        try {
          await uploadImageAsync("fullbody");
          document.getElementById("status-fullbody").textContent = "✓ Full body uploaded";
          await uploadImageAsync("headshot");
          document.getElementById("status-headshot").textContent = "✓ Headshot uploaded";
          // Phase 1: start color analysis (needs only gender + headshot)
          try {
            await postJson("/v1/onboarding/analysis/start-phase1", { user_id: state.userId }, "");
          } catch (_) { /* best-effort */ }
          setStep(5); // → dob
        } catch (error) {
          showError("imagesErr", String(error.message || error));
        } finally {
          button.disabled = false;
          button.textContent = "Upload Photos and Continue";
        }
      });
      document.getElementById("saveStyleBtn").addEventListener("click", async () => {
        hideError("styleErr");
        const button = document.getElementById("saveStyleBtn");
        if (state.style.selectedEvents.length < 3 || state.style.selectedEvents.length > 5) {
          showError("styleErr", "Select between 3 and 5 images.");
          return;
        }
        button.disabled = true;
        button.textContent = "Saving...";
        try {
          await postJson("/v1/onboarding/style/complete", {
            user_id: state.userId,
            shown_images: currentShownImages(),
            selections: state.style.selectedEvents
          }, "Unable to save style preference");
          window.location.href = "/?user=" + encodeURIComponent(state.userId) + "&view=profile";
        } catch (error) {
          showError("styleErr", String(error.message || error));
        } finally {
          button.disabled = !(state.style.selectedEvents.length >= 3 && state.style.selectedEvents.length <= 5);
          button.textContent = "Continue to Profile Processing";
        }
      });

      document.getElementById("goToPlatformBtn").addEventListener("click", () => {
        window.location.href = "/?user=" + encodeURIComponent(state.userId) + "&view=chat";
      });
    }

    initProgress();
    renderChoiceGrid("genderGrid", "genderInput", GENDER_OPTIONS);
    renderChoiceGrid("professionGrid", "professionInput", PROFESSION_OPTIONS);
    bindBackButtons();
    Object.values(state.cropper).forEach(bindCropper);
    bindFormActions();
    setStep(0);
  </script>
</body>
</html>
"""


def get_wardrobe_manager_html(user_id: str = "") -> str:
    initial_user_id = escape(user_id)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sigma Aura Wardrobe Manager</title>
  <style>
    :root {{
      --bg: #f4ede5;
      --surface: rgba(255, 252, 247, 0.94);
      --surface-strong: #fffdfa;
      --ink: #1f1b17;
      --muted: #6a6258;
      --line: #d9cdbf;
      --line-strong: #baa78e;
      --accent: #1f6f5f;
      --accent-soft: #e4efe9;
      --warm: #b7742a;
      --danger: #a22929;
      --danger-soft: #fdeeee;
      --shadow: 0 24px 64px rgba(49, 37, 23, 0.14);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #f7e4cb 0%, rgba(247, 228, 203, 0.34) 26%, transparent 52%),
        radial-gradient(circle at bottom right, #ddebe4 0%, rgba(221, 235, 228, 0.45) 22%, transparent 50%),
        linear-gradient(135deg, #f5efe7 0%, #efe4d8 48%, #ece2d6 100%);
      padding: 24px 16px;
    }}
    .shell {{
      width: min(1180px, 100%);
      margin: 0 auto;
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      gap: 18px;
    }}
    .sidebar,
    .main-panel,
    .card {{
      border: 1px solid rgba(186, 167, 142, 0.42);
      border-radius: 24px;
      background: var(--surface);
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }}
    .sidebar {{
      padding: 26px;
      background:
        linear-gradient(180deg, rgba(31, 111, 95, 0.94) 0%, rgba(22, 83, 71, 0.96) 100%);
      color: #f7f2ea;
      display: grid;
      align-content: start;
      gap: 18px;
    }}
    .eyebrow {{
      font-size: 12px;
      letter-spacing: 0.22em;
      text-transform: uppercase;
      opacity: 0.74;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    .sidebar h1 {{
      font-size: 34px;
      line-height: 1.02;
    }}
    .sidebar p {{
      color: rgba(247, 242, 234, 0.84);
      line-height: 1.55;
      font-size: 14px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      width: fit-content;
      gap: 8px;
      padding: 10px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.12);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .sidebar-list {{
      display: grid;
      gap: 10px;
    }}
    .sidebar-list div {{
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.08);
      font-size: 13px;
      line-height: 1.45;
    }}
    .main {{
      display: grid;
      gap: 18px;
    }}
    .main-panel {{
      padding: 24px;
      display: grid;
      gap: 18px;
    }}
    .topline {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .topline h2 {{
      font-size: 28px;
      line-height: 1.05;
    }}
    .muted {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }}
    .input-row,
    .summary-grid,
    .wardrobe-grid,
    .form-grid {{
      display: grid;
      gap: 14px;
    }}
    .input-row {{
      grid-template-columns: minmax(0, 1fr) auto;
    }}
    .summary-grid {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
    .wardrobe-grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .form-grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .card {{
      padding: 18px;
    }}
    .metric-value {{
      font-size: 30px;
      font-weight: 700;
      letter-spacing: -0.03em;
      margin-top: 10px;
    }}
    .field {{
      display: grid;
      gap: 8px;
    }}
    .field label {{
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .field input,
    .field textarea,
    .field select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px 16px;
      background: var(--surface-strong);
      color: var(--ink);
      font-size: 15px;
    }}
    .field textarea {{
      min-height: 96px;
      resize: vertical;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .btn {{
      border: none;
      border-radius: 16px;
      padding: 13px 16px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }}
    .btn.primary {{
      background: var(--accent);
      color: #fff;
    }}
    .btn.secondary {{
      background: #fff;
      color: var(--ink);
      border: 1px solid var(--line);
    }}
    .btn.danger {{
      background: var(--danger-soft);
      color: var(--danger);
      border: 1px solid rgba(162, 41, 41, 0.12);
    }}
    .status {{
      display: none;
      padding: 12px 14px;
      border-radius: 14px;
      font-size: 13px;
      line-height: 1.45;
    }}
    .status.show {{
      display: block;
    }}
    .status.error {{
      background: var(--danger-soft);
      color: var(--danger);
    }}
    .status.ok {{
      background: var(--accent-soft);
      color: var(--accent);
    }}
    .item-card {{
      border: 1px solid rgba(217, 205, 191, 0.86);
      border-radius: 18px;
      padding: 16px;
      background: var(--surface-strong);
      display: grid;
      gap: 12px;
    }}
    .item-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
    }}
    .item-title {{
      font-size: 18px;
      line-height: 1.15;
    }}
    .tag-row {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .tag {{
      padding: 7px 10px;
      border-radius: 999px;
      background: #f4eee7;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .list {{
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }}
    .list div {{
      padding: 10px 12px;
      border-radius: 14px;
      background: #f8f2eb;
      font-size: 13px;
      line-height: 1.45;
    }}
    .empty {{
      padding: 26px;
      border: 1px dashed var(--line-strong);
      border-radius: 18px;
      text-align: center;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.5);
    }}
    @media (max-width: 980px) {{
      .shell {{
        grid-template-columns: 1fr;
      }}
      .summary-grid,
      .wardrobe-grid,
      .form-grid,
      .input-row {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div>
        <div class="eyebrow">Sigma Aura</div>
        <h1>Wardrobe Management UI</h1>
      </div>
      <p>Review saved wardrobe items, fix metadata, delete bad entries, and inspect the wardrobe completeness scoring Aura uses for wardrobe-first decisions.</p>
      <div class="pill">Wardrobe-first operating view</div>
      <div class="sidebar-list">
        <div>Browse and edit saved wardrobe items</div>
        <div>Wardrobe completeness scoring for your current rotation</div>
        <div>Wardrobe gap analysis view for missing staples and occasion coverage</div>
      </div>
    </aside>

    <main class="main">
      <section class="main-panel">
        <div class="topline">
          <div>
            <div class="eyebrow" style="color: var(--muted); opacity: 1;">Direct Manager</div>
            <h2>See what Aura thinks is in your closet.</h2>
          </div>
          <a class="btn secondary" href="/?user={initial_user_id}">Back to Chat</a>
        </div>
        <p class="muted">Use a user id to load wardrobe items and the summary that powers wardrobe gap detection.</p>
        <div class="input-row">
          <div class="field">
            <label for="userIdInput">User ID</label>
            <input id="userIdInput" type="text" value="{initial_user_id}" placeholder="user_123" />
          </div>
          <div class="actions" style="justify-content: end; align-self: end;">
            <button class="btn primary" id="loadWardrobeBtn">Load Wardrobe</button>
          </div>
        </div>
        <div id="statusBox" class="status"></div>
      </section>

      <section class="summary-grid">
        <div class="card">
          <div class="eyebrow" style="color: var(--muted); opacity: 1;">Wardrobe Summary</div>
          <div class="metric-value" id="summaryCount">0 items</div>
          <p class="muted" id="summaryText">Load a user to inspect wardrobe coverage.</p>
        </div>
        <div class="card">
          <div class="eyebrow" style="color: var(--muted); opacity: 1;">Completeness Score</div>
          <div class="metric-value" id="completenessScore">0%</div>
          <p class="muted">Wardrobe completeness scoring for user's typical occasion coverage.</p>
        </div>
        <div class="card">
          <div class="eyebrow" style="color: var(--muted); opacity: 1;">Gap Analysis</div>
          <div class="metric-value" id="gapCount">0</div>
          <p class="muted">Wardrobe gap analysis view for missing categories and weak occasion coverage.</p>
        </div>
      </section>

      <section class="wardrobe-grid">
        <div class="card">
          <div class="topline">
            <div>
              <div class="eyebrow" style="color: var(--muted); opacity: 1;">Gaps</div>
              <h3>What is missing</h3>
            </div>
          </div>
          <div class="list" id="gapList"></div>
        </div>
        <div class="card">
          <div class="topline">
            <div>
              <div class="eyebrow" style="color: var(--muted); opacity: 1;">Coverage</div>
              <h3>Occasion coverage</h3>
            </div>
          </div>
          <div class="list" id="coverageList"></div>
        </div>
      </section>

      <section class="main-panel">
        <div class="topline">
          <div>
            <div class="eyebrow" style="color: var(--muted); opacity: 1;">Edit Metadata</div>
            <h2>Update a saved item</h2>
          </div>
        </div>
        <div class="form-grid">
          <div class="field">
            <label for="itemTitle">Title</label>
            <input id="itemTitle" type="text" placeholder="Navy Blazer" />
          </div>
          <div class="field">
            <label for="itemCategory">Category</label>
            <input id="itemCategory" type="text" placeholder="blazer" />
          </div>
          <div class="field">
            <label for="itemSubtype">Subtype</label>
            <input id="itemSubtype" type="text" placeholder="single-breasted blazer" />
          </div>
          <div class="field">
            <label for="itemOccasion">Occasion Fit</label>
            <input id="itemOccasion" type="text" placeholder="office" />
          </div>
          <div class="field">
            <label for="itemPrimaryColor">Primary Color</label>
            <input id="itemPrimaryColor" type="text" placeholder="navy" />
          </div>
          <div class="field">
            <label for="itemFormality">Formality</label>
            <input id="itemFormality" type="text" placeholder="smart_casual" />
          </div>
          <div class="field" style="grid-column: 1 / -1;">
            <label for="itemDescription">Description</label>
            <textarea id="itemDescription" placeholder="Add notes that help Aura reason about this piece."></textarea>
          </div>
          <div class="field" style="grid-column: 1 / -1;">
            <label for="itemNotes">Notes</label>
            <textarea id="itemNotes" placeholder="Fit notes, seasonality, comfort boundaries, or pairing hints."></textarea>
          </div>
        </div>
        <div class="actions">
          <button class="btn primary" id="saveEditBtn" disabled>Save Changes</button>
          <button class="btn secondary" id="clearEditBtn">Clear</button>
          <span class="muted" id="editingState">Pick an item below to edit metadata.</span>
        </div>
      </section>

      <section class="main-panel">
        <div class="topline">
          <div>
            <div class="eyebrow" style="color: var(--muted); opacity: 1;">Saved Items</div>
            <h2>Your wardrobe items</h2>
          </div>
        </div>
        <div id="wardrobeItems" class="wardrobe-grid">
          <div class="empty" style="grid-column: 1 / -1;">Load a user to browse wardrobe items.</div>
        </div>
      </section>
    </main>
  </div>

  <script>
    const state = {{
      userId: {initial_user_id!r},
      items: [],
      summary: null,
      editingId: "",
    }};

    const userIdInput = document.getElementById("userIdInput");
    const statusBox = document.getElementById("statusBox");
    const wardrobeItems = document.getElementById("wardrobeItems");
    const summaryCount = document.getElementById("summaryCount");
    const completenessScore = document.getElementById("completenessScore");
    const summaryText = document.getElementById("summaryText");
    const gapCount = document.getElementById("gapCount");
    const gapList = document.getElementById("gapList");
    const coverageList = document.getElementById("coverageList");
    const editingState = document.getElementById("editingState");
    const saveEditBtn = document.getElementById("saveEditBtn");

    const fieldMap = {{
      title: document.getElementById("itemTitle"),
      description: document.getElementById("itemDescription"),
      garment_category: document.getElementById("itemCategory"),
      garment_subtype: document.getElementById("itemSubtype"),
      occasion_fit: document.getElementById("itemOccasion"),
      primary_color: document.getElementById("itemPrimaryColor"),
      formality_level: document.getElementById("itemFormality"),
      notes: document.getElementById("itemNotes"),
    }};

    function setStatus(message, tone = "ok") {{
      statusBox.textContent = message || "";
      statusBox.className = "status show " + tone;
    }}

    function clearStatus() {{
      statusBox.className = "status";
      statusBox.textContent = "";
    }}

    function renderSummary() {{
      const summary = state.summary;
      summaryCount.textContent = (summary ? summary.count : 0) + " items";
      completenessScore.textContent = (summary ? summary.completeness_score_pct : 0) + "%";
      summaryText.textContent = (summary && summary.summary) ? summary.summary : "Load a user to inspect wardrobe coverage.";
      const gaps = (summary && summary.gap_items) ? summary.gap_items : [];
      gapCount.textContent = String(gaps.length);
      gapList.innerHTML = gaps.length
        ? gaps.map((item) => "<div>" + item + "</div>").join("")
        : '<div>No obvious gaps detected yet.</div>';
      const coverage = (summary && summary.occasion_coverage) ? summary.occasion_coverage : [];
      coverageList.innerHTML = coverage.length
        ? coverage.map((item) => "<div>" + item.label + ": " + item.item_count + " item(s)</div>").join("")
        : '<div>No occasion coverage data yet.</div>';
    }}

    function startEdit(itemId) {{
      const item = state.items.find((entry) => entry.id === itemId);
      if (!item) {{
        return;
      }}
      state.editingId = itemId;
      Object.entries(fieldMap).forEach(([key, element]) => {{
        element.value = item[key] || "";
      }});
      editingState.textContent = "Editing " + (item.title || "wardrobe item") + ".";
      saveEditBtn.disabled = false;
      window.scrollTo({{ top: document.body.scrollHeight * 0.38, behavior: "smooth" }});
    }}

    function clearEdit() {{
      state.editingId = "";
      Object.values(fieldMap).forEach((element) => {{
        element.value = "";
      }});
      editingState.textContent = "Pick an item below to edit metadata.";
      saveEditBtn.disabled = true;
    }}

    function renderItems() {{
      if (!state.items.length) {{
        wardrobeItems.innerHTML = '<div class="empty" style="grid-column: 1 / -1;">No active wardrobe items found for this user yet.</div>';
        return;
      }}
      wardrobeItems.innerHTML = state.items.map((item) => {{
        const tags = [
          item.garment_category,
          item.primary_color,
          item.occasion_fit,
          item.formality_level,
        ].filter(Boolean);
        return `
          <article class="item-card">
            <div class="item-head">
              <div>
                <div class="item-title">${{item.title || "Wardrobe Item"}}</div>
                <div class="muted">${{item.description || "No description saved yet."}}</div>
              </div>
              <div class="tag">${{item.source || "wardrobe"}}</div>
            </div>
            <div class="tag-row">
              ${{tags.map((tag) => `<span class="tag">${{tag}}</span>`).join("") || '<span class="tag">untagged</span>'}}
            </div>
            <div class="actions">
              <button class="btn secondary" data-action="edit" data-id="${{item.id}}">Edit</button>
              <button class="btn danger" data-action="delete" data-id="${{item.id}}">Delete</button>
            </div>
          </article>
        `;
      }}).join("");
    }}

    async function loadWardrobe() {{
      const userId = userIdInput.value.trim();
      if (!userId) {{
        setStatus("Enter a user id first.", "error");
        return;
      }}
      state.userId = userId;
      clearEdit();
      clearStatus();
      try {{
        const [itemsResp, summaryResp] = await Promise.all([
          fetch("/v1/onboarding/wardrobe/" + encodeURIComponent(userId)),
          fetch("/v1/onboarding/wardrobe/" + encodeURIComponent(userId) + "/summary"),
        ]);
        if (!itemsResp.ok || !summaryResp.ok) {{
          throw new Error("Unable to load wardrobe data.");
        }}
        const itemsPayload = await itemsResp.json();
        const summaryPayload = await summaryResp.json();
        state.items = itemsPayload.items || [];
        state.summary = summaryPayload;
        renderItems();
        renderSummary();
        setStatus("Wardrobe loaded.", "ok");
      }} catch (error) {{
        setStatus(error.message || "Unable to load wardrobe data.", "error");
      }}
    }}

    async function saveEdit() {{
      if (!state.editingId || !state.userId) {{
        return;
      }}
      const payload = {{ user_id: state.userId }};
      Object.entries(fieldMap).forEach(([key, element]) => {{
        payload[key] = element.value.trim();
      }});
      try {{
        const resp = await fetch("/v1/onboarding/wardrobe/items/" + encodeURIComponent(state.editingId), {{
          method: "PATCH",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload),
        }});
        if (!resp.ok) {{
          const body = await resp.json().catch(() => ({{}}));
          throw new Error(body.detail || "Unable to update wardrobe item.");
        }}
        await loadWardrobe();
        setStatus("Wardrobe item updated.", "ok");
      }} catch (error) {{
        setStatus(error.message || "Unable to update wardrobe item.", "error");
      }}
    }}

    async function deleteItem(itemId) {{
      if (!state.userId) {{
        return;
      }}
      try {{
        const resp = await fetch("/v1/onboarding/wardrobe/items/" + encodeURIComponent(itemId) + "?user_id=" + encodeURIComponent(state.userId), {{
          method: "DELETE",
        }});
        if (!resp.ok) {{
          const body = await resp.json().catch(() => ({{}}));
          throw new Error(body.detail || "Unable to delete wardrobe item.");
        }}
        if (state.editingId === itemId) {{
          clearEdit();
        }}
        await loadWardrobe();
        setStatus("Wardrobe item deleted.", "ok");
      }} catch (error) {{
        setStatus(error.message || "Unable to delete wardrobe item.", "error");
      }}
    }}

    document.getElementById("loadWardrobeBtn").addEventListener("click", loadWardrobe);
    document.getElementById("saveEditBtn").addEventListener("click", saveEdit);
    document.getElementById("clearEditBtn").addEventListener("click", clearEdit);
    wardrobeItems.addEventListener("click", (event) => {{
      const target = event.target;
      if (!(target instanceof HTMLElement)) {{
        return;
      }}
      const action = target.dataset.action || "";
      const itemId = target.dataset.id || "";
      if (!action || !itemId) {{
        return;
      }}
      if (action === "edit") {{
        startEdit(itemId);
      }} else if (action === "delete") {{
        deleteItem(itemId);
      }}
    }});

    if (state.userId) {{
      loadWardrobe();
    }} else {{
      renderSummary();
    }}
  </script>
</body>
</html>
"""


def get_processing_html(user_id: str = "") -> str:
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet" />
  <title>Sigma Aura Profile Processing</title>
  <style>
    :root {
      --bg: #f6f0ea;
      --surface: #fffaf5;
      --ink: #201915;
      --muted: #6e655f;
      --line: #dfd1c4;
      --accent: #6f2f45;
      --accent-soft: #f3e6ea;
      --warm: #b08a4e;
      --danger: #9b2323;
      --danger-bg: #fceeee;
      --shadow: 0 22px 60px rgba(54, 32, 24, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(184, 139, 150, 0.22), transparent 28%),
        radial-gradient(circle at 85% 12%, rgba(176, 138, 78, 0.14), transparent 24%),
        linear-gradient(180deg, #fbf6f1 0%, #f6f0ea 42%, #f1e6da 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px 16px;
    }
    .shell {
      width: min(100%, 1120px);
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      border-radius: 28px;
      overflow: hidden;
      background: rgba(255, 251, 246, 0.86);
      box-shadow: var(--shadow);
      border: 1px solid rgba(188, 172, 151, 0.45);
    }
    .side {
      padding: 32px 26px;
      background: linear-gradient(180deg, rgba(111, 47, 69, 0.94) 0%, rgba(90, 36, 56, 0.96) 100%);
      color: #f6f2eb;
      display: grid;
      align-content: start;
      gap: 22px;
    }
    .eyebrow {
      font-size: 12px;
      letter-spacing: 0.24em;
      text-transform: uppercase;
      opacity: 0.76;
    }
    .side h1 {
      margin: 0;
      font-family: "Cormorant Garamond", serif;
      font-size: 34px;
      font-weight: 600;
      line-height: 1.05;
    }
    .side p {
      margin: 0;
      font-size: 14px;
      line-height: 1.55;
      color: rgba(246, 242, 235, 0.86);
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.12);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .steps {
      display: grid;
      gap: 10px;
    }
    .step-item {
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.08);
      font-size: 13px;
      line-height: 1.45;
    }
    .main {
      padding: 28px;
      display: grid;
      gap: 18px;
    }
    .card {
      background: var(--surface);
      border: 1px solid rgba(188, 172, 151, 0.45);
      border-radius: 24px;
      padding: 24px;
    }
    .status {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }
    .status h2 {
      margin: 0 0 6px;
      font-size: 28px;
    }
    .status p {
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
      font-size: 14px;
    }
    .status-badge {
      padding: 10px 14px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 700;
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .progress {
      width: 100%;
      height: 10px;
      border-radius: 999px;
      background: #efe6dc;
      overflow: hidden;
      margin-top: 14px;
    }
    .progress-bar {
      width: 14%;
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent) 0%, #b08a4e 100%);
      transition: width 300ms ease;
    }
    .error {
      display: none;
      padding: 12px 14px;
      border-radius: 14px;
      background: var(--danger-bg);
      color: var(--danger);
      font-size: 13px;
    }
    .error.show {
      display: block;
    }
    .agent-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }
    .agent-card {
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      background: #fff;
      display: grid;
      gap: 12px;
    }
    .agent-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    .agent-card h3 {
      margin: 0;
      font-size: 16px;
    }
    .agent-card p {
      margin: 0;
      font-size: 13px;
      color: var(--muted);
      line-height: 1.45;
    }
    .agent-rerun-btn {
      padding: 10px 12px;
      font-size: 12px;
      border-radius: 12px;
      white-space: nowrap;
    }
    .results {
      display: grid;
      gap: 16px;
    }
    .profile-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .profile-item {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px 16px;
      background: #fff;
    }
    .profile-item label {
      display: block;
      margin-bottom: 6px;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 700;
    }
    .profile-item div {
      font-size: 15px;
      line-height: 1.4;
      word-break: break-word;
    }
    .result-group {
      border: 1px solid var(--line);
      border-radius: 18px;
      overflow: hidden;
      background: #fff;
    }
    .result-group-header {
      padding: 14px 18px;
      background: #f8f4ee;
      border-bottom: 1px solid var(--line);
      font-size: 13px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 700;
    }
    .row {
      display: grid;
      grid-template-columns: 180px 1fr 100px;
      gap: 12px;
      padding: 14px 18px;
      border-bottom: 1px solid #efe7dd;
      align-items: start;
    }
    .row:last-child {
      border-bottom: none;
    }
    .attr-name {
      font-weight: 700;
      font-size: 14px;
    }
    .attr-value {
      font-size: 14px;
      line-height: 1.45;
    }
    .attr-value small {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
    }
    .confidence {
      justify-self: end;
      padding: 7px 10px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
    }
    .actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 8px;
    }
    button {
      border: none;
      border-radius: 16px;
      padding: 14px 18px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
    }
    button.primary {
      background: var(--accent);
      color: #fff;
    }
    button.secondary {
      background: #fff;
      color: var(--ink);
      border: 1px solid var(--line);
    }
    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .hidden {
      display: none;
    }
    @media (max-width: 920px) {
      .shell {
        grid-template-columns: 1fr;
      }
      .profile-grid,
      .agent-grid,
      .row {
        grid-template-columns: 1fr;
      }
      .main {
        padding: 18px;
      }
      .confidence {
        justify-self: start;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="side">
      <div>
        <div class="eyebrow">Sigma Aura</div>
        <h1>Profile processing in progress.</h1>
      </div>
      <p>Three independent analysis sub-agents are running on the onboarding inputs. Results will be stored locally and rendered here as soon as all agents complete.</p>
      <div class="pill" id="userPill">User __USER_ID__</div>
      <div class="steps">
        <div class="step-item"><strong>Body type analysis</strong><br />Gender, age, height, waist and full body image.</div>
        <div class="step-item"><strong>Color analysis 1</strong><br />Skin surface color, hair, eyes from headshot.</div>

        <div class="step-item"><strong>Other details</strong><br />Face shape, neck, hair, jawline and shoulder slope.</div>
      </div>
    </aside>

    <main class="main">
      <section class="card">
        <div class="status">
          <div>
            <h2 id="statusTitle">Preparing analysis run</h2>
            <p id="statusText">The profile processing screen starts automatically once onboarding is complete.</p>
          </div>
          <div class="status-badge" id="statusBadge">Pending</div>
        </div>
        <div class="progress"><div class="progress-bar" id="progressBar"></div></div>
        <div class="error" id="errorBox"></div>
      <div class="actions">
          <button class="secondary hidden" id="retryBtn">Retry Analysis</button>
          <button class="secondary hidden" id="rerunBtn">Re-Run Analysis</button>
          <button class="secondary" id="logoutBtn">Logout</button>
          <button class="primary hidden" id="openPlatformBtn">Open Aura</button>
        </div>
      </section>

      <section class="card">
        <div class="result-group">
          <div class="result-group-header">Stored Profile Details</div>
          <div class="profile-grid" id="profileGrid"></div>
        </div>
      </section>

      <section class="card">
        <div class="agent-grid" id="agentGrid">
          <div class="agent-card">
            <div class="agent-head"><h3>Body Type Analysis</h3><button class="secondary hidden agent-rerun-btn" data-agent="body_type_analysis">Re-Run This Section</button></div>
            <p id="agent-body_type_analysis">Waiting to start.</p>
          </div>
          <div class="agent-card">
            <div class="agent-head"><h3>Color Analysis 1</h3><button class="secondary hidden agent-rerun-btn" data-agent="color_analysis_headshot">Re-Run This Section</button></div>
            <p id="agent-color_analysis_headshot">Waiting to start.</p>
          </div>
          <div class="agent-card">
            <div class="agent-head"><h3>Other Details</h3><button class="secondary hidden agent-rerun-btn" data-agent="other_details_analysis">Re-Run This Section</button></div>
            <p id="agent-other_details_analysis">Waiting to start.</p>
          </div>
        </div>
      </section>

      <section class="card hidden" id="resultsCard">
        <div class="results" id="results"></div>
      </section>
    </main>
  </div>

  <script>
    const userId = "__USER_ID__";
    const statusTitle = document.getElementById("statusTitle");
    const statusText = document.getElementById("statusText");
    const statusBadge = document.getElementById("statusBadge");
    const progressBar = document.getElementById("progressBar");
    const errorBox = document.getElementById("errorBox");
    const retryBtn = document.getElementById("retryBtn");
    const rerunBtn = document.getElementById("rerunBtn");
    const logoutBtn = document.getElementById("logoutBtn");
    const openPlatformBtn = document.getElementById("openPlatformBtn");
    const resultsCard = document.getElementById("resultsCard");
    const resultsWrap = document.getElementById("results");
    const profileGrid = document.getElementById("profileGrid");
    const agentRerunButtons = Array.from(document.querySelectorAll(".agent-rerun-btn"));

    const AGENT_LABELS = {
      body_type_analysis: "Body type analysis",
      color_analysis_headshot: "Color analysis 1",
      other_details_analysis: "Other details"
    };

    function showError(message) {
      errorBox.textContent = message;
      errorBox.classList.add("show");
    }

    function hideError() {
      errorBox.textContent = "";
      errorBox.classList.remove("show");
    }

    function extractError(data, fallback) {
      if (!data) return fallback;
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail)) return data.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
      return data.message || fallback;
    }

    async function postJson(url, payload, fallback) {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(extractError(data, fallback));
      return data;
    }

    function setAgentText(agentName, text) {
      const node = document.getElementById("agent-" + agentName);
      if (node) node.textContent = text;
    }

    function setAgentRerunVisibility(show) {
      agentRerunButtons.forEach((button) => {
        button.classList.toggle("hidden", !show);
        button.disabled = !show;
      });
    }

    function renderProfile(profile) {
      profileGrid.innerHTML = "";
      const ordered = [
        ["Mobile Number", profile.mobile || ""],
        ["Name", profile.name || ""],
        ["Date of Birth", profile.date_of_birth || ""],
        ["Gender", profile.gender || ""],
        ["Height (cm)", profile.height_cm || ""],
        ["Waist (cm)", profile.waist_cm || ""],
        ["Profession", profile.profession || ""],
        ["Primary Archetype", ((profile.style_preference || {}).primaryArchetype) || ""],
        ["Secondary Archetype", ((profile.style_preference || {}).secondaryArchetype) || ""],
        ["Risk Tolerance", ((profile.style_preference || {}).riskTolerance) || ""],
        ["Formality Lean", ((profile.style_preference || {}).formalityLean) || ""],
        ["Pattern Type", ((profile.style_preference || {}).patternType) || ""]
      ];
      ordered.forEach(([label, value]) => {
        const item = document.createElement("div");
        item.className = "profile-item";
        item.innerHTML = `
          <label>${label}</label>
          <div>${value || "-"}</div>
        `;
        profileGrid.appendChild(item);
      });
    }

    function renderStatus(status) {
      const state = status.status || "not_started";
      const grouped = status.grouped_attributes || {};
      renderProfile(status.profile || {});
      statusBadge.textContent = state.replace(/_/g, " ");

        if (state === "completed") {
          statusTitle.textContent = "Profile analysis complete";
          statusText.textContent = "All four sub-agents finished, the collated analysis has been saved, and the values below are the stored output.";
        progressBar.style.width = "100%";
        retryBtn.classList.add("hidden");
        rerunBtn.classList.remove("hidden");
        openPlatformBtn.classList.remove("hidden");
        setAgentRerunVisibility(true);
        hideError();
        Object.keys(AGENT_LABELS).forEach((agentName) => {
          const count = Object.keys(grouped[agentName] || {}).length;
          setAgentText(agentName, count ? count + " attributes saved." : "Completed.");
        });
        renderResults(grouped, status.derived_interpretations || {});
        return;
      }

      if (state === "failed") {
        statusTitle.textContent = "Profile analysis failed";
        statusText.textContent = "The run did not complete. You can retry the analysis from this screen.";
        progressBar.style.width = "100%";
        retryBtn.classList.remove("hidden");
        rerunBtn.classList.add("hidden");
        openPlatformBtn.classList.add("hidden");
        setAgentRerunVisibility(true);
        showError(status.error_message || "Analysis failed.");
        return;
      }

      const progressByState = {
        not_started: 14,
        pending: 24,
        running: 68
      };
      progressBar.style.width = (progressByState[state] || 18) + "%";
      statusTitle.textContent = "Processing profile analysis";
      statusText.textContent = "The analysis agents are running independently and the page will update when all saved outputs are ready.";
      retryBtn.classList.add("hidden");
      rerunBtn.classList.add("hidden");
      openPlatformBtn.classList.add("hidden");
      setAgentRerunVisibility(false);
      hideError();

      Object.keys(AGENT_LABELS).forEach((agentName) => {
        const output = status.agent_outputs && status.agent_outputs[agentName];
        const count = output ? Object.keys(output).length : 0;
        setAgentText(agentName, count ? count + " attributes prepared." : "Running or waiting.");
      });
    }

    function renderResults(grouped, derivedInterpretations) {
      resultsWrap.innerHTML = "";
      const derivedNames = Object.keys(derivedInterpretations || {});
      if (derivedNames.length) {
        const group = document.createElement("div");
        group.className = "result-group";
        const header = document.createElement("div");
        header.className = "result-group-header";
        header.textContent = "Deterministic Interpretations";
        group.appendChild(header);
        derivedNames.forEach((name) => {
          const item = derivedInterpretations[name];
          const row = document.createElement("div");
          row.className = "row";
          row.innerHTML = `
            <div class="attr-name">${name}</div>
            <div class="attr-value">
              ${item.value}
              <small>${item.evidence_note || ""}</small>
            </div>
            <div class="confidence">${Math.round((item.confidence || 0) * 100)}%</div>
          `;
          group.appendChild(row);
        });
        resultsWrap.appendChild(group);
      }
      Object.keys(AGENT_LABELS).forEach((agentName) => {
        const values = grouped[agentName] || {};
        const names = Object.keys(values);
        if (!names.length) return;
        const group = document.createElement("div");
        group.className = "result-group";
        const header = document.createElement("div");
        header.className = "result-group-header";
        header.textContent = AGENT_LABELS[agentName];
        group.appendChild(header);
        names.forEach((name) => {
          const item = values[name];
          const row = document.createElement("div");
          row.className = "row";
          row.innerHTML = `
            <div class="attr-name">${name}</div>
            <div class="attr-value">
              ${item.value}
              <small>${item.evidence_note || ""}</small>
            </div>
            <div class="confidence">${Math.round((item.confidence || 0) * 100)}%</div>
          `;
          group.appendChild(row);
        });
        resultsWrap.appendChild(group);
      });
      resultsCard.classList.remove("hidden");
    }

    async function fetchStatus() {
      const response = await fetch("/v1/onboarding/analysis/" + encodeURIComponent(userId));
      const data = await response.json();
      if (!response.ok) throw new Error(extractError(data, "Unable to load analysis status"));
      return data;
    }

    async function ensureStarted() {
      return await postJson("/v1/onboarding/analysis/start", { user_id: userId }, "Unable to start analysis");
    }

    async function poll() {
      while (true) {
        const status = await fetchStatus();
        renderStatus(status);
        if (status.status === "completed" || status.status === "failed") return;
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
    }

    async function startFlow() {
      if (!userId) {
        showError("Missing user id for processing screen.");
        return;
      }
      hideError();
      try {
        const current = await fetchStatus();
        renderStatus(current);
        if (current.status !== "completed") {
          await ensureStarted();
          await poll();
        }
      } catch (error) {
        showError(String(error.message || error));
        retryBtn.classList.remove("hidden");
      }
    }

    retryBtn.addEventListener("click", async () => {
      retryBtn.disabled = true;
      try {
        await ensureStarted();
        await poll();
      } catch (error) {
        showError(String(error.message || error));
      } finally {
        retryBtn.disabled = false;
      }
    });

    rerunBtn.addEventListener("click", async () => {
      rerunBtn.disabled = true;
      openPlatformBtn.disabled = true;
      statusBadge.textContent = "rerunning";
      statusTitle.textContent = "Re-running profile analysis";
      statusText.textContent = "The saved analysis is being regenerated from the onboarding inputs.";
      progressBar.style.width = "24%";
      hideError();
      try {
        await postJson("/v1/onboarding/analysis/rerun", { user_id: userId }, "Unable to re-run analysis");
        await poll();
      } catch (error) {
        showError(String(error.message || error));
      } finally {
        rerunBtn.disabled = false;
        openPlatformBtn.disabled = false;
      }
    });

    logoutBtn.addEventListener("click", () => {
      window.location.href = "/";
    });

    agentRerunButtons.forEach((button) => {
      button.addEventListener("click", async () => {
        const agentName = button.dataset.agent || "";
        if (!agentName) return;
        button.disabled = true;
        hideError();
        statusTitle.textContent = "Re-running " + (AGENT_LABELS[agentName] || "analysis section");
        statusText.textContent = "The selected section is being regenerated and the saved interpretation will refresh when it completes.";
        try {
          await postJson("/v1/onboarding/analysis/rerun-agent", { user_id: userId, agent_name: agentName }, "Unable to re-run selected analysis section.");
          await poll();
        } catch (error) {
          showError(error.message || "Unable to re-run selected analysis section.");
          button.disabled = false;
        }
      });
    });

    openPlatformBtn.addEventListener("click", () => {
      window.location.href = "/?user=" + encodeURIComponent(userId) + "&view=chat";
    });

    startFlow();
  </script>
</body>
</html>
"""
    return html.replace("__USER_ID__", escape(user_id or "", quote=True))
