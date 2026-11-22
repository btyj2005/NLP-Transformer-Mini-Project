BEGIN;

DO $roles$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'matchlab_writer') THEN
        CREATE ROLE matchlab_writer LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'matchlab_reader') THEN
        CREATE ROLE matchlab_reader LOGIN;
    END IF;
END;
$roles$;

CREATE SCHEMA IF NOT EXISTS matchlab_analytics;
REVOKE ALL ON SCHEMA matchlab_analytics FROM PUBLIC, anon, authenticated, service_role;
GRANT USAGE ON SCHEMA matchlab_analytics TO matchlab_reader, matchlab_writer;

CREATE TABLE IF NOT EXISTS matchlab_analytics.events (
    kind text NOT NULL CHECK (kind IN ('visit', 'mode_selected', 'game_started', 'game_completed')),
    scope_id uuid NOT NULL,
    session_id uuid NOT NULL,
    round_id uuid,
    mode text CHECK (mode IN ('Bestie Mode', 'Couple Mode')),
    source text NOT NULL CHECK (source IN ('LinkedIn', 'GitHub', 'Direct / Other')),
    occurred_at timestamptz NOT NULL,
    PRIMARY KEY (kind, scope_id),
    CHECK (
        (kind = 'visit' AND round_id IS NULL AND mode IS NULL AND scope_id = session_id)
        OR (kind <> 'visit' AND round_id IS NOT NULL AND mode IS NOT NULL AND scope_id = round_id)
    )
);

CREATE INDEX IF NOT EXISTS matchlab_events_occurred_at ON matchlab_analytics.events (occurred_at);
REVOKE ALL ON matchlab_analytics.events FROM PUBLIC, anon, authenticated, service_role;
GRANT INSERT ON matchlab_analytics.events TO matchlab_writer;
GRANT SELECT ON matchlab_analytics.events TO matchlab_reader;
ALTER TABLE matchlab_analytics.events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS matchlab_insert ON matchlab_analytics.events;
CREATE POLICY matchlab_insert ON matchlab_analytics.events FOR INSERT TO matchlab_writer WITH CHECK (true);
DROP POLICY IF EXISTS matchlab_read ON matchlab_analytics.events;
CREATE POLICY matchlab_read ON matchlab_analytics.events FOR SELECT TO matchlab_reader USING (true);

COMMIT;
