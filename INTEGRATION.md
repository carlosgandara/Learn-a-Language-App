# Learning flow and future SaaS integration

The app still runs locally with JSON storage. No Neon database, authentication,
subscription service, or external repository has been changed.

## Learning content and progress

Language vocabulary files map each stable concept ID to an object containing:

* `translation` and `accepted_answers`: canonical text and reviewed alternatives.
* `example`: a populated sentence (`text`) and its English `translation`.
* `part_of_speech`: noun, verb, or adjective.
* `pronunciation`: `null` until a pronunciation transcription is supplied.
* `audio`: a placeholder relative static path, such as
  `audio/vocabulary/es/mesa.mp3`. No audio recordings have been created. Do not
  render a playable audio control until the corresponding file is available.
* `usage_notes`: a list for meaning, region, or formality notes.
* `forms`: a list for reviewed plurals, conjugations, or other word forms.

All 600 current entries have sentence examples and audio paths (200 Spanish,
200 French, 200 Tagalog). All three language files cover exactly the same 200
IDs as `concepts.json`. Translations and accepted answers are preserved.
Pronunciation transcriptions and word forms remain unfilled placeholders;
usage notes are populated for a few ambiguous entries. Examples use short,
beginner-friendly sentence patterns, with existing coffee lesson examples kept.
Daily Dose checks accepted answers with the existing Unicode/case/whitespace
normalization. Shooter and multiple-choice tests display the canonical translation.
Both loaders retain the richer metadata and still accept legacy string entries
for incremental imports. Shared concepts and saved progress IDs remain unchanged.


`data/curriculum.json` explicitly assigns ten concept IDs to each configured
lesson. Café and Restaurant are configured in all three existing languages.
Later lessons keep their teaching content but display a preparation message
until their ten-word sets are selected. Vocabulary order never defines a level.

Lesson completion sets `course[level_id].lesson_done`. Daily Dose requires
three consecutive correct typed recalls for each word. Daily Dose keeps a
server-owned cycle of word IDs and the current position. Each word is answered
once per cycle. Any miss queues that word for mandatory Word Shooter when the
cycle ends; there is no miss threshold or optional support link. The cycle ID
and expected word are checked on each answer, including refreshes and stale tabs.
Three successful shots per missed word finish the support round and automatically
return to Daily Dose, where the missed words are recalled first. Another miss in
that retry cycle queues another required shooter round. Shots never grant typed
recall mastery. Incomplete support blocks Daily Dose answers and tests on the
server. A clean cycle continues with remaining unmastered words, or opens the
learning path once all words are mastered.

Required shooter practice has no life limit or Play Again screen. Incorrect shots
continue the same support round without discarding successful practice. A brief
“Let’s practice what you missed” transition precedes play, followed by a brief
recall message before returning to Daily Dose automatically.

The untimed practice and final exam each contain 10 vocabulary and 10 lesson
questions, with three distinct choices. Existing lessons usually contain three
phrases, so the ten lesson questions intentionally revisit them in both directions.
Final exams require completed practice and 16/20 to unlock the next level.
Only one active attempt is stored per learner/language/level. Starting again
replaces it. Refresh/resume retains the active question's deadline. Timing,
answer keys, scoring, prerequisites, and unlocks are checked on the server.
Answer submission must include the attempt ID and current index; duplicate or
stale answers are rejected. Failed exams show missed items for review and retry.

Existing JSON files and historical completion/mastery are preserved. New course
progress starts separately: an old lesson completion is not a passed final exam.
The existing lesson reset preserves course progress and exam passes.

## Persistence boundary

Word Match (`word_match.py`, `/word-match`) stores recognition history and one
resumable board in `games.word_match`, scoped by the same learner/language store.
Word Shooter remains available alongside Word Match.

