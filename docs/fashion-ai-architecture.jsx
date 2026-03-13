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
};

const F = "'JetBrains Mono', 'SF Mono', monospace";

const Node = ({ x, y, w, h, title, items, color, dim, onClick, active, icon }) => (
  <g onClick={onClick} style={{ cursor: onClick ? "pointer" : "default" }}>
    <rect x={x} y={y} width={w} height={h} rx={5} fill={active ? dim : C.surface} stroke={active ? color : C.border} strokeWidth={active ? 1.5 : 0.5} />
    <rect x={x} y={y} width={w} height={22} rx={5} fill={dim} />
    <rect x={x} y={y + 17} width={w} height={5} fill={dim} />
    {icon && <text x={x + 10} y={y + 15} fontSize="10" fill={color}>{icon}</text>}
    <text x={x + (icon ? 22 : 10)} y={y + 15} fontSize="9.5" fontWeight="600" fill={C.text} fontFamily={F}>{title}</text>
    {items && items.map((item, i) => (
      <text key={i} x={x + 10} y={y + 36 + i * 14} fontSize="7.5" fill={C.textMuted} fontFamily={F}>{item}</text>
    ))}
  </g>
);

const Arrow = ({ x1, y1, x2, y2, color = C.textDim, label, dashed }) => {
  const dx = x2-x1, dy = y2-y1, len = Math.sqrt(dx*dx+dy*dy);
  const ux = dx/len, uy = dy/len;
  const ax = x2-ux*5, ay = y2-uy*5;
  const mx = (x1+x2)/2, my = (y1+y2)/2;
  return (
    <g>
      <line x1={x1} y1={y1} x2={ax} y2={ay} stroke={color} strokeWidth={0.8} opacity={0.5} strokeDasharray={dashed?"3,2":"none"} />
      <polygon points={`${x2},${y2} ${x2-ux*6-uy*3},${y2-uy*6+ux*3} ${x2-ux*6+uy*3},${y2-uy*6-ux*3}`} fill={color} opacity={0.5} />
      {label && <>
        <rect x={mx-label.length*2.5} y={my-6} width={label.length*5} height={12} rx={2} fill={C.bg} />
        <text x={mx} y={my+3} fontSize="6.5" fill={C.textDim} fontFamily={F} textAnchor="middle">{label}</text>
      </>}
    </g>
  );
};

const CArrow = ({ x1, y1, x2, y2, cx, cy, color = C.textDim, label }) => {
  const path = `M ${x1},${y1} Q ${cx},${cy} ${x2},${y2}`;
  const t=0.95;
  const nx = (1-t)*(1-t)*x1+2*(1-t)*t*cx+t*t*x2;
  const ny = (1-t)*(1-t)*y1+2*(1-t)*t*cy+t*t*y2;
  const ddx=x2-nx, ddy=y2-ny, dl=Math.sqrt(ddx*ddx+ddy*ddy);
  const ux=ddx/dl, uy=ddy/dl;
  const mt=0.5;
  const mx=(1-mt)*(1-mt)*x1+2*(1-mt)*mt*cx+mt*mt*x2;
  const my=(1-mt)*(1-mt)*y1+2*(1-mt)*mt*cy+mt*mt*y2;
  return (
    <g>
      <path d={path} stroke={color} strokeWidth={0.8} fill="none" opacity={0.4} />
      <polygon points={`${x2},${y2} ${x2-ux*6-uy*3},${y2-uy*6+ux*3} ${x2-ux*6+uy*3},${y2-uy*6-ux*3}`} fill={color} opacity={0.4} />
      {label && <>
        <rect x={mx-label.length*2.5} y={my-6} width={label.length*5} height={12} rx={2} fill={C.bg} />
        <text x={mx} y={my+3} fontSize="6.5" fill={C.textDim} fontFamily={F} textAnchor="middle">{label}</text>
      </>}
    </g>
  );
};

const LayerBand = ({ y, h, label, color }) => (
  <g>
    <rect x={0} y={y} width={1080} height={h} fill={color} opacity={0.03} />
    <line x1={0} y1={y} x2={1080} y2={y} stroke={color} strokeWidth={0.5} opacity={0.15} />
    <text x={14} y={y+14} fontSize="8" fontWeight="700" fill={color} fontFamily={F} letterSpacing={2} opacity={0.6}>{label}</text>
  </g>
);

