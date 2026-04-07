-- Server-side persistence for "saved looks": users can pin a recommended
-- outfit so it survives browser data clears and is available across devices.
--
-- A saved look points back at the originating turn (and the outfit rank
-- within it) so the renderer can rehydrate the full outfit card from
-- conversation_turns.resolved_context_json without duplicating product rows.
CREATE TABLE IF NOT EXISTS saved_looks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
    turn_id         uuid REFERENCES conversation_turns(id) ON DELETE SET NULL,
    outfit_rank     int  NOT NULL DEFAULT 1,
    title           text NOT NULL DEFAULT '',
    item_ids        text[] NOT NULL DEFAULT '{}',
    snapshot_json   jsonb NOT NULL DEFAULT '{}'::jsonb,
    notes           text NOT NULL DEFAULT '',
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS saved_looks_user_id_idx
    ON saved_looks (user_id, created_at DESC)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS saved_looks_turn_id_idx
    ON saved_looks (turn_id);
