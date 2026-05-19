/* V.3 — Virtual Try On modal controller (vanilla ES module).
 *
 * Lives in the storefront as a theme app extension asset. Pairs with
 * `blocks/virtual-try-on.liquid` (button + data attributes) and
 * `assets/virtual-try-on.css` (modal/card styles).
 *
 * Flow on click:
 *   1. Mint or read localStorage["vibe_session_id"] — same UUID the
 *      in-app Vibe Conversation uses, so a customer who uploaded a
 *      body photo there doesn't need to re-upload here (and vice
 *      versa).
 *   2. Open a native <dialog>. Two cards side by side:
 *        Card A — body-photo picker. File input is full-bleed; once a
 *                 file is chosen we preview it, POST to
 *                 /apps/vibe/api/onboarding/image (category=full_body),
 *                 and kick off the try-on as soon as the upload
 *                 returns 2xx.
 *        Card B — try-on result. Blank until upload completes, then
 *                 spinner + "Rendering…" status, then the rendered
 *                 image.
 *   3. Engine refusals (missing_person_image, quality_gate_failed) are
 *      surfaced as inline friendly text in card B — the customer can
 *      retry by picking a different photo without closing the modal.
 *
 * Notes:
 *   - Endpoints are routed through the App Proxy (/apps/vibe/*) and
 *     therefore inherit HMAC validation on the vibe-app side. Nothing
 *     special to do client-side.
 *   - Uses no framework. The block can be added to any theme without
 *     pulling in React/Vue/etc.
 *   - <dialog>.showModal() handles focus trap, Escape-to-close, and
 *     inert-when-closed. We add a backdrop click handler manually
 *     since <dialog>'s default behaviour is to ignore clicks on
 *     ::backdrop.
 */

