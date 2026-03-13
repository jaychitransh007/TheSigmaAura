# Fashion Styling AI — Complete Knowledge Context

## Architecture Overview

This document contains the complete knowledge base for the Fashion Styling AI system. It is organized into focused modules, each assigned to specific agents. Agents load only their designated modules — never the full document.

Current runtime note:
- the active `agentic_application` implementation does not inject this document directly into prompts
- these modules remain the reference knowledge architecture for future prompt/module loading and evaluation design
- current planner/evaluator prompts rely on model priors plus structured user and catalog context

---

## Agent-to-Module Mapping

```
┌─────────────────────────┬──────────────────────────────────────────────┐
│ Agent                   │ Modules Loaded                               │
├─────────────────────────┼──────────────────────────────────────────────┤
│ Occasion Analyst        │ M05: Occasion & Dress Code Conventions       │
│                         │ M10: Cultural & Regional Conventions         │
├─────────────────────────┼──────────────────────────────────────────────┤
│ Outfit Architect        │ M01: Universal Styling Principles            │
│                         │ M02: Body Shape & Silhouette Strategy        │
│                         │ M03: Seasonal Color System & Application     │
│                         │ M04: Proportion Correction Strategies        │
│                         │ M08: Neckline, Collar & Detail Mapping       │
│                         │ M09: Fabric, Texture & Weight Guidelines     │
├─────────────────────────┼──────────────────────────────────────────────┤
│ Catalog Search Agent    │ M11: Catalog Attribute Mapping Reference     │
├─────────────────────────┼──────────────────────────────────────────────┤
│ Outfit Assembler        │ M06: Garment Pairing & Combination Rules     │
│                         │ M09: Fabric, Texture & Weight Guidelines     │
├─────────────────────────┼──────────────────────────────────────────────┤
│ Outfit Evaluator        │ M07: Outfit Evaluation Framework             │
│                         │ M01: Universal Styling Principles (compact)  │
│                         │ M03: Seasonal Color System (compact)         │
├─────────────────────────┼──────────────────────────────────────────────┤
│ Presentation Agent      │ M12: Client Communication Guidelines         │
└─────────────────────────┴──────────────────────────────────────────────┘
```

### Loading Strategy

Each module has two tiers:
- **Compact Tier**: Core principles covering ~80% of use cases. Always loaded.
- **Detailed Tier**: Edge cases, interactions, and nuanced exceptions. Loaded only when the Orchestrator detects complexity (unusual body combinations, ambiguous occasions, conflicting constraints).

Modules are marked with `[COMPACT]` and `[DETAILED]` headers within each section.

---

# M01: Universal Styling Principles

**Assigned to**: Outfit Architect (full), Outfit Evaluator (compact only)

This module covers foundational visual principles that apply to all people regardless of body type, coloring, or personal preference. These are perceptual tendencies rooted in how the human eye processes proportion, balance, and harmony.

---

## 1.1 Proportion Theory

### [COMPACT]

The rule of thirds is the most reliable proportion principle in styling. An outfit that creates a visual break at approximately one-third of the body's height produces a more dynamic and flattering composition than an equal 50/50 split. This break is typically created by a waistline, hem, or tuck point.

Common applications:
- Tucking a top into high-waisted bottoms creates roughly a 1/3 top to 2/3 bottom ratio, which visually elongates the legs.
- A cropped jacket over a longer dress or top creates a 1/3 outer to 2/3 inner ratio that adds structure without shortening the body.
- A long top over narrow bottoms creates a 2/3 top to 1/3 bottom ratio — this works when the intent is to draw attention to the upper body and create a relaxed silhouette.

The golden ratio (approximately 3:5 or 5:8) is a subtler variation of the same principle. It produces slightly more organic proportions than a strict 1/3 split.

Critical caveat: These ratios are starting points, not rigid rules. A person's actual torso-to-leg ratio determines whether the standard 1/3 break flatters or distorts. Someone with a naturally long torso and short legs benefits from a higher break to visually lengthen the legs. Someone with a short torso and long legs can bring the break lower without losing proportion.

### [DETAILED]

When layering three pieces (top, mid-layer, outer), proportion applies at two levels:
- The visible lengths of each layer should create unequal intervals. Three equal-length layers look stacked and boxy. Graduated lengths (short → medium → long or the reverse) create visual rhythm.
- The overall silhouette still needs to respect the 1/3 principle in terms of where the dominant visual break falls.

Proportion interacts with visual weight. A heavily textured or brightly colored garment draws the eye and appears to occupy more visual space than its actual length would suggest. A small bright top over dark neutral bottoms reads as a larger top-to-bottom ratio than the measurements alone would indicate.

Vertical proportion also applies to individual garments. A dress with a defined waist should place that waist definition at or near the natural waist or slightly above — never below, as this shortens the torso and disrupts the body's natural proportional balance.

---

## 1.2 Visual Line Theory

### [COMPACT]

Every garment creates lines that the eye follows. These lines are formed by seams, edges, hems, necklines, closures, stripes, and even the drape of fabric. Understanding how lines affect perception is essential to silhouette strategy.

Vertical lines elongate and slim. They draw the eye up and down, creating an impression of height and narrowness. Created by: vertical seams, long necklaces, column silhouettes, vertical stripes, single-breasted closures, open cardigans over fitted tops.

Horizontal lines widen and shorten. They draw the eye side to side, creating an impression of breadth. Created by: wide necklines (boat neck), horizontal stripes, belts, contrasting waistbands, cropped jackets, and any hem line that interrupts the vertical flow of the body.

Diagonal lines create movement and dynamism. They suggest energy without strongly elongating or widening. Created by: asymmetric hems, wrap closures, draped necklines, bias-cut fabrics, diagonal pattern placement.

Curved lines soften and feminize. They create a fluid, relaxed impression. Created by: cowl necklines, peplum hems, draped fabrics, gathered waists, scalloped edges.

### [DETAILED]

Line interaction is critical. A garment rarely creates just one type of line. A structured blazer with padded shoulders creates strong horizontal lines at the shoulder but vertical lines through the lapels and the body's center front. The net effect depends on which lines dominate — if shoulder width is exaggerated beyond the lapel length, the horizontal reads stronger.

Line density matters. Multiple thin vertical stripes have a different effect than a single bold vertical stripe. Thin, closely spaced verticals create a texture that the eye can blend into a surface, reducing the elongating effect. A single bold vertical seam or stripe creates a clear directional pull.

Where lines terminate affects their impact. A horizontal stripe that ends at the widest part of the hip draws maximum attention to that width. The same stripe ending mid-thigh has a weaker widening effect because the eye doesn't register it as marking a body landmark.

---

## 1.3 Color Theory in Outfit Construction

