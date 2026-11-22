-- Run as the Supabase project database administrator after migration 001.
BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_cron;

CREATE TABLE IF NOT EXISTS matchlab_analytics.match_scores (
    round_id uuid PRIMARY KEY,
    overall double precision NOT NULL CHECK (overall BETWEEN 0 AND 100),
    scores double precision[] NOT NULL CHECK (
        array_ndims(scores) = 1 AND cardinality(scores) = 5
        AND array_position(scores, NULL) IS NULL AND 0 <= ALL(scores) AND 100 >= ALL(scores)
    ),
    prompts text[] NOT NULL CHECK (
        array_ndims(prompts) = 1 AND cardinality(prompts) = 5
        AND array_position(prompts, NULL) IS NULL
    )
);

CREATE TABLE IF NOT EXISTS matchlab_analytics.private_match_details (
    round_id uuid PRIMARY KEY REFERENCES matchlab_analytics.match_scores (round_id),
    names text[] NOT NULL CHECK (cardinality(names) = 2),
    first_answers text[] NOT NULL CHECK (cardinality(first_answers) = 5),
    second_answers text[] NOT NULL CHECK (cardinality(second_answers) = 5),
    deletion_hash bytea NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '30 days')
);

CREATE INDEX IF NOT EXISTS matchlab_details_expiry
    ON matchlab_analytics.private_match_details (expires_at);

REVOKE ALL ON matchlab_analytics.match_scores, matchlab_analytics.private_match_details
    FROM PUBLIC, anon, authenticated, service_role, matchlab_writer, matchlab_reader;
GRANT INSERT ON matchlab_analytics.match_scores TO matchlab_writer;
GRANT SELECT ON matchlab_analytics.match_scores TO matchlab_reader;
GRANT INSERT (round_id, names, first_answers, second_answers, deletion_hash)
    ON matchlab_analytics.private_match_details TO matchlab_writer;
GRANT SELECT (round_id, names, first_answers, second_answers)
    ON matchlab_analytics.private_match_details TO matchlab_reader;

ALTER TABLE matchlab_analytics.match_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE matchlab_analytics.private_match_details ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS score_insert ON matchlab_analytics.match_scores;
CREATE POLICY score_insert ON matchlab_analytics.match_scores FOR INSERT
    TO matchlab_writer WITH CHECK (true);
DROP POLICY IF EXISTS score_read ON matchlab_analytics.match_scores;
CREATE POLICY score_read ON matchlab_analytics.match_scores FOR SELECT
    TO matchlab_reader USING (true);
DROP POLICY IF EXISTS details_insert ON matchlab_analytics.private_match_details;
CREATE POLICY details_insert ON matchlab_analytics.private_match_details FOR INSERT
    TO matchlab_writer WITH CHECK (true);
DROP POLICY IF EXISTS details_read ON matchlab_analytics.private_match_details;
CREATE POLICY details_read ON matchlab_analytics.private_match_details FOR SELECT
    TO matchlab_reader USING (expires_at > now());

CREATE OR REPLACE FUNCTION matchlab_analytics.delete_private_match(code uuid)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    DELETE FROM matchlab_analytics.private_match_details
    WHERE deletion_hash = sha256(convert_to(code::text, 'UTF8'));
$$;

REVOKE ALL ON FUNCTION matchlab_analytics.delete_private_match(uuid)
    FROM PUBLIC, anon, authenticated, service_role, matchlab_reader;
GRANT EXECUTE ON FUNCTION matchlab_analytics.delete_private_match(uuid) TO matchlab_writer;

-- The named job is updated in place when this migration is run again.
SELECT cron.schedule(
    'matchlab-expire-private-details', '17 * * * *',
    'DELETE FROM matchlab_analytics.private_match_details WHERE expires_at <= now()'
);
COMMIT;
