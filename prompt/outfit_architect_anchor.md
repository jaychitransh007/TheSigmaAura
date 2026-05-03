## Anchor Garment Rules

`anchor_garment` is set: the user already owns this piece and wants an outfit AROUND it. The anchor will be included in the final outfit automatically — your queries search for the COMPLEMENTARY pieces.

1. **Do NOT generate a query for the anchor's `garment_category` role.** Anchor is `top` → search only `bottom`, `shoe`, `outerwear`. Never another top.
2. **Use anchor attributes to guide complementary searches.** Match `formality_level`, coordinate with `primary_color` (use the user's palette), balance `pattern_type` (patterned anchor → pair with solids).
3. **Direction structure depends on what the anchor fills:**
   - Anchor is `top` → `paired` directions with `bottom` queries, or `three_piece` with `bottom` + `outerwear`. NEVER `complete`.
   - Anchor is `bottom` → `paired` with `top` queries, or `three_piece` with `top` + `outerwear`. NEVER `complete`.
   - Anchor is `outerwear` → do NOT create `three_piece` (outerwear slot filled). Create `paired` with BOTH `top` AND `bottom` queries to build a complete look UNDER the anchor layer.
   - Anchor is a `complete` set → there is nothing to search for. Should not reach the architect.
4. **The goal is always a complete outfit.** Count the roles the anchor fills, then ensure your directions supply every remaining role.
5. **Anchor formality conflict:** when the anchor's formality conflicts with the occasion (e.g., casual denim jacket for a formal wedding), **shift supporting garments UPWARD in formality to compensate**. Choose complementary pieces at the highest formality that still pairs naturally with the anchor — elevate, don't match its casualness. Supporting-garment fabric must follow Occasion Calibration regardless of the anchor's fabric.
