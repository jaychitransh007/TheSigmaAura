import { useState } from "react";

const C = {
  bg: "#08090d",
  surface: "#0e1018",
  surfaceAlt: "#141620",
  border: "#1e2030",
  borderActive: "#3a3f5c",
  text: "#d8dae6",
  textMuted: "#7a7f99",
  textDim: "#4a4e66",
  layer1: "#c49a6a",
  layer1Dim: "#c49a6a22",
  layer2: "#6a9ec4",
  layer2Dim: "#6a9ec422",
  layer3: "#8bc46a",
  layer3Dim: "#8bc46a22",
  accent: "#c46a9e",
  accentDim: "#c46a9e22",
  data: "#9e8bc4",
  dataDim: "#9e8bc422",
  warn: "#c4b86a",
  warnDim: "#c4b86a22",
  agent: "#e0976e",
  agentDim: "#e0976e22",
  tool: "#6ec4b8",
  toolDim: "#6ec4b822",
};

const F = "'JetBrains Mono', 'SF Mono', monospace";

/* ── Badge: small "AGENT" or "TOOL" pill rendered in the node header ── */
const Badge = ({ x, y, label, color }) => {
  const w = label.length * 5.5 + 8;
  return (
    <g>
      <rect x={x} y={y - 8} width={w} height={12} rx={3} fill={color} opacity={0.25} stroke={color} strokeWidth={0.5} />
      <text x={x + w / 2} y={y} fontSize="6.5" fontWeight="700" fill={color} fontFamily={F} textAnchor="middle" letterSpacing={0.8}>{label}</text>
    </g>
  );
};

const Node = ({ x, y, w, h, title, items, color, dim, onClick, active, badge }) => (
  <g onClick={onClick} style={{ cursor: onClick ? "pointer" : "default" }}>
    <rect x={x} y={y} width={w} height={h} rx={5} fill={active ? dim : C.surface} stroke={active ? color : C.border} strokeWidth={active ? 1.5 : 0.5} />
    <rect x={x} y={y} width={w} height={22} rx={5} fill={dim} />
    <rect x={x} y={y + 17} width={w} height={5} fill={dim} />
    <text x={x + 10} y={y + 15} fontSize="9.5" fontWeight="600" fill={C.text} fontFamily={F}>{title}</text>
    {badge && <Badge x={x + w - (badge.length * 5.5 + 8) - 8} y={y + 15} label={badge} color={badge === "AGENT" ? C.agent : C.tool} />}
    {items && items.map((item, i) => (
      <text key={i} x={x + 10} y={y + 36 + i * 14} fontSize="7.5" fill={C.textMuted} fontFamily={F}>{item}</text>
    ))}
  </g>
);

const Arrow = ({ x1, y1, x2, y2, color = C.textDim, label, dashed }) => {
  const dx = x2 - x1, dy = y2 - y1, len = Math.sqrt(dx * dx + dy * dy);
  if (len === 0) return null;
  const ux = dx / len, uy = dy / len;
  const ax = x2 - ux * 5, ay = y2 - uy * 5;
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  return (
    <g>
      <line x1={x1} y1={y1} x2={ax} y2={ay} stroke={color} strokeWidth={0.8} opacity={0.5} strokeDasharray={dashed ? "3,2" : "none"} />
      <polygon points={`${x2},${y2} ${x2 - ux * 6 - uy * 3},${y2 - uy * 6 + ux * 3} ${x2 - ux * 6 + uy * 3},${y2 - uy * 6 - ux * 3}`} fill={color} opacity={0.5} />
      {label && <>
        <rect x={mx - label.length * 2.5} y={my - 6} width={label.length * 5} height={12} rx={2} fill={C.bg} />
        <text x={mx} y={my + 3} fontSize="6.5" fill={C.textDim} fontFamily={F} textAnchor="middle">{label}</text>
      </>}
    </g>
  );
};

const CArrow = ({ x1, y1, x2, y2, cx, cy, color = C.textDim, label }) => {
  const path = `M ${x1},${y1} Q ${cx},${cy} ${x2},${y2}`;
  const t = 0.95;
  const nx = (1 - t) * (1 - t) * x1 + 2 * (1 - t) * t * cx + t * t * x2;
  const ny = (1 - t) * (1 - t) * y1 + 2 * (1 - t) * t * cy + t * t * y2;
  const ddx = x2 - nx, ddy = y2 - ny, dl = Math.sqrt(ddx * ddx + ddy * ddy);
  if (dl === 0) return null;
  const ux = ddx / dl, uy = ddy / dl;
  const mt = 0.5;
  const mx = (1 - mt) * (1 - mt) * x1 + 2 * (1 - mt) * mt * cx + mt * mt * x2;
  const my = (1 - mt) * (1 - mt) * y1 + 2 * (1 - mt) * mt * cy + mt * mt * y2;
  return (
    <g>
      <path d={path} stroke={color} strokeWidth={0.8} fill="none" opacity={0.4} />
      <polygon points={`${x2},${y2} ${x2 - ux * 6 - uy * 3},${y2 - uy * 6 + ux * 3} ${x2 - ux * 6 + uy * 3},${y2 - uy * 6 - ux * 3}`} fill={color} opacity={0.4} />
      {label && <>
        <rect x={mx - label.length * 2.5} y={my - 6} width={label.length * 5} height={12} rx={2} fill={C.bg} />
        <text x={mx} y={my + 3} fontSize="6.5" fill={C.textDim} fontFamily={F} textAnchor="middle">{label}</text>
      </>}
    </g>
  );
};

const LayerBand = ({ y, h, label, color }) => (
  <g>
    <rect x={0} y={y} width={1200} height={h} fill={color} opacity={0.03} />
    <line x1={0} y1={y} x2={1200} y2={y} stroke={color} strokeWidth={0.5} opacity={0.15} />
    <text x={14} y={y + 14} fontSize="8" fontWeight="700" fill={color} fontFamily={F} letterSpacing={2} opacity={0.6}>{label}</text>
  </g>
);

