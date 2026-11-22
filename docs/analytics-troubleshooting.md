# Owner Analytics database troubleshooting

In **Owner Analytics → Database diagnostics**, click **Check reader and writer**.
The reader checks its role and row-level security and reads from the events table.
The writer attempts a real insert and rolls it back, so it does not affect counts.
The dashboard and Streamlit logs use short diagnostic codes.

## Streamlit Secrets

In Supabase **Connect → Session pooler**, copy the hostname exactly as shown and
take the project ref from the part after `postgres.` in the sample username. In
Streamlit **Manage app → Settings → Secrets**, update these keys within the existing
`[owner_analytics]` section. Keep the other settings in that section and the
existing Auth0 settings.

```toml
[owner_analytics]
write_dsn = "host=POOLER_HOST port=5432 dbname=postgres user=matchlab_writer.PROJECT_REF password=WRITER_ROLE_PASSWORD"
read_dsn = "host=POOLER_HOST port=5432 dbname=postgres user=matchlab_reader.PROJECT_REF password=READER_ROLE_PASSWORD"
```

- **POOLER_ROUTE**. Check that both values use the same Session pooler host and
  project ref. Use the custom role name before the dot.
- **LOGIN_REJECTED**. Check each role has `LOGIN` and use the PostgreSQL password
  set for that role. Supabase API keys are unrelated to these connections.
  If a role password contains whitespace, quotes or backslashes, use a PostgreSQL
  URI and percent-encode the password component before pasting it into TOML.
- **TLS**. First check the exact hostname. If certificate verification fails,
  download the root CA as PEM from Supabase **Database Settings → SSL Configuration**
  and add the following value in the same Streamlit Secrets section. It is used
  for both connections. The app always verifies hostname and certificate.

  ```toml
  ssl_root_cert_pem = '''
  -----BEGIN CERTIFICATE-----
  PASTE THE DOWNLOADED CERTIFICATE BODY HERE
  -----END CERTIFICATE-----
  '''
  ```

- **SCHEMA_MISSING**, **ACCESS_DENIED** or **READER_POLICY**. Check that both
  connections point to the same project where you applied
  [the analytics migration](../migrations/001_owner_analytics.sql). The migration
  can be reapplied in the Supabase SQL Editor to restore the declared grants and
  policies while preserving event rows. The writer needs schema usage, table
  insert and the insert policy. The reader needs schema usage, table select and
  the select policy. Keep RLS enabled.

Save the settings and rerun diagnostics. After both checks pass, open the live
game in a new signed-out browser session. Refresh the owner dashboard and check
for the visit. Supabase records the event in `matchlab_analytics.events` and retains
it when Streamlit restarts. A real visit in production counts toward analytics.
