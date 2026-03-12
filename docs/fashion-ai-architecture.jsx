import { useState } from "react";

const COLORS = {
  bg: "#0a0a0f",
  surface: "#12121a",
  surfaceHover: "#1a1a26",
  border: "#2a2a3a",
  borderActive: "#4a4a6a",
  text: "#e8e8f0",
  textMuted: "#8888a0",
  textDim: "#5a5a72",
  accent1: "#c4956a",
  accent1Dim: "#c4956a33",
  accent2: "#6a9ec4",
  accent2Dim: "#6a9ec433",
  accent3: "#8bc46a",
  accent3Dim: "#8bc46a33",
  accent4: "#c46a9e",
  accent4Dim: "#c46a9e33",
  accent5: "#c4c46a",
  accent5Dim: "#c4c46a33",
  accent6: "#9e6ac4",
  accent6Dim: "#9e6ac433",
  white: "#ffffff",
};

const AgentNode = ({ title, subtitle, items, color, colorDim, x, y, width = 220, onClick, isActive }) => (
  <g
    onClick={onClick}
    style={{ cursor: "pointer" }}
    className="agent-node"
  >
    <rect
      x={x}
      y={y}
      width={width}
      height={items ? 28 + items.length * 18 + 16 : 52}
      rx={6}
      fill={isActive ? colorDim : COLORS.surface}
      stroke={isActive ? color : COLORS.border}
      strokeWidth={isActive ? 1.5 : 0.5}
    />
    <rect
      x={x}
      y={y}
      width={width}
      height={26}
      rx={6}
      fill={colorDim}
    />
    <rect
      x={x}
      y={y + 20}
      width={width}
      height={6}
      fill={colorDim}
    />
    <circle cx={x + 14} cy={y + 13} r={4} fill={color} opacity={0.8} />
    <text x={x + 24} y={y + 17} fill={COLORS.text} fontSize="11" fontWeight="600" fontFamily="'JetBrains Mono', monospace">
      {title}
    </text>
    {subtitle && !items && (
      <text x={x + 14} y={y + 40} fill={COLORS.textMuted} fontSize="9" fontFamily="'JetBrains Mono', monospace">
        {subtitle}
      </text>
    )}
    {items && items.map((item, i) => (
      <text key={i} x={x + 14} y={y + 42 + i * 18} fill={COLORS.textMuted} fontSize="8.5" fontFamily="'JetBrains Mono', monospace">
        {item}
      </text>
    ))}
  </g>
);

const Arrow = ({ x1, y1, x2, y2, color = COLORS.textDim, dashed = false, label = "" }) => {
  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  const ux = dx / len;
  const uy = dy / len;
  const ax2 = x2 - ux * 6;
  const ay2 = y2 - uy * 6;

  return (
    <g>
      <line
        x1={x1} y1={y1} x2={ax2} y2={ay2}
        stroke={color}
        strokeWidth={1}
        strokeDasharray={dashed ? "4,3" : "none"}
        opacity={0.6}
      />
      <polygon
        points={`${x2},${y2} ${x2 - ux * 7 - uy * 3.5},${y2 - uy * 7 + ux * 3.5} ${x2 - ux * 7 + uy * 3.5},${y2 - uy * 7 - ux * 3.5}`}
        fill={color}
        opacity={0.6}
      />
      {label && (
        <>
          <rect
            x={midX - label.length * 2.8}
            y={midY - 7}
            width={label.length * 5.6}
            height={14}
            rx={3}
            fill={COLORS.bg}
          />
          <text x={midX} y={midY + 3} fill={COLORS.textDim} fontSize="7.5" fontFamily="'JetBrains Mono', monospace" textAnchor="middle">
            {label}
          </text>
        </>
      )}
    </g>
  );
};