const DataStore = ({ x, y, w, h, label, items, color, dim }) => (
  <g>
    <rect x={x} y={y} width={w} height={h} rx={3} fill={dim} stroke={color} strokeWidth={0.5} strokeDasharray="4,2" />
    <text x={x + w / 2} y={y + 14} fontSize="8" fontWeight="600" fill={color} fontFamily={F} textAnchor="middle">{label}</text>
    {items && items.map((item, i) => (
      <text key={i} x={x + 8} y={y + 28 + i * 12} fontSize="7" fill={C.textMuted} fontFamily={F}>{item}</text>
    ))}
  </g>
);

/* ── Detail panel data ── */
const details = {
  onboarding: {
    title: "User Onboarding Input",
    desc: "OTP-based onboarding flow that collects identity and body measurement data. Mobile number serves as the unique identifier. Fixed OTP (123456) for development. Profile fields are persisted to the onboarding_profiles table in Supabase.",
    items: [
      "Mobile number (unique identifier, OTP-verified)",
      "Name, Date of Birth, Gender",
      "Height (cm), Waist (cm), Profession",
      "Images: full_body, headshot (3:2 aspect ratio)",
      "Images stored with SHA256-encrypted filenames",
      "Stored in: onboarding_profiles + onboarding_images",
    ]
  },
  image_analysis: {
    title: "3-Agent Analysis Pipeline [AGENT]",
    desc: "Three specialized vision agents run in parallel via ThreadPoolExecutor. Each uses GPT-5.4 with high reasoning effort and strict JSON schema output. Every attribute returns {value, confidence, evidence_note}. Followed by digital draping for seasonal color analysis.",
    items: [
      "Agent 1 — body_type_analysis (full_body image):",
      "  ShoulderToHipRatio, TorsoToLegRatio, BodyShape, VisualWeight,",
      "  VerticalProportion, ArmVolume, MidsectionState, BustVolume",
      "Agent 2 — color_analysis_headshot (headshot):",
      "  SkinSurfaceColor, HairColor, HairColorTemperature, EyeColor, EyeClarity",
      "Agent 3 — other_details_analysis (headshot + full_body):",
      "  FaceShape, NeckLength, HairLength, JawlineDefinition, ShoulderSlope",
      "Model: gpt-5.4 | Reasoning: high | Output: strict JSON schema",
      "Stored in: user_analysis_runs (snapshot per run)",
    ]
  },
  interpretation: {
    title: "Deterministic Interpretation Engine [TOOL]",
    desc: "Pure Python rule-based derivation — no LLM calls. Converts raw analysis attributes into 5 actionable interpretations. SeasonalColorGroup uses a 4-season model (Spring, Summer, Autumn, Winter) derived from warmth and depth scoring. Serves as fallback when digital draping is unavailable.",
    items: [
      "SeasonalColorGroup — 4 seasons (Spring, Summer, Autumn, Winter)",
      "  Warm+Light→Spring, Warm+Deep→Autumn, Cool+Light→Summer, Cool+Deep→Winter",
      "  From: SkinSurfaceColor, HairColor, HairColorTemperature, EyeColor, EyeClarity",
      "  Overridden by digital draping when headshot available",
      "ContrastLevel — Low / Medium-Low / Medium / Medium-High / High",
      "  From: depth spread across skin, hair, eye values",
      "FrameStructure — Light+Narrow / Light+Broad / Medium+Balanced / Solid+Narrow / Solid+Broad",
      "  From: VisualWeight, ShoulderSlope, ArmVolume, height_cm",
      "HeightCategory — Petite (<160cm) / Average (160-175cm) / Tall (>175cm)",
      "WaistSizeBand — Very Small / Small / Medium / Large / Very Large",
      "Stored in: user_derived_interpretations",
    ]
  },
  style_pref: {
    title: "Style Preference Identification [TOOL]",
    desc: "Progressive image selection flow — 8 initial flat lays → 4 expansion images per selection → 3-5 total selections. Produces the StylePreference profile using the 104-image tagged pool. Stored in user_style_preference table.",
    items: [
      "Layer 1: 8 archetype images (2×4 grid)",
      "Layer 2: 4 diagnostic images (triggered on first L1 select)",
      "Layer 3: 4 refined images (triggered on first L2 select)",
      "Output: primaryArchetype, secondaryArchetype",
      "Output: riskTolerance, formalityLean, patternType",
      "Output: blending ratios, comfort boundaries",
      "Stored in: user_style_preference + selected_images",
    ]
  },
  digital_draping: {
    title: "Digital Draping [AGENT] (gpt-5.4)",
    desc: "LLM-based seasonal color analysis via relative comparison. Uses 3-round vision chain on headshot overlays to determine the user's seasonal color group(s). Overrides the deterministic interpreter when headshot is available. Results stored in user_effective_seasonal_groups.",
    items: [
      "Round 1: Warm vs Cool (gold vs silver overlay on headshot)",
      "Round 2: Within-branch (Spring vs Autumn, or Summer vs Winter)",
      "Round 3: Confirmation (winner vs cross-temperature neighbor)",
      "Overlay: bottom 45% of image, RGBA alpha=0.35",
      "Probability distribution over 4 seasons (sums to 1.0)",
      "Selection: clear winner (>0.50 or gap>0.20) → 1 group",
      "  Top-2 clash → 2 groups",
      "  3+ clash → prefer Autumn then Winter (tiebreak priority)",
      "Max 2 groups per user",
      "Model: gpt-5.4 | Output: strict JSON {choice, confidence, reasoning}",
      "Stored in: user_effective_seasonal_groups + user_analysis_snapshots.draping_output",
    ]
  },
  comfort_learning: {
    title: "Comfort Learning [TOOL]",
    desc: "Behavioral signal system that refines the user's seasonal palette over time based on outfit interactions. High-intent signals (outfit likes) trigger updates after reaching a threshold. Low-intent signals (color keyword requests) are recorded but don't trigger updates. Integrated into the feedback endpoint.",
    items: [
      "High-intent: outfit like for garment outside current seasonal groups",
      "Low-intent: explicit color keyword request (e.g. 'navy', 'coral')",
      "Threshold: 5 high-intent signals → triggers seasonal group update",
      "Max 2 groups per user (replaces lowest-probability group if at max)",
      "Season-to-color mapping: 4 seasons with warm/cool temperature",
      "Triggered from: POST /v1/conversations/{id}/feedback (like events)",
      "Stored in: user_comfort_learning + user_effective_seasonal_groups",
    ]
  },
  orchestrator: {
    title: "Orchestrator (orchestrator.py)",
    desc: "Central 10-stage pipeline that handles every recommendation request. Loads saved user state via OnboardingGateway, runs occasion resolver for structured signal extraction, builds conversation memory, then evaluates the context gate. If context is insufficient, short-circuits with a clarifying question + quick-reply chips. Otherwise continues: Architect → Search → Assembler → Evaluator → Formatter → Virtual Try-On. Latency tracked per agent via time.monotonic().",
    items: [
      "1. User Context Builder — loads profile via OnboardingGateway",
      "2. Context Builder — occasion resolver + conversation memory build",
      "3. Context Gate — rule-based signal scoring (<1ms), short-circuits if insufficient",
      "4. Outfit Architect [AGENT] — LLM resolves context + plans (gpt-5.4)",
      "5. Catalog Search [AGENT] — embed + hard filters + pgvector similarity",
      "6. Outfit Assembler [TOOL] — deterministic compatibility + follow-up scoring",
      "7. Outfit Evaluator [AGENT] — LLM ranking (gpt-5.4)",
      "8. Response Formatter [TOOL] — intent-aware messaging, max 3 outfit cards",
      "9. Virtual Try-On [AGENT] — Gemini image generation",
      "10. Persist — turn artifacts + conversation memory",
      "response_type: 'recommendation' | 'clarification'",
      "Architect failure → error returned to user (no silent fallback)",
    ]
  },
  context_resolver: {
    title: "Occasion Resolver [TOOL]",
    desc: "Rule-based live-context extraction that runs before the context gate. Extracts structured signals (occasion, formality, time, needs, follow-up intent) from the raw user message so that both the context gate scoring and conversation memory persistence see resolved signals.",
    items: [
      "Role: pre-gate signal extraction + conversation memory bridging",
      "Runs before context gate — signals feed into gate scoring",
      "Phrase priority: 'smart casual' before 'casual', 'work meeting' before 'work'",
      "Extracts: occasion_signal, formality_hint, time_hint",
      "Specific needs: elongation, slimming, comfort_priority, authority, approachability",
      "Follow-up intents: increase_boldness, decrease_formality, change_color, etc.",
      "Enables multi-turn context accumulation across gate-blocked turns",
    ]
  },
  context_gate: {
    title: "Context Gate [TOOL] (rule-based, <1ms)",
    desc: "Fast rule-based gate that checks whether the conversation has enough styling context to produce meaningful recommendations. If context is insufficient, short-circuits the pipeline with a clarifying question and quick-reply suggestion chips.",
    items: [
      "Module: context_gate.py — evaluate(combined_context, consecutive_blocks)",
      "Scoring: occasion (2.0), formality (1.0), category (1.0), season (0.5), style (0.5), follow-up bonus (1.0)",
      "Threshold: 3.0 points — enough for meaningful recommendations",
      "Bypass: 'surprise me' / 'just show me' / follow-up turns / max 2 consecutive blocks",
      "Output: ContextGateResult(sufficient, score, missing_signal, question, quick_replies)",
      "Short-circuit: response_type='clarification', outfits=[], follow_up_suggestions=chips",
    ]
  },
  conversation_memory: {
    title: "Conversation Memory [TOOL]",
    desc: "Server-side cross-turn state persisted on session_context_json. Built from the previous turn's state, then applied onto the current LiveContext to carry forward occasion, formality, time, and specific needs when the current message omits them.",
    items: [
      "Fields: occasion_signal, formality_hint, time_hint, specific_needs",
      "Fields: plan_type, followup_count, last_recommendation_ids",
      "Formality shifting for increase/decrease intents",
      "last_recommendations carries all 8 signal dimensions:",
      "  colors, categories, subtypes, roles, occasions,",
      "  formalities, patterns, volumes, fits, silhouettes",
    ]
  },
  outfit_architect: {
    title: "Outfit Architect [AGENT] (gpt-5.4)",
    desc: "Planner agent that interprets the raw user message and translates it into a structured recommendation plan. Concept-first paired planning for coordinated outfits. Structured follow-up intent rules for change_color (preserve non-color, shift colors), similar_to_previous (preserve all dimensions), and others. No deterministic fallback.",
    items: [
      "Model: gpt-5.4 | Output: strict JSON schema",
      "Dual role: context resolution + retrieval planning in one call",
      "Input: raw user_message + conversation_history + profile + memory",
      "Output: resolved_context + RecommendationPlan (plan_type, directions)",
      "Concept-first planning: color coordination, volume balance, pattern distribution",
      "Follow-up intent rules:",
      "  change_color — different colors, preserve occasion/formality/silhouette/volume/fit",
      "  similar_to_previous — preserve all dimensions, vary by different products",
      "  increase_boldness, increase/decrease_formality, full_alternative, more_options",
      "Plan types: complete_only | paired_only | mixed",
      "Hard filters: enum-constrained vocabulary via JSON schema",
      "No fallback — failure returns error to user",
    ]
  },
  knowledge: {
    title: "Knowledge Context",
    desc: "Reference prompt/module architecture for future richer agent prompting. The active runtime does not inject these full modules directly; planner and evaluator currently rely on model priors plus structured user and catalog context.",
    items: [
      "M01: Universal Styling Principles",
      "M02: Body Shape & Silhouette Strategy",
      "M03: Seasonal Color System",
      "M04: Proportion Correction + M05: Occasion Conventions",
      "M08: Neckline/Detail + M09: Fabric Guidelines",
    ]
  },
  embedding_api: {
    title: "Embedding API [TOOL] (query-time)",
    desc: "OpenAI text-embedding-3-small at 1536 dimensions. Same model is used for both catalog pre-embedding and live query embedding. Cosine similarity is the active distance metric.",
    items: [
      "Model: text-embedding-3-small",
      "Dimensions: 1536",
      "Cost: $0.02 / million tokens",
      "~150 tokens per query document",
      "Called once per QuerySpec in the RecommendationPlan",
    ]
  },
  vector_search: {
    title: "Catalog Search [AGENT] (pgvector)",
    desc: "Executes embedding search per architect query direction. Embeds the query document, applies merged hard filters, runs cosine similarity against catalog_item_embeddings, hydrates products from catalog_enriched. No filter relaxation.",
    items: [
      "Hard filters: gender_expression, styling_completeness, garment_category, garment_subtype",
      "Direction filters: styling_completeness (complete / needs_bottomwear / needs_topwear)",
      "Soft signals (via embedding similarity): occasion, formality, time_of_day, color",
      "No filter relaxation — single search pass, no retry with dropped filters",
      "Retrieval: default 12 products per query",
      "Hydration: product_id → catalog_enriched row",
      "Output: RetrievedSet per query (direction_id, query_id, role, products)",
    ]
  },
  assembler: {
    title: "Outfit Assembler [TOOL] (deterministic)",
    desc: "Converts retrieved product sets into evaluable outfit candidates. Compatibility pruning with formality, occasion, color temperature, pattern, volume, fit, and texture checks. Follow-up intent scoring: change_color penalizes +0.10 per overlapping color; similar_to_previous boosts -0.05 for matching occasion and -0.03 per shared color.",
    items: [
      "Complete directions: each product → one candidate (score = similarity)",
      "Paired directions: top × bottom cross-product (capped at 15 each)",
      "Compatibility checks: formality, occasion, color temp, pattern, volume, fit, texture",
      "Follow-up scoring (change_color):",
      "  +0.10 penalty per color overlapping with previous recommendation",
      "Follow-up scoring (similar_to_previous):",
      "  -0.05 boost for matching occasion, -0.03 per shared color",
      "MAX_PAIRED_CANDIDATES = 30",
      "Items carry 16 fields including 6 enrichment attributes",
    ]
  },
  evaluator: {
    title: "Outfit Evaluator [AGENT] (gpt-5.4)",
    desc: "LLM-powered ranking agent with dual scoring. Outputs 16 integer percentage fields per outfit: 8 evaluation criteria (body harmony, color suitability, style fit, risk tolerance, occasion, comfort boundary, specific needs, pairing coherence) measuring fit for this user, plus 8 style archetype scores (classic, dramatic, romantic, natural, minimalist, creative, sporty, edgy) describing the outfit's aesthetic. Candidate-by-candidate deltas with 8 signal dimensions. Full evaluation output (notes + all 16 _pct fields) is persisted in turn artifacts.",
    items: [
      "Model: gpt-5.4 | Output: strict JSON schema (16 _pct fields)",
      "8 evaluation criteria: body, color, style, risk, occasion, comfort, needs, pairing",
      "8 style archetype scores: classic, dramatic, romantic, natural, minimalist, creative, sporty, edgy",
      "Archetype scores describe outfit aesthetic, not user preference",
      "Candidate deltas: 8 signals vs prior recommendation",
      "change_color: penalize shared_colors, reward preserved non-color dims",
      "similar_to_previous: reward all non-empty shared dimensions",
      "Sparse output normalization: backfills from deltas",
      "Graceful fallback: criteria from assembly_score, archetypes default 0",
      "Full evaluation persisted in turn artifacts (notes + 16 _pct fields)",
      "Hard cap: maximum 5 evaluated recommendations",
    ]
  },
  presentation: {
    title: "Response Formatter [TOOL] + 3-Column PDP UI",
    desc: "Intent-aware messaging and suggestion chips. change_color opens with 'fresh color direction'; similar_to_previous opens with 'similar style'. Each intent gets tailored follow-up suggestion chips. Renders 3-column PDP cards with thumbnail rail, hero image (try-on default), and info panel showing rank, title, per-product title + price + Buy Now button, Canvas-rendered radar chart (8 style archetype axes, purple fill), 8 color-coded evaluation criteria progress bars, and feedback CTAs.",
    items: [
      "Max 3 outfit cards per response",
      "Intent-aware opening messages:",
      "  change_color → 'fresh color direction'",
      "  similar_to_previous → 'similar style'",
      "Intent-aware follow-up chips:",
      "  After change_color: 'similar to these', 'different style'",
      "  After similar_to_previous: 'different color', 'something bolder'",
      "3-column PDP: thumbnails (80px) | hero (flex) | info (40%)",
      "Default hero: virtual try-on when present",
      "Info panel: rank → title → products (title + price + Buy Now) →",
      "  radar chart (Canvas, 8 axes, purple fill) → 8 criteria bars →",
      "  feedback CTAs (Like immediate / Dislike textarea)",
      "Criteria bars: color-coded (green ≥80%, yellow ≥60%, red <60%)",
      "POST /v1/conversations/{id}/feedback → one row per garment",
    ]
  },
  virtual_tryon: {
    title: "Virtual Try-On [AGENT] (Gemini)",
    desc: "Image generation agent that produces virtual try-on previews for each outfit. Uses Google Gemini gemini-3.1-flash-image-preview model with the user's full_body onboarding image. Runs in parallel via ThreadPoolExecutor (max 3 workers). Body-preserving prompt ensures immutable geometry.",
    items: [
      "Model: gemini-3.1-flash-image-preview (Google Gemini API)",
      "Input: user full_body image + first product image per outfit",
      "Parallel execution: ThreadPoolExecutor, max 3 workers",
      "Image preprocessing: resize to max 1024px (Pillow/LANCZOS)",
      "Prompt: body-preserving — treats person's body as immutable geometry",
      "Output: base64 data URL attached to OutfitCard.tryon_image",
      "Graceful degradation: outfit returned without try-on on failure",
    ]
  },
  qna_agent: {
    title: "QnA Narration [TOOL] (deterministic)",
    desc: "Template-based narration layer that converts raw pipeline stage names into human-readable, context-aware messages. No LLM calls — uses f-string templates keyed by stage_detail with context dicts passed from the orchestrator.",
    items: [
      "Module: qna_messages.py — generate_stage_message(stage, detail, ctx)",
      "21 template keys covering all 10 pipeline stages",
      "Static + dynamic templates with context-aware rendering",
      "Graceful degradation: missing context → safe fallback text",
      "Wired via orchestrator emit() → stage_callback(stage, detail, message)",
    ]
  },
  catalog_upload: {
    title: "Catalog Upload (/admin/catalog)",
    desc: "Admin UI for CSV-based catalog ingestion. Uploaded files are saved to data/catalog/uploads/. Supports sync of enriched rows, embedding generation, and URL backfill operations.",
    items: [
      "Base fields: product_id, title, description, price, images, url",
      "Upload: POST /v1/admin/catalog/upload (CSV file)",
      "Sync: POST /v1/admin/catalog/items/sync (enrich + upsert)",
      "Embeddings: POST /v1/admin/catalog/embeddings/sync",
      "Backfill: POST /v1/admin/catalog/items/backfill-urls",
      "Status: GET /v1/admin/catalog/status (job history + status)",
    ]
  },
  enrichment: {
    title: "Attribute Enrichment Pipeline",
    desc: "Async process that analyzes each garment via LLM vision + text analysis and populates 50+ attributes organized in 8 labeled sections, each with confidence scores.",
    items: [
      "Input: title + description + product images",
      "8 attribute sections:",
      "  1. GARMENT_IDENTITY: Category, Subtype, Length, Completeness, Gender",
      "  2. SILHOUETTE_AND_FIT: Contour, Type, Volume, Ease, Fit, Shoulder, Waist, Hip",
      "  3. NECKLINE_SLEEVE_EXPOSURE: Neckline, Depth, Sleeve, Exposure",
      "  4. FABRIC_AND_BUILD: Drape, Weight, Texture, Stretch, Edge, Construction",
      "  5. EMBELLISHMENT: Level, Type, Zone",
      "  6. VISUAL_DIRECTION: VerticalBias, WeightPlacement, Focus, BodyZone, Line",
      "  7. PATTERN_AND_COLOR: Pattern, Scale, Contrast, Temp, Sat, Primary, Secondary",
      "  8. OCCASION_AND_SIGNAL: Formality, Occasion, Signal, TimeOfDay",
      "Row status: ok | complete | error (only ok/complete are embeddable)",
    ]
  },
  sentence_gen: {
    title: "Document Generator [TOOL]",
    desc: "Converts enriched rows into structured embedding documents with labeled sections mirroring the 8 attribute groups. Each attribute includes its confidence score.",
    items: [
      "Quality gate: confidence-aware value rendering (>=0.6 threshold)",
      "Only embeds rows with row_status in {ok, complete}",
      "Sections: CATALOG_ROW + PRODUCT + 8 attribute sections",
      "Format: '- AttributeName: value [confidence=X.XX]'",
      "Metadata extracted for filtering: garment_category, subtype,",
      "  styling_completeness, gender_expression, formality, occasion, color, price",
    ]
  },
  embedding_batch: {
    title: "Batch Embedding [TOOL]",
    desc: "Embeds all catalog documents using OpenAI text-embedding-3-small at 1536 dimensions. Same model as query-time embedding for compatibility.",
    items: [
      "Model: text-embedding-3-small (same as query-time)",
      "Dimensions: 1536",
      "Batch size: 200 sentences per API call",
      "Deduplicates on product_id before upsert",
      "Cost: ~$0.03 for 10,000 garments",
    ]
  },
  catalog_db: {
    title: "Catalog Database (Supabase + pgvector)",
    desc: "PostgreSQL with pgvector extension. Stores enriched product data in catalog_enriched (50+ attribute columns) and embedding vectors in catalog_item_embeddings (VECTOR(1536)). HNSW index for cosine similarity search.",
    items: [
      "catalog_enriched: product_id (unique), title, desc, price, url,",
      "  image_urls, row_status, 50+ attribute columns + confidence scores",
      "catalog_item_embeddings: product_id, embedding VECTOR(1536), metadata_json",
      "metadata_json: garment_category, subtype, completeness, gender, formality,",
      "  occasion, time_of_day, primary_color, price",
      "HNSW index for cosine similarity search",
      "Canonical product URLs persisted during ingestion",
    ]
  },
};

