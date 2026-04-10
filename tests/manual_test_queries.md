# Manual Test Queries — Outfit Architect Pipeline

Use these queries against the staging app to validate Phase 13/13B changes.
For each query, check: direction count, direction types, garment subtypes chosen,
outfit count in response, and whether the outfit makes stylistic sense.

---

## Masculine

### 1. Wedding engagement (semi-formal evening)
```
What should I wear to my friend's wedding engagement?
```
**Expect:** occasion=wedding_engagement, formality=semi_formal, time=evening, deep/rich colors, silk/structured wool fabrics, embellishment subtle-moderate. 3 directions with subtype diversification (kurta/shirt/kurta_set). No sherwanis or heavy brocade (that's ceremony, not engagement).

### 2. Daily office (paired only, no blazer)
```
Find me outfits for daily office wear
```
**Expect:** occasion=daily_office, formality=smart_casual, paired directions ONLY (no three_piece/blazer). Subtypes diversified across directions (shirt/tshirt/sweater — only from inventory). 3 outfits.

### 3. Formal office (blazer appropriate)
```
I have a client presentation tomorrow
```
**Expect:** occasion=office, formality=business_casual or smart_casual, paired + three_piece directions (blazer in three_piece). ranking_bias=formal_first or conservative.

### 4. Casual weekend
```
Something casual for a weekend brunch
```
**Expect:** occasion=brunch, formality=casual, time=daytime, paired only. Cotton/linen/jersey fabrics. Relaxed silhouettes. Full daytime palette range.

### 5. Single garment browse
```
Show me kurtas
```
**Expect:** target_product_type=kurta, 1 direction only, hard_filter garment_subtype=["kurta","kurta_set"], retrieval_count ~6. No full outfit planning.

### 6. Sangeet (cultural evening event)
```
Outfit for a sangeet night
```
**Expect:** occasion=sangeet, time=evening, smart_casual-semi_formal. Silk/cotton-silk fabrics. Embellishment subtle-moderate, playful/colorful. Deep evening palette. Complete + paired + three_piece all valid.

### 7. Follow-up: increase boldness
> First send query #2 or #4, then:
```
Show me something bolder
```
**Expect:** is_followup=true, followup_intent=increase_boldness. Preserves occasion/formality from prior turn. Shifts toward bolder colors, patterns, or silhouettes.

### 8. Follow-up: change color
> First send any recommendation query, then:
```
Same but in different colors
```
**Expect:** is_followup=true, followup_intent=change_color. Preserves occasion_fits, formality_levels, garment_subtypes, silhouette_types, volume_profiles, fit_types from previous_recommendations[0]. Uses DIFFERENT colors from same seasonal group.

### 9. Beach vacation
```
Beach vacation outfits
```
**Expect:** occasion=beach/vacation, paired only (no outerwear, no complete sets). Tee+shorts, shirt+linen_trouser type combos. Light relaxed fabrics. No embellishment.

### 10. Comfort-first date
```
Date night outfit, something I'd actually feel comfortable in
```
**Expect:** occasion=date_night, time=evening, ranking_bias=comfort_first. Respects low risk-tolerance. Smart_casual. Evening color palette (deep/rich). No heavy embellishment.

---

## Feminine

### 11. Cocktail party
```
What should I wear to a cocktail party?
```
**Expect:** occasion=cocktail_party, formality=semi_formal, time=evening. Paired + three_piece + complete (dress) all valid. Suiting wool/silk/structured fabrics. Embellishment minimal-subtle. No traditional motifs.

### 12. Daily office (feminine)
```
Daily office looks for me
```
**Expect:** occasion=daily_office, paired only. Cotton/linen. No embellishment. Subtypes diversified (kurti/blouse+trouser/shirt+trouser — from inventory).

### 13. Wedding ceremony (formal)
```
Show me outfits for a wedding ceremony
```
**Expect:** occasion=wedding, formality=formal. Heavy embellishment OK. Silk/brocade/heavy jacquard. Complete (lehenga_set/saree) + paired + three_piece. Deep/rich palette if evening.

### 14. Single garment browse (feminine)
```
Find me dresses
```
**Expect:** target_product_type=dress, 1 direction, hard_filter garment_subtype=dress. Single-garment mode.

### 15. Mehndi
```
Mehndi outfit ideas
```
**Expect:** occasion=mehndi, time=evening, smart_casual-semi_formal. Playful/colorful. Cotton-silk/silk blend. Embellishment subtle-moderate. No somber colors or stiff suiting.

### 16. Style override (creative)
```
Something creative and bold for a house party
```
**Expect:** Style archetype override to Creative (regardless of saved profile). ranking_bias=expressive. Bolder patterns, unexpected silhouettes. Party-appropriate formality.

### 17. Weather-fabric conflict
```
Outdoor wedding in Goa in summer
```
**Expect:** occasion=wedding, formality=formal. Weather=hot/humid. Weather-fabric override kicks in: silk/crepe/organza/cotton-silk blend (NOT velvet/heavy wool/brocade). Occasion still governs formality and embellishment.

### 18. Professional but not boring
```
I want to look professional but not boring
```
**Expect:** occasion=office or daily_office. specific_needs should include authority + approachability. Style-stretch direction should push slightly beyond default archetype.

---

## Anchor / Pairing

### 19. Outerwear anchor for date
> Attach an image of a navy blazer, then:
```
Style this for a date night
```
**Expect:** Anchor=outerwear → paired directions with BOTH top+bottom queries. No three_piece (outerwear slot filled). Date night formality (smart_casual). Evening colors.

### 20. Top anchor for Diwali
> Attach an image of a white kurta, then:
```
What goes with this for Diwali?
```
**Expect:** Anchor=top → paired (bottom) or three_piece (bottom+outerwear). No complete direction. Festive occasion calibration. Complementary colors from user's palette.

---

## Edge Cases

### 21. Anchor formality conflict
> Attach an image of a casual denim jacket, then:
```
Style this for a wedding
```
**Expect:** Anchor=outerwear (casual denim) + occasion=wedding (formal). Supporting garments should shift UP in formality to compensate — silk/structured trouser, premium shirt. NOT matching the denim's casualness.

### 22. Follow-up: similar
> First send any recommendation query, then:
```
Show me something similar
```
**Expect:** followup_intent=similar_to_previous. Preserves garment_subtypes, primary_colors, formality_levels, occasion_fits, volume_profiles, fit_types, silhouette_types. Different products only.

### 23. Catalog follow-up after wardrobe-first
> (Requires user with wardrobe items) After getting a wardrobe-first answer:
```
Show me catalog options instead
```
**Expect:** source_preference=catalog, is_followup=true. Full catalog pipeline runs (architect → search → assemble → evaluate).

### 24. Ambiguous follow-up (tiebreaker test)
> After any recommendation:
```
Show me something similar but in a different color
```
**Expect:** Matches both change_color and similar_to_previous. Tiebreaker should pick change_color (higher priority). Colors change, everything else preserved.

### 25. Non-existent subtype guard
> After getting daily office results, check the architect plan:
```
Everyday work outfits
```
**Expect:** All garment subtypes in the plan MUST exist in catalog_inventory. No polo (0 in catalog). Subtypes should be shirt/tshirt/sweater or other inventory-backed types. 3 outfits with diverse tops.

---

## What to Check for Each Query

- [ ] **Direction count:** 2-3 for broad, 1 for specific/browse
- [ ] **Direction types:** match the occasion table (no blazer for daily_office, no complete for casual)
- [ ] **Subtype diversification:** different GarmentSubtype across directions for the same role
- [ ] **Inventory compliance:** no subtypes with 0 items in catalog
- [ ] **Outfit count:** 3 outfits (or 2 minimum). If 1, check for search timeouts or product overlap
- [ ] **Fabric match:** premium for formal, casual for casual, weather override when weather_context present
- [ ] **Color coherence:** top ≠ bottom color, BaseColors for anchors, AccentColors for statements, no AvoidColors
- [ ] **Follow-up preservation:** prior turn dimensions carried forward correctly
- [ ] **ranking_bias:** conservative for office/safe, expressive for bold/creative, comfort_first when comfort mentioned
