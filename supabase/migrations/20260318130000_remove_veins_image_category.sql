-- Remove veins image category from onboarding.
-- Digital draping replaces undertone-based color analysis entirely.

-- Clean up any existing veins rows (soft removal — data preserved in backups)
DELETE FROM onboarding_images WHERE category = 'veins';

-- Drop the old CHECK constraint and replace with one excluding 'veins'
ALTER TABLE onboarding_images DROP CONSTRAINT IF EXISTS onboarding_images_category_check;
ALTER TABLE onboarding_images ADD CONSTRAINT onboarding_images_category_check CHECK (category IN ('full_body', 'headshot'));