### [COMPACT]

Color in an outfit operates on three dimensions: hue (the actual color), value (lightness versus darkness), and saturation (vibrancy versus mutedness). Outfit harmony depends on managing all three.

Monochromatic outfits use variations of a single hue. This creates an unbroken vertical line that elongates the body and simplifies the visual impression. Monochromatic doesn't mean identical shades — tonal variation within the same color family adds depth. Example: chocolate brown trousers with a camel sweater and tan coat.

Complementary color combinations use colors opposite each other on the color wheel. These create energy and visual contrast. They're high-impact and draw attention. Should be used intentionally, not accidentally. Example: a navy outfit with rust-orange accessories.

Analogous color combinations use colors adjacent on the wheel. These create harmony and cohesion. They feel intentional but subtle. Example: olive green trousers with a warm mustard top.

Neutral grounding: Most successful outfits use a neutral base (black, white, grey, navy, beige, brown, olive) with one or two color accents. The neutral creates stability while the accent provides interest and a focal point.

Value contrast between top and bottom has the strongest impact on perceived proportion. High value contrast (white top, black bottom) creates a clear visual break that shortens the overall line. Low value contrast (navy top, dark grey bottom) creates continuity that elongates.

### [DETAILED]

Saturation matching across pieces is often overlooked but critical. A highly saturated cobalt blue top paired with muted dusty olive trousers creates an imbalance — the top screams while the bottom whispers. Matching saturation levels (both muted, or both vibrant) creates cohesion even when hues differ significantly.

Color placement strategy: Darker and cooler colors recede, making areas appear smaller and less prominent. Lighter and warmer colors advance, making areas appear larger and more noticeable. This can be used strategically — a dark top minimizes a broad upper body while light trousers draw attention to the legs.

The 60-30-10 rule is a useful starting framework for multi-color outfits: 60% dominant color (usually a neutral), 30% secondary color, 10% accent. This creates a balanced visual hierarchy without any single color overwhelming.

---

## 1.4 Focal Point Principle

### [COMPACT]

Every strong outfit has one area that draws the eye first. This is the focal point. It might be an interesting neckline, an unusual texture, a pop of color, or a distinctive structural element. The focal point should be intentional — it directs where people look first when they see the person.

Without a focal point, an outfit feels flat and unmemorable. With too many competing focal points, it feels chaotic and the eye has nowhere to rest.

Focal point placement should be strategic:
- Near the face draws attention to expression and identity — this is the most universally flattering placement.
- At the waist draws attention to definition and shape.
- At the hem or shoes draws the eye downward — useful for creating an impression of grounding or edginess, but should be balanced so the face isn't lost.

The focal point is created by contrast — whichever element differs most from its surroundings becomes the focal point. A bright scarf on a neutral outfit, a textured knit against smooth fabrics, or a structured jacket over fluid pieces.

### [DETAILED]

Focal point and body awareness interact. If a client wants to minimize attention to their midsection, the focal point should be placed away from that area — at the neckline, shoulders, or even footwear. If they want to celebrate their waist definition, a contrasting belt or cinched detail creates a focal point there.

Competing focal points can be resolved by hierarchy — making one element clearly dominant and the other subordinate. A statement top with interesting shoes works if the shoes are a subtler echo of the top's energy rather than fighting for equal attention.

---

## 1.5 Scale and Proportion in Details

### [COMPACT]

The physical scale of a person should inform the scale of garment details, prints, and accessories. Scale refers to the overall visual "size" a person presents — influenced by height, bone structure, and visual weight.

Larger-scaled individuals (tall, broad-framed, or visually substantial) can carry larger prints, wider lapels, chunkier knits, and bolder garment details without being overwhelmed. Small-scale details on a large frame look insignificant and disproportionate.

Smaller-scaled individuals (petite, fine-boned, or visually delicate) look best in proportionate details — smaller prints, narrower lapels, finer knit gauges, delicate buttons. Oversized details on a small frame overpower the person.

Mid-scaled individuals have the most flexibility and can lean in either direction depending on the desired effect.

Exceptions exist for intentional contrast. Oversized details on a small frame can be a deliberate style statement (oversized coat, chunky boots). But this works because the entire outfit commits to the scale contrast — one oversized element among otherwise proportionate pieces just looks wrong.

### [DETAILED]

Pattern scale interacts with body area. A large-scale pattern on a small body area (like a sleeve) gets cropped and distorted, losing its visual impact. The same pattern on a larger area (like a skirt or jacket back) has room to display properly. When recommending patterns, consider not just the person's overall scale but the specific garment area where the pattern appears.

Lapel width relates to shoulder width. Narrow lapels on very broad shoulders exaggerate the breadth. Wider lapels on narrow shoulders add visual width. The lapel should be proportionate to the chest/shoulder area.

---

## 1.6 Visual Weight of Fabrics

### [COMPACT]

Fabric interacts with the body in fundamentally different ways depending on its weight, drape, structure, and surface texture. Understanding fabric behavior is essential for predicting how a garment will look on a specific body.

Heavy fabrics (wool suiting, denim, tweed, brocade) add visual bulk and maintain structure. They hold shape away from the body, creating defined silhouettes. They are effective for adding substance to slender frames, creating structure on softer body types, and maintaining clean lines. They can overwhelm petite frames if used excessively.

Light fabrics (silk, chiffon, cotton voile, lightweight linen) skim and float. They follow the body's contours without adding bulk. They are effective for creating movement, reducing visual volume, and flattering larger frames where adding bulk is undesirable. They provide less structure, which means they reveal body shape more directly.

Stiff fabrics (taffeta, organza, heavy cotton, structured wool) stand away from the body, creating their own silhouette independent of the body beneath. They can conceal, add volume where desired, and create dramatic shapes.

Clingy fabrics (jersey, stretch knit, silk charmeuse) adhere to the body and reveal its contours. They work best on areas where the client is comfortable being outlined and should be used thoughtfully on areas of self-consciousness.

### [DETAILED]

Texture affects perceived visual weight beyond actual fabric weight. A lightweight but textured fabric (like bouclé or lightweight tweed) reads heavier than a smooth lightweight fabric. Texture adds visual substance.

Matte fabrics absorb light and minimize visual prominence. Shiny fabrics reflect light and draw the eye, making areas appear larger and more prominent. Satin across the hips reads differently from matte cotton across the hips, even at the same weight and fit.

Fabric memory — how well a fabric holds its shape after wearing — matters for silhouette maintenance throughout the day. A structured blazer in a fabric with poor memory will lose its clean lines by afternoon. For clients who need their outfit to perform reliably over hours, recommend fabrics that maintain structure.

