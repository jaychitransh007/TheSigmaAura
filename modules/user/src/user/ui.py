from html import escape


def get_onboarding_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sigma Aura Onboarding</title>
  <style>
    :root {
      --bg: #f3ece3;
      --surface: rgba(255, 251, 246, 0.94);
      --surface-strong: #fffdf9;
      --ink: #1c1b19;
      --muted: #6c665d;
      --line: #d8cec1;
      --line-strong: #bcac97;
      --accent: #1f6f5f;
      --accent-soft: #e3efe9;
      --accent-warm: #b7742a;
      --danger: #9b2323;
      --danger-bg: #fceeee;
      --shadow: 0 22px 60px rgba(45, 36, 24, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #f8e7d0 0%, rgba(248, 231, 208, 0.35) 28%, transparent 55%),
        radial-gradient(circle at bottom right, #dfeee8 0%, rgba(223, 238, 232, 0.45) 24%, transparent 52%),
        linear-gradient(135deg, #f6f0e9 0%, #f0e6dc 46%, #ece4da 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px 16px;
    }
    .shell {
      width: min(100%, 1040px);
      display: grid;
      grid-template-columns: minmax(0, 360px) minmax(0, 1fr);
      border: 1px solid rgba(188, 172, 151, 0.45);
      border-radius: 28px;
      overflow: hidden;
      background: rgba(255, 251, 246, 0.72);
      box-shadow: var(--shadow);
      backdrop-filter: blur(16px);
    }
    .sidebar {
      padding: 36px 28px;
      background:
        linear-gradient(180deg, rgba(31, 111, 95, 0.92) 0%, rgba(24, 90, 77, 0.94) 100%);
      color: #f6f2eb;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }
    .eyebrow {
      font-size: 12px;
      letter-spacing: 0.24em;
      text-transform: uppercase;
      opacity: 0.74;
    }
    .sidebar h1 {
      margin: 0;
      font-size: 34px;
      line-height: 1.02;
      letter-spacing: 0.01em;
    }
    .sidebar p {
      margin: 0;
      color: rgba(246, 242, 235, 0.84);
      line-height: 1.55;
      font-size: 14px;
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
      padding: 28px;
      background: var(--surface);
      display: flex;
      flex-direction: column;
      gap: 18px;
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
      background: var(--accent-warm);
    }
    .panel {
      border: 1px solid rgba(188, 172, 151, 0.45);
      border-radius: 24px;
      padding: 28px;
      background: var(--surface-strong);
      min-height: 560px;
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
      min-height: 200px;
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
      .shell {
        grid-template-columns: 1fr;
      }
      .sidebar {
        padding: 28px 22px 20px;
      }
      .main {
        padding: 18px;
      }
      .panel {
        min-height: 0;
        padding: 22px 18px;
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
        <h1>Onboard before you enter the conversation studio.</h1>
      </div>
      <p>This first pass collects the profile details, three reference photos, and a final style-archetype preference profile before downstream analysis begins.</p>
      <div class="status-card">
        <strong>OTP for local testing</strong>
        <div class="otp-pill">123456</div>
      </div>
      <div class="checklist">
        <strong>What we collect now</strong>
        <div class="checklist-item"><span class="check-icon">1</span><span>Mobile and OTP verification</span></div>
        <div class="checklist-item"><span class="check-icon">2</span><span>Name, birth date, gender, height and waist</span></div>
        <div class="checklist-item"><span class="check-icon">3</span><span>Profession from a fixed set of values</span></div>
        <div class="checklist-item"><span class="check-icon">4</span><span>Full body, headshot, and vein reference photos</span></div>
        <div class="checklist-item"><span class="check-icon">5</span><span>Progressive 8-archetype style preference selection</span></div>
      </div>
    </aside>

    <main class="main">
      <div class="topline">
        <div class="step-meta" id="stepMeta">Step 1 of 11</div>
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

        <div class="step" id="step-dob">
          <h2 class="step-title">Add your date of birth.</h2>
          <p class="step-desc">Use the calendar selector so the value is normalized before it is stored.</p>
          <div class="field">
            <label for="dobInput">Date of Birth</label>
            <input id="dobInput" type="date" />
          </div>
          <div class="error" id="dobErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="2">Back</button>
            <button class="btn primary" id="dobNextBtn">Continue</button>
          </div>
        </div>

        <div class="step" id="step-gender">
          <h2 class="step-title">Select gender.</h2>
          <p class="step-desc">This remains a fixed set for now and feeds the local profile record.</p>
          <div class="choice-grid cols-2" id="genderGrid"></div>
          <input id="genderInput" type="hidden" />
          <div class="error" id="genderErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="3">Back</button>
            <button class="btn primary" id="genderNextBtn">Continue</button>
          </div>
        </div>

        <div class="step" id="step-body">
          <h2 class="step-title">Capture core body measurements.</h2>
          <p class="step-desc">Height and waist are stored in centimeters for fit-related downstream analysis.</p>
          <div class="grid-2">
            <div class="field">
              <label for="heightInput">Height (cm)</label>
              <input id="heightInput" type="number" min="50" max="300" step="0.1" placeholder="170" />
            </div>
            <div class="field">
              <label for="waistInput">Waist (cm)</label>
              <input id="waistInput" type="number" min="30" max="200" step="0.1" placeholder="80" />
            </div>
          </div>
          <div class="error" id="bodyErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="4">Back</button>
            <button class="btn primary" id="bodyNextBtn">Continue</button>
          </div>
        </div>

        <div class="step" id="step-profession">
          <h2 class="step-title">Choose your profession.</h2>
          <p class="step-desc">This is a controlled list right now so the profile schema stays stable.</p>
          <div class="choice-grid cols-2" id="professionGrid"></div>
          <input id="professionInput" type="hidden" />
          <div class="error" id="professionErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="5">Back</button>
            <button class="btn primary" id="professionNextBtn">Save Profile</button>
          </div>
        </div>

        <div class="step" id="step-img-fullbody">
          <h2 class="step-title">Upload your full body reference.</h2>
          <p class="step-desc">Use a top-to-toe image. After selecting a photo, position it inside the fixed 2:3 frame before upload.</p>
          <div class="image-card">
            <div class="uploader">
              <div class="dropzone" id="dropzone-fullbody">
                <div>
                  <strong>Select full body image</strong>
                  <div class="caption">Standing pose, full frame, good lighting.</div>
                </div>
              </div>
              <input id="input-fullbody" type="file" accept="image/*" hidden />
              <div class="crop-shell" id="crop-shell-fullbody">
                <div class="crop-stage">
                  <canvas class="crop-canvas" id="canvas-fullbody" width="800" height="1200"></canvas>
                  <div class="crop-overlay"></div>
                  <div class="ratio-badge">2:3 frame</div>
                </div>
                <div class="crop-controls">
                  <div class="zoom-row">
                    <span>Zoom</span>
                    <input id="zoom-fullbody" type="range" min="1" max="4" step="0.01" value="1" />
                    <button class="btn ghost" type="button" id="change-fullbody">Change Photo</button>
                  </div>
                  <div class="caption">Drag the image to reposition it inside the frame. The saved output will match this 2:3 crop.</div>
                </div>
              </div>
            </div>
          </div>
          <div class="error" id="fullbodyErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="6">Back</button>
            <button class="btn primary" id="uploadFullbodyBtn">Upload and Continue</button>
          </div>
        </div>

        <div class="step" id="step-img-headshot">
          <h2 class="step-title">Upload your headshot.</h2>
          <p class="step-desc">Use a face-forward shot. Position it inside the same 2:3 frame before upload.</p>
          <div class="image-card">
            <div class="uploader">
              <div class="dropzone" id="dropzone-headshot">
                <div>
                  <strong>Select headshot image</strong>
                  <div class="caption">Clear face visibility, neutral expression, even light.</div>
                </div>
              </div>
              <input id="input-headshot" type="file" accept="image/*" hidden />
              <div class="crop-shell" id="crop-shell-headshot">
                <div class="crop-stage">
                  <canvas class="crop-canvas" id="canvas-headshot" width="800" height="1200"></canvas>
                  <div class="crop-overlay"></div>
                  <div class="ratio-badge">2:3 frame</div>
                </div>
                <div class="crop-controls">
                  <div class="zoom-row">
                    <span>Zoom</span>
                    <input id="zoom-headshot" type="range" min="1" max="4" step="0.01" value="1" />
                    <button class="btn ghost" type="button" id="change-headshot">Change Photo</button>
                  </div>
                  <div class="caption">Drag and adjust until the crop is correct, then upload.</div>
                </div>
              </div>
            </div>
          </div>
          <div class="error" id="headshotErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="7">Back</button>
            <button class="btn primary" id="uploadHeadshotBtn">Upload and Continue</button>
          </div>
        </div>

        <div class="step" id="step-img-veins">
          <h2 class="step-title">Upload the vein reference image.</h2>
          <p class="step-desc">Use a clear veins image, typically from the inner wrist or similar visible vein area, then adjust it in the same frame.</p>
          <div class="image-card">
            <div class="uploader">
              <div class="dropzone" id="dropzone-veins">
                <div>
                  <strong>Select vein reference image</strong>
                  <div class="caption">Natural light helps. Keep the vein area sharp and centered.</div>
                </div>
              </div>
              <input id="input-veins" type="file" accept="image/*" hidden />
              <div class="crop-shell" id="crop-shell-veins">
                <div class="crop-stage">
                  <canvas class="crop-canvas" id="canvas-veins" width="800" height="1200"></canvas>
                  <div class="crop-overlay"></div>
                  <div class="ratio-badge">2:3 frame</div>
                </div>
                <div class="crop-controls">
                  <div class="zoom-row">
                    <span>Zoom</span>
                    <input id="zoom-veins" type="range" min="1" max="4" step="0.01" value="1" />
                    <button class="btn ghost" type="button" id="change-veins">Change Photo</button>
                  </div>
                  <div class="caption">The uploaded image will be the cropped 2:3 output shown in the frame.</div>
                </div>
              </div>
            </div>
          </div>
          <div class="error" id="veinsErr"></div>
          <div class="actions">
            <button class="btn secondary" data-back="8">Back</button>
            <button class="btn primary" id="uploadVeinsBtn">Upload and Continue</button>
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
            <button class="btn secondary" data-back="9">Back</button>
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
    const STEP_ORDER = [
      "mobile",
      "otp",
      "name",
      "dob",
      "gender",
      "body",
      "profession",
      "img-fullbody",
      "img-headshot",
      "img-veins",
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
        errorId: "fullbodyErr",
        nextStep: 8
      },
      headshot: {
        category: "headshot",
        errorId: "headshotErr",
        nextStep: 9
      },
      veins: {
        category: "veins",
        errorId: "veinsErr",
        nextStep: 10
      }
    };
    const REQUIRED_IMAGE_CATEGORIES = ["full_body", "headshot", "veins"];

    const state = {
      currentStep: 0,
      userId: "",
      cropper: {
        fullbody: createCropState("fullbody"),
        headshot: createCropState("headshot"),
        veins: createCropState("veins")
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

    function determineResumeDestination(status) {
      const uploaded = Array.isArray(status.images_uploaded) ? status.images_uploaded : [];
      const hasAllImages = REQUIRED_IMAGE_CATEGORIES.every((category) => uploaded.includes(category));

      if (status.onboarding_complete || (status.profile_complete && hasAllImages && status.style_preference_complete)) {
        return { type: "processing" };
      }
      if (status.profile_complete) {
        if (!uploaded.includes("full_body")) return { type: "step", index: 7 };
        if (!uploaded.includes("headshot")) return { type: "step", index: 8 };
        if (!uploaded.includes("veins")) return { type: "step", index: 9 };
        if (!status.style_preference_complete) return { type: "step", index: 10 };
        return { type: "processing" };
      }
      return { type: "step", index: 2 };
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
        if (key === "veins") {
          state.style.loaded = false;
          setStep(details.nextStep);
          return;
        }
        setStep(details.nextStep);
      } catch (error) {
        showError(errorId, String(error.message || error));
      } finally {
        button.disabled = false;
        button.textContent = nextLabel;
      }
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
          const statusResponse = await fetch("/v1/onboarding/status/" + encodeURIComponent(state.userId));
          const status = await statusResponse.json();
          if (!statusResponse.ok) {
            throw new Error(extractError(status, "Unable to load onboarding status"));
          }
          const destination = determineResumeDestination(status);
          if (destination.type === "processing") {
            window.location.href = "/onboard/processing?user=" + encodeURIComponent(state.userId);
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

      document.getElementById("nameNextBtn").addEventListener("click", () => {
        hideError("nameErr");
        const name = document.getElementById("nameInput").value.trim();
        if (!name) {
          showError("nameErr", "Name is required.");
          return;
        }
        setStep(3);
      });

      document.getElementById("dobNextBtn").addEventListener("click", () => {
        hideError("dobErr");
        const dob = document.getElementById("dobInput").value;
        if (!dob) {
          showError("dobErr", "Date of birth is required.");
          return;
        }
        setStep(4);
      });

      document.getElementById("genderNextBtn").addEventListener("click", () => {
        hideError("genderErr");
        if (!document.getElementById("genderInput").value) {
          showError("genderErr", "Select a gender option.");
          return;
        }
        setStep(5);
      });

      document.getElementById("bodyNextBtn").addEventListener("click", () => {
        hideError("bodyErr");
        const height = parseFloat(document.getElementById("heightInput").value);
        const waist = parseFloat(document.getElementById("waistInput").value);
        if (!Number.isFinite(height) || height < 50 || height > 300) {
          showError("bodyErr", "Enter height between 50 and 300 cm.");
          return;
        }
        if (!Number.isFinite(waist) || waist < 30 || waist > 200) {
          showError("bodyErr", "Enter waist between 30 and 200 cm.");
          return;
        }
        setStep(6);
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
          setStep(7);
        } catch (error) {
          showError("professionErr", String(error.message || error));
        } finally {
          button.disabled = false;
          button.textContent = "Save Profile";
        }
      });

      document.getElementById("uploadFullbodyBtn").addEventListener("click", () => {
        uploadImage("fullbody", "uploadFullbodyBtn", "Upload and Continue");
      });
      document.getElementById("uploadHeadshotBtn").addEventListener("click", () => {
        uploadImage("headshot", "uploadHeadshotBtn", "Upload and Continue");
      });
      document.getElementById("uploadVeinsBtn").addEventListener("click", () => {
        uploadImage("veins", "uploadVeinsBtn", "Upload and Continue");
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
          window.location.href = "/onboard/processing?user=" + encodeURIComponent(state.userId);
        } catch (error) {
          showError("styleErr", String(error.message || error));
        } finally {
          button.disabled = !(state.style.selectedEvents.length >= 3 && state.style.selectedEvents.length <= 5);
          button.textContent = "Continue to Profile Processing";
        }
      });

      document.getElementById("goToPlatformBtn").addEventListener("click", () => {
        window.location.href = "/?user=" + encodeURIComponent(state.userId);
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


def get_processing_html(user_id: str = "") -> str:
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sigma Aura Profile Processing</title>
  <style>
    :root {
      --bg: #f3ece3;
      --surface: #fffdf9;
      --ink: #1c1b19;
      --muted: #6c665d;
      --line: #d8cec1;
      --accent: #1f6f5f;
      --accent-soft: #e3efe9;
      --warm: #b7742a;
      --danger: #9b2323;
      --danger-bg: #fceeee;
      --shadow: 0 22px 60px rgba(45, 36, 24, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #f8e7d0 0%, rgba(248, 231, 208, 0.35) 28%, transparent 55%),
        radial-gradient(circle at bottom right, #dfeee8 0%, rgba(223, 238, 232, 0.45) 24%, transparent 52%),
        linear-gradient(135deg, #f6f0e9 0%, #f0e6dc 46%, #ece4da 100%);
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
      background: linear-gradient(180deg, rgba(31, 111, 95, 0.94) 0%, rgba(24, 90, 77, 0.96) 100%);
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
      font-size: 32px;
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
      background: linear-gradient(90deg, var(--accent) 0%, var(--warm) 100%);
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
      <p>Four independent analysis sub-agents are running on the onboarding inputs. Results will be stored locally and rendered here as soon as all agents complete.</p>
      <div class="pill" id="userPill">User __USER_ID__</div>
      <div class="steps">
        <div class="step-item"><strong>Body type analysis</strong><br />Gender, age, height, waist and full body image.</div>
        <div class="step-item"><strong>Color analysis 1</strong><br />Skin surface color, hair, eyes from headshot.</div>
        <div class="step-item"><strong>Color analysis 2</strong><br />Skin undertone from vein reference image.</div>
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
            <div class="agent-head"><h3>Color Analysis 2</h3><button class="secondary hidden agent-rerun-btn" data-agent="color_analysis_veins">Re-Run This Section</button></div>
            <p id="agent-color_analysis_veins">Waiting to start.</p>
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
      color_analysis_veins: "Color analysis 2",
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
      window.location.href = "/?user=" + encodeURIComponent(userId);
    });

    startFlow();
  </script>
</body>
</html>
"""
    return html.replace("__USER_ID__", escape(user_id or "", quote=True))
