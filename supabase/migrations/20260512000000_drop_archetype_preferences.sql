-- May 2026: drop the columns that backed the now-removed style-archetype
-- preference. risk_tolerance stays — it's the single retained per-user
-- style preference. Dropped values are coerced to the new 3-value scale
-- (conservative | balanced | expressive); the legacy 5-value scale
-- (conservative | moderate-conservative | moderate | moderate-adventurous |
-- adventurous) collapses as below.

-- 1. Coerce existing risk_tolerance values to the new 3-value canonical set
--    BEFORE dropping the surrounding context columns. Done as an UPDATE
--    rather than a CHECK constraint so existing rows survive.
UPDATE user_style_preference_snapshots
   SET risk_tolerance = CASE
       WHEN risk_tolerance IN ('conservative', 'moderate-conservative') THEN 'conservative'
       WHEN risk_tolerance IN ('moderate-adventurous', 'adventurous')   THEN 'expressive'
       WHEN risk_tolerance = 'moderate'                                 THEN 'balanced'
       WHEN risk_tolerance = ''                                         THEN 'balanced'
       ELSE risk_tolerance  -- leave anything unrecognised alone; downstream tolerates
   END
 WHERE risk_tolerance IS NOT NULL;

-- 2. Drop the columns that backed the removed archetype/formality/pattern
--    fields and the image-picker artifacts.
ALTER TABLE user_style_preference_snapshots
  DROP COLUMN IF EXISTS primary_archetype,
  DROP COLUMN IF EXISTS secondary_archetype,
  DROP COLUMN IF EXISTS blend_ratio_primary,
  DROP COLUMN IF EXISTS blend_ratio_secondary,
  DROP COLUMN IF EXISTS formality_lean,
  DROP COLUMN IF EXISTS pattern_type,
  DROP COLUMN IF EXISTS comfort_boundaries_json,
  DROP COLUMN IF EXISTS archetype_scores_json,
  DROP COLUMN IF EXISTS selected_image_ids_json,
  DROP COLUMN IF EXISTS selected_images_json,
  DROP COLUMN IF EXISTS selection_count;

-- 3. Drop the onboarding-gate flag that required the (now-deleted)
--    image-picker step. profile_confidence's risk_tolerance_set factor
--    replaces the user-facing meaning.
ALTER TABLE onboarding_profiles DROP COLUMN IF EXISTS style_preference_complete;
ALTER TABLE onboarding_profile_snapshots DROP COLUMN IF EXISTS style_preference_complete;