Stretch content changes how a garment relates to the body over time. High-stretch fabrics conform initially but can stretch out, changing the fit throughout the day. Low-stretch fabrics maintain their shape but may restrict movement. For clients who prioritize comfort, moderate stretch with good recovery is ideal.

---

## 1.7 Fit Hierarchy

### [COMPACT]

Not all fit points are equally important. When assessing or recommending garment fit, prioritize in this order:

1. Shoulder fit (most critical). The shoulder seam should sit at the point where the shoulder meets the arm. If shoulders don't fit, the entire garment drapes incorrectly. A tailor can adjust almost everything else, but restructuring shoulders is expensive and often compromises the garment.

2. Chest and torso fit. The garment should follow the body's contour without pulling, gaping, or creating tension lines. In tailored pieces, the chest should lie flat with no X-shaped pull marks at the closure.

3. Length. Jacket length, sleeve length, trouser length — these affect proportion and can be tailored relatively easily, but getting them right matters for the overall line.

4. Waist and hip. The garment should allow natural movement without excess volume. In tailored pieces, slight suppression at the waist creates shape. In relaxed pieces, enough ease for comfort without swimming.

This hierarchy means: when recommending garments, always prioritize shoulder and torso fit. Color, style, and detail are secondary to a garment that actually fits the body correctly. A perfectly colored garment that fits poorly will always look worse than a slightly off-palette garment that fits beautifully.

### [DETAILED]

Fit expectations vary by garment category and style intent. A tailored blazer has very different fit standards from an oversized bomber jacket. The hierarchy still applies — even in oversized styling, the shoulder should be intentionally dropped rather than accidentally misplaced. Intentional oversize means the garment was designed for that effect. Accidental oversize means the garment is simply too big.

Signs of poor fit to watch for:
- Horizontal pulling lines across the chest or back: garment too tight in that area.
- Diagonal pulling from the button: garment too tight at the closure point.
- Collar lifting away from the neck in back: shoulder slope mismatch or poor balance.
- Sleeve twisting: sleeve pattern doesn't match the arm's natural rotation.
- Excess fabric billowing at the waist: too much ease without intentional design.

---

# M02: Body Shape & Silhouette Strategy

**Assigned to**: Outfit Architect (full)

This module maps body shape classifications to silhouette strategies. It translates physical attributes into garment recommendations.

---

## 2.1 Body Shape Framework

### [COMPACT]

Body shape is determined primarily by the relationship between shoulders, waist, and hips. The main classifications are:

**Inverted Triangle** — Shoulders notably wider than hips. Waist may or may not be defined.
- Strategy: Balance by adding visual volume below the waist and minimizing shoulder emphasis.
- Effective: A-line skirts, wide-leg trousers, flared hems, raglan sleeves, V-necklines that narrow the shoulder visually.
- Avoid: Boat necklines, cap sleeves, structured shoulder pads, slim-fit skirts that emphasize the narrow hip.

**Rectangle** — Shoulders, waist, and hips roughly aligned. Minimal waist definition.
- Strategy: Create visual curves or embrace the straight line depending on client preference.
- To create curves: Belted pieces, peplum details, fit-and-flare silhouettes, wrap styles that cinch the waist.
- To embrace the line: Column dresses, straight-cut trousers, shift dresses, minimalist tailoring. This approach works especially well for clients with a modern or minimalist style archetype.
- Avoid: Boxy, shapeless pieces that neither create curves nor celebrate the straight line — they just look unfitted.

**Hourglass** — Shoulders and hips roughly balanced, waist notably narrower.
- Strategy: Follow the body's natural curves. Garments that define the waist honor the body's proportions.
- Effective: Wrap dresses, fitted waists, pencil skirts, tailored blazers with waist suppression, belted pieces.
- Avoid: Oversized or boxy shapes that hide the waist and create a larger silhouette than necessary. Stiff fabrics that don't conform to the body's curves.
- Caveat: Not all hourglass clients want to emphasize curves. Respect client preference — some prefer to dress more structurally.

**Triangle (Pear)** — Hips wider than shoulders.
- Strategy: Balance by adding visual interest and volume to the upper body while keeping the lower body streamlined or proportionate.
- Effective: Structured shoulders, boat necklines, statement tops, detailed necklines, darker colors on the bottom, straight-leg or bootcut trousers.
- Avoid: Clingy fabrics on hips, hip-level pockets, light-colored or patterned bottoms that draw attention to the widest area (unless client wants this).

**Oval / Apple** — Fullness concentrated at the midsection. Shoulders and hips may be narrower than the middle.
- Strategy: Create a vertical flow that skims the midsection without clinging. Draw attention to the upper chest, face, and legs.
- Effective: V-necklines that create a vertical line, empire waistlines, A-line shapes, straight or column silhouettes, darker midsection with lighter extremities, well-structured fabrics that hold shape.
- Avoid: Clingy fabrics around the midsection, tight waistbands, belts at the natural waist (unless waist is defined), cropped tops that truncate the torso.

### [DETAILED]

Most real bodies are blends of these shapes rather than pure types. A person might have hourglass proportions but with a fuller midsection, making them a blend of hourglass and oval. In these cases, prioritize the attribute the client feels most aware of. If they're self-conscious about the midsection, apply oval strategies there while honoring the hourglass elsewhere.

Body shape interacts with height significantly:
- A petite pear shape needs different trouser strategies than a tall pear shape. Wide-leg trousers that balance a tall pear can overwhelm a petite one.
- A tall rectangle can carry column dressing that would make a petite rectangle look lost.
- A petite hourglass can be overwhelmed by heavy structure that a tall hourglass wears easily.

Body shape changes over time and with life circumstances. The system should re-evaluate if significant changes are noted. Postpartum bodies, weight fluctuations, aging-related shifts in fat distribution — all affect which strategies are most effective.

---

## 2.2 Frame Structure and Visual Weight

### [COMPACT]

Frame structure refers to the underlying bone structure — broad versus narrow, heavy versus fine. This is separate from body shape and body fat distribution.

A broad-framed person with narrow hips is different from a fine-framed person with narrow hips. The broad frame carries heavier fabrics and bolder details. The fine frame needs lighter construction.

Visual weight is the overall impression of heaviness or lightness a person projects. It's influenced by frame structure, body composition, height, and even hair volume. A tall, large-framed person with dense hair has high visual weight. A petite, fine-boned person with fine hair has low visual weight.

Visual weight guides fabric weight, detail scale, and overall outfit "heaviness." High-visual-weight individuals need garments with enough substance to match — thin, flimsy fabrics look insubstantial. Low-visual-weight individuals look best in lighter constructions — heavy, stiff fabrics can wear the person rather than the other way around.

### [DETAILED]