const DataStore = ({ x, y, w, h, label, items, color, dim }) => (
  <g>
    <rect x={x} y={y} width={w} height={h} rx={3} fill={dim} stroke={color} strokeWidth={0.5} strokeDasharray="4,2" />
    <text x={x+w/2} y={y+14} fontSize="8" fontWeight="600" fill={color} fontFamily={F} textAnchor="middle">{label}</text>
    {items && items.map((item, i) => (
      <text key={i} x={x+8} y={y+28+i*12} fontSize="7" fill={C.textMuted} fontFamily={F}>{item}</text>
    ))}
  </g>
);

const details = {
  onboarding: {
    title: "User Onboarding Input",
    desc: "OTP-based onboarding flow that collects identity and body measurement data. Mobile number serves as the unique identifier. Fixed OTP (123456) for development. Profile fields are persisted to the onboarding_profiles table in Supabase.",
    items: [
      "Mobile number (unique identifier, OTP-verified)",
      "Name, Date of Birth, Gender",
      "Height (cm), Waist (cm), Profession",
      "Images: full_body, headshot, veins (3:2 aspect ratio)",
      "Images stored with SHA256-encrypted filenames",
      "Stored in: onboarding_profiles + onboarding_images",
    ]
  },
  image_analysis: {
    title: "4-Agent Analysis Pipeline",
    desc: "Four specialized vision agents run in parallel via ThreadPoolExecutor. Each uses GPT-5.4 with high reasoning effort and strict JSON schema output. Every attribute returns {value, confidence, evidence_note}. Vein images are also contrast-enhanced before submission.",
    items: [
      "Agent 1 — body_type_analysis (full_body image):",
      "  ShoulderToHipRatio, TorsoToLegRatio, BodyShape, VisualWeight,",
      "  VerticalProportion, ArmVolume, MidsectionState, BustVolume",
      "Agent 2 — color_analysis_headshot (headshot):",
      "  SkinSurfaceColor, HairColor, HairColorTemperature, EyeColor, EyeClarity",
      "Agent 3 — color_analysis_veins (veins + enhanced veins):",
      "  SkinUndertone",
      "Agent 4 — other_details_analysis (headshot + full_body):",
      "  FaceShape, NeckLength, HairLength, JawlineDefinition, ShoulderSlope",
      "Model: gpt-5.4 | Reasoning: high | Output: strict JSON schema",
      "Stored in: user_analysis_runs (snapshot per run)",
    ]
  },
  interpretation: {
    title: "Deterministic Interpretation Engine",
    desc: "Pure Python rule-based derivation — no LLM calls. Converts raw analysis attributes into 5 actionable interpretations. SeasonalColorGroup uses a 12-season model derived from warmth scoring, depth scoring, and clarity scoring across skin, hair, and eye attributes.",
    items: [
      "SeasonalColorGroup — 12 seasons (e.g. Light Spring, Deep Autumn, Clear Winter)",
      "  From: SkinUndertone, SkinSurfaceColor, HairColor, HairColorTemperature, EyeColor, EyeClarity",
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
    title: "Style Preference Identification",
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
  user_profile: {
    title: "User Profile Store (Supabase)",
    desc: "Persistent storage of all user data collected during onboarding. Loaded by the application orchestrator (via OnboardingGateway) for every recommendation request. Profile richness is scored as full/moderate/basic/minimal.",
    items: [
      "onboarding_profiles: mobile, name, DOB, gender, height_cm, waist_cm, profession",
      "onboarding_images: full_body, headshot, veins (encrypted filenames)",
      "user_analysis_runs: 4-agent outputs + collated attributes",
      "user_derived_interpretations: season, contrast, frame, height, waist",
      "user_style_preference: archetype, risk, formality lean, pattern, boundaries",
      "Minimum profile for recommendations: gender + SeasonalColorGroup + primaryArchetype",
    ]
  },
  orchestrator: {
    title: "Orchestrator (orchestrator.py)",
    desc: "Central 7-stage pipeline that handles every recommendation request. Loads saved user state via OnboardingGateway, resolves live context, builds and applies conversation memory for follow-ups, then runs Architect → Search → Assembler → Evaluator → Formatter. Persists all turn artifacts and updates conversation-level state. Supports both sync and async (job-based) turn processing.",
    items: [
      "1. User Context Builder — loads profile via OnboardingGateway",
      "2. Occasion Resolver — rule-based, no LLM",
      "3. Conversation Memory — build from session_context_json, apply to live context",
      "4. Outfit Architect — LLM planning (gpt-5-mini)",
      "5. Catalog Search Agent — embed + filter + pgvector similarity",
      "6. Outfit Assembler — deterministic compatibility pruning",
      "7. Outfit Evaluator — LLM ranking (gpt-5-mini)",
      "8. Response Formatter — max 5 outfit cards",
      "Filter relaxation: [] → [occasion_fit] → [occasion_fit, formality_level]",
      "Async mode: POST /turns/start → poll /turns/{job_id}/status with stage events",
      "Persists: live context, memory, plan, filters, candidates, recommendations",
    ]
  },
  context_resolver: {
    title: "Occasion Resolver (rule-based)",
    desc: "Deterministic live-context extraction with ordered phrase-priority matching (longest match first). Identifies occasion, formality, time-of-day, specific body/style needs, and follow-up intent. Follow-up detection requires prior assistant recommendations to exist in the conversation.",
    items: [
      "Input: raw user message text + has_previous_recommendations flag",
      "Phrase priority: 'smart casual' before 'casual', 'work meeting' before 'work'",
      "Extracts: occasion_signal, formality_hint, time_hint",
      "Specific needs: elongation, slimming, comfort_priority, authority, approachability",
      "Follow-up intents: increase_boldness, decrease_formality, increase_formality,",
      "  change_color, full_alternative, more_options, similar_to_previous",
      "Output: LiveContext (Pydantic model)",
    ]
  },
  conversation_memory: {
    title: "Conversation Memory",
    desc: "Server-side cross-turn state persisted on session_context_json of the conversation row. Built from the previous turn's state, then applied onto the current LiveContext to carry forward occasion, formality, time, and specific needs when the current message omits them.",
    items: [
      "Fields: occasion_signal, formality_hint, time_hint, specific_needs",
      "Fields: plan_type, followup_count, last_recommendation_ids",
      "Formality shifting for increase/decrease intents",
      "Deduplication + order preservation on specific_needs",
      "Persisted per turn: memory + last_plan_type + last_recommendations",
      "last_recommendations carries: colors, categories, subtypes, roles,",
      "  occasions, formalities, patterns, volumes, fits, silhouettes",
    ]
  },
  outfit_architect_query_docs: {
    title: "Outfit Architect (gpt-5-mini)",
    desc: "Planner agent that translates combined user context into a structured recommendation plan. Uses OpenAI gpt-5-mini with strict JSON schema output. Returns one or more retrieval directions with structured query documents that mirror the catalog embedding representation. Deterministic fallback to complete_only, paired_only, or mixed plan if LLM fails.",
    items: [
      "Model: gpt-5-mini | Output: strict JSON schema",
      "Input: UserContext + LiveContext + ConversationMemory + previous_recommendations",
      "Output: RecommendationPlan (plan_type, retrieval_count=12, directions)",
      "Plan types: complete_only | paired_only | mixed",
      "Direction types: complete (1 query) | paired (top + bottom queries)",
      "Query document sections (mirror catalog embedding structure):",
      "  USER_NEED, PROFILE_AND_STYLE, GARMENT_REQUIREMENTS,",
      "  FABRIC_AND_BUILD, PATTERN_AND_COLOR, OCCASION_AND_SIGNAL",
      "Follow-up: change_color rewrites away from prior colors",
      "Follow-up: similar_to_previous reuses prior silhouette/pattern signals",
      "Fallback: plan_source='fallback' with conservative direction set",
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
    title: "Embedding API (query-time)",
    desc: "OpenAI text-embedding-3-small at 1536 dimensions. Same model is used for both catalog pre-embedding and live query embedding. Cosine similarity is the active distance metric. One embedding call per query document in the recommendation plan.",
    items: [
      "Model: text-embedding-3-small",
      "Dimensions: 1536",
      "Cost: $0.02 / million tokens",
      "~150 tokens per query document",
      "Called once per QuerySpec in the RecommendationPlan",
    ]
  },
  vector_search: {
    title: "Catalog Search Agent (pgvector)",
    desc: "Executes embedding search per architect query direction. Embeds the query document, applies merged hard filters (global + directional + query-document-extracted), runs cosine similarity against catalog_item_embeddings, hydrates products from catalog_enriched. Supports filter relaxation when retrieval is too narrow.",
    items: [
      "Global hard filter: gender_expression (never relaxed)",
      "Contextual filters: occasion_fit, formality_level",
      "Direction filters: styling_completeness (complete vs needs_pairing)",
      "Query-document filters: extracted server-side from architect output",
      "Relaxation: [] → drop occasion_fit → drop occasion_fit + formality_level",
      "Retrieval: default 12 products per query",
      "Hydration: product_id → catalog_enriched row",
      "Output: RetrievedSet per query (direction_id, query_id, role, products, applied_filters)",
    ]
  },
  assembler: {
    title: "Outfit Assembler (deterministic)",
    desc: "Converts retrieved product sets into evaluable outfit candidates. Complete outfits pass through directly. Paired directions (top + bottom) undergo deterministic compatibility pruning with formality, occasion, color temperature, pattern, and volume checks. Max 30 paired candidates.",
    items: [
      "Complete directions: each product becomes one candidate (score = similarity)",
      "Paired directions: cross-product of tops × bottoms (capped at 15 each)",
      "Formality compatibility matrix (adjacent levels only):",
      "  casual↔smart_casual↔business_casual↔semi_formal↔formal↔ultra_formal",
      "Occasion: exact match required when both present (hard reject)",
      "Color temperature: warm↔neutral, cool↔neutral (penalty, not reject)",
      "Pattern: both patterned = small penalty, solid + any = pass",
      "Volume: both oversized = hard reject",
      "Score = avg(top.similarity, bottom.similarity) - penalties",
      "MAX_PAIRED_CANDIDATES = 30",
      "Item attributes carried: product_id, title, image_url, price, product_url,",
      "  garment_category, subtype, primary_color, formality, occasion, pattern, volume, fit, silhouette",
    ]
  },
  evaluator: {
    title: "Outfit Evaluator (gpt-5-mini)",
    desc: "Active LLM ranking component. Evaluates assembled outfit candidates against body harmony, color suitability, occasion appropriateness, style-archetype fit, risk tolerance, comfort boundaries, and pairing coherence. Returns strict JSON with ranked recommendations. Graceful fallback ranks by assembly_score if LLM fails. Hard output cap of 5 recommendations.",
    items: [
      "Model: gpt-5-mini | Output: strict JSON schema",
      "Input: assembled candidates + CombinedContext + RecommendationPlan",
      "Evaluation criteria: body harmony, color suitability, occasion fit,",
      "  style-archetype alignment, risk tolerance, comfort boundaries, pairing coherence",
      "Follow-up: receives candidate-by-candidate deltas against previous recommendations",
      "Sparse output normalization: backfills notes from follow-up deltas",
      "Graceful fallback: ranks by assembly_score when LLM call fails",
      "Fallback reasoning uses delta summaries for follow-up intents",
      "Hard cap: maximum 5 evaluated recommendations",
      "Output: EvaluatedRecommendation (rank, match_score, title, reasoning,",
      "  body_note, color_note, style_note, occasion_note, item_ids)",
    ]
  },
  presentation: {
    title: "Response Formatter + UI",
    desc: "Converts evaluated recommendations into user-facing OutfitCard payloads and renders them in the conversation UI. Generates a contextual message and follow-up suggestions. Maximum 5 outfit cards. UI renders result.outfits with images, titles, prices, reasoning notes, and product links.",
    items: [
      "Max 5 outfit cards per response",
      "Each card: rank, title, reasoning, body/color/style/occasion notes",
      "Each item: product_id, image_url, title, price, product_url, similarity",
      "Follow-up suggestions generated contextually",
      "Contextual message summarizing recommendations",
      "UI renders: outfit images, reasoning, product links",
      "Follow-ups: 'show bolder', 'different color', 'more formal' → loop through orchestrator",
    ]
  },
  catalog_upload: {
    title: "Catalog Upload (/admin/catalog)",
    desc: "Admin UI for CSV-based catalog ingestion. Uploaded files are saved to data/catalog/uploads/. Supports sync of enriched rows, embedding generation, and URL backfill operations. Accessible at /admin/catalog.",
    items: [
      "Base fields: product_id, title, description, price, images, url",
      "Upload: POST /v1/admin/catalog/upload (CSV file)",
      "Sync: POST /v1/admin/catalog/items/sync (enrich + upsert)",
      "Embeddings: POST /v1/admin/catalog/embeddings/sync",
      "Backfill: POST /v1/admin/catalog/items/backfill-urls",
      "Status: GET /v1/admin/catalog/status",
    ]
  },
  enrichment: {
    title: "Attribute Enrichment Pipeline",
    desc: "Async process that analyzes each garment via LLM vision + text analysis and populates 50+ attributes organized in 8 labeled sections, each with confidence scores. Produces the enriched catalog stored in catalog_enriched.",
    items: [
      "Input: title + description + product images",
      "8 attribute sections:",
      "  1. GARMENT_IDENTITY: Category, Subtype, Length, Completeness, Gender",
      "  2. SILHOUETTE_AND_FIT: Contour, Type, Volume, Ease, Fit, Shoulder, Waist, Hip",
      "  3. NECKLINE_SLEEVE_EXPOSURE: Neckline, Depth, Sleeve, Exposure",
      "  4. FABRIC_AND_BUILD: Drape, Weight, Texture, Stretch, Edge, Construction",
      "  5. EMBELLISHMENT: Level, Type, Zone",
      "  6. VISUAL_DIRECTION: VerticalBias, WeightPlacement, Focus, BodyZone, Line",
      "  7. PATTERN_AND_COLOR: Pattern, Scale, Orientation, Contrast, Temp, Sat, Value, Count, Primary, Secondary",
      "  8. OCCASION_AND_SIGNAL: FormalityStrength, Formality, Occasion, Signal, TimeOfDay",
      "Row status: ok | complete | error (only ok/complete are embeddable)",
    ]
  },
  sentence_gen: {
    title: "Document Generator",
    desc: "Converts enriched rows into structured embedding documents with labeled sections mirroring the 8 attribute groups. Each attribute includes its confidence score. Documents are used for both catalog embedding and query-time semantic alignment.",
    items: [
      "Quality gate: confidence-aware value rendering (≥0.6 threshold)",
      "Only embeds rows with row_status in {ok, complete}",
      "Output: one structured document per garment",
      "Sections: CATALOG_ROW + PRODUCT + 8 attribute sections",
      "Format: '- AttributeName: value [confidence=X.XX]'",
      "Metadata extracted for filtering: garment_category, subtype,",
      "  styling_completeness, gender_expression, formality, occasion, time, color, price",
    ]
  },
  embedding_batch: {
    title: "Batch Embedding",
    desc: "Embeds all catalog documents using OpenAI text-embedding-3-small at 1536 dimensions. Runs as batch job via catalog admin sync. Same model as query-time embedding for compatibility. Deduplicates on product_id before upsert.",
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
    desc: "PostgreSQL with pgvector extension. Stores enriched product data in catalog_enriched (50+ attribute columns, product_id unique) and embedding vectors in catalog_item_embeddings (VECTOR(1536), indexed on product_id). HNSW index used for cosine similarity search.",
    items: [
      "catalog_enriched: product_id (unique), title, description, price, url,",
      "  image_urls, row_status, 50+ attribute columns with confidence scores",
      "catalog_item_embeddings: product_id, embedding VECTOR(1536), metadata_json",
      "metadata_json: garment_category, subtype, completeness, gender, formality,",
      "  occasion, time_of_day, primary_color, price",
      "HNSW index for cosine similarity search",
      "Canonical product URLs persisted during ingestion",
    ]
  },
};

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
          3-layer architecture: User Profiling · Application Intelligence · Catalog Pipeline &nbsp;·&nbsp; Click any node for details
        </p>
      </div>

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <div style={{ flex: d ? "0 0 62%" : "1", overflow: "auto", padding: "12px", transition: "flex 0.3s ease" }}>
          <svg viewBox="0 0 1080 970" style={{ width: "100%", height: "auto", minWidth: 700 }}>
            <defs>
              <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
                <path d="M 30 0 L 0 0 0 30" fill="none" stroke={C.border} strokeWidth="0.15" opacity="0.3" />
              </pattern>
            </defs>
            <rect width="1080" height="970" fill="url(#grid)" />

            {/* === LAYER 1: USER PROFILING === */}
            <LayerBand y={0} h={310} label="LAYER 1 — USER PROFILING (one-time onboarding)" color={C.layer1} />

            <Node x={30} y={30} w={190} h={80} title="User Onboarding" icon="●" items={["OTP → Profile → Images", "Gender, DOB, Height, Waist, Profession"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("onboarding")} active={sel==="onboarding"} />

            <Node x={260} y={30} w={220} h={95} title="4-Agent Analysis (gpt-5.4)" icon="◐" items={["body_type_analysis (full_body)", "color_analysis_headshot (headshot)", "color_analysis_veins (veins)", "other_details_analysis (headshot+full_body)"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("image_analysis")} active={sel==="image_analysis"} />

            <Node x={520} y={30} w={200} h={80} title="Interpretation Engine" icon="◈" items={["SeasonalColorGroup (12 seasons)", "ContrastLevel, FrameStructure", "HeightCategory, WaistSizeBand"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("interpretation")} active={sel==="interpretation"} />

            <Node x={30} y={145} w={280} h={95} title="Style Preference (Image Selection)" icon="◧" items={["104 flat-lay image pool (52M + 52F)", "L1: 8 archetype grid → L2: 4 diagnostic", "→ L3: 4 refined | Select 3-5 total", "→ primaryArchetype, RiskTolerance, Boundaries"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("style_pref")} active={sel==="style_pref"} />

            {/* Arrows within Layer 1 */}
            <Arrow x1={220} y1={70} x2={260} y2={70} color={C.layer1} />
            <Arrow x1={480} y1={70} x2={520} y2={70} color={C.layer1} />

            {/* User Profile Store */}
            <DataStore x={760} y={30} w={280} h={125} label="⬡ User Profile Store (Supabase)" color={C.data} dim={C.dataDim}
              items={["onboarding_profiles: gender, DOB, height, waist, profession", "onboarding_images: full_body, headshot, veins", "user_analysis_runs: 4-agent outputs + collated", "user_derived_interpretations: 5 derived attributes", "user_style_preference: archetype, risk, formality"]} />

            {/* Arrows to profile store */}
            <Arrow x1={120} y1={110} x2={760} y2={60} color={C.data} label="save" dashed />
            <Arrow x1={720} y1={70} x2={760} y2={70} color={C.data} label="save" dashed />
            <Arrow x1={310} y1={235} x2={760} y2={135} color={C.data} label="save" dashed />

            {/* Divider area */}
            <line x1={30} y1={280} x2={1050} y2={280} stroke={C.layer1} strokeWidth={0.3} opacity={0.2} strokeDasharray="6,3" />

            {/* === LAYER 2: APPLICATION === */}
            <LayerBand y={310} h={410} label="LAYER 2 — APPLICATION LAYER (per-request agentic pipeline)" color={C.layer2} />

            {/* User message */}
            <Node x={30} y={335} w={200} h={50} title="User Message" icon="▸" items={['"I need outfit for a farewell party"']}
              color={C.layer2} dim={C.layer2Dim} onClick={null} active={false} />

            {/* Orchestrator */}
            <Node x={280} y={330} w={230} h={85} title="Orchestrator (8 stages)" icon="◉" items={["Load profile → Resolve context → Memory", "Architect → Search → Assemble", "Evaluate → Format → Persist turn"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("orchestrator")} active={sel==="orchestrator"} />

            {/* Profile feed into orchestrator */}
            <CArrow x1={900} y1={155} x2={400} y2={330} cx={900} cy={260} color={C.data} label="load profile" />

            {/* Context Resolver */}
            <Node x={280} y={430} w={230} h={55} title="Occasion Resolver (rule-based)" icon="⊞" items={["occasion: party, formality: smart-casual", "specific_needs: [], follow-up intents"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("context_resolver")} active={sel==="context_resolver"} />

            <Arrow x1={130} y1={380} x2={280} y2={370} color={C.layer2} label="user_need" />
            <Arrow x1={395} y1={415} x2={395} y2={430} color={C.layer2} />

            {/* Conversation Memory */}
            <Node x={30} y={430} w={200} h={55} title="Conversation Memory" icon="⟲" items={["Server-side cross-turn state", "Carries: occasion, formality, plan_type"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("conversation_memory")} active={sel==="conversation_memory"} />

            <Arrow x1={230} y1={457} x2={280} y2={457} color={C.layer2} label="apply" />

            {/* Knowledge Context */}
            <DataStore x={30} y={510} w={200} h={90} label="⬡ Knowledge Context" color={C.warn} dim={C.warnDim}
              items={["M01-M04: Styling principles", "M05: Occasion conventions", "M08-M09: Detail + Fabric", "Reference prompts (not injected in v1)"]} />

            {/* Outfit Architect Query Docs */}
            <Node x={280} y={510} w={230} h={100} title="Outfit Architect (gpt-5-mini)" icon="◆" items={["Strict JSON schema output", "Plan: complete_only | paired_only | mixed", "Query docs mirror catalog embedding structure:", "USER_NEED, GARMENT_REQUIREMENTS,", "FABRIC_AND_BUILD, PATTERN_AND_COLOR", "Deterministic fallback if LLM fails"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("outfit_architect_query_docs")} active={sel==="outfit_architect_query_docs"} />

            <Arrow x1={395} y1={485} x2={395} y2={510} color={C.layer2} label="combined context" />
            <Arrow x1={230} y1={555} x2={280} y2={555} color={C.warn} label="knowledge" dashed />

            {/* Embedding API (query-time) */}
            <Node x={560} y={510} w={180} h={60} title="Embed Query" icon="⊕" items={["text-embedding-3-small", "1536 dims, cosine similarity"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("embedding_api")} active={sel==="embedding_api"} />

            <Arrow x1={510} y1={545} x2={560} y2={545} color={C.layer2} label="query text" />

            {/* Vector Search */}
            <Node x={790} y={480} w={220} h={85} title="Catalog Search Agent" icon="⊙" items={["Hard filters: gender, occasion, formality", "Direction: styling_completeness", "Relaxation: occasion → formality", "Returns: hydrated products per query"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("vector_search")} active={sel==="vector_search"} />

            <Arrow x1={740} y1={540} x2={790} y2={530} color={C.layer2} label="query vector" />

            {/* Arrow from catalog DB to vector search */}
            <CArrow x1={900} y1={860} x2={900} y2={565} cx={1040} cy={720} color={C.layer3} label="catalog vectors" />

            {/* Outfit Assembler */}
            <Node x={790} y={585} w={220} h={60} title="Outfit Assembler" icon="⊞" items={["Complete: passthrough (score=similarity)", "Paired: top×bottom compatibility pruning", "Max 30 pairs, 5 compatibility checks"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("assembler")} active={sel==="assembler"} />

            <Arrow x1={900} y1={565} x2={900} y2={585} color={C.layer2} label="retrieved sets" />

            {/* Evaluator */}
            <Node x={560} y={660} w={220} h={80} title="Outfit Evaluator (gpt-5-mini)" icon="◆" items={["Ranks by fit: body, color, occasion, style", "Follow-up: delta reasoning vs prior recs", "Fallback: assembly_score ranking", "Hard cap: max 5 recommendations"]}
              color={C.accent} dim={C.accentDim} onClick={() => setSel("evaluator")} active={sel==="evaluator"} />

            <Arrow x1={790} y1={630} x2={780} y2={670} color={C.layer2} label="candidates" />
            <CArrow x1={900} y1={155} x2={580} y2={660} cx={1060} cy={430} color={C.data} label="user profile" />

            {/* Presentation */}
            <Node x={280} y={675} w={230} h={55} title="Response Formatter + UI" icon="▸" items={["Max 5 outfit cards with reasoning notes", "Follow-up → loops back to Orchestrator"]}
              color={C.accent} dim={C.accentDim} onClick={() => setSel("presentation")} active={sel==="presentation"} />

            <Arrow x1={560} y1={700} x2={510} y2={700} color={C.accent} label="ranked results" />

            {/* Follow-up loop */}
            <CArrow x1={280} y1={695} x2={280} y2={380} cx={180} cy={540} color={C.accent} label="follow-up loop" />

            {/* Divider */}
            <line x1={30} y1={745} x2={1050} y2={745} stroke={C.layer2} strokeWidth={0.3} opacity={0.2} strokeDasharray="6,3" />

            {/* === LAYER 3: CATALOG === */}
            <LayerBand y={750} h={220} label="LAYER 3 — CATALOG PIPELINE (async enrichment)" color={C.layer3} />

            {/* Upload */}
            <Node x={30} y={780} w={170} h={55} title="Catalog Upload" icon="▲" items={["CSV via /admin/catalog UI", "id, title, desc, price, images, url"]}
              color={C.layer3} dim={C.layer3Dim} onClick={() => setSel("catalog_upload")} active={sel==="catalog_upload"} />

            {/* Enrichment */}
            <Node x={240} y={775} w={230} h={75} title="Attribute Enrichment" icon="◈" items={["LLM vision + text analysis per garment", "→ 50+ attributes in 8 labeled sections", "→ Confidence scores per attribute", "→ row_status: ok | complete | error"]}
              color={C.layer3} dim={C.layer3Dim} onClick={() => setSel("enrichment")} active={sel==="enrichment"} />

            <Arrow x1={200} y1={807} x2={240} y2={807} color={C.layer3} />

            {/* Sentence Gen */}
            <Node x={510} y={775} w={200} h={75} title="Document Generator" icon="≡" items={["Enriched rows → structured docs", "8 sections mirror embedding alignment", "Confidence gating (≥0.6)", "Metadata extracted for filtering"]}
              color={C.layer3} dim={C.layer3Dim} onClick={() => setSel("sentence_gen")} active={sel==="sentence_gen"} />

            <Arrow x1={470} y1={807} x2={510} y2={807} color={C.layer3} label="enriched rows" />

            {/* Batch Embed */}
            <Node x={510} y={875} w={200} h={60} title="Batch Embedding" icon="⊕" items={["text-embedding-3-small (same model)", "1536 dims, dedup on product_id", "~$0.03 for 10K garments"]}
              color={C.layer3} dim={C.layer3Dim} onClick={() => setSel("embedding_batch")} active={sel==="embedding_batch"} />

            <Arrow x1={610} y1={850} x2={610} y2={875} color={C.layer3} label="documents" />

            {/* Catalog DB */}
            <DataStore x={790} y={785} w={250} h={95} label="⬡ Catalog Database (pgvector)" color={C.layer3} dim={C.layer3Dim}
              items={["catalog_enriched: 50+ attrs, product_id unique", "catalog_item_embeddings: VECTOR(1536)", "metadata_json: filterable fields", "HNSW index, cosine similarity"]} />

            <Arrow x1={710} y1={905} x2={790} y2={860} color={C.layer3} label="vectors" />
            <Arrow x1={710} y1={807} x2={790} y2={807} color={C.layer3} label="enriched data" />

            {/* Compatibility callout */}
            <rect x={510} y={940} width={200} height={22} rx={3} fill={C.warnDim} stroke={C.warn} strokeWidth={0.5} />
            <text x={610} y={954} fontSize="7" fontWeight="600" fill={C.warn} fontFamily={F} textAnchor="middle">⚠ Same model + dims for catalog & query</text>

          </svg>
        </div>

        {d && (
          <div className="detail-panel" style={{ flex: "0 0 38%", borderLeft: `1px solid ${C.border}`, padding: "20px", overflow: "auto", background: C.surfaceAlt }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <h2 style={{ fontSize: 13, fontWeight: 700, margin: 0, letterSpacing: 1 }}>{d.title}</h2>
              <button onClick={() => setSel(null)} style={{ background: "none", border: `1px solid ${C.border}`, color: C.textMuted, cursor: "pointer", fontSize: 10, padding: "2px 7px", borderRadius: 3, fontFamily: F }}>✕</button>
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
