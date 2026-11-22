# Owner analytics and match details rollout

## 1. Apply the migration

Open the SQL Editor in the existing Supabase project. Run
[migration 002](../migrations/002_match_details.sql) as the project database administrator
after migration 001. If the editor reports that pg_cron is unavailable, enable the Supabase
Cron integration and rerun migration 002. The migration is transactional and can be rerun.
Leave the existing Streamlit secrets and database passwords in place.

Verify the named job exists and is active:

```sql
select jobname, schedule, active
from cron.job
where jobname = 'matchlab-expire-private-details';
```

Refresh Owner Analytics to start reading score history. Existing events are retained.
Until migration 002 is applied, visitors can play and the owner can use traffic and
gameplay analytics. No old scores or private details are backfilled. Public consent controls
can take up to one minute to appear after migration.

## 2. Understand collection and expiry

Anonymous overall and per-question scores use the game’s existing 0–100 scale.
These scores and the standard usage events have no automatic expiry.
The exact questions are saved with score snapshots so they can be read after prompt edits.

During each player’s final question, an unchecked consent control explains that saved names
and answers are visible to the verified owner. The other player’s decision is hidden.
Both players must actively opt in for the same finalized round. Editing a player’s answers
requires that player to make a new choice. The game stores names and answers in a separate
table and stops returning them 30 days after insertion. The hourly UTC cleanup physically
deletes expired rows within about one hour when Cron is healthy.

Standard Supabase backups may contain a prior copy until the project’s backup retention
period ends. After restoring a backup, run expired-data cleanup before allowing reads and
reapply any deletion requests made since the backup where applicable.

## 3. Remove shared answers

Either player can copy the same random deletion code from the results page and submit it
under **About → Delete shared match details**. The code authorizes deletion of both players’
names and answers for that round. Keep it private. The database stores its hash and keeps
the anonymous scores when deleting private details. The app gives the same confirmation
for an already-removed or unknown valid-format code.

## 4. Verify on Streamlit

Check the live app as a logged-out visitor, then sign in with the verified owner GitHub
account. Check reader and writer under **Database diagnostics**. After a test round,
refresh analytics and open the completed game. Use an opt-in round to test the deletion
code, then reopen its details. The score should remain and the names and answers should
be absent. Play a second round with only one player agreeing and verify that no code is
issued and no player text appears in analytics. Use disposable names and answers.
