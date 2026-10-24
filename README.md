# Despacio language learning

Run `python app.py`, then open http://127.0.0.1:5000/menu.

Each configured level follows lesson → Daily Dose → untimed practice → final
test. After a Daily Dose cycle, missed words automatically enter required Word Shooter
practice, then return to Daily Dose for recall. Pass the final
test with 16/20 to unlock the next level.

See [INTEGRATION.md](INTEGRATION.md) for content assignments, tests, saved-progress
behavior, and the planned Flask SaaS Starter / Neon integration boundary.

Word Match is available from the Games menu at `/word-match`. Match ten translated
words with their ten English meanings. Recent mistakes get priority; current-level
words fill the remaining cards. Strong rounds gradually introduce other words
with a short preview. Matching progress is separate from Daily Dose recall mastery.

Errors include a reference linked to `logs/app.jsonl`. See
[DEBUGGING.md](DEBUGGING.md) for storage checks and traceback lookup. Restart the
running server to load these changes.