Visual weight interacts with style archetype in important ways. A high-visual-weight person with a minimalist style preference creates an interesting challenge — minimalism typically relies on lighter, simpler pieces, but these may look insubstantial on a large frame. The solution is minimalism through quality and weight — substantial fabrics in simple cuts, rich textures in quiet colors — rather than minimalism through lightness.

---

# M03: Seasonal Color System & Application

**Assigned to**: Outfit Architect (full), Outfit Evaluator (compact only)

This module defines the seasonal color classification system and how to apply it to garment selection and outfit construction.

---

## 3.1 The Four-Season Foundation

### [COMPACT]

The seasonal color system classifies people by three qualities of their natural coloring: temperature (warm versus cool), depth (light versus dark), and clarity (clear/bright versus muted/soft).

**Spring** — Warm + Light + Clear
Natural coloring: Typically golden or peachy skin undertones, light to medium warm hair (golden blonde, strawberry, light golden brown), clear bright eyes (light blue, green, warm hazel with golden flecks).
Best colors: Warm, bright, and clear — coral, peach, warm pink, golden yellow, fresh green, turquoise, warm ivory.
Neutrals: Camel, warm beige, light brown, cream (not stark white).
Avoid: Cool, dark, or muted colors — black (too heavy), burgundy (too dark), dusty rose (too muted), icy blue (too cool).

**Summer** — Cool + Light + Muted
Natural coloring: Pink or rosy skin undertones, ash-toned hair (ash blonde, ash brown, light mousy brown), soft muted eyes (grey-blue, soft hazel, muted green).
Best colors: Cool, soft, and muted — lavender, dusty rose, powder blue, soft sage, mauve, periwinkle, soft teal.
Neutrals: Soft grey, blue-grey, cocoa, taupe, off-white with cool undertone.
Avoid: Warm, bright, or heavy colors — orange (too warm), bright yellow (too warm and bright), black (too harsh), pure white (too stark).

**Autumn** — Warm + Deep + Muted
Natural coloring: Golden or olive skin undertones, warm-toned hair (auburn, chestnut, dark golden brown, copper), warm rich eyes (dark brown, warm hazel, olive green).
Best colors: Warm, deep, and rich — terracotta, olive green, burnt orange, mustard, warm burgundy, deep teal, chocolate brown, rust.
Neutrals: Chocolate brown, olive, camel, warm beige, dark warm grey, cream.
Avoid: Cool, bright, or pastel colors — icy blue (too cool), baby pink (too light and cool), bright fuchsia (too cool and bright), silver (too cool).

**Winter** — Cool + Deep + Clear
Natural coloring: Cool-toned skin (pink, blue, or olive with cool undertone), dark hair (dark brown, blue-black, cool-toned black), high contrast between hair and skin, vivid or deep eyes (dark brown, bright blue, cool green).
Best colors: Cool, bold, and high-contrast — true red, emerald green, royal blue, bright fuchsia, pure white, black, icy pink, bright purple.
Neutrals: Black, pure white, charcoal, navy, cool grey.
Avoid: Warm, muted, or earthy colors — mustard (too warm), rust (too warm), dusty rose (too muted), beige (too warm and muted).

### [DETAILED]

The 12-season system expands each season into three sub-types, with each sub-type emphasizing one of the three qualities as dominant:

**Spring sub-types:**
- Light Spring: Dominant quality is lightness. The lightest, most delicate of the Springs. Colors are soft pastels with warmth — peach, light coral, buttercup yellow. Overlaps with Light Summer but stays warm.
- Warm Spring: Dominant quality is warmth. The purest warm palette. Rich golden tones — amber, golden yellow, warm green, salmon. Most clearly warm of all seasons.
- Clear/Bright Spring: Dominant quality is clarity. The most vivid Spring. Bright warm colors — electric coral, bright turquoise, vivid warm pink. Overlaps with Clear Winter but stays warm.

**Summer sub-types:**
- Light Summer: Dominant quality is lightness. Very delicate, almost ethereal coloring. Softest pastels — lavender, powder blue, soft pink. Overlaps with Light Spring but stays cool.
- Cool Summer: Dominant quality is coolness. The most clearly cool palette. Blue-based tones — periwinkle, raspberry, blue-grey, cool pink. Overlaps with Cool Winter but stays soft.
- Soft Summer: Dominant quality is mutedness. The most muted of all seasons. Dusty, greyed-down tones — sage, dusty blue, mauve, soft charcoal. Overlaps with Soft Autumn but stays cool.

**Autumn sub-types:**
- Soft Autumn: Dominant quality is mutedness. Muted, gentle warmth. Dusty warm tones — soft olive, muted terracotta, warm taupe. Overlaps with Soft Summer but stays warm.
- Warm Autumn: Dominant quality is warmth. The richest, most golden palette. Amber, pumpkin, warm brown, bronze, orange-red. Most clearly warm of the Autumns.
- Deep Autumn: Dominant quality is depth. Rich and dark with warmth. Dark olive, dark chocolate, aubergine, deep teal, dark rust. Overlaps with Deep Winter but stays warm.

**Winter sub-types:**
- Deep Winter: Dominant quality is depth. Rich and dark with coolness. Dark navy, deep plum, dark emerald, black-brown. Overlaps with Deep Autumn but stays cool.
- Cool Winter: Dominant quality is coolness. The most clearly cool palette. True reds, bright blues, icy violet, sharp fuchsia. Overlaps with Cool Summer but stays vivid.
- Clear/Bright Winter: Dominant quality is clarity. The most vivid of all seasons. High-contrast, electric tones — bright white, vivid emerald, electric blue, hot pink. Overlaps with Clear Spring but stays cool.

---

## 3.2 Applying Color to Outfit Construction

### [COMPACT]

Once the client's seasonal palette is determined, color application follows a priority hierarchy:

**Near the face is highest priority.** The colors closest to the face have the most impact on how the person's complexion reads. A flattering color near the face brightens the skin, enhances the eyes, and creates a healthy appearance. An unflattering color near the face can make the person look sallow, tired, or washed out. This means tops, shirts, scarves, and necklines should always be in-palette. Trousers and skirts have more flexibility because they're distant from the face.

**Neutrals form the foundation.** Each season has its own set of flattering neutrals. These should form the wardrobe's base — trousers, outerwear, and foundational pieces in the season's neutrals create versatility and allow accent colors to rotate.

**Accent colors create interest.** The season's most vibrant or distinctive colors work as accent pieces — a single top, a scarf, a layering piece. These provide visual interest and focal points.

**Color combinations within a palette.** Colors within the same seasonal palette naturally harmonize because they share underlying qualities (all warm-muted, or all cool-clear). This means a Deep Autumn client can confidently combine olive with terracotta and chocolate because these all share warmth and depth.

### [DETAILED]

