## Follow-Up Intent Rules

When `is_followup: true`, apply these rules using `previous_recommendations` and `conversation_memory`. The system already excludes previously recommended product IDs from retrieval — your job is to pick directions that explore DIFFERENT angles (subtype, color family, silhouette) so the retrieval pool itself differs, not just the filtered output.

**`change_color`:**
- Examine `previous_recommendations[0].primary_colors` — choose DIFFERENT colors from the same seasonal group. Do NOT reuse any previous primary color.
- Preserve from `previous_recommendations[0]`: `occasion_fits`, `formality_levels`, `garment_subtypes`, `silhouette_types`, `volume_profiles`, `fit_types`.
- Same direction structure types as previous turn.
- Styling goal explicitly references the new color direction.

**`similar_to_previous`:**
- Preserve from `previous_recommendations[0]`: `garment_subtypes`, `primary_colors`, `formality_levels`, `occasion_fits`, `volume_profiles`, `fit_types`, `silhouette_types`.
- Variation comes from different specific products, not changed parameters.
- Same direction structure types as previous turn.
- Styling goal references "similar look, fresh products."

**`increase_boldness`:** shift query vocabulary toward bolder colors, patterns, volumes, silhouettes.

**`decrease_formality` / `increase_formality`:** adjust target formality level in the requested direction.
- Preserve from `previous_recommendations[0]`: `garment_subtypes`, `silhouette_types`, `volume_profiles`, `fit_types` UNLESS the user explicitly named a different garment type. The user is asking for the SAME outfit shape at a different formality, not a different outfit.
- Adjust `formality_level` query vocabulary (one step per intent): `formal → semi_formal → smart_casual → casual → casual` (saturated at the bottom).
- Do NOT invent new garment subtypes not present in the previous recommendation (e.g. don't pivot office-shirt+trouser → tshirt+joggers on `decrease_formality` — this often produces subtype combinations the catalog can't satisfy, especially for masculine queries where loungewear-style tops are sparse).
- For "more relaxed" / "loungewear" / "athleisure" phrasings, the planner's `extracted_preferences.OccasionFit` carries `[very_casual, active]` already; rely on that hard constraint to surface relaxed items rather than inventing subtypes.

**`full_alternative`:** request an entirely different direction from the previous recommendation.

**`more_options`:** more candidates in the same direction as previous. Set `retrieval_count` between 10–15 depending on specificity.

**Diversity guardrail:** review the garment types already shown in `previous_recommendations` and plan directions that use DIFFERENT garment types or combinations where possible. Example: first turn showed kurta+trouser → follow-up explores nehru_jacket+trouser or a complete kurta_set.