(function () {
  "use strict";

  if (typeof window === "undefined") return;

  // Stays in sync with vibe-app/app/lib/session.client.ts. If you
  // change one, change the other — the whole point is that the body
  // photo a customer uploads on the storefront PDP modal is the same
  // photo Vibe Conversation already has on file.
  var SESSION_KEY = "vibe_session_id";
  var UPLOAD_ENDPOINT = "/apps/vibe/api/onboarding/image";
  var TRYON_ENDPOINT = "/apps/vibe/api/tryon";

  function getOrMintSessionId() {
    try {
      var existing = window.localStorage.getItem(SESSION_KEY);
      if (existing && existing.length > 0) return existing;
    } catch (_) {
      // Safari private mode + cookies disabled → localStorage throws.
      // Fall through to in-memory id so the modal still works for the
      // duration of this page load.
    }
    var minted = uuidv4();
    try {
      window.localStorage.setItem(SESSION_KEY, minted);
    } catch (_) {
      // ignore; we'll just use a fresh id each session
    }
    return minted;
  }

  function uuidv4() {
    // crypto.randomUUID() is widely available (>=Safari 15.4, Chrome
    // 92). Fall back to a Math.random()-seeded synthesizer for very
    // old browsers; an opaque session id doesn't need cryptographic
    // strength.
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  // ── Modal lifecycle ────────────────────────────────────────────────

  function openModalForBlock(block) {
    var modalTitle = block.getAttribute("data-modal-title") || "See it on you";
    var modalSubtitle =
      block.getAttribute("data-modal-subtitle") ||
      "Upload a full-body photo (head to toe, arms relaxed). I'll render this piece on you in a few seconds.";
    var productImageUrl = block.getAttribute("data-product-image") || "";

    if (!productImageUrl) {
      // The block must carry the garment URL; nothing useful to do
      // without it. Silent no-op rather than a crash — the merchant
      // probably hasn't set a featured image on the product yet.
      // eslint-disable-next-line no-console
      console.warn(
        "[vibe-tryon] No product image; aborting open.",
        block,
      );
      return;
    }

    var dialog = buildDialog(modalTitle, modalSubtitle);
    document.body.appendChild(dialog);

    var state = {
      sessionId: getOrMintSessionId(),
      productImageUrl: productImageUrl,
      uploading: false,
      rendering: false,
      uploadedFile: null,
    };

    wireDialog(dialog, state);

    // showModal() needs to run after the element is in the DOM,
    // otherwise Firefox throws.
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      // <dialog> polyfill skipped — Safari has supported it since
      // 15.4. If we hit a browser without it, fall back to attribute
      // + manual class so the customer can still see the modal even
      // if focus management isn't perfect.
      dialog.setAttribute("open", "");
      dialog.classList.add("vibe-tryon-modal--polyfill");
    }
  }

  function buildDialog(title, subtitle) {
    var dialog = document.createElement("dialog");
    dialog.className = "vibe-tryon-modal";
    dialog.setAttribute("aria-labelledby", "vibe-tryon-title");

    // Plain string + innerHTML is acceptable here: every interpolated
    // value comes from the merchant-controlled theme settings or
    // static strings. No customer-supplied input is rendered.
    dialog.innerHTML =
      '<button type="button" class="vibe-tryon-modal__close" aria-label="Close" data-vibe-tryon-close>×</button>' +
      '<div class="vibe-tryon-modal__header">' +
      '<h2 id="vibe-tryon-title"></h2>' +
      "<p></p>" +
      "</div>" +
      '<div class="vibe-tryon-modal__body">' +
      // Card A — body photo
      '<div class="vibe-tryon-card" data-vibe-tryon-card="body">' +
      '<div class="vibe-tryon-card__label">Your photo</div>' +
      '<div class="vibe-tryon-card__body">' +
      '<p class="vibe-tryon-card__hint">Tap to upload a full-body photo<br>(head to toe, arms relaxed)</p>' +
      '<button type="button" class="vibe-tryon-card__cta" tabindex="-1">Choose photo</button>' +
      '<input type="file" accept="image/*" class="vibe-tryon-card__file-input" aria-label="Upload body photo" data-vibe-tryon-file>' +
      "</div>" +
      "</div>" +
      // Card B — try-on result
      '<div class="vibe-tryon-card" data-vibe-tryon-card="result">' +
      '<div class="vibe-tryon-card__label">Try-on</div>' +
      '<div class="vibe-tryon-card__body">' +
      '<p class="vibe-tryon-card__hint">Your try-on will appear here</p>' +
      "</div>" +
      "</div>" +
      "</div>";

    // Set text content rather than interpolating into the HTML string
    // so any theme-setting copy that contains < / > / & doesn't break
    // the markup.
    dialog.querySelector("#vibe-tryon-title").textContent = title;
    dialog.querySelector(".vibe-tryon-modal__header p").textContent = subtitle;

    return dialog;
  }

  function wireDialog(dialog, state) {
    // Stash on the element so handlers attached to replacement nodes
    // (e.g. the file input we re-create after the customer picks a
    // photo) can find the same state object without closure scope
    // gymnastics. Set once here so it's available before the very
    // first render.
    dialog.__vibeState = state;

    var closeBtn = dialog.querySelector("[data-vibe-tryon-close]");
    var fileInput = dialog.querySelector("[data-vibe-tryon-file]");

    closeBtn.addEventListener("click", function () {
      closeAndCleanup(dialog);
    });

    // <dialog>'s ::backdrop swallows clicks by default. Close when the
    // click landed on the dialog element itself (i.e. outside the
    // internal content rect).
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) {
        var rect = dialog.getBoundingClientRect();
        var inside =
          event.clientX >= rect.left &&
          event.clientX <= rect.right &&
          event.clientY >= rect.top &&
          event.clientY <= rect.bottom;
        if (!inside) closeAndCleanup(dialog);
      }
    });

    dialog.addEventListener("close", function () {
      // <dialog>'s native close (Escape key, form method=dialog, etc.)
      // — make sure we tear down the node either way.
      if (dialog.parentNode) {
        dialog.parentNode.removeChild(dialog);
      }
    });

    fileInput.addEventListener("change", function (event) {
      var file = event.target.files && event.target.files[0];
      if (!file) return;
      handleFileChosen(dialog, state, file);
    });
  }

  function closeAndCleanup(dialog) {
    if (typeof dialog.close === "function") {
      dialog.close();
    } else if (dialog.parentNode) {
      dialog.parentNode.removeChild(dialog);
    }
  }

  // ── Body card — preview + upload ───────────────────────────────────

  function handleFileChosen(dialog, state, file) {
    if (state.uploading || state.rendering) return;
    state.uploadedFile = file;

    // Show local preview immediately. We don't wait for the server
    // round trip — feels snappier.
    renderBodyPreview(dialog, file);

    // Kick off upload. Try-on runs as soon as upload returns 2xx.
    uploadBodyPhoto(dialog, state, file);
  }

  function renderBodyPreview(dialog, file) {
    var card = dialog.querySelector('[data-vibe-tryon-card="body"]');
    var body = card.querySelector(".vibe-tryon-card__body");
    var reader = new FileReader();
    reader.onload = function (ev) {
      // Replace the card body with the preview image. Keep the file
      // input on top so the customer can still tap to pick a different
      // photo while the try-on renders.
      body.innerHTML =
        '<img class="vibe-tryon-card__image" alt="Your body photo">' +
        '<input type="file" accept="image/*" class="vibe-tryon-card__file-input" aria-label="Replace body photo" data-vibe-tryon-file>';
      body.querySelector("img").src = ev.target.result;

      // Re-wire the replacement input. Pull state off the dialog
      // (set in wireDialog) so a "pick a different photo" tap
      // restarts the upload → render flow.
      var newInput = body.querySelector("[data-vibe-tryon-file]");
      newInput.addEventListener("change", function (event) {
        var nextFile = event.target.files && event.target.files[0];
        var stateRef = dialog.__vibeState;
        if (nextFile && stateRef) handleFileChosen(dialog, stateRef, nextFile);
      });

      card.classList.add("vibe-tryon-card--has-image");
    };
    reader.readAsDataURL(file);
  }

  function uploadBodyPhoto(dialog, state, file) {
    state.uploading = true;

    setResultState(dialog, "loading", "Saving your photo…");

    var form = new FormData();
    form.append("sessionId", state.sessionId);
    form.append("category", "full_body");
    form.append("file", file, file.name || "full_body.jpg");

    fetch(UPLOAD_ENDPOINT, {
      method: "POST",
      body: form,
      credentials: "same-origin",
    })
      .then(function (res) {
        return res.json().then(function (body) {
          return { status: res.status, body: body };
        });
      })
      .then(function (response) {
        state.uploading = false;
        if (response.status < 200 || response.status >= 300 || !response.body.ok) {
          var message =
            (response.body && response.body.error) ||
            "Couldn't save the photo. Try again?";
          setResultState(dialog, "error", message);
          return;
        }
        // Photo saved — fire the try-on.
        startTryon(dialog, state);
      })
      .catch(function (err) {
        state.uploading = false;
        // eslint-disable-next-line no-console
        console.warn("[vibe-tryon] upload failed", err);
        setResultState(
          dialog,
          "error",
          "Couldn't save the photo. Check your connection and try again.",
        );
      });
  }

  // ── Try-on render ──────────────────────────────────────────────────

  function startTryon(dialog, state) {
    state.rendering = true;
    setResultState(dialog, "loading", "Rendering your try-on…");

    var body = new URLSearchParams();
    body.append("sessionId", state.sessionId);
    body.append("productImageUrl", state.productImageUrl);

    fetch(TRYON_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
      credentials: "same-origin",
    })
      .then(function (res) {
        return res.json().then(function (payload) {
          return { status: res.status, body: payload };
        });
      })
      .then(function (response) {
        state.rendering = false;
        if (
          response.status >= 200 &&
          response.status < 300 &&
          response.body.ok &&
          response.body.dataUrl
        ) {
          setResultImage(dialog, response.body.dataUrl);
          return;
        }
        // Engine refusal path. The friendliest copy depends on
        // reasonCode — missing_person_image is the most common one
        // and means the body photo we just uploaded didn't actually
        // contain a person.
        var reason =
          response.body && response.body.reasonCode
            ? response.body.reasonCode
            : null;
        var message;
        if (reason === "missing_person_image") {
          message =
            "I couldn't find a full-body photo on file. Pick a head-to-toe photo and try again.";
        } else if (response.body && response.body.error) {
          message = response.body.error;
        } else {
          message = "Couldn't render the try-on. Try a different photo?";
        }
        setResultState(dialog, "error", message);
      })
      .catch(function (err) {
        state.rendering = false;
        // eslint-disable-next-line no-console
        console.warn("[vibe-tryon] render failed", err);
        setResultState(
          dialog,
          "error",
          "Couldn't reach the try-on service. Try again in a moment.",
        );
      });
  }

  // ── Result card states ─────────────────────────────────────────────

  function setResultState(dialog, kind, message) {
    var card = dialog.querySelector('[data-vibe-tryon-card="result"]');
    var body = card.querySelector(".vibe-tryon-card__body");
    card.classList.remove("vibe-tryon-card--has-image");
    if (kind === "loading") {
      body.innerHTML =
        '<div class="vibe-tryon-card__spinner-wrap">' +
        '<div class="vibe-tryon-card__spinner" aria-hidden="true"></div>' +
        '<div class="vibe-tryon-card__status"></div>' +
        "</div>";
      body.querySelector(".vibe-tryon-card__status").textContent = message;
    } else if (kind === "error") {
      body.innerHTML = '<p class="vibe-tryon-card__error"></p>';
      body.querySelector(".vibe-tryon-card__error").textContent = message;
    } else {
      body.innerHTML =
        '<p class="vibe-tryon-card__hint">Your try-on will appear here</p>';
    }
  }

  function setResultImage(dialog, dataUrl) {
    var card = dialog.querySelector('[data-vibe-tryon-card="result"]');
    var body = card.querySelector(".vibe-tryon-card__body");
    body.innerHTML = '<img class="vibe-tryon-card__image" alt="Your try-on">';
    body.querySelector("img").src = dataUrl;
    card.classList.add("vibe-tryon-card--has-image");
  }

  // ── Bootstrap ──────────────────────────────────────────────────────

  function bindBlocks(root) {
    var buttons = root.querySelectorAll("[data-vibe-tryon-open]");
    for (var i = 0; i < buttons.length; i += 1) {
      var btn = buttons[i];
      if (btn.__vibeTryonBound) continue;
      btn.__vibeTryonBound = true;
      btn.addEventListener("click", function (event) {
        var trigger = event.currentTarget;
        var block = trigger.closest(".vibe-tryon-block");
        if (block) openModalForBlock(block);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bindBlocks(document);
    });
  } else {
    bindBlocks(document);
  }

  // Some themes (Dawn section-rendering) replace product sections via
  // fetch + innerHTML when the customer toggles a variant. Re-bind
  // when a new block shows up.
  if (typeof MutationObserver !== "undefined") {
    var observer = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i += 1) {
        var added = mutations[i].addedNodes;
        for (var j = 0; j < added.length; j += 1) {
          var node = added[j];
          if (node && node.nodeType === 1) {
            if (node.matches && node.matches(".vibe-tryon-block")) {
              bindBlocks(node.parentNode || document);
            } else if (node.querySelector) {
              var inner = node.querySelector(".vibe-tryon-block");
              if (inner) bindBlocks(node);
            }
          }
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }
})();