Cross-seasonal borrowing is possible at the boundaries. A Deep Autumn can often wear some Deep Winter colors because they share depth as a dominant quality. A Light Spring can borrow from Light Summer because they share lightness. However, the borrowed colors should be used away from the face where their impact is less critical.

Contrast level modifies how the palette is applied in outfits:
- High-contrast individuals (dark hair, light skin) can wear outfits with strong value contrast between top and bottom — dark trousers with a light top. The contrast in the outfit echoes the contrast in their coloring.
- Low-contrast individuals (medium hair, medium skin, medium eyes) look most harmonious in tonal or analogous outfits where the value range is narrow.
- Matching the outfit's contrast level to the person's natural contrast creates the most cohesive impression.

Metals and warm/cool alignment: Gold, brass, and bronze are warm metals — they align with Spring and Autumn palettes. Silver, platinum, and white gold are cool metals — they align with Summer and Winter palettes. Rose gold is a bridge that works for warm seasons and some soft cool seasons.

---

# M04: Proportion Correction Strategies

**Assigned to**: Outfit Architect (full)

This module provides specific techniques for addressing common proportion goals through garment selection.

---

## 4.1 Torso-to-Leg Ratio Correction

### [COMPACT]

**Long torso, short legs:**
Goal: Visually lengthen the legs and shorten the torso.
- High-rise trousers/skirts move the visual waistline up, giving legs more apparent length.
- Tucking tops into bottoms creates a clear break that allocates more visual length to the lower body.
- Matching shoes to trouser color creates an unbroken lower-body line that elongates.
- Shorter tops that end above the hip avoid extending the torso further.
- Vertical details on the lower body (front creases, vertical seams) elongate the legs.
- Avoid: Low-rise bottoms, long untucked tops, horizontal details at the hip line.

**Short torso, long legs:**
Goal: Give the torso more visual space.
- Lower-rise or mid-rise bottoms drop the visual waistline, elongating the torso area.
- Longer tops worn untucked or half-tucked extend the torso.
- Color blocking with a different color on the top and bottom can adjust where the break reads.
- Tops with vertical details (V-necks, vertical stripes, open front layers) elongate the torso.
- Avoid: Very high-rise bottoms, cropped tops, wide belts that compress the torso.

### [DETAILED]

The interaction between torso-to-leg ratio and height adds complexity:
- A petite person with short legs needs to be careful that high-rise trousers don't create an absurdly short torso — the correction should be moderate.
- A tall person with a long torso can make bolder corrections because there's more length to redistribute.

Layering can disguise torso length. A third piece (jacket, cardigan, vest) that ends at a strategic point can create an artificial break that overrides the natural torso-to-leg perception.

---

## 4.2 Shoulder Correction

### [COMPACT]

**Narrow shoulders:**
Goal: Add visual width at the shoulder to create a more balanced frame.
- Structured shoulder in jackets and tops (light padding, defined shoulder seam).
- Boat necklines and wide necklines create a horizontal line that widens the shoulder visually.
- Horizontal details at the shoulder level (epaulettes, yoke seams, contrasting shoulder panels).
- Set-in sleeves with a defined shoulder point.

**Broad shoulders:**
Goal: Soften or minimize shoulder width.
- Raglan sleeves blend the shoulder into the sleeve, reducing the defined shoulder point.
- V-necklines draw the eye inward and downward, narrowing the shoulder area.
- Dropped shoulder seams move the structural line below the actual shoulder, softening the width.
- Avoid: Shoulder pads, boat necklines, cap sleeves, spaghetti straps (these expose the full shoulder width).

**Sloped shoulders:**
Goal: Create a more horizontal shoulder line.
- Structured shoulder in outerwear and jackets — light padding fills the slope.
- Set-in sleeves with a crisp shoulder point.
- Avoid: Raglan and dropped-shoulder styles that follow the slope rather than correcting it.

**Square shoulders:**
Goal: Soften if desired, or leverage for sharp tailoring.
- Raglan sleeves soften the angular shoulder line.
- Soft, unstructured fabrics at the shoulder reduce the angular impression.
- Alternatively, lean into it — square shoulders carry tailored blazers and structured pieces exceptionally well.

### [DETAILED]

Shoulder correction interacts with body shape. A triangle (pear) body with narrow shoulders benefits from shoulder-widening strategies at the top AND volume-minimizing strategies at the bottom simultaneously. These work in concert to rebalance the silhouette. However, the degree of correction should match — massively padded shoulders with a pencil skirt creates a different imbalance.

---

## 4.3 Height Enhancement and Reduction

### [COMPACT]

**Petite (adding visual height):**
- Monochromatic or tonal dressing creates an unbroken vertical line.
- Vertical seams, vertical stripes, and vertical pattern orientation.
- Proper proportion — the 1/3 to 2/3 rule is especially important for petite frames because even small deviations are more noticeable on a shorter frame.
- Fitted to semi-fitted silhouettes — excess fabric volume overwhelms a petite frame and shortens visually.
- Avoid: Oversized garments that swallow the frame, wide horizontal stripes, too many visual breaks.

**Tall (managing height):**
- Height rarely needs correction — most tall individuals benefit from embracing their vertical line.
- If the client wants to reduce perceived height: horizontal breaks, color blocking, wide belts, and cropped proportions can interrupt the vertical.
- Tall individuals have more freedom with volume, oversized silhouettes, wide-leg trousers, and dramatic proportions that would overwhelm a shorter frame.

### [DETAILED]

Petite proportion is not just about adding height — it's about maintaining balance at a smaller scale. A midi skirt that looks proportionate on a 5'8" frame may hit awkwardly on a 5'2" frame because the knee-to-hem ratio changes. Hem lengths should be evaluated relative to the individual's total height, not based on absolute measurements.

For tall frames, the risk is looking "long" rather than "tall." Long flat lines without shape can make a tall person look elongated rather than statuesque. Adding structure, waist definition, and horizontal interest at strategic points creates shape within the height.

---

# M05: Occasion & Dress Code Conventions

**Assigned to**: Occasion Analyst (full)

This module defines dress code expectations, formality levels, and occasion-specific guidelines.

---

## 5.1 Formality Spectrum

### [COMPACT]

**White Tie** — Highest formality. Extremely rare.
Implies: Full-length gowns, formal tuxedos with tailcoat. Very strict conventions.

**Black Tie** — High formality, evening events.
Implies: Floor-length or elegant cocktail-length dresses, dark formal suits or tuxedos. Dark, rich fabrics. Minimal experimentation. Colors typically dark or jewel-toned.

**Black Tie Optional** — High formality with flexibility.
Implies: Same level of dressiness as black tie but with room for interpretation. A cocktail dress is appropriate where it might not be at strict black tie. Dark suit instead of tuxedo is acceptable.