Each board has ten distinct concept IDs and twenty shuffled cards. Recent Daily
Dose misses and matching mistakes get first priority, then current-level words.
After two strong consecutive rounds (at most 14 attempts for 10 pairs), one slot
can introduce vocabulary outside the current level; the quota increases every
two strong rounds, up to three slots, without displacing missed words. Unfamiliar
outside words receive a three-second preview before play. A word leaves the
mistake-priority pool after two clean matches unless a new miss is recorded.

The server validates card IDs and pair meanings, keeps matches visible, enforces
the mismatch reveal pause, and rejects stale boards. Refresh resumes the board,
including an unfinished preview. Recognition never changes Daily Dose mastery,
exam prerequisites, or level unlocks. Tests cover selection, mismatches, completed
boards, previews, persistence, and account/language isolation.

`PROGRESS_STORE` implements:

* `load(learner_id, language, default) -> dict`
* `save(learner_id, language, progress) -> None`

The default `JsonProgressStore` uses the original local-user paths, atomic file
replacement, and hashed directory names for other identities. This adapter and
the process lock are for local single-process development. Do not deploy them
as shared production storage across workers.

`LEARNER_ID_RESOLVER` is a trusted server callback, currently returning
`local-user`. When authentication is integrated, resolve the verified account ID
from the starter's `auth.security.authenticated_user()` and reject anonymous
requests. Never accept a learner ID from JSON, a query string, or a client cookie.
All progress, exam attempts and results must be scoped by account and language.

## Verified starter integration points

Reviewed the public repository on 2026-10-24:

* [Starter application factory](https://github.com/carlosgandara/Flask-SaaS-Starter/blob/main/app.py)
  initializes authentication, billing, diagnostics, configuration, and migrations.
* [Database module](https://github.com/carlosgandara/Flask-SaaS-Starter/blob/main/auth/db.py)
  exports SQLAlchemy `SessionLocal`, `engine`, and `Base`; `users.id` is an integer.
* [Authentication/security](https://github.com/carlosgandara/Flask-SaaS-Starter/blob/main/auth/security.py)
  exports `authenticated_user()`, `token_required`, `csrf_token()`, and
  `check_browser_request()`.
* [README](https://github.com/carlosgandara/Flask-SaaS-Starter/blob/main/README.md)
  requires Neon/PostgreSQL for production and explicit migrations. Browser POSTs
  use `X-CSRF-Token` and exact Origin validation. Access-token refresh is part of
  the starter's browser client.

The new flow is a separate `/learn` blueprint in `course.py`. Legacy lesson/menu
routes remain in `app.py`. At integration time, package those legacy routes with
the blueprint under the starter's factory, preserve endpoint names or update
links, and inject its shared database session and authenticated user resolver.
The current module-level Flask app is not yet a drop-in SaaS extension.

Add a versioned migration for a learning-progress table keyed by
`(user_id REFERENCES users(id), language)` with JSONB progress, schema version,
and a revision counter. The JSON payload already includes stable lesson and
concept IDs, course records, active attempts, and result history. Consider
separate attempt/result tables when analytics need them.

Implement a PostgreSQL adapter using transactions and row locking or optimistic
revision checks across each complete load/update/save operation. A last-write-wins
upsert alone can lose answers between workers. Replace the local lock with this
transaction boundary, and return a retryable conflict for concurrent stale writes.
Do not create or alter tables during module import. Import local progress into a
selected account only through an explicit migration, never into every account.

Protect learning routes with the starter's authenticated-session and applicable
membership policies. Reuse its browser request helper for refresh recovery and
CSRF headers on all mutations, including legacy lesson answers and study time.
The standalone clients currently use ordinary same-origin fetch; they do not yet
send the starter's CSRF token. This wiring belongs in the integration step.

## Run and verify

Install Flask and langcodes in your Python environment, then run `python app.py`.
Open `/menu`, choose Café, and follow the learning path.

Run `python -m unittest discover -s tests -v` and
`node tests/test_shooter_controls.cjs`. Tests use isolated in-memory or temporary
progress and never rewrite learner files. Browser checks can use an isolated
preview store rather than the real local-user profile.
