-- Add title column to conversations for user-assigned names
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS title text NOT NULL DEFAULT '';
