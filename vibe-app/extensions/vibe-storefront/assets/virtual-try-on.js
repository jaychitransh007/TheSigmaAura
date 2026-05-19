/* Phase W deprecation stub.
 *
 * The Virtual Try-On button is now a simple link to
 * /apps/vibe/style?product=<handle> in a new tab — no JS required
 * for the entry path. The previous V.3 modal popup is retired; its
 * file-upload + result-card construction code lived here.
 *
 * This file stays referenced by the merchant's published theme
 * (added when the block was installed in the theme editor) until
 * W.8 prunes the asset reference entirely. Leaving the body as a
 * no-op keeps the asset URL valid so the theme editor doesn't 404
 * during the cleanup window — same rollback-safety reasoning as
 * leaving the modal CSS intact for one release.
 *
 * Do NOT add new behaviour here. Reference: docs/OPEN_TASKS.md §
 * Phase W (entry-point pivot) and § W.8 (asset cleanup).
 */
(function () {
  "use strict";
  // Intentionally empty.
})();