const CurvedArrow = ({ x1, y1, x2, y2, cx, cy, color = COLORS.textDim, label = "" }) => {
  const path = `M ${x1},${y1} Q ${cx},${cy} ${x2},${y2}`;
  const t = 0.95;
  const nearEndX = (1-t)*(1-t)*x1 + 2*(1-t)*t*cx + t*t*x2;
  const nearEndY = (1-t)*(1-t)*y1 + 2*(1-t)*t*cy + t*t*y2;
  const dx = x2 - nearEndX;
  const dy = y2 - nearEndY;
  const len = Math.sqrt(dx*dx + dy*dy);
  const ux = dx/len;
  const uy = dy/len;
  const midT = 0.5;
  const midX = (1-midT)*(1-midT)*x1 + 2*(1-midT)*midT*cx + midT*midT*x2;
  const midY = (1-midT)*(1-midT)*y1 + 2*(1-midT)*midT*cy + midT*midT*y2;

  return (
    <g>
      <path d={path} stroke={color} strokeWidth={1} fill="none" opacity={0.5} />
      <polygon
        points={`${x2},${y2} ${x2 - ux*7 - uy*3.5},${y2 - uy*7 + ux*3.5} ${x2 - ux*7 + uy*3.5},${y2 - uy*7 - ux*3.5}`}
        fill={color} opacity={0.5}
      />
      {label && (
        <>
          <rect x={midX - label.length*2.8} y={midY-7} width={label.length*5.6} height={14} rx={3} fill={COLORS.bg} />
          <text x={midX} y={midY+3} fill={COLORS.textDim} fontSize="7.5" fontFamily="'JetBrains Mono', monospace" textAnchor="middle">{label}</text>
        </>
      )}
    </g>
  );
};

const SectionLabel = ({ x, y, text, color }) => (
  <g>
    <line x1={x} y1={y + 4} x2={x + 18} y2={y + 4} stroke={color} strokeWidth={2} opacity={0.6} />
    <text x={x + 24} y={y + 8} fill={color} fontSize="10" fontWeight="700" fontFamily="'JetBrains Mono', monospace" letterSpacing="2" opacity={0.8}>
      {text}
    </text>
  </g>
);

