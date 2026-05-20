// Allowlist sanitizer for Shopify body_html before it reaches
// `dangerouslySetInnerHTML` in GarmentDetail.
//
// Replaces an earlier regex-based denylist that was flagged in
// review (PR #527) — regex sanitizers can't reliably account for
// nested tags, attribute-name encodings, or HTML5 parsing quirks.
// DOMPurify parses the input as HTML and rebuilds the output from a
// strict allowlist of safe tags + attributes, which is the
// best-practice for rendering merchant-controlled HTML through
// React's dangerouslySetInnerHTML.
//
// `isomorphic-dompurify` ships both a browser implementation and an
// SSR-safe jsdom-backed one — Remix's SSR pass + the client
// hydration pass both call this with the same result, no
// branching needed.

import DOMPurify from "isomorphic-dompurify";

// Tags + attributes we want to keep from Shopify's body_html. The
// allowlist matches what build_shopify_csv.py emits ("<p>lede</p>
// <p><strong>The vibe:</strong></p><ul><li><strong>Fit:</strong>
// …</li>…</ul>") plus the headings / line breaks merchants are
// likely to layer in via the Shopify admin's rich-text editor.
const ALLOWED_TAGS = [
  "p",
  "br",
  "strong",
  "b",
  "em",
  "i",
  "u",
  "ul",
  "ol",
  "li",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "span",
  "small",
];

// No attributes allowed by default. The current Shopify body_html
// for TheSigmaVibe doesn't use any (no href, no class, no style),
// so an empty list keeps the surface as tight as possible. If a
// merchant adds a link inside a description later we'd expand this
// to ["href", "title"] for anchor tags specifically — but for now
// rendering a clean text + bullet block is the entire job.
const ALLOWED_ATTR: string[] = [];

export function sanitizeProductBodyHtml(html: string): string {
  if (!html) return "";
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    // Strip any leftover unknown protocols (javascript:, data:) on
    // anchor / image src — defense in depth even though we don't
    // allow those tags in the first place.
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i,
    // Don't keep <script> or <style> bodies as text — drop them.
    KEEP_CONTENT: true,
    // Belt-and-suspenders: block these even if a future tag list
    // accidentally allows them.
    FORBID_TAGS: ["script", "style", "iframe", "object", "embed", "form", "input"],
    FORBID_ATTR: ["onerror", "onload", "onclick", "onfocus", "style"],
  });
}