**Semi-Formal / Cocktail** — Upper-middle formality.
Implies: Cocktail dresses, tailored separates, dressy blouses with formal trousers/skirts, dressy midi. More color freedom than black tie. Fabrics are refined but not necessarily formal.

**Smart Casual** — Middle formality, the most ambiguous dress code.
Implies: Polished but not formal. Blazer with quality trousers and no tie, or a well-constructed dress with relaxed accessories. Every piece should look chosen, not thrown on. Avoid: athletic wear, very distressed denim, graphic tees, flip-flops.

**Business Professional** — Workplace formal.
Implies: Suits, tailored blazers, dress trousers, formal skirts or dresses, closed-toe shoes. Conservative colors (navy, charcoal, black, muted tones).

**Business Casual** — Workplace relaxed.
Implies: Varies widely by industry. Generally: collared shirts, chinos or quality trousers, knit tops, blouses, unstructured blazers, loafers. The emphasis is approachable professionalism.

**Casual** — No formality requirement.
Implies: Personal preference dominates. Denim, t-shirts, sneakers, casual dresses. Still styled — casual doesn't mean careless.

### [DETAILED]

**Wedding guest dress codes:**
- "Formal" or "Black Tie" wedding: Follow standard black tie guidelines.
- "Cocktail attire" wedding: Semi-formal, cocktail dress or dressy separates.
- "Semi-formal" wedding: Typically equivalent to cocktail attire.
- "Casual" or "Garden" wedding: Smart casual with elevated touches. Floral prints, lighter fabrics, less structure.
- "Beach wedding": Smart casual adapted for sand and heat. Breathable fabrics, lighter colors, less structure.
- Universal wedding guest rule: Never wear white or very close to white. Avoid anything that could upstage the couple.

**Seasonal context affects formality interpretation:**
- Summer events shift all dress codes lighter — lighter fabrics, lighter colors, less layering.
- Winter events allow heavier fabrics, darker palettes, and more layering at all formality levels.

**Time of day:**
- Daytime events (before 6 PM) are generally less formal than evening events.
- Evening events lean darker, richer, more dramatic.

---

## 5.2 Setting-Specific Adjustments

### [COMPACT]

**Outdoor events:**
- Lighter fabrics, breathable materials.
- Consider wind (avoid very lightweight, flyaway fabrics).
- Consider terrain (avoid impractical choices for the setting).
- Consider sun exposure — lighter colors are cooler.

**Indoor formal venues (hotel ballrooms, museums, galleries):**
- Standard dress code applies. Temperature controlled, so fabric weight is flexible.
- Consider the cultural context of the venue.

**Restaurant dining:**
- Match the restaurant's formality. Fine dining implies smart casual to semi-formal.
- Comfort matters — the person will be sitting for extended periods.

**Travel:**
- Prioritize wrinkle resistance, comfort, and versatility.
- Fabrics that pack well: jersey, knit, ponte, technical fabrics, wrinkle-resistant cotton.
- Avoid: linen (wrinkles severely), delicate silks, stiff formal fabrics.

---

# M06: Garment Pairing & Combination Rules

**Assigned to**: Outfit Assembler (full)

This module governs how individual garments work together when assembled into complete outfits.

---

## 6.1 Volume Balance

### [COMPACT]

The foundational rule of garment pairing is volume balance: if one half of the outfit is voluminous, the other half should be fitted, and vice versa.

Volume on top + slim on bottom: Oversized sweater with fitted trousers. Draws visual weight upward.

Slim on top + volume on bottom: Fitted tee with wide-leg trousers. Draws visual weight downward.

Volume on top + volume on bottom: Deliberately oversized, fashion-forward silhouette. Needs confidence and usually works on taller frames. Only recommend for moderate-to-high risk tolerance.

Slim on top + slim on bottom: Streamlined, body-conscious silhouette. Works well for hourglass shapes or clients who want to showcase their figure.

The volume balance choice should connect to the client's body analysis. If the goal is to balance a pear shape, volume on top with slim on bottom counteracts the wider hip.

### [DETAILED]

Mid-layers complicate volume balance. A blazer adds structure and volume to the upper body even if the underlying top is fitted. When recommending three-piece combinations, consider the net visual volume of all visible upper-body layers combined versus the bottom.

Volume also interacts with fabric. Lightweight volume creates softness and movement. Stiff volume creates structure and drama. The choice depends on the client's style archetype.

---

## 6.2 Formality Matching

### [COMPACT]

All garments in an outfit should occupy a similar range on the formality spectrum. Pieces within one formality step of each other pair naturally.

**Formality signals** come from fabric (silk reads more formal than cotton), construction (tailored reads more formal than unstructured), details (covered buttons read more formal than exposed), and fit (tailored reads more formal than relaxed).

When pairing, the highest-formality piece sets the floor and the lowest sets the ceiling. The gap between them should be narrow for cohesion.

### [DETAILED]

Intentional formality mixing is a valid style choice but requires: moderate-to-high risk tolerance, one clearly dominant piece, and the contrast must read as intentional. A silk blouse with quality denim reads as intentional. A formal suit jacket with sweatpants reads as confused.

---

## 6.3 Color Pairing Across Garments

### [COMPACT]

**Temperature consistency:** All pieces should share color temperature (warm or cool). A warm top with cool bottoms creates subtle discord.

**Value relationship:** The value difference between top and bottom determines contrast. Low value contrast creates elongation. High value contrast creates a clear visual break.

**Saturation matching:** Pieces should share a similar saturation level. A vivid top with muted trousers creates imbalance.

**Neutrals bridge everything:** A seasonal-appropriate neutral on one piece allows the other piece to carry the client's palette color freely. This is the simplest and most reliable pairing strategy.

### [DETAILED]

Pattern mixing rules: Shared common color, different pattern scales (one large, one small), shared visual energy level. A solid third piece can mediate between two patterns.

---

## 6.4 Fabric and Texture Pairing

### [COMPACT]

**Weight compatibility:** Pair fabrics of similar weight range. A heavy wool blazer over a sheer chiffon top creates weight imbalance.

**Texture contrast is desirable but controlled.** Some texture variation adds visual interest. Extreme texture contrast can feel jarring unless deliberate.

**Seasonal fabric families:**
- Warm-weather: cotton, linen, lightweight silk, chambray, seersucker.
- Cool-weather: wool, cashmere, corduroy, heavy knits, leather, suede, flannel.
- Transitional: medium-weight cotton, ponte, jersey, lightweight wool, gabardine.
Mixing seasonal families within one outfit feels incongruent.

### [DETAILED]

