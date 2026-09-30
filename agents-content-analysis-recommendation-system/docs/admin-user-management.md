# Admin User Management

Route: `/#/admin-users`, menu: "จัดการผู้ใช้". All API endpoints require an active
admin with a valid login session. Normal accounts cannot call these endpoints.

## Actions

- List/search username or email, filter role/status and paginate 20 accounts.
- View creation/login/session activity timestamps and counts of saved clips,
  analysis results and followed topics. Session counts are **not** online counts:
  they count sessions not ended in the database, not unexpired JWTs.
- Create an account; passwords are hashed using the existing authentication code.
  Responses and audit events never include passwords or password hashes.
- Edit username/email, change `user`/`admin`, suspend or reactivate an account.
- End all existing sessions. Email, role and status changes also end sessions,
  so old tokens cannot regain access after reactivation. Fresh login uses DB role.
- Delete an account after typing its current username and reviewing its impact.

The currently signed-in admin cannot modify/delete their own account from this
page. Mutations lock the shared system configuration row, then recheck the actor
and target with current row locks. This serializes account changes and prevents
two admins from demoting/deleting one another concurrently. The last active admin
is protected. Requests also carry the displayed account revision; stale edits and
confirmations receive HTTP 409 rather than silently overwriting newer changes.

## Delete Semantics

Deletion is permanent for the account and its saved private DB records:
`user_contents`, their `analysis_results`, `recommendations`, `content_keywords`,
content-based `cluster_memberships`, follows, notifications, login sessions and
account-specific settings. Shared keyword dictionary entries, datasets, models,
cluster history and global settings are retained.

System logs retain a `deleted_actor_user_id` in details and clear their foreign
key. Training runs remain, with a nullable `requested_by`; the delete audit event
records the retained run IDs and original user ID. Accounts with queued/running
training cannot be deleted until the run ends; suspension is still available.
The startup migration makes `model_training_runs.requested_by` nullable on MySQL
without deleting historical data. A pre-existing SQLite database with a NOT NULL
column needs a separate table-rebuild migration; fresh test DBs use the new schema.

After the DB transaction succeeds, uploaded video files belonging exclusively to
the deleted account are removed only when their resolved paths are inside the
project `videos` directory and use the uploader's UUID filename convention.
Referenced/shared files and arbitrary historical paths are not deleted. File
cleanup failures produce a warning in the response and System Logs. This does
not promise erasure of backups, externally hosted videos or transient job caches.
An in-flight analysis may fail saving if its owner is deleted meanwhile.

## API

- `GET /admin/users?q=&role=all&state=all&offset=0&limit=20`
- `GET /admin/users/{id}`
- `POST /admin/users` (username, email, password, role)
- `PUT /admin/users/{id}` (username, email, role, is_active, expected_revision)
- `POST /admin/users/{id}/revoke-sessions` (expected_revision)
- `DELETE /admin/users/{id}` (JSON expected_revision and confirmation)

Unknown mutation fields are forbidden. Duplicate identities and foreign-key
conflicts roll back the DB mutation. There is deliberately no password viewer,
arbitrary password-hash editor, or unverified password-reset workflow.

## Verification

`python -m unittest tests.test_user_management`

`flutter test --no-pub`

Backend tests enforce SQLite foreign keys and exercise authorization, sessions,
stale requests, self-protection, audit retention, child deletion, shared/unsafe
file paths and rollback. Browser smoke testing uses only disposable accounts and
does not change existing users.
