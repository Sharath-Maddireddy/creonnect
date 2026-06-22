-- Migration: Create creator_trend_results table
-- Run on PostgreSQL (psql) or via your DB migration tooling.

CREATE TABLE IF NOT EXISTS creator_trend_results (
    account_id TEXT PRIMARY KEY,
    niche_json JSONB NULL,
    global_trends_json JSONB NULL,
    recommendations_json JSONB NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_creator_trend_results_updated_at ON creator_trend_results (updated_at);

-- Optional: trigger to auto-update updated_at on row modification
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_creator_trend_results_updated_at'
    ) THEN
        CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_creator_trend_results_updated_at
        BEFORE UPDATE ON creator_trend_results
        FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();
    END IF;
END$$;
