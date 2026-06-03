# Local testing strategy

This document defines the local quality gates for the v2 wiki-polis Flask app.
The checks are intentionally layered: fast checks run before commits, broader
behavior and migration checks run before pushes, and network-dependent audits
stay manual until the project has scheduled CI.

## Goals

- Keep local feedback fast enough that developers actually run it.
- Make schema drift visible before a branch is pushed.
- Ensure every route has an explicit authorization classification.
- Exercise representative endpoint behavior for public, participant, moderator,
  and global-admin access.
- Keep security and quality checks reproducible from committed scripts.

## Check layers

| Layer | Command | Purpose | Hook |
|---|---|---|---|
| Fast static checks | `./scripts/check-v2` | Syntax-level Python checks and committed-secret scan. | pre-commit |
| Behavior tests | `./scripts/test-v2` | Full pytest suite, including migration and endpoint coverage. | pre-push |
| Code audit | `./scripts/audit-code-v2` | Bandit high-severity scan, likely dead-code detection, duplicate-code detection. | pre-push |
| Full local gate | `./scripts/pre-push-v2` | Fast static checks, code audit, and full tests. | pre-push |
| Dependency audit | `cd v2 && uv run pip-audit` | Known-vulnerability scan of locked Python dependencies. | manual |

## Migration coverage

The project uses two database setup paths, and both need coverage:

1. Fresh local databases use `flask --app app init-db`. This path creates the
   current SQLAlchemy schema and stamps Alembic at head.
2. Existing databases use `flask --app app db upgrade`. This path applies the
   incremental Alembic migrations over an older schema.

The migration tests therefore assert both:

- a fresh SQLite database can be initialized and stamped at the current head;
- a legacy SQLite schema can be upgraded through Alembic and gains the expected
  columns.

The smoke assertions include both selected high-risk columns and a metadata
comparison against the SQLAlchemy model columns. The tests also open the migrated
database through the Flask app and perform ORM inserts across the key models.

The selected high-risk columns include:

- `participations.new_stmt_ids`
- `participations.public_username`
- `participations.revealed_at`
- `conversations.closed_at`
- `conversations.paused`
- `arguments.hidden`

## Route coverage

Route authorization is covered in two complementary ways:

- `v2/docs/route_authorization_matrix.md` is the human review document.
- `tests/test_route_authorization_matrix.py` is the executable inventory.

When a route is added, removed, or moved between blueprints, the inventory test
must be updated with the intended policy class. This prevents accidental public
or admin-only routes from appearing without review.

## Endpoint smoke coverage

Endpoint smoke tests use Flask's `test_client` and isolated SQLite databases.
They do not require a running local Flask server or the Polis Docker stack.

The smoke matrix covers representative access paths:

- public pages and health checks;
- unauthenticated redirects for participant pages;
- authenticated participant pages;
- global-admin-only pages;
- conversation-scoped moderator pages;
- proxy and unsafe-method rejection behavior.

Detailed business behavior remains in the focused test modules such as
`test_admin.py`, `test_auth.py`, `test_conversations.py`,
`test_proxy_blueprint.py`, and `test_arguments.py`.

## Static quality checks

The local static gate is deliberately conservative:

- `ruff` catches syntax-level and undefined-name problems across tracked v2
  Python files.
- `detect-secrets` checks for newly introduced committed secrets.
- `bandit` scans tracked v2 Python files for high-severity security findings.
- `vulture` reports likely dead code in tracked v2 application Python files with
  a high confidence threshold.
- `pylint` runs only the duplicate-code checker over tracked v2 application
  Python files.

Dead-code and duplicate-code checks can produce false positives around Flask
routes, template entry points, migrations, and deliberate form-handling
repetition. Keep suppressions narrow and documented when they are needed.

## Installing hooks

Install local Git hooks with:

```bash
./scripts/install-local-hooks
```

This installs both pre-commit and pre-push hooks using the committed
`.pre-commit-config.yaml`.

Run the same checks manually with:

```bash
./scripts/check-v2
./scripts/audit-code-v2
./scripts/test-v2
./scripts/pre-push-v2
```