Sheen levels should be considered alongside texture. Mixing matte and shiny fabrics can either elevate or cheapen an outfit depending on context. A matte trouser with a subtle sheen blouse reads as elegant contrast.

The ratio of structured to unstructured fabrics affects overall character. Most outfits benefit from a balance — one structured piece with one fluid piece creates dynamic interplay.

---

# M07: Outfit Evaluation Framework

**Assigned to**: Outfit Evaluator (full)

This module defines how to holistically evaluate and rank candidate outfits.

---

## 7.1 Evaluation Criteria

### [COMPACT]

Each candidate outfit is evaluated with reasoned assessment, not formulaic scores:

**1. Body Harmony** — Does the silhouette flatter the body shape? Do proportions enhance the client's natural proportions? Does garment visual weight match the client's frame?

**2. Color Alignment** — Are colors near the face within the client's seasonal palette? Is color temperature consistent? Does outfit contrast match the client's natural contrast?

**3. Occasion Appropriateness** — Does formality match? Is the setting considered? Are cultural expectations met? Would the client feel comfortable?

**4. Style Alignment** — Does it reflect the client's style archetype? Is risk level appropriate? Are comfort priorities respected? Does it close the aspiration gap?

**5. Internal Cohesion** — Do pieces look intentionally combined? Is formality consistent? Is color palette harmonious? Is volume balanced? Do fabrics cohere? Is there a clear focal point?

**6. Overall Impression** — The holistic gut-check. Sometimes an outfit passes all criteria but lacks soul. Sometimes an outfit breaks a minor rule but has undeniable rightness.

### [DETAILED]

**Ranking logic when criteria conflict:**

Occasion appropriateness is non-negotiable — it acts as a filter, not a scale. Among remaining candidates, body harmony and color alignment are weighted most heavily. Style alignment differentiates when two outfits score similarly on body and color. Internal cohesion separates good from great. Overall impression is the tiebreaker and veto.

---

## 7.2 Comparative Ranking

### [COMPACT]

When ranking multiple candidates, reason comparatively:
- Which outfit best serves the stated occasion need?
- Which would make the client feel most confident?
- Which has the strongest visual impact within their comfort zone?
- Which is most versatile (could pieces be restyled)?

Present top 3-5 candidates with specific reasoning for each placement. Reference specific attributes — not vague praise.

---

# M08: Neckline, Collar & Detail Mapping

**Assigned to**: Outfit Architect (full)

---

## 8.1 Neckline Selection

### [COMPACT]

**Round face:** V-neck, deep scoop, plunging. Create vertical lines. Avoid: crew neck, jewel neck (echo roundness).

**Oval face:** Most versatile. Use neckline to address other attributes (neck length, shoulder width).

**Square face:** Scoop neck, round neck, cowl neck, soft drape. Introduce curves. Avoid: square necklines echoing jaw geometry.

**Heart face (wide forehead, narrow chin):** Scoop, sweetheart, off-shoulder. Avoid: strapless or very wide necklines extending top width.

**Long/oblong face:** Boat neck, wide scoop, square neckline, cowl. Add horizontal emphasis. Avoid: very deep V-necks that elongate further.

### [DETAILED]

Neckline depth interacts with bust volume:
- High necklines on fuller bust can create a "shelf" effect. A slightly lower neckline allows draping.
- Very deep necklines on fuller bust can shift register from polished to overtly sensual.
- Smaller bust benefits from higher necklines and intricate neckline details.

Neckline should synthesize face shape, neck length, shoulder width, and bust volume — not optimize for just one.

---

## 8.2 Neck Length Considerations

### [COMPACT]

**Short neck:** V-necklines, open collars, anything exposing collarbone and upper chest. Avoid turtlenecks and chokers.

**Long neck:** Can wear turtlenecks, crew necks, high collars gracefully. Mock necks, mandarin collars work well. Very deep plunging necklines can over-emphasize length.

**Average neck:** Maximum flexibility. Choose based on other attributes.

### [DETAILED]

Hair length interacts with neck perception. Long hair covers the neck, reducing visible length. Short-necked clients with long hair may need open necklines even more. Long-necked clients with long hair may not need neckline correction.

---

# M09: Fabric, Texture & Weight Guidelines

**Assigned to**: Outfit Architect (full), Outfit Assembler (full)

---

## 9.1 Fabric Selection by Body Attribute

### [COMPACT]

**Larger arm volume:** Avoid clingy sleeves. Opt for fabrics with body that skim — medium-weight cotton, light wool, ponte. Flutter sleeves work because they're loose by design.

**Fuller midsection:** Structured fabrics that hold shape, not collapse into contours. Medium-weight fabrics that skim. Avoid thin jersey (clings) and very stiff fabrics (tents and creates boxy shape).

**Fuller bust:** Enough structure to support without bulk. Avoid very thin (strains), very thick (adds volume), and very stiff (projects outward). Medium-weight wovens and quality knits work best.

**Slim frames:** Lighter fabrics that don't overwhelm. Texture and layering add dimension. Some structure helps create shape without the frame disappearing inside the garment.

### [DETAILED]

Fabric drape and body shape interact: Draped fabrics follow gravity and body contour — they celebrate curves on curvy bodies and fall straight on straight bodies. Stiff fabrics create their own shape independent of the body — they can either cage curves or be cut to follow them through tailoring.

---

## 9.2 Climate and Comfort

### [COMPACT]

- Hot climate: Cotton, linen, chambray, lightweight silk, moisture-wicking blends. Avoid polyester, heavy wool.
- Cold climate: Wool, cashmere, flannel, heavyweight knits. Avoid thin cottons and lightweight silks as primary layers.
- Transitional/indoor: Most options work. Prioritize aesthetic and body-related factors.

Stretch and comfort: If ComfortPriorities includes mobility, favor fabrics with stretch content (elastane blends, knits, jersey) over rigid wovens.

---

# M10: Cultural & Regional Conventions

**Assigned to**: Occasion Analyst (full)

---

## 10.1 Cultural Dress Codes

### [COMPACT]

**Religious events:** Modesty expectations vary. Many ceremonies expect shoulders covered, knees covered, limited décolletage. Head covering may be expected in certain contexts. When uncertain, err on more coverage.

**International business:** Different regions have different formality baselines. When styling for cross-cultural business, default one step more formal than the client's home standard.

**Cultural celebrations:** Some cultures have color conventions (white for funerals in some Asian cultures, bright colors for Indian celebrations, black for Western funerals). Cultural garment expectations may apply.

### [DETAILED]

**Cultural sensitivity:** Never recommend wearing traditional cultural garments as fashion statements outside that culture unless the context specifically invites it. When uncertain about cultural appropriateness, flag the uncertainty and recommend the client confirm with the host. The goal is respectful participation, not cultural tourism.

