-- May 2026: drop user_sentiment_history. The sentiment-tracking service
-- that backed this table was removed when the WhatsApp/sentiment
-- runtime was cleaned out (see project_overview "WhatsApp/sentiment
-- code removed" note). The table has 96 historical rows and zero
-- current readers/writers across modules/, services/, ops/.
--
-- DROP TABLE cascades the FK constraints (REFERENCES users,
-- conversations, conversation_turns) automatically. Indexes drop with
-- the table. The migration tracking row in supabase_migrations is the
-- only record that survives.

DROP TABLE IF EXISTS user_sentiment_history;
