# SaaS and Neon integration boundary

Everything belonging to the language app is in learning/. The app still uses
JSON by default. No live Neon database, SaaS repository, account, membership
policy or remote data has changed. Database adapters were tested on disposable
SQLite and PostgreSQL JSONB schema compilation, not a live Neon instance.

## One Flask app

Root app.py only calls learning.create_app() and starts standalone development.
The SaaS host keeps its own factory and calls learning.init_learning(app)
alongside authentication and billing initialization.

Views have names such as learning.menu, learning.course.overview and
learning.word_match.page. Existing page URLs remain /menu, /level/..., /learn/...
and /word-match. If the host already owns /, learning leaves it alone; use /menu
as the entry point. Assets are /learning/static/ and templates are namespaced
under templates/learning/. The host should check other URL collisions before
registration. Arbitrary URL prefixes are not yet supported because existing
activity clients use retained root-level answer/study URLs.

## Host configuration

Set these before init_learning(app):

| Configuration | Purpose |
| --- | --- |
| LEARNING_CONTENT_STORE | Concepts, translations, lessons and curriculum |
| LEARNING_PROGRESS_STORE | Learner progress, active attempts and game records |
| LEARNING_LEARNER_ID_RESOLVER | Trusted callback returning the authenticated user ID |
| LEARNING_ACCESS_CHECK | Optional authentication/membership request check |
| LEARNING_MUTATION_CHECK | Optional CSRF/Origin check on unsafe requests |
| LEARNING_AUTH_SCRIPT_URL | Optional host refresh/CSRF browser helper, loaded before activity scripts |

Host registration requires an explicit identity resolver. Only the standalone
factory supplies local-user. None/empty identities return 401 on progress access.
Never take an account ID from request JSON, query parameters or client cookies.
Request hooks return None to continue or return/abort with the host's login,
recovery or access-denied response. Public static assets bypass access checks.
Mutation checks cover all learning writes, including study time and lesson answers.

Reuse the starter's existing engine, Base.metadata, verified authenticated_user(),
CSRF/Origin validation, membership policy and browser refresh client. The package
exposes connection points; those host-specific policies are not enabled here.
init_learning does not install global logging or process hooks on the host.
The standalone factory installs packaged diagnostics; the host keeps its own.

Reviewed starter interfaces:
- [Factory](https://github.com/carlosgandara/Flask-SaaS-Starter/blob/main/app.py)
- [Shared engine and users.id](https://github.com/carlosgandara/Flask-SaaS-Starter/blob/main/auth/db.py)
- [Authentication/security](https://github.com/carlosgandara/Flask-SaaS-Starter/blob/main/auth/security.py)
- [Setup and browser requirements](https://github.com/carlosgandara/Flask-SaaS-Starter/blob/main/README.md)

## Interchangeable repositories

ContentStore defines list_languages(), get_concepts(), get_vocabulary(language),
get_levels(language), and get_curriculum(). JsonContentStore reads learning/data.
SqlAlchemyContentStore returns the same structures from a supplied engine/table.
All stable concept/lesson IDs and rich translation metadata are preserved.

The initial learning_content table stores documents keyed by kind and language:
concepts, curriculum, vocabulary and levels. Payloads use PostgreSQL JSONB. This
keeps the first content migration simple; normalization into individual concept
or lesson tables can happen behind the repository later. Use explicit curriculum
ID order, never JSONB key order. Content caches belong to each Flask app; restart
workers after content changes or clear each app's learning content_cache extension.

ProgressStore defines load(learner_id, language, default) and
save(learner_id, language, progress). JsonProgressStore retains atomic writes,
bounded permission retries and the local process lock. It is for local
single-process development, not shared production file storage.

SqlAlchemyProgressStore uses learning_progress keyed by (user_id, language),
a foreign key to users.id, JSONB progress, and a revision counter. It preserves
course, mastery, test attempts/results, study time and game records. Loads carry
internal _storage_revision metadata. Saves use transactions and update only the
loaded revision. Stale updates and simultaneous first saves raise
StorageConflictError; learning returns 409 so clients reload/resume rather than
overwrite newer work. Revisions advance only after commit. Failed writes roll back.

Adapters accept a host-owned engine and tables. They never create an engine,
connect, change schema or import content during construction. Implementations are
in storage/sqlalchemy_store.py. Root requirements include SQLAlchemy for adapter
tests; learning/requirements-neon.txt lists the optional PostgreSQL driver.
Reuse the starter's driver and configure its engine with hidden SQL parameters.

## Explicit migration steps for later

1. Use a staging database. Call define_tables(host_metadata) to attach definitions
   to metadata that already contains users.id. Add a versioned host migration for
   learning_content and learning_progress. Never run create_all during import.
2. Explicitly import content once with import_content(engine, content_table,
   JsonContentStore(...)). It is atomic and expects an empty content table;
   duplicate imports fail/roll back instead of overwriting existing data.
3. Configure both adapters with the host engine and tables. Resolve verified
   integer user IDs from authentication.
4. If preserving local history, explicitly choose its owning account and import
   each language profile. Never copy local-user progress into every account.
   Files in legacy/ are retained for review, not automatically imported.
5. Wire access, membership, CSRF, browser refresh and shared logging. Test account
   isolation, expired sessions, concurrent saves and free/paid access on staging.

## Existing teaching behavior

Cafe and Restaurant retain explicit ten-word curriculum assignments; later units
still need themed word selections. Each of es/fr/tl covers the same 200 concepts,
with examples and audio placeholders. No audio recordings are generated.
Daily Dose requires three consecutive typed recalls; missed cycles enter required
Word Shooter and then return to recall. Word Match practices recognition without
granting recall mastery. Untimed practice precedes the final test; 16/20 unlocks
the next level. Existing moved learner progress retains its original contents.

## Verification

Run from the repository root:

    python -m unittest discover -s learning/tests -v
    node learning/tests/test_ui_diagnostics.cjs
    node learning/tests/test_daily_dose_cycle.cjs
    node learning/tests/test_shooter_controls.cjs

Tests cover host composition, separate content caches, identity and policy hooks,
repository switching, foreign keys, account/language isolation, revision conflicts,
rollback and missing-schema failures. No live database is used.