---

# M11: Catalog Attribute Mapping Reference

**Assigned to**: Catalog Search Agent (full)

---

## 11.1 Concept-to-Attribute Translation

### [COMPACT]

Common translations from Architect concepts to catalog attributes:

"relaxed fit" → FitEase: relaxed/loose; FitType: relaxed/oversized
"structured silhouette" → SilhouetteContour: structured; FabricDrape: crisp/stiff; EdgeSharpness: sharp/defined
"warm neutral base" → ColorTemperature: warm; ColorSaturation: low-medium; PrimaryColor: camel/beige/cream/tan/khaki/sand
"elongating effect" → LineDirection: vertical; PatternOrientation: vertical; SilhouetteType: column/straight
"minimal, clean" → EmbellishmentLevel: none/minimal; ConstructionDetail: minimal; PatternType: solid; ContrastLevel: low
"semi-formal evening" → FormalityLevel: semi-formal; FormalitySignalStrength: moderate-high; OccasionFit: evening/celebration; TimeOfDay: evening
"flatter broader shoulders" → NecklineType: V-neck/scoop; ShoulderStructure: raglan/dropped/natural
"draw attention away from midsection" → WaistDefinition: undefined/empire; FabricDrape: skim/structured-skim; BodyFocusZone: upper-chest/shoulder

### [DETAILED]

**Hard filters (never relax):** GarmentCategory, GenderExpression, OccasionFit, StylingCompleteness.
**Medium filters (relax if few results):** FormalityLevel, ColorTemperature, FitType, SilhouetteContour.
**Soft filters (for ranking, not filtering):** EmbellishmentLevel, PatternType, ConstructionDetail, FabricTexture.

**Constraint relaxation order:**
1. PatternType and EmbellishmentLevel
2. ColorSaturation and ColorValue ranges
3. FabricTexture and FabricWeight
4. SilhouetteContour (structured → semi-structured, or relaxed → semi-relaxed)
5. Never relax: GarmentCategory, GenderExpression, OccasionFit

---

## 11.2 Embedding Query Construction

### [COMPACT]

Sentence templates for each embedding column:

**Occasion:** "A [FormalityLevel] garment suitable for [OccasionSignal] events, [TimeOfDay], with [SkinExposureLevel] skin exposure and [GenderExpression] expression."

**Silhouette & Proportion:** "A [SilhouetteContour] [SilhouetteType] silhouette with [FitEase] ease, [VolumeProfile] volume, [ShoulderStructure] shoulders, [WaistDefinition] waist, [GarmentLength] length, with visual weight [VerticalWeightBias]."

**Color & Visual:** "A [ColorTemperature] garment in [PrimaryColor], [ColorSaturation] saturation, [ColorValue] value, [ContrastLevel] contrast, with [PatternType] pattern in [PatternScale] scale."

**Fabric & Construction:** "A [FabricWeight] garment with [FabricDrape] drape, [FabricTexture] texture, [StretchLevel] stretch, [EdgeSharpness] edges, [EmbellishmentLevel] embellishment."

**Style Identity:** Synthesize all attributes into overall character: "A [overall adjective] [GarmentSubtype] that feels [mood/vibe], suitable for a [style archetype] aesthetic."

**Pairing:** "A garment with [VolumeProfile] volume, [FitEase] ease, [ColorTemperature] temperature at [ColorValue] value, [FormalityLevel] formality, [FabricWeight] weight."

---

# M12: Client Communication Guidelines

**Assigned to**: Presentation Agent (full)

---

## 12.1 Recommendation Presentation

### [COMPACT]

**Lead with the outfit, not the analysis.** Present the recommendation first, then support with reasoning.

**Reasoning should be personal and specific.** Instead of "V-necks are flattering," say "the V-neckline works with your face shape and this shade of olive is one of your strongest Deep Autumn colors."

**Use accessible language.** Avoid jargon. Say "creates balance between upper and lower body" not "visual weight distribution."

**Present options with clear differentiation.** "Option 1 is classic and safe. Option 2 is bolder with color. Option 3 breaks the expected silhouette."

**Anticipate follow-ups.** "If you want bolder, I can push color. If the silhouette doesn't feel right, I can explore different cuts in the same palette."

### [DETAILED]

**Handling rejection:** Ask why — color, cut, or overall feel? Route the answer to the right part of the pipeline for re-processing.

**Building trust:** Early recommendations should lean slightly conservative relative to risk tolerance. As trust builds, gradually introduce bolder suggestions.

**Explaining trade-offs honestly:** If no perfect match exists, say so and explain what each option prioritizes and what it compromises.

---

# Appendix A: Seasonal Palette Quick Reference

## Spring
Neutrals: Cream, camel, light warm grey, warm beige, light brown.
Core: Coral, peach, salmon, warm pink, golden yellow, light orange, warm green, turquoise, aqua.
Metals: Gold, brass, rose gold.

## Summer
Neutrals: Soft grey, blue-grey, cocoa, taupe, soft white.
Core: Lavender, dusty rose, powder blue, soft sage, mauve, periwinkle, soft teal, raspberry, plum.
Metals: Silver, platinum, white gold, rose gold.

## Autumn
Neutrals: Chocolate brown, olive, camel, warm beige, khaki, dark warm grey, cream.
Core: Terracotta, burnt orange, rust, mustard, olive green, deep teal, warm burgundy, amber, bronze, moss green, aubergine.
Metals: Gold, brass, bronze, copper.

## Winter
Neutrals: Black, pure white, charcoal, navy, cool grey.
Core: True red, emerald green, royal blue, bright fuchsia, icy pink, icy blue, deep purple, bright teal, cobalt, deep burgundy.
Metals: Silver, platinum, white gold.

---

# Appendix B: Body Shape Quick Decision Matrix

```
Shoulders > Hips         → Inverted Triangle → Add lower volume, reduce upper emphasis
Shoulders ≈ Hips + waist → Hourglass         → Follow curves, define waist
Shoulders ≈ Hips - waist → Rectangle         → Create curves OR embrace linearity
Shoulders < Hips         → Triangle/Pear     → Add upper emphasis, streamline lower
Midsection dominant      → Oval/Apple        → Vertical flow, skim midsection, open neckline
```

---

# Appendix C: Decision Priority Hierarchy

When criteria conflict, resolve in this order:

1. **Occasion appropriateness** — Non-negotiable filter
2. **Fit and silhouette** — Most impactful on appearance
3. **Color palette** — High visual impact, especially near face
4. **Proportion strategy** — Enhances body, partially achievable with fit alone
5. **Style archetype** — Shapes emotional experience
6. **Risk tolerance** — Can always adjust on follow-up
7. **Internal cohesion** — Quality marker, separates good from great
