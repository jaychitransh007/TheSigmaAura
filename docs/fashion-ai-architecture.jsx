/**
 * Sigma Aura — High-Level System Architecture
 * Last updated: April 5, 2026
 *
 * Render at: https://component.gallery/preview or any React sandbox
 * Single-screen overview of the entire platform: surfaces, pipelines, data, and use cases.
 */

const C = {
  bg: "#08090d",
  surface: "#0e1018",
  surfaceAlt: "#141620",
  border: "#1e2030",
  borderHi: "#3a3f5c",
  text: "#d8dae6",
  muted: "#7a7f99",
  dim: "#4a4e66",
  entry: "#c49a6a",
  entryDim: "#c49a6a18",
  intel: "#6a9ec4",
  intelDim: "#6a9ec418",
  runtime: "#8bc46a",
  runtimeDim: "#8bc46a18",
  output: "#c46a9e",
  outputDim: "#c46a9e18",
  data: "#9e8bc4",
  dataDim: "#9e8bc418",
  safety: "#c4b86a",
  safetyDim: "#c4b86a18",
};

const F = "'JetBrains Mono','SF Mono',monospace";

/* ── Primitives ── */

const Box = ({ x, y, w, h, label, sub, color, dim, items, radius = 6 }) => (
  <g>
    <rect x={x} y={y} width={w} height={h} rx={radius} fill={dim || C.surface} stroke={color || C.border} strokeWidth={0.7} />
    <text x={x + w / 2} y={y + 14} fontSize="9" fontWeight="700" fill={color || C.text} fontFamily={F} textAnchor="middle">{label}</text>
    {sub && <text x={x + w / 2} y={y + 24} fontSize="6.5" fill={C.muted} fontFamily={F} textAnchor="middle">{sub}</text>}
    {items && items.map((t, i) => (
      <text key={i} x={x + w / 2} y={y + (sub ? 36 : 28) + i * 11} fontSize="6.5" fill={C.muted} fontFamily={F} textAnchor="middle">{t}</text>
    ))}
  </g>
);

const Pill = ({ x, y, w, label, color }) => (
  <g>
    <rect x={x} y={y} width={w} height={18} rx={9} fill={color + "20"} stroke={color} strokeWidth={0.5} />
    <text x={x + w / 2} y={y + 12} fontSize="7" fontWeight="600" fill={color} fontFamily={F} textAnchor="middle">{label}</text>
  </g>
);

const Arrow = ({ x1, y1, x2, y2, color = C.dim, label }) => {
  const dx = x2 - x1, dy = y2 - y1, len = Math.sqrt(dx * dx + dy * dy);
  if (len === 0) return null;
  const ux = dx / len, uy = dy / len;
  const ax = x2 - ux * 4, ay = y2 - uy * 4;
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  return (
    <g>
      <line x1={x1} y1={y1} x2={ax} y2={ay} stroke={color} strokeWidth={0.7} opacity={0.45} />
      <polygon points={`${x2},${y2} ${x2 - ux * 5 - uy * 2.5},${y2 - uy * 5 + ux * 2.5} ${x2 - ux * 5 + uy * 2.5},${y2 - uy * 5 - ux * 2.5}`} fill={color} opacity={0.45} />
      {label && <text x={mx} y={my - 3} fontSize="6" fill={C.dim} fontFamily={F} textAnchor="middle">{label}</text>}
    </g>
  );
};

const Band = ({ y, h, label, color }) => (
  <g>
    <rect x={0} y={y} width={980} height={h} fill={color} opacity={0.03} />
    <line x1={0} y1={y} x2={980} y2={y} stroke={color} strokeWidth={0.4} opacity={0.18} />
    <text x={12} y={y + 12} fontSize="7" fontWeight="700" fill={color} fontFamily={F} letterSpacing={1.5} opacity={0.55}>{label}</text>
  </g>
);