/* ──────────────────────────────────────────────────────────────────────
   LAYOUT GRID
   ──────────────────────────────────────────────────────────────────────
   viewBox: 1200 × 1200  (120px wider than before, 140px taller)

   Layer 1 (User Profiling):      y =   0 … 340
   Layer 2 (Application):         y = 350 … 910
   Layer 3 (Catalog Pipeline):    y = 920 … 1200

   Columns (4-column grid):
     Col A: x =  30, w = 240
     Col B: x = 300, w = 260
     Col C: x = 590, w = 240
     Col D: x = 860, w = 300
   ────────────────────────────────────────────────────────────────────── */

export default function Architecture() {
  const [sel, setSel] = useState(null);
  const d = sel ? details[sel] : null;

  return (
    <div style={{ background: C.bg, minHeight: "100vh", fontFamily: F, color: C.text, display: "flex", flexDirection: "column" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap');
        g[style*="pointer"]:hover rect:first-child { filter: brightness(1.2); }
        .detail-panel { animation: fadeIn 0.2s ease-out; }
        @keyframes fadeIn { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:translateY(0); } }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: ${C.bg}; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 3px; }
      `}</style>

      <div style={{ padding: "20px 28px 6px", borderBottom: `1px solid ${C.border}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 7, height: 7, borderRadius: "50%", background: C.layer1, boxShadow: `0 0 10px ${C.layer1}66` }} />
          <h1 style={{ fontSize: 14, fontWeight: 700, margin: 0, letterSpacing: 3, textTransform: "uppercase" }}>Aura — Fashion Styling AI Architecture</h1>
        </div>
        <p style={{ fontSize: 9, color: C.textMuted, margin: "6px 0 10px 17px", letterSpacing: 0.5 }}>
          3-layer architecture: User Profiling · Application Intelligence · Catalog Pipeline
          &nbsp;&middot;&nbsp;
          <span style={{ color: C.agent }}>AGENT</span> = LLM-powered
          &nbsp;&middot;&nbsp;
          <span style={{ color: C.tool }}>TOOL</span> = Deterministic
          &nbsp;&middot;&nbsp;
          Click any node for details
        </p>
      </div>

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <div style={{ flex: d ? "0 0 62%" : "1", overflow: "auto", padding: "12px", transition: "flex 0.3s ease" }}>
          <svg viewBox="0 0 1200 1200" style={{ width: "100%", height: "auto", minWidth: 700 }}>
            <defs>
              <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
                <path d="M 30 0 L 0 0 0 30" fill="none" stroke={C.border} strokeWidth="0.15" opacity="0.3" />
              </pattern>
            </defs>
            <rect width="1200" height="1200" fill="url(#grid)" />

            {/* ═══════════════════════════════════════════════
                LAYER 1 — USER PROFILING (y: 0–340)
                ═══════════════════════════════════════════════ */}
            <LayerBand y={0} h={340} label="LAYER 1 — USER PROFILING (one-time onboarding)" color={C.layer1} />

            {/* Row 1: Onboarding → Analysis → Interpretation */}
            <Node x={30} y={30} w={240} h={75} title="User Onboarding" items={["OTP → Profile → Images", "Gender, DOB, Height, Waist, Profession"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("onboarding")} active={sel === "onboarding"} />

            <Node x={300} y={30} w={260} h={100} title="3-Agent Analysis Pipeline" items={["body_type_analysis (full_body)", "color_analysis_headshot (headshot)", "other_details_analysis (headshot+full_body)", "Model: gpt-5.4 | Parallel execution"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("image_analysis")} active={sel === "image_analysis"} badge="AGENT" />

            <Node x={590} y={30} w={240} h={85} title="Interpretation Engine" items={["SeasonalColorGroup (4 seasons)", "ContrastLevel, FrameStructure", "HeightCategory, WaistSizeBand"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("interpretation")} active={sel === "interpretation"} badge="TOOL" />

            {/* Row 2: Style Preference + Digital Draping + Comfort Learning */}
            <Node x={30} y={150} w={260} h={95} title="Style Preference" items={["104 flat-lay image pool (52M + 52F)", "L1: 8 archetypes → L2: 4 diagnostic → L3: 4 refined", "→ primaryArchetype, riskTolerance, boundaries"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("style_pref")} active={sel === "style_pref"} badge="TOOL" />

            <Node x={320} y={150} w={240} h={80} title="Digital Draping" items={["3-round LLM vision chain (headshot)", "R1: Warm/Cool → R2: Branch → R3: Confirm", "→ 4-season probability distribution", "→ 1-2 effective seasonal groups"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("digital_draping")} active={sel === "digital_draping"} badge="AGENT" />

            <Node x={590} y={150} w={240} h={65} title="Comfort Learning" items={["Behavioral palette refinement", "High-intent: 5 outfit likes → update", "Max 2 groups per user"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("comfort_learning")} active={sel === "comfort_learning"} badge="TOOL" />

            {/* Interpretation → Digital Draping arrow */}
            <Arrow x1={710} y1={115} x2={440} y2={150} color={C.layer1} label="fallback" dashed />

            {/* Arrows in Layer 1 */}
            <Arrow x1={270} y1={68} x2={300} y2={68} color={C.layer1} />
            <Arrow x1={560} y1={68} x2={590} y2={68} color={C.layer1} />

            {/* User Profile Store — right side */}
            <DataStore x={860} y={30} w={300} h={160} label="User Profile Store (Supabase)" color={C.data} dim={C.dataDim}
              items={["onboarding_profiles: gender, DOB, height, waist, profession", "onboarding_images: full_body, headshot", "user_analysis_runs: 3-agent outputs + collated", "user_derived_interpretations: 5 derived attributes", "user_style_preference: archetype, risk, formality, pattern", "user_effective_seasonal_groups: draping/comfort source", "user_comfort_learning: behavioral signals"]} />

            {/* Save arrows to profile store */}
            <Arrow x1={150} y1={105} x2={860} y2={55} color={C.data} label="save" dashed />
            <Arrow x1={830} y1={68} x2={860} y2={68} color={C.data} label="save" dashed />
            <Arrow x1={290} y1={240} x2={860} y2={150} color={C.data} label="save" dashed />
            <Arrow x1={560} y1={190} x2={860} y2={160} color={C.data} label="save" dashed />
            <Arrow x1={830} y1={182} x2={860} y2={175} color={C.data} label="save" dashed />

            {/* Layer 1–2 divider */}
            <line x1={30} y1={320} x2={1160} y2={320} stroke={C.layer1} strokeWidth={0.3} opacity={0.2} strokeDasharray="6,3" />

            {/* ═══════════════════════════════════════════════
                LAYER 2 — APPLICATION LAYER (y: 350–910)
                ═══════════════════════════════════════════════ */}
            <LayerBand y={350} h={560} label="LAYER 2 — APPLICATION LAYER (per-request agentic pipeline)" color={C.layer2} />

            {/* Row 1: User Message → Orchestrator → QnA */}
            <Node x={30} y={380} w={240} h={50} title="User Message" items={['"I need outfit for a farewell party"']}
              color={C.layer2} dim={C.layer2Dim} />

            <Node x={300} y={375} w={260} h={80} title="Orchestrator (10 stages)" items={["Load profile → Context → Gate", "Architect → Search → Assemble", "Evaluate → Format → Try-On → Persist"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("orchestrator")} active={sel === "orchestrator"} />

            <Node x={590} y={380} w={240} h={50} title="QnA Narration" items={["Deterministic stage → message", "Context-aware f-string templates"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("qna_agent")} active={sel === "qna_agent"} badge="TOOL" />

            <Arrow x1={270} y1={405} x2={300} y2={405} color={C.layer2} label="user_need" />
            <Arrow x1={560} y1={410} x2={590} y2={410} color={C.layer2} label="stage + ctx" />

            {/* Profile feed into orchestrator */}
            <CArrow x1={1010} y1={190} x2={430} y2={375} cx={1010} cy={290} color={C.data} label="load profile" />

            {/* Row 2: Context Prep + Memory + Context Gate */}
            <Node x={30} y={475} w={240} h={55} title="Conversation Memory" items={["Server-side cross-turn state", "Carries: occasion, formality, plan_type, 8 signals"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("conversation_memory")} active={sel === "conversation_memory"} badge="TOOL" />

            <Node x={300} y={475} w={260} h={55} title="Context Prep (signal extraction)" items={["Occasion resolver → structured signals", "Builds LiveContext + conversation memory"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("context_resolver")} active={sel === "context_resolver"} badge="TOOL" />

            <Node x={590} y={475} w={240} h={55} title="Context Gate (<1ms)" items={["Score signals → threshold 3.0", "Insufficient → clarify + chips"]}
              color={C.warn} dim={C.warnDim} onClick={() => setSel("context_gate")} active={sel === "context_gate"} badge="TOOL" />

            <Arrow x1={430} y1={455} x2={430} y2={475} color={C.layer2} />
            <Arrow x1={270} y1={502} x2={300} y2={502} color={C.layer2} label="apply" />
            <Arrow x1={560} y1={502} x2={590} y2={502} color={C.warn} label="evaluate" />

            {/* Gate short-circuit arrow */}
            <CArrow x1={710} y1={530} x2={430} y2={810} cx={780} cy={690} color={C.warn} label="short-circuit (clarification)" />

            {/* Row 3: Knowledge + Architect + Embed Query */}
            <DataStore x={30} y={560} w={240} h={80} label="Knowledge Context" color={C.warn} dim={C.warnDim}
              items={["M01-M04: Styling principles", "M05: Occasion conventions", "M08-M09: Detail + Fabric", "Reference prompts (not injected in v1)"]} />

            <Node x={300} y={555} w={260} h={105} title="Outfit Architect (gpt-5.4)" items={["LLM concept-first paired planning", "Structured follow-up intent rules:", "  change_color — preserve non-color, shift colors", "  similar_to_previous — preserve all dimensions", "Hard filters: enum-constrained vocabulary", "No fallback — failure = error to user"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("outfit_architect")} active={sel === "outfit_architect"} badge="AGENT" />

            <Node x={590} y={560} w={240} h={55} title="Embed Query" items={["text-embedding-3-small", "1536 dims, cosine similarity"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("embedding_api")} active={sel === "embedding_api"} badge="TOOL" />

            <Arrow x1={430} y1={530} x2={430} y2={555} color={C.layer2} label="gate passed" />
            <Arrow x1={270} y1={600} x2={300} y2={600} color={C.warn} label="knowledge" dashed />
            <Arrow x1={560} y1={590} x2={590} y2={590} color={C.layer2} label="query text" />

            {/* Row 4: Catalog Search + Assembler — right column */}
            <Node x={860} y={540} w={300} h={70} title="Catalog Search (pgvector)" items={["Hard: gender, completeness, category, subtype", "Direction: needs_bottomwear / needs_topwear", "No relaxation — single search pass"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("vector_search")} active={sel === "vector_search"} badge="AGENT" />

            <Arrow x1={830} y1={588} x2={860} y2={575} color={C.layer2} label="query vector" />

            <Node x={860} y={635} w={300} h={75} title="Outfit Assembler" items={["Complete: passthrough | Paired: top x bottom pruning", "5 compat checks + follow-up intent scoring:", "  change_color: +0.10 per overlapping color", "  similar_to_previous: -0.05 occasion, -0.03/color"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("assembler")} active={sel === "assembler"} badge="TOOL" />

            <Arrow x1={1010} y1={610} x2={1010} y2={635} color={C.layer2} label="retrieved sets" />

            {/* Arrow from catalog DB to vector search */}
            <CArrow x1={1010} y1={1045} x2={1010} y2={610} cx={1180} cy={830} color={C.layer3} label="catalog vectors" />

            {/* Row 5: Evaluator + Formatter + Try-On */}
            <Node x={590} y={720} w={260} h={80} title="Outfit Evaluator (gpt-5.4)" items={["Dual scoring: 8 criteria + 8 archetype _pct fields", "8-signal deltas vs prior recommendations", "Full evaluation persisted in turn artifacts", "Fallback: assembly_score | Max 5 evaluations"]}
              color={C.accent} dim={C.accentDim} onClick={() => setSel("evaluator")} active={sel === "evaluator"} badge="AGENT" />

            <Arrow x1={860} y1={700} x2={850} y2={740} color={C.layer2} label="candidates" />

            {/* User profile into evaluator */}
            <CArrow x1={1010} y1={190} x2={620} y2={720} cx={1180} cy={460} color={C.data} label="user profile" />

            <Node x={300} y={730} w={260} h={70} title="Response Formatter + PDP UI" items={["Max 3 cards: Buy Now + radar chart + criteria bars", "Radar: 8 archetype axes, Canvas-rendered, purple fill", "Criteria: 8 progress bars, color-coded by threshold", "Intent-aware messaging + follow-up chips"]}
              color={C.accent} dim={C.accentDim} onClick={() => setSel("presentation")} active={sel === "presentation"} badge="TOOL" />

            <Arrow x1={590} y1={760} x2={560} y2={760} color={C.accent} label="ranked results" />

            <Node x={30} y={745} w={240} h={60} title="Virtual Try-On (Gemini)" items={["gemini-3.1-flash-image-preview", "Parallel: 3 workers, body-preserving", "Graceful degradation on failure"]}
              color={C.accent} dim={C.accentDim} onClick={() => setSel("virtual_tryon")} active={sel === "virtual_tryon"} badge="AGENT" />

            <Arrow x1={300} y1={775} x2={270} y2={775} color={C.accent} label="outfit cards" />

            {/* User image feed into try-on */}
            <CArrow x1={1010} y1={190} x2={150} y2={745} cx={50} cy={440} color={C.data} label="full_body image" />

            {/* Feedback arrow to data store */}
            <CArrow x1={430} y1={800} x2={860} y2={190} cx={1180} cy={520} color={C.data} label="feedback_events" />

            {/* Follow-up loop */}
            <CArrow x1={150} y1={805} x2={300} y2={420} cx={180} cy={600} color={C.accent} label="follow-up loop" />

            {/* Layer 2–3 divider */}
            <line x1={30} y1={900} x2={1160} y2={900} stroke={C.layer2} strokeWidth={0.3} opacity={0.2} strokeDasharray="6,3" />

            {/* ═══════════════════════════════════════════════
                LAYER 3 — CATALOG PIPELINE (y: 920–1200)
                ═══════════════════════════════════════════════ */}
            <LayerBand y={920} h={280} label="LAYER 3 — CATALOG PIPELINE (async enrichment)" color={C.layer3} />

            {/* Row 1: Upload → Enrichment → Document Gen */}
            <Node x={30} y={955} w={240} h={55} title="Catalog Upload" items={["CSV via /admin/catalog UI", "id, title, desc, price, images, url"]}
              color={C.layer3} dim={C.layer3Dim} onClick={() => setSel("catalog_upload")} active={sel === "catalog_upload"} />

            <Node x={300} y={950} w={260} h={75} title="Attribute Enrichment" items={["LLM vision + text analysis per garment", "→ 50+ attributes in 8 labeled sections", "→ Confidence scores per attribute", "→ row_status: ok | complete | error"]}
              color={C.layer3} dim={C.layer3Dim} onClick={() => setSel("enrichment")} active={sel === "enrichment"} badge="AGENT" />

            <Node x={590} y={950} w={240} h={75} title="Document Generator" items={["Enriched rows → structured docs", "8 sections mirror embedding alignment", "Confidence gating (>=0.6)", "Metadata extracted for filtering"]}
              color={C.layer3} dim={C.layer3Dim} onClick={() => setSel("sentence_gen")} active={sel === "sentence_gen"} badge="TOOL" />

            <Arrow x1={270} y1={982} x2={300} y2={982} color={C.layer3} />
            <Arrow x1={560} y1={982} x2={590} y2={982} color={C.layer3} label="enriched rows" />

            {/* Row 2: Batch Embedding */}
            <Node x={590} y={1055} w={240} h={55} title="Batch Embedding" items={["text-embedding-3-small (same model)", "1536 dims, dedup on product_id"]}
              color={C.layer3} dim={C.layer3Dim} onClick={() => setSel("embedding_batch")} active={sel === "embedding_batch"} badge="TOOL" />

            <Arrow x1={710} y1={1025} x2={710} y2={1055} color={C.layer3} label="documents" />

            {/* Catalog DB — right side */}
            <DataStore x={860} y={960} w={300} h={95} label="Catalog Database (pgvector)" color={C.layer3} dim={C.layer3Dim}
              items={["catalog_enriched: 50+ attrs, product_id unique", "catalog_item_embeddings: VECTOR(1536)", "metadata_json: filterable fields", "HNSW index, cosine similarity"]} />

            <Arrow x1={830} y1={1082} x2={860} y2={1030} color={C.layer3} label="vectors" />
            <Arrow x1={830} y1={982} x2={860} y2={990} color={C.layer3} label="enriched data" />

            {/* Compatibility callout */}
            <rect x={590} y={1135} width={240} height={22} rx={3} fill={C.warnDim} stroke={C.warn} strokeWidth={0.5} />
            <text x={710} y={1149} fontSize="7" fontWeight="600" fill={C.warn} fontFamily={F} textAnchor="middle">Same model + dims for catalog & query</text>

          </svg>
        </div>

        {d && (
          <div className="detail-panel" style={{ flex: "0 0 38%", borderLeft: `1px solid ${C.border}`, padding: "20px", overflow: "auto", background: C.surfaceAlt }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <h2 style={{ fontSize: 13, fontWeight: 700, margin: 0, letterSpacing: 1 }}>{d.title}</h2>
              <button onClick={() => setSel(null)} style={{ background: "none", border: `1px solid ${C.border}`, color: C.textMuted, cursor: "pointer", fontSize: 10, padding: "2px 7px", borderRadius: 3, fontFamily: F }}>&#x2715;</button>
            </div>
            <p style={{ fontSize: 10.5, color: C.textMuted, lineHeight: 1.7, margin: "14px 0" }}>{d.desc}</p>
            <div style={{ fontSize: 9, fontWeight: 700, color: C.layer1, letterSpacing: 2, textTransform: "uppercase", marginBottom: 8 }}>Details</div>
            {d.items.map((item, i) => (
              <div key={i} style={{ fontSize: 9.5, color: C.textMuted, padding: "5px 0 5px 10px", borderLeft: `1px solid ${C.border}`, marginBottom: 3, lineHeight: 1.5 }}>{item}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