const details = {
  user_context: {
    title: "User Context Layer",
    description: "Persistent client profile collected once and referenced every time. Contains all observable and derived attributes about the client.",
    sections: [
      { name: "Identity", items: ["Gender", "Age", "Profession"] },
      { name: "Body Type", items: ["Height, Waist, Shoulder-to-hip ratio", "Torso-to-leg ratio, BodyShape", "VisualWeight, ArmVolume", "MidsectionState, BustVolume"] },
      { name: "Color Analysis", items: ["SkinSurfaceColor, SkinUndertone", "HairColor, EyeColor", "HairColorTemperature, EyeClarity"] },
      { name: "Additional Details", items: ["FaceShape, NeckLength, HairLength", "ShoulderSlope, JawlineDefinition"] },
      { name: "Interpretations", items: ["ContrastLevel, WaistSizeBand", "FrameStructure, SeasonalColorGroup"] },
    ],
  },
  style_pref: {
    title: "Style Preference Layer",
    description: "Captures the client's aesthetic identity — who they want to be, not just who they are. Collected through guided visual conversation.",
    sections: [
      { name: "Attributes", items: ["StyleArchetype (classic, minimal, bohemian...)", "RiskTolerance (conservative → adventurous)", "ComfortPriorities (hard vetoes)", "AspirationGap (current vs desired self)"] },
      { name: "Collection Method", items: ["Show curated reference images", "Capture reactions + reasoning", "Agent interprets to build profile"] },
    ],
  },
  orchestrator: {
    title: "Orchestrator Agent",
    description: "The brain of the system. Receives user requests, decomposes into sub-tasks, routes to specialist agents, manages handoffs, and synthesizes final output.",
    sections: [
      { name: "Responsibilities", items: ["Parse user request intent", "Pull User Context + Style Preference", "Plan agent execution sequence", "Manage data flow between agents", "Set target recommendation count", "Handle follow-up loops"] },
    ],
  },
  occasion: {
    title: "Occasion Analyst Agent",
    description: "Interprets the raw occasion description into structured styling constraints using deep knowledge of social and cultural dress conventions.",
    sections: [
      { name: "Input", items: ["Raw occasion description from user"] },
      { name: "Output", items: ["Formality level & dress code", "Setting & climate context", "Time of day", "Social role (guest, host, participant)", "Cultural considerations", "Implicit rules & boundaries"] },
    ],
  },
  architect: {
    title: "Outfit Architect Agent",
    description: "The creative core. Reasons about what the ideal outfit should be and produces multiple outfit directions — each with different garment counts and detailed attribute-level specs.",
    sections: [
      { name: "Input", items: ["User Context + Style Preference", "Structured Occasion Context"] },
      { name: "Output — Multiple Directions", items: ["Direction 1: Complete garment spec", "Direction 2: Two-piece specs + relationship", "Direction 3: Three-piece specs + relationship", "(Directions vary by occasion)"] },
      { name: "Knowledge Required", items: ["Universal principles (proportion, color theory)", "Body-shape-to-silhouette mapping", "Seasonal palette application", "Proportion correction strategies"] },
    ],
  },
  catalog_search: {
    title: "Catalog Search Agent",
    description: "Translates conceptual outfit directions into queries against the 46-attribute garment catalog using hybrid search — hard filters first, then multi-embedding semantic ranking.",
    sections: [
      { name: "Hybrid Search Strategy", items: ["Hard filters: GenderExpression, OccasionFit,", "  StylingCompleteness, GarmentCategory", "Then: Multi-embedding similarity ranking"] },
      { name: "6 Embedding Columns", items: ["Occasion embedding", "Silhouette & proportion embedding", "Color & visual embedding", "Fabric & construction embedding", "Style identity embedding", "Pairing embedding"] },
      { name: "Constraint Relaxation", items: ["Loosen: color specifics first", "Preserve: fit, occasion appropriateness"] },
    ],
  },
  assembler: {
    title: "Outfit Assembler Agent",
    description: "Evaluates garment combinations when catalog returns individual pieces. Reasons about garment-to-garment compatibility to build complete outfits.",
    sections: [
      { name: "Compatibility Dimensions", items: ["Color harmony & temperature consistency", "Formality alignment", "Visual weight distribution & balance", "Fabric weight & texture cohesion", "Volume balance (top vs bottom)", "Proportion interplay"] },
      { name: "Logic", items: ["Complete garments pass through directly", "Individual pieces get combined + evaluated", "Uses pairing embeddings + LLM reasoning"] },
    ],
  },
  evaluator: {
    title: "Outfit Evaluator Agent",
    description: "Scores and ranks all candidate outfits holistically — both complete garments found and assembled combinations — using LLM reasoning rather than rigid formulas.",
    sections: [
      { name: "Evaluation Criteria", items: ["Body fit: does it flatter this person?", "Color match: seasonal palette alignment?", "Occasion: appropriate for context?", "Style match: archetype & risk tolerance?", "Cohesion: do pieces work together?", "Overall: would they feel good in this?"] },
      { name: "Output", items: ["Ranked list with reasoning per candidate"] },
    ],
  },
  presentation: {
    title: "Presentation Agent",
    description: "Communicates recommendations to the client with accessible reasoning. Handles follow-up requests that loop back through the Orchestrator.",
    sections: [
      { name: "Responsibilities", items: ["Present top 3-5 recommendations", "Explain reasoning in plain language", "Handle feedback & follow-ups", "Route refinements back to Orchestrator"] },
    ],
  },
  knowledge: {
    title: "Knowledge Context Layer",
    description: "Domain expertise embedded into each agent's system prompt. Not a separate agent — it's the fashion education each specialist carries.",
    sections: [
      { name: "For Outfit Architect", items: ["Universal styling principles", "Body-shape-to-silhouette guidelines", "Seasonal palette definitions", "Proportion correction strategies"] },
      { name: "For Occasion Analyst", items: ["Dress code definitions", "Cultural & regional conventions", "Social role expectations"] },
      { name: "For Assembler", items: ["Color pairing principles", "Texture & fabric compatibility", "Visual weight distribution logic"] },
      { name: "For Evaluator", items: ["What makes outfits cohesive", "How to weigh competing priorities", "When rule-breaks elevate vs undermine"] },
    ],
  },
  catalog: {
    title: "Garment Catalog",
    description: "The product database with 46 attributes per garment, stored with both structured fields for hard filtering and 6 specialized embedding columns for semantic search.",
    sections: [
      { name: "46 Attributes including", items: ["GarmentCategory, SilhouetteType, FitType", "NecklineType, SleeveLength, FabricDrape", "PatternType, ColorTemperature, FormalityLevel", "StylingCompleteness, OccasionFit, etc."] },
      { name: "6 Embedding Columns", items: ["Occasion | Silhouette & Proportion", "Color & Visual | Fabric & Construction", "Style Identity | Pairing"] },
      { name: "Search Strategy", items: ["Hybrid: Hard attribute filters →", "Multi-embedding weighted similarity"] },
    ],
  },
};