const Store = ({ x, y, w, h, label, items, color }) => (
  <g>
    <rect x={x} y={y} width={w} height={h} rx={4} fill={color + "10"} stroke={color} strokeWidth={0.5} strokeDasharray="3,2" />
    <text x={x + w / 2} y={y + 12} fontSize="7.5" fontWeight="600" fill={color} fontFamily={F} textAnchor="middle">{label}</text>
    {items && items.map((t, i) => (
      <text key={i} x={x + w / 2} y={y + 24 + i * 10} fontSize="6" fill={C.muted} fontFamily={F} textAnchor="middle">{t}</text>
    ))}
  </g>
);

/* ════════════════════════════════════════════════════════════════════
   MAIN DIAGRAM
   ════════════════════════════════════════════════════════════════════ */

export default function AuraArchitecture() {
  return (
    <div style={{ background: C.bg, padding: 16, borderRadius: 12, overflow: "auto" }}>

      {/* ── Title ── */}
      <div style={{ textAlign: "center", marginBottom: 8 }}>
        <div style={{ fontFamily: F, fontSize: 16, fontWeight: 700, color: C.text, letterSpacing: 1 }}>SIGMA AURA — SYSTEM ARCHITECTURE</div>
        <div style={{ fontFamily: F, fontSize: 10, color: C.muted, marginTop: 2 }}>Personal Fashion Copilot · Stylist for retention, shopping for revenue</div>
      </div>

      {/* ── Use-Case Pills ── */}
      <svg width="980" height="30" style={{ display: "block", margin: "0 auto 4px" }}>
        <Pill x={30}  y={6} w={120} label="Dress Me" color={C.entry} />
        <Pill x={160} y={6} w={120} label="Style This" color={C.entry} />
        <Pill x={290} y={6} w={120} label="Check My Outfit" color={C.entry} />
        <Pill x={420} y={6} w={120} label="Should I Buy?" color={C.entry} />
        <Pill x={550} y={6} w={120} label="What Suits Me?" color={C.entry} />
        <Pill x={680} y={6} w={120} label="Plan a Trip" color={C.entry} />
        <Pill x={810} y={6} w={120} label="Try It On Me" color={C.entry} />
      </svg>

      {/* ── Main SVG ── */}
      <svg viewBox="0 0 980 620" width="980" style={{ display: "block", margin: "0 auto", fontFamily: F }}>

        {/* ── Layer bands ── */}
        <Band y={0}   h={70}  label="ENTRY SURFACES"       color={C.entry} />
        <Band y={70}  h={100} label="USER INTELLIGENCE"     color={C.intel} />
        <Band y={170} h={170} label="INTENT RUNTIME"        color={C.runtime} />
        <Band y={340} h={80}  label="OUTPUT & EXPERIENCE"   color={C.output} />
        <Band y={420} h={90}  label="SAFETY & TRUST"        color={C.safety} />
        <Band y={510} h={110} label="DATA STORES"           color={C.data} />

        {/* ═══ ENTRY SURFACES ═══ */}
        <Box x={60}  y={18} w={200} h={42} label="Web App" sub="Onboarding · Chat · Wardrobe · Profile" color={C.entry} dim={C.entryDim} />
        <Box x={300} y={18} w={200} h={42} label="Chat Management" sub="Rename · Delete · History · Filters" color={C.entry} dim={C.entryDim} />
        <Box x={540} y={18} w={200} h={42} label="Wardrobe Studio" sub="Add · Edit · Delete · Search · Filters" color={C.entry} dim={C.entryDim} />
        <Box x={780} y={18} w={150} h={42} label="Catalog Admin" sub="Upload · Enrich · Embed" color={C.entry} dim={C.entryDim} />

        {/* ═══ USER INTELLIGENCE ═══ */}
        <Box x={30}  y={82} w={140} h={78} label="Onboarding" color={C.intel} dim={C.intelDim}
          items={["OTP + Profile", "Images (body, head)", "Style Preferences"]} />
        <Box x={185} y={82} w={140} h={78} label="Analysis Pipeline" sub="3 agents · gpt-5.4" color={C.intel} dim={C.intelDim}
          items={["Body Type", "Color Analysis", "Detail Analysis"]} />
        <Box x={340} y={82} w={140} h={78} label="Interpretations" color={C.intel} dim={C.intelDim}
          items={["Seasonal Color Group", "Color Palette (B/A/A)", "Frame · Height · Contrast"]} />
        <Box x={495} y={82} w={140} h={78} label="Digital Draping" sub="3-round LLM vision" color={C.intel} dim={C.intelDim}
          items={["Warm vs Cool", "Season Refinement", "Cross-Temp Confirm"]} />
        <Box x={650} y={82} w={140} h={78} label="Style Profile" color={C.intel} dim={C.intelDim}
          items={["Primary Archetype", "Risk · Formality", "Comfort Boundaries"]} />
        <Box x={805} y={82} w={140} h={78} label="Confidence" color={C.intel} dim={C.intelDim}
          items={["Profile Confidence", "Recommendation Conf.", "9-Factor Scoring"]} />

        {/* Intelligence arrows */}
        <Arrow x1={100} y1={60} x2={100} y2={82} color={C.intel} />
        <Arrow x1={170} y1={121} x2={185} y2={121} color={C.intel} />
        <Arrow x1={325} y1={121} x2={340} y2={121} color={C.intel} />
        <Arrow x1={480} y1={121} x2={495} y2={121} color={C.intel} />
        <Arrow x1={635} y1={121} x2={650} y2={121} color={C.intel} />
        <Arrow x1={790} y1={121} x2={805} y2={121} color={C.intel} />

        {/* ═══ INTENT RUNTIME ═══ */}
        {/* Planner row */}
        <Box x={60}  y={185} w={180} h={48} label="Copilot Planner" sub="gpt-5.4 · Intent Router" color={C.runtime} dim={C.runtimeDim}
          items={["11 intents · 6 actions"]} />
        <Box x={260} y={185} w={180} h={48} label="Context Compiler" sub="Profile + Memory + Wardrobe" color={C.runtime} dim={C.runtimeDim}
          items={["Conversation Memory carry-fwd"]} />
        <Box x={460} y={185} w={180} h={48} label="Orchestrator" sub="Central dispatch + pipeline" color={C.runtime} dim={C.runtimeDim}
          items={["Latency tracked per stage"]} />
        <Box x={660} y={185} w={280} h={48} label="Dedicated Intent Handlers" color={C.runtime} dim={C.runtimeDim}
          items={["Outfit Check · Shopping · Pairing · Style · Capsule · Explain"]} />

        {/* Planner arrows */}
        <Arrow x1={240} y1={209} x2={260} y2={209} color={C.runtime} />
        <Arrow x1={440} y1={209} x2={460} y2={209} color={C.runtime} />
        <Arrow x1={640} y1={209} x2={660} y2={209} color={C.runtime} />

        {/* Pipeline row */}
        <Box x={60}  y={248} w={130} h={78} label="Outfit Architect" sub="gpt-5.4 · LLM planner" color={C.runtime} dim={C.runtimeDim}
          items={["Plan type + directions", "Concept-first pairing", "Follow-up intent rules"]} />
        <Box x={205} y={248} w={130} h={78} label="Catalog Search" sub="pgvector · cosine sim" color={C.runtime} dim={C.runtimeDim}
          items={["Hard + soft filters", "12 products / query", "No filter relaxation"]} />
        <Box x={350} y={248} w={130} h={78} label="Assembler" sub="Deterministic" color={C.runtime} dim={C.runtimeDim}
          items={["Compatibility pruning", "Follow-up scoring", "Max 30 candidates"]} />
        <Box x={495} y={248} w={130} h={78} label="Evaluator" sub="gpt-5.4 · Dual scoring" color={C.runtime} dim={C.runtimeDim}
          items={["8 criteria + 8 archetypes", "Delta-aware ranking", "Fallback: assembly score"]} />
        <Box x={640} y={248} w={140} h={78} label="Wardrobe Engine" color={C.runtime} dim={C.runtimeDim}
          items={["Wardrobe-first retrieval", "Gap detection", "Source labeling"]} />
        <Box x={795} y={248} w={145} h={78} label="Virtual Try-On" sub="Gemini · Parallel" color={C.runtime} dim={C.runtimeDim}
          items={["Body-preserving prompt", "Quality gate", "Disk + DB cache"]} />

        {/* Pipeline arrows */}
        <Arrow x1={190} y1={287} x2={205} y2={287} color={C.runtime} />
        <Arrow x1={335} y1={287} x2={350} y2={287} color={C.runtime} />
        <Arrow x1={480} y1={287} x2={495} y2={287} color={C.runtime} />
        <Arrow x1={625} y1={287} x2={640} y2={287} color={C.runtime} />
        <Arrow x1={780} y1={287} x2={795} y2={287} color={C.runtime} />

        {/* ═══ OUTPUT & EXPERIENCE ═══ */}
        <Box x={60}  y={352} w={180} h={56} label="Response Formatter" sub="Max 3 outfits · Source-aware" color={C.output} dim={C.outputDim}
          items={["Intent-aware messaging", "Follow-up suggestion chips"]} />
        <Box x={260} y={352} w={180} h={56} label="3-Column PDP Cards" sub="Thumbnails · Hero · Info" color={C.output} dim={C.outputDim}
          items={["Radar chart + progress bars", "Buy Now · Like / Dislike"]} />
        <Box x={460} y={352} w={180} h={56} label="Chat UI" sub="Sidebar · Composer · Feed" color={C.output} dim={C.outputDim}
          items={["Image attach · Wardrobe pick", "Stage narration (QnA)"]} />
        <Box x={660} y={352} w={140} h={56} label="Wardrobe UI" sub="Closet Studio" color={C.output} dim={C.outputDim}
          items={["Search · Category · Color", "Edit modal · Delete"]} />
        <Box x={815} y={352} w={130} h={56} label="Profile UI" sub="Style Code · Palette" color={C.output} dim={C.outputDim}
          items={["Inline edit toggle", "Color chips (B/A/A)"]} />

        {/* Output arrows */}
        <Arrow x1={240} y1={380} x2={260} y2={380} color={C.output} />
        <Arrow x1={440} y1={380} x2={460} y2={380} color={C.output} />

        {/* ═══ SAFETY & TRUST ═══ */}
        <Box x={60}  y={432} w={180} h={66} label="Image Moderation" sub="Dual-layer" color={C.safety} dim={C.safetyDim}
          items={["Heuristic blocklist", "Vision API check", "Restricted categories"]} />
        <Box x={260} y={432} w={180} h={66} label="Policy Engine" sub="Fail-closed guardrails" color={C.safety} dim={C.safetyDim}
          items={["Nudity / minors block", "Lingerie exclusion", "Try-on quality gate"]} />
        <Box x={460} y={432} w={180} h={66} label="Comfort Learning" sub="Behavioral refinement" color={C.safety} dim={C.safetyDim}
          items={["Outfit like signals", "Seasonal palette update", "Threshold: 5 high-intent"]} />
        <Box x={660} y={432} w={140} h={66} label="Feedback Loop" sub="Per-outfit capture" color={C.safety} dim={C.safetyDim}
          items={["Like / Dislike + notes", "Turn-level correlation", "Comfort learning input"]} />
        <Box x={815} y={432} w={130} h={66} label="Dependency Inst." sub="First-50 validation" color={C.safety} dim={C.safetyDim}
          items={["Turn-completion events", "Cohort anchors", "Memory-input lift"]} />

        {/* ═══ DATA STORES ═══ */}
        <Store x={30}  y={525} w={150} h={80} label="User Data" color={C.data}
          items={["onboarding_profiles", "onboarding_images", "analysis + interpretations", "style_preference", "effective_seasonal_groups"]} />
        <Store x={195} y={525} w={150} h={80} label="Conversations" color={C.data}
          items={["conversations (+ title)", "conversation_turns", "session_context_json", "feedback_events"]} />
        <Store x={360} y={525} w={150} h={80} label="Wardrobe" color={C.data}
          items={["user_wardrobe_items", "46 enrichment attributes", "is_active soft delete", "image_url + image_path"]} />
        <Store x={525} y={525} w={150} h={80} label="Catalog" color={C.data}
          items={["catalog_enriched (50+ attr)", "catalog_item_embeddings", "pgvector 1536d cosine", "catalog_jobs"]} />
        <Store x={690} y={525} w={150} h={80} label="Try-On & Media" color={C.data}
          items={["virtual_tryon_images", "Disk: data/tryon/images/", "Cache by garment ID set", "quality_score_pct"]} />
        <Store x={855} y={525} w={105} h={80} label="Telemetry" color={C.data}
          items={["model_calls", "tool_traces", "policy_event_log", "dependency_validation"]} />

        {/* ── Cross-layer vertical flows ── */}
        {/* Entry → Intelligence */}
        <Arrow x1={160} y1={60} x2={255} y2={82} color={C.intel} label="analyze" />
        {/* Intelligence → Runtime */}
        <Arrow x1={410} y1={160} x2={350} y2={185} color={C.runtime} label="context" />
        <Arrow x1={720} y1={160} x2={550} y2={185} color={C.runtime} label="confidence" />
        {/* Runtime → Output */}
        <Arrow x1={150} y1={326} x2={150} y2={352} color={C.output} label="format" />
        <Arrow x1={550} y1={233} x2={550} y2={352} color={C.output} label="render" />
        {/* Safety ↔ Runtime */}
        <Arrow x1={150} y1={432} x2={150} y2={326} color={C.safety} label="guard" />
        <Arrow x1={550} y1={498} x2={550} y2={326} color={C.safety} label="learn" />
        {/* Runtime → Data */}
        <Arrow x1={270} y1={326} x2={270} y2={525} color={C.data} label="persist" />
        <Arrow x1={435} y1={326} x2={435} y2={525} color={C.data} label="wardrobe" />
        <Arrow x1={600} y1={326} x2={600} y2={525} color={C.data} label="catalog" />
        <Arrow x1={867} y1={326} x2={765} y2={525} color={C.data} label="cache" />

      </svg>

      {/* ── Legend ── */}
      <svg width="980" height="28" style={{ display: "block", margin: "4px auto 0" }}>
        {[
          { x: 60,  label: "Entry Surfaces", color: C.entry },
          { x: 210, label: "User Intelligence", color: C.intel },
          { x: 380, label: "Intent Runtime", color: C.runtime },
          { x: 540, label: "Output & Experience", color: C.output },
          { x: 720, label: "Safety & Trust", color: C.safety },
          { x: 870, label: "Data Stores", color: C.data },
        ].map(({ x, label, color }) => (
          <g key={label}>
            <rect x={x} y={8} width={10} height={10} rx={2} fill={color} opacity={0.5} />
            <text x={x + 16} y={17} fontSize="8" fill={C.muted} fontFamily={F}>{label}</text>
          </g>
        ))}
      </svg>

      {/* ── Tech Stack Summary ── */}
      <div style={{ fontFamily: F, fontSize: 9, color: C.muted, textAlign: "center", marginTop: 8, lineHeight: 1.6 }}>
        <span style={{ color: C.intel }}>Models:</span> gpt-5.4 (planner/architect/evaluator/analysis) · gpt-5-mini (catalog enrichment) · text-embedding-3-small (1536d) · gemini-3.1-flash-image-preview (try-on)
        <br />
        <span style={{ color: C.data }}>Stack:</span> Python · FastAPI · Supabase (PostgreSQL + pgvector) · Server-rendered HTML/CSS/JS (no framework)
        <br />
        <span style={{ color: C.safety }}>Stats:</span> 35 migrations · 264 tests · 11 intents · 7 follow-up types · 50+ catalog attributes · 46 wardrobe attributes
      </div>
    </div>
  );
}
