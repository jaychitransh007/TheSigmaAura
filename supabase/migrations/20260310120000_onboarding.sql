-- Onboarding: user profile input and image metadata tables

CREATE TABLE IF NOT EXISTS onboarding_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL UNIQUE,
  mobile text NOT NULL UNIQUE,
  otp_last_used_hash text,
  otp_verified_at timestamptz,
  name text NOT NULL DEFAULT '',
  date_of_birth date,
  gender text
    CHECK (gender IS NULL OR gender IN ('male', 'female', 'non_binary', 'prefer_not_to_say')),
  height_cm numeric(5, 1),
  waist_cm numeric(5, 1),
  profession text
    CHECK (profession IS NULL OR profession IN (
      'software_engineer', 'doctor', 'lawyer', 'teacher', 'designer',
      'architect', 'business_finance', 'marketing', 'artist', 'student',
      'entrepreneur', 'homemaker', 'other'
    )),
  profile_complete boolean NOT NULL DEFAULT false,
  onboarding_complete boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_onboarding_profiles_mobile
  ON onboarding_profiles(mobile);

CREATE TABLE IF NOT EXISTS onboarding_images (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  category text NOT NULL
    CHECK (category IN ('full_body', 'headshot', 'veins')),
  encrypted_filename text NOT NULL,
  original_filename text NOT NULL DEFAULT '',
  file_path text NOT NULL,
  mime_type text NOT NULL DEFAULT 'image/jpeg',
  file_size_bytes int NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, category)
);

CREATE INDEX IF NOT EXISTS idx_onboarding_images_user
  ON onboarding_images(user_id);