export default function FashionAIArchitecture() {
  const [selected, setSelected] = useState(null);

  const handleClick = (key) => {
    setSelected(selected === key ? null : key);
  };

  const detail = selected ? details[selected] : null;

  return (
    <div style={{
      background: COLORS.bg,
      minHeight: "100vh",
      fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
      color: COLORS.text,
      display: "flex",
      flexDirection: "column",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap');
        .agent-node:hover rect:first-child {
          filter: brightness(1.3);
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .detail-panel {
          animation: fadeIn 0.2s ease-out;
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: ${COLORS.bg}; }
        ::-webkit-scrollbar-thumb { background: ${COLORS.border}; border-radius: 3px; }
      `}</style>

      {/* Header */}
      <div style={{
        padding: "24px 32px 8px",
        borderBottom: `1px solid ${COLORS.border}`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 8, height: 8, borderRadius: "50%",
            background: COLORS.accent1,
            boxShadow: `0 0 12px ${COLORS.accent1}66`,
          }} />
          <h1 style={{
            fontSize: 16, fontWeight: 700, margin: 0,
            letterSpacing: 3, color: COLORS.text, textTransform: "uppercase",
          }}>
            Fashion Styling AI — System Architecture
          </h1>
        </div>
        <p style={{ fontSize: 10, color: COLORS.textMuted, margin: "8px 0 12px 20px", letterSpacing: 0.5 }}>
          Agentic system for personalized outfit recommendation · Click any node for details
        </p>
      </div>

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Diagram */}
        <div style={{
          flex: detail ? "0 0 65%" : "1",
          overflow: "auto",
          padding: "16px",
          transition: "flex 0.3s ease",
        }}>
          <svg viewBox="0 0 960 820" style={{ width: "100%", height: "auto", minWidth: 700 }}>
            {/* Background grid */}
            <defs>
              <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke={COLORS.border} strokeWidth="0.2" opacity="0.3" />
              </pattern>
            </defs>
            <rect width="960" height="820" fill="url(#grid)" />

            {/* === SECTION: INPUT LAYER === */}
            <SectionLabel x={20} y={20} text="INPUT LAYER" color={COLORS.accent1} />

            {/* User Request */}
            <AgentNode
              title="User Request"
              subtitle="'I need an outfit for...'"
              color={COLORS.accent1} colorDim={COLORS.accent1Dim}
              x={370} y={38} width={220}
              onClick={() => {}} isActive={false}
            />

            {/* === SECTION: PERSISTENT CONTEXT === */}
            <SectionLabel x={20} y={106} text="PERSISTENT CONTEXT" color={COLORS.accent2} />

            <AgentNode
              title="User Context"
              items={["Identity · Body Type", "Color Analysis · Additional Details", "→ Interpretations"]}
              color={COLORS.accent2} colorDim={COLORS.accent2Dim}
              x={100} y={124} width={220}
              onClick={() => handleClick("user_context")} isActive={selected === "user_context"}
            />

            <AgentNode
              title="Style Preference"
              items={["StyleArchetype · RiskTolerance", "ComfortPriorities", "AspirationGap"]}
              color={COLORS.accent2} colorDim={COLORS.accent2Dim}
              x={370} y={124} width={220}
              onClick={() => handleClick("style_pref")} isActive={selected === "style_pref"}
            />

            <AgentNode
              title="Knowledge Context"
              items={["Universal Principles", "Personal Styling Rules", "Occasion Conventions"]}
              color={COLORS.accent2} colorDim={COLORS.accent2Dim}
              x={640} y={124} width={220}
              onClick={() => handleClick("knowledge")} isActive={selected === "knowledge"}
            />

            {/* Arrows from context to orchestrator */}
            <Arrow x1={210} y1={198} x2={430} y2={260} color={COLORS.accent2} label="profile" />
            <Arrow x1={480} y1={198} x2={480} y2={260} color={COLORS.accent2} label="prefs" />
            <Arrow x1={750} y1={198} x2={530} y2={260} color={COLORS.accent2} label="expertise" dashed />

            {/* Arrow from user request to orchestrator */}
            <Arrow x1={480} y1={90} x2={480} y2={260} color={COLORS.accent1} label="" />

            {/* === SECTION: ORCHESTRATION === */}
            <SectionLabel x={20} y={240} text="ORCHESTRATION" color={COLORS.accent3} />

            <AgentNode
              title="Orchestrator Agent"
              items={["Decomposes request → sub-tasks", "Routes to specialist agents", "Manages data flow & handoffs"]}
              color={COLORS.accent3} colorDim={COLORS.accent3Dim}
              x={370} y={260} width={220}
              onClick={() => handleClick("orchestrator")} isActive={selected === "orchestrator"}
            />

            {/* === SECTION: SPECIALIST AGENTS === */}
            <SectionLabel x={20} y={360} text="SPECIALIST AGENTS" color={COLORS.accent4} />

            {/* Occasion Analyst */}
            <AgentNode
              title="Occasion Analyst"
              items={["Formality · Dress code", "Setting · Climate · Time", "Social role · Culture"]}
              color={COLORS.accent4} colorDim={COLORS.accent4Dim}
              x={80} y={385} width={210}
              onClick={() => handleClick("occasion")} isActive={selected === "occasion"}
            />

            {/* Outfit Architect */}
            <AgentNode
              title="Outfit Architect"
              items={["Generates outfit directions:", "Dir 1: Complete garment spec", "Dir 2: Two-piece + relationship", "Dir 3: Three-piece + relationship"]}
              color={COLORS.accent4} colorDim={COLORS.accent4Dim}
              x={370} y={380} width={220}
              onClick={() => handleClick("architect")} isActive={selected === "architect"}
            />

            {/* Arrows: Orchestrator to Occasion Analyst */}
            <Arrow x1={400} y1={334} x2={250} y2={385} color={COLORS.accent3} label="occasion desc" />

            {/* Arrow: Occasion Analyst to Outfit Architect */}
            <Arrow x1={290} y1={430} x2={370} y2={430} color={COLORS.accent4} label="context" />

            {/* Arrow: Orchestrator to Outfit Architect */}
            <Arrow x1={480} y1={334} x2={480} y2={380} color={COLORS.accent3} label="" />

            {/* Knowledge feeding into agents */}
            <CurvedArrow x1={750} y1={198} x2={265} y2={385} cx={300} cy={280} color={COLORS.accent2} label="" />
            <CurvedArrow x1={780} y1={198} x2={480} y2={380} cx={700} cy={310} color={COLORS.accent2} label="" />


            {/* === SECTION: CATALOG LAYER === */}
            <SectionLabel x={20} y={498} text="SEARCH & ASSEMBLY" color={COLORS.accent5} />

            {/* Catalog Search */}
            <AgentNode
              title="Catalog Search Agent"
              items={["Hard filters → narrow pool", "Multi-embedding similarity ranking", "Constraint relaxation logic"]}
              color={COLORS.accent5} colorDim={COLORS.accent5Dim}
              x={165} y={520} width={240}
              onClick={() => handleClick("catalog_search")} isActive={selected === "catalog_search"}
            />

            {/* Garment Catalog */}
            <AgentNode
              title="Garment Catalog"
              items={["46 attributes per garment", "6 embedding columns", "Hybrid search: filters + vectors"]}
              color={COLORS.accent5} colorDim={COLORS.accent5Dim}
              x={165} y={616} width={240}
              onClick={() => handleClick("catalog")} isActive={selected === "catalog"}
            />

            {/* Outfit Assembler */}
            <AgentNode
              title="Outfit Assembler Agent"
              items={["Complete garments → pass through", "Individual pieces → combine & evaluate", "Color, formality, volume, fabric checks"]}
              color={COLORS.accent5} colorDim={COLORS.accent5Dim}
              x={530} y={520} width={260}
              onClick={() => handleClick("assembler")} isActive={selected === "assembler"}
            />

            {/* Arrow: Architect to Catalog Search */}
            <Arrow x1={420} y1={472} x2={340} y2={520} color={COLORS.accent4} label="directions" />

            {/* Arrow: Catalog Search to Catalog */}
            <Arrow x1={285} y1={594} x2={285} y2={616} color={COLORS.accent5} label="" />

            {/* Arrow: Catalog to Catalog Search (return) */}
            <Arrow x1={310} y1={616} x2={310} y2={594} color={COLORS.accent5} label="" />

            {/* Arrow: Catalog Search to Assembler */}
            <Arrow x1={405} y1={555} x2={530} y2={555} color={COLORS.accent5} label="candidates" />

            {/* Knowledge feeding into assembler */}
            <CurvedArrow x1={820} y1={198} x2={730} y2={520} cx={900} cy={400} color={COLORS.accent2} label="" />

            {/* === SECTION: EVALUATION === */}
            <SectionLabel x={20} y={660} text="EVALUATION & OUTPUT" color={COLORS.accent6} />

            {/* Evaluator */}
            <AgentNode
              title="Outfit Evaluator Agent"
              items={["Body fit · Color match · Occasion", "Style match · Cohesion · Feel", "→ Ranked list with reasoning"]}
              color={COLORS.accent6} colorDim={COLORS.accent6Dim}
              x={370} y={680} width={220}
              onClick={() => handleClick("evaluator")} isActive={selected === "evaluator"}
            />

            {/* Presentation Agent */}
            <AgentNode
              title="Presentation Agent"
              items={["Top 3-5 recommendations", "Plain language reasoning", "Handles follow-ups → loop back"]}
              color={COLORS.accent6} colorDim={COLORS.accent6Dim}
              x={370} y={760} width={220}
              onClick={() => handleClick("presentation")} isActive={selected === "presentation"}
            />

            {/* Arrow: Assembler to Evaluator */}
            <Arrow x1={620} y1={594} x2={520} y2={680} color={COLORS.accent5} label="complete outfits" />

            {/* Arrow: Evaluator to Presentation */}
            <Arrow x1={480} y1={754} x2={480} y2={760} color={COLORS.accent6} label="" />

            {/* Feedback loop: Presentation back to Orchestrator */}
            <CurvedArrow
              x1={590} y1={790}
              x2={590} y2={290}
              cx={900} cy={550}
              color={COLORS.accent6}
              label="follow-up loop"
            />

            {/* Knowledge to evaluator */}
            <CurvedArrow x1={860} y1={198} x2={590} y2={690} cx={940} cy={500} color={COLORS.accent2} label="" />

            {/* Dashed lines showing knowledge feeds */}
            <text x={870} y={350} fill={COLORS.accent2} fontSize="8" fontFamily="'JetBrains Mono', monospace" opacity={0.5} transform="rotate(90, 870, 350)">
              knowledge feeds into all agents
            </text>

          </svg>
        </div>

        {/* Detail Panel */}
        {detail && (
          <div className="detail-panel" style={{
            flex: "0 0 35%",
            borderLeft: `1px solid ${COLORS.border}`,
            padding: "24px",
            overflow: "auto",
            background: COLORS.surface,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <h2 style={{ fontSize: 14, fontWeight: 700, margin: 0, color: COLORS.text, letterSpacing: 1 }}>
                {detail.title}
              </h2>
              <button
                onClick={() => setSelected(null)}
                style={{
                  background: "none", border: `1px solid ${COLORS.border}`,
                  color: COLORS.textMuted, cursor: "pointer", fontSize: 11,
                  padding: "2px 8px", borderRadius: 4, fontFamily: "inherit",
                }}
              >
                ✕
              </button>
            </div>

            <p style={{ fontSize: 11, color: COLORS.textMuted, lineHeight: 1.7, margin: "16px 0" }}>
              {detail.description}
            </p>

            {detail.sections.map((section, i) => (
              <div key={i} style={{ marginBottom: 20 }}>
                <div style={{
                  fontSize: 9, fontWeight: 700, color: COLORS.accent1,
                  letterSpacing: 2, textTransform: "uppercase", marginBottom: 8,
                }}>
                  {section.name}
                </div>
                {section.items.map((item, j) => (
                  <div key={j} style={{
                    fontSize: 10, color: COLORS.textMuted, padding: "4px 0 4px 12px",
                    borderLeft: `1px solid ${COLORS.border}`, marginBottom: 2, lineHeight: 1.5,
                  }}>
                    {item}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
