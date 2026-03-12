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
    desc: "Collects basic identity information from the user — gender, age range, profession. This is the entry point for the entire profiling pipeline.",
    items: ["Gender", "Age range", "Profession/lifestyle context", "Stored as: onboarding_profile"]
  },
  image_analysis: {
    title: "Image Analysis",
    desc: "User uploads a photo. The system extracts observable body and color attributes using vision analysis. Produces raw measurements and observations before interpretation.",
    items: [
      "Body Type: Height, Waist, Shoulder-to-hip ratio, Torso-to-leg ratio, BodyShape, VisualWeight, ArmVolume, MidsectionState, BustVolume",
      "Color Analysis: SkinSurfaceColor, SkinUndertone, HairColor, EyeColor, HairColorTemperature, EyeClarity",
      "Additional: FaceShape, NeckLength, HairLength, ShoulderSlope, JawlineDefinition",
    ]
  },
  interpretation: {
    title: "Interpretation Engine",
    desc: "Derives higher-level style attributes from raw analysis observations. These are the actionable attributes that feed into outfit recommendations.",
    items: ["ContrastLevel (from skin + hair + eye interaction)", "WaistSizeBand (from waist measurement)", "FrameStructure (from shoulder, hip, visual weight)", "SeasonalColorGroup (from all color attributes)", "HeightCategory (from height analysis)"]
  },
  style_pref: {
    title: "Style Preference Identification",
    desc: "Progressive image selection flow — 8 initial flat lays → 4 expansion images per selection → 3-5 total selections. Produces the StylePreference profile using the 104-image tagged pool.",
    items: [
      "Layer 1: 8 archetype images (2×4 grid)",
      "Layer 2: 4 diagnostic images (triggered on first L1 select)",
      "Layer 3: 4 refined images (triggered on first L2 select)",
      "Output: StyleArchetype, RiskTolerance, FormalityLean, ComfortBoundaries, PatternType",
    ]
  },
  user_profile: {
    title: "User Profile Store",
    desc: "Persistent storage of all user data collected during onboarding. Loaded by the orchestrator for every recommendation request.",
    items: [
      "onboarding_profile: gender, age, profession",
      "analysis: all body + color attributes",
      "interpretations: seasonal group, contrast, frame, height, waist",
      "style_preference: archetype, risk, formality lean, boundaries",
    ]
  },
  orchestrator: {
    title: "Orchestrator (orchestrator.py)",
    desc: "Active application runtime. It loads saved user state, resolves live message context, applies conversation memory, calls the planner, retrieval, assembly, evaluation, and formatting stages, then persists every turn artifact back to storage.",
    items: [
      "Loads: profile, analysis, interpretations, style preference",
      "Resolves: live context + follow-up intent + memory carry-forward",
      "Calls: Outfit Architect → Search → Assembler → Evaluator → Formatter",
      "Persists: live context, plan, filters, candidates, recommendations",
    ]
  },
  context_resolver: {
    title: "Occasion Resolver",
    desc: "Rule-based live-context extraction with phrase-priority matching. Identifies occasion, formality, time-of-day, specific needs, and whether the turn is a real follow-up based on prior recommendations.",
    items: [
      "Input: raw user message text",
      "Extracts: occasion_signal, formality_hint, time_hint, specific_needs",
      "Follow-up aware: only active when prior recommendations exist",
      "Example: 'work dinner, want to look taller' → occasion + formality + elongation",
    ]
  },
  query_builder: {
    title: "Outfit Architect (outfit_architect.py)",
    desc: "Planner agent that translates combined user context into a structured recommendation plan. It returns strict JSON with one or more retrieval directions and structured query documents that mirror the catalog embedding representation. Deterministic fallback planning exists when the LLM fails.",
    items: [
      "Input: saved profile + live context + conversation memory",
      "Output: RecommendationPlan with complete, paired, or mixed directions",
      "Sections: USER_NEED, PROFILE_AND_STYLE, GARMENT_REQUIREMENTS, FABRIC_AND_BUILD, PATTERN_AND_COLOR, OCCASION_AND_SIGNAL",
      "Server fallback: conservative complete/paired plan if LLM fails",
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
    title: "Embedding API",
    desc: "OpenAI text-embedding-3-small at 1536 dimensions. Same model is used for both catalog pre-embedding and live query embedding. Cosine similarity is the active distance metric.",
    items: [
      "Model: text-embedding-3-small",
      "Dimensions: 1536",
      "Cost: $0.02 / million tokens",
      "~150 tokens per query sentence",
    ]
  },
  vector_search: {
    title: "Catalog Search Agent + Vector Search",
    desc: "Embeds each architect query document, applies merged hard filters, runs cosine similarity against pgvector, hydrates products from `catalog_enriched`, and supports filter relaxation when retrieval is too narrow. The active runtime supports both complete outfits and paired directions.",
    items: [
      "Hard filters: GenderExpression, OccasionFit, FormalityLevel, StylingCompleteness",
      "Supports: complete directions and top/bottom pairing directions",
      "Relaxation order: occasion_fit, then formality_level",
      "Vector: HNSW index, cosine distance",
      "Returns: hydrated products + applied filter snapshot per query",
    ]
  },
  evaluator: {
    title: "Outfit Evaluator (LLM)",
    desc: "Active ranking component. It evaluates complete outfits and assembled pairs against body harmony, color, occasion, style, and user needs. If the LLM step fails, the runtime degrades gracefully to deterministic ordering based on assembly score and retrieval strength.",
    items: [
      "Input: 10-20 candidates + user profile + style pref + occasion",
      "Evaluates: body harmony, color, occasion, style, cohesion",
      "Graceful fallback: deterministic ranking when model call fails",
      "Output: top 3-5 ranked outfits with reasoning",
    ]
  },
  presentation: {
    title: "Response Formatter + UI",
    desc: "Formats ranked recommendations into user-facing outfit cards and renders them in the conversation UI. The active runtime now carries image, title, price, similarity, and product URL, with compatibility fallback for older recommendation payloads.",
    items: [
      "Shows: outfit images, title, price, reasoning, product link, similarity",
      "Prefers: result.outfits, falls back to legacy recommendations",
      "Follow-ups: 'show bolder', 'different color' loop through orchestrator",
    ]
  },
  catalog_upload: {
    title: "Catalog Upload",
    desc: "Raw product catalog uploaded (CSV/API). Contains base product fields: id, title, description, price, images, url. This is the starting point of the async enrichment pipeline.",
    items: ["Base fields: id, title, description, price, images, url", "Raw unprocessed garment data"]
  },
  enrichment: {
    title: "Attribute Enrichment Pipeline",
    desc: "Async process that analyzes each garment (via LLM vision + text analysis) and populates all 44 enum attributes + 2 text color attributes + 44 confidence scores. Produces the 102-column enriched catalog.",
    items: [
      "Input: title + description + product images",
      "Output: 44 enum attributes + 2 text colors",
      "Also: 44 confidence scores (one per attribute)",
      "Status: row_status + error_reason per row",
    ]
  },
  sentence_gen: {
    title: "Sentence Generator",
    desc: "Converts enriched attributes into one structured embedding document per garment. Covers silhouette, color, fabric, occasion, and style identity while preserving explicit labeled fields for retrieval compatibility.",
    items: [
      "Quality gate: confidence >= 0.6 per attribute",
      "Quality gate: skip if >40% attributes missing",
      "Output: one structured embedding document per garment",
      "Includes: title + description excerpt + all attributes",
    ]
  },
  embedding_batch: {
    title: "Batch Embedding",
    desc: "Embeds all catalog documents using OpenAI text-embedding-3-small at 1536 dimensions. Runs as batch job. Same model as query-time embedding for compatibility.",
    items: [
      "Model: text-embedding-3-small (same as query-time)",
      "Dimensions: 1536",
      "Batch size: 200 sentences per API call",
      "Cost: ~$0.03 for 10,000 garments",
    ]
  },
  catalog_db: {
    title: "Catalog Database",
    desc: "PostgreSQL with pgvector. Stores enriched product data in `catalog_enriched` plus embedding vectors in `catalog_item_embeddings`. HNSW index is used on the embedding column.",
    items: [
      "Enriched product rows live in: catalog_enriched",
      "Embedding column: VECTOR(1536)",
      "Structured document text stored for debugging",
      "HNSW index for cosine similarity search",
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
          <h1 style={{ fontSize: 14, fontWeight: 700, margin: 0, letterSpacing: 3, textTransform: "uppercase" }}>Fashion Styling AI — Complete System Architecture</h1>
        </div>
        <p style={{ fontSize: 9, color: C.textMuted, margin: "6px 0 10px 17px", letterSpacing: 0.5 }}>
          3-layer architecture: User Profiling · Application Intelligence · Catalog Pipeline &nbsp;·&nbsp; Click any node for details
        </p>
      </div>

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <div style={{ flex: d ? "0 0 62%" : "1", overflow: "auto", padding: "12px", transition: "flex 0.3s ease" }}>
          <svg viewBox="0 0 1080 920" style={{ width: "100%", height: "auto", minWidth: 700 }}>
            <defs>
              <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
                <path d="M 30 0 L 0 0 0 30" fill="none" stroke={C.border} strokeWidth="0.15" opacity="0.3" />
              </pattern>
            </defs>
            <rect width="1080" height="920" fill="url(#grid)" />

            {/* === LAYER 1: USER PROFILING === */}
            <LayerBand y={0} h={310} label="LAYER 1 — USER PROFILING (one-time onboarding)" color={C.layer1} />

            <Node x={30} y={30} w={190} h={80} title="User Onboarding" icon="●" items={["Gender, Age, Profession", "Manual input via UI"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("onboarding")} active={sel==="onboarding"} />

            <Node x={260} y={30} w={220} h={95} title="Image Analysis" icon="◐" items={["Upload photo → vision analysis", "Body: shape, proportions, volume", "Color: skin, hair, eyes, undertone", "Details: face, neck, shoulder, jaw"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("image_analysis")} active={sel==="image_analysis"} />

            <Node x={520} y={30} w={200} h={80} title="Interpretation Engine" icon="◈" items={["SeasonalColorGroup", "ContrastLevel, FrameStructure", "HeightCategory, WaistSizeBand"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("interpretation")} active={sel==="interpretation"} />

            <Node x={30} y={145} w={280} h={95} title="Style Preference (Image Selection)" icon="◧" items={["104 flat-lay image pool (52M + 52F)", "L1: 8 archetype grid → L2: 4 diagnostic", "→ L3: 4 refined | Select 3-5 total", "→ StyleArchetype, RiskTolerance, Boundaries"]}
              color={C.layer1} dim={C.layer1Dim} onClick={() => setSel("style_pref")} active={sel==="style_pref"} />

            {/* Arrows within Layer 1 */}
            <Arrow x1={220} y1={70} x2={260} y2={70} color={C.layer1} />
            <Arrow x1={480} y1={70} x2={520} y2={70} color={C.layer1} />

            {/* User Profile Store */}
            <DataStore x={760} y={30} w={280} h={110} label="⬡ User Profile Store" color={C.data} dim={C.dataDim}
              items={["onboarding: gender, age, profession", "analysis: body + color attributes", "interpretations: season, contrast, frame", "style_preference: archetype, risk, formality"]} />

            {/* Arrows to profile store */}
            <Arrow x1={120} y1={110} x2={760} y2={60} color={C.data} label="save" dashed />
            <Arrow x1={720} y1={70} x2={760} y2={70} color={C.data} label="save" dashed />
            <Arrow x1={310} y1={235} x2={760} y2={120} color={C.data} label="save" dashed />

            {/* Divider area */}
            <line x1={30} y1={280} x2={1050} y2={280} stroke={C.layer1} strokeWidth={0.3} opacity={0.2} strokeDasharray="6,3" />

            {/* === LAYER 2: APPLICATION === */}
            <LayerBand y={310} h={360} label="LAYER 2 — APPLICATION LAYER (per-request recommendation)" color={C.layer2} />

            {/* User message */}
            <Node x={30} y={335} w={200} h={50} title="User Message" icon="▸" items={['"I need outfit for a farewell party"']}
              color={C.layer2} dim={C.layer2Dim} onClick={null} active={false} />

            {/* Orchestrator */}
            <Node x={280} y={330} w={230} h={85} title="Orchestrator" icon="◉" items={["Loads saved user profile state", "Merges with live message", "Runs context resolver (rule-based)", "Sets hard filters → passes to Query Builder"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("orchestrator")} active={sel==="orchestrator"} />

            {/* Profile feed into orchestrator */}
            <CArrow x1={900} y1={140} x2={400} y2={330} cx={900} cy={260} color={C.data} label="load profile" />

            {/* Context Resolver */}
            <Node x={280} y={430} w={230} h={55} title="Context Resolver" icon="⊞" items={["occasion: party, formality: smart-casual", "time: evening, specific_needs: none"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("context_resolver")} active={sel==="context_resolver"} />

            <Arrow x1={130} y1={380} x2={280} y2={370} color={C.layer2} label="user_need" />
            <Arrow x1={395} y1={415} x2={395} y2={430} color={C.layer2} />

            {/* Knowledge Context */}
            <DataStore x={30} y={510} w={200} h={90} label="⬡ Knowledge Context" color={C.warn} dim={C.warnDim}
              items={["M01-M04: Styling principles", "M05: Occasion conventions", "M08-M09: Detail + Fabric", "Injected into LLM system prompt"]} />

            {/* Query Builder */}
            <Node x={280} y={510} w={230} h={100} title="Query Builder (LLM)" icon="◆" items={["System prompt + knowledge context", "Structured output sections:", "GARMENT_REQUIREMENTS", "FABRIC_AND_BUILD, PATTERN_AND_COLOR", "OCCASION_AND_SIGNAL", "→ catalog-facing retrieval language"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("query_builder")} active={sel==="query_builder"} />

            <Arrow x1={395} y1={485} x2={395} y2={510} color={C.layer2} label="combined context" />
            <Arrow x1={230} y1={555} x2={280} y2={555} color={C.warn} label="knowledge" dashed />

            {/* Embedding API (query-time) */}
            <Node x={560} y={510} w={180} h={60} title="Embed Query" icon="⊕" items={["text-embedding-3-small", "1536 dims, cosine similarity"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("embedding_api")} active={sel==="embedding_api"} />

            <Arrow x1={510} y1={545} x2={560} y2={545} color={C.layer2} label="query text" />

            {/* Vector Search */}
            <Node x={790} y={480} w={220} h={85} title="Vector Search (pgvector)" icon="⊙" items={["Hard filters: Gender, Occasion,", "  StylingCompleteness=complete", "Then: cosine similarity on embedding", "Returns: top 10-15 candidates"]}
              color={C.layer2} dim={C.layer2Dim} onClick={() => setSel("vector_search")} active={sel==="vector_search"} />

            <Arrow x1={740} y1={540} x2={790} y2={530} color={C.layer2} label="query vector" />

            {/* Arrow from catalog DB to vector search */}
            <CArrow x1={900} y1={810} x2={900} y2={565} cx={1040} cy={700} color={C.layer3} label="catalog vectors" />

            {/* Evaluator */}
            <Node x={560} y={610} w={220} h={80} title="Outfit Evaluator (LLM)" icon="◆" items={["Target next stage, not fully active yet", "Should reason: body, color, occasion, style", "Should rerank retrieved candidates", "Returns: ranked top 3-5 with reasoning"]}
              color={C.accent} dim={C.accentDim} onClick={() => setSel("evaluator")} active={sel==="evaluator"} />

            <Arrow x1={870} y1={565} x2={780} y2={620} color={C.layer2} label="10-20 products" />
            <CArrow x1={900} y1={140} x2={580} y2={610} cx={1060} cy={400} color={C.data} label="user profile" />

            {/* Presentation */}
            <Node x={280} y={625} w={230} h={55} title="Presentation to User" icon="▸" items={["Top 3-5 outfits with images + reasoning", "Follow-up → loops back to Orchestrator"]}
              color={C.accent} dim={C.accentDim} onClick={() => setSel("presentation")} active={sel==="presentation"} />

            <Arrow x1={560} y1={650} x2={510} y2={650} color={C.accent} label="ranked results" />

            {/* Follow-up loop */}
            <CArrow x1={280} y1={645} x2={280} y2={380} cx={180} cy={510} color={C.accent} label="follow-up loop" />

            {/* Divider */}
            <line x1={30} y1={695} x2={1050} y2={695} stroke={C.layer2} strokeWidth={0.3} opacity={0.2} strokeDasharray="6,3" />

            {/* === LAYER 3: CATALOG === */}
            <LayerBand y={700} h={220} label="LAYER 3 — CATALOG PIPELINE (async enrichment)" color={C.layer3} />

            {/* Upload */}
            <Node x={30} y={730} w={170} h={55} title="Catalog Upload" icon="▲" items={["CSV / API ingestion", "id, title, desc, price, images, url"]}
              color={C.layer3} dim={C.layer3Dim} onClick={() => setSel("catalog_upload")} active={sel==="catalog_upload"} />

            {/* Enrichment */}
            <Node x={240} y={725} w={230} h={75} title="Attribute Enrichment" icon="◈" items={["LLM vision + text analysis per garment", "→ 44 enum + 2 text color attributes", "→ 44 confidence scores per attribute", "→ row_status + error_reason"]}
              color={C.layer3} dim={C.layer3Dim} onClick={() => setSel("enrichment")} active={sel==="enrichment"} />

            <Arrow x1={200} y1={757} x2={240} y2={757} color={C.layer3} />

            {/* Sentence Gen */}
            <Node x={510} y={725} w={200} h={75} title="Document Generator" icon="≡" items={["Converts enriched rows → structured docs", "Embedding-friendly labeled format", "Confidence gating (≥0.6)", "Includes title + description excerpt"]}
              color={C.layer3} dim={C.layer3Dim} onClick={() => setSel("sentence_gen")} active={sel==="sentence_gen"} />

            <Arrow x1={470} y1={757} x2={510} y2={757} color={C.layer3} label="102 cols" />

            {/* Batch Embed */}
            <Node x={510} y={825} w={200} h={60} title="Batch Embedding" icon="⊕" items={["text-embedding-3-small (same model)", "1536 dims, batch size 200", "~$0.03 for 10K garments"]}
              color={C.layer3} dim={C.layer3Dim} onClick={() => setSel("embedding_batch")} active={sel==="embedding_batch"} />

            <Arrow x1={610} y1={800} x2={610} y2={825} color={C.layer3} label="sentences" />

            {/* Catalog DB */}
            <DataStore x={790} y={735} w={250} h={95} label="⬡ Catalog Database (pgvector)" color={C.layer3} dim={C.layer3Dim}
              items={["catalog_enriched + catalog_item_embeddings", "1 embedding column: VECTOR(1536)", "structured doc text stored for debug", "HNSW index, cosine similarity"]} />

            <Arrow x1={710} y1={855} x2={790} y2={810} color={C.layer3} label="vectors" />
            <Arrow x1={710} y1={757} x2={790} y2={757} color={C.layer3} label="enriched data" />

            {/* Compatibility callout */}
            <rect x={510} y={890} width={200} height={22} rx={3} fill={C.warnDim} stroke={C.warn} strokeWidth={0.5} />
            <text x={610} y={904} fontSize="7" fontWeight="600" fill={C.warn} fontFamily={F} textAnchor="middle">⚠ Same model + dims for catalog & query</text>

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
