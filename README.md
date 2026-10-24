# Despacio language learning

All language features, content, assets, storage adapters and tests live in
[learning/](learning/README.md). Root app.py is a small standalone launcher.

Run from the repository root:

    python -m pip install -r requirements.txt
    python app.py

Open http://127.0.0.1:5000/menu. Restart an already running server after the package
move. Your local profiles now live in learning/data/progress/local-user/.

Lessons lead to Daily Dose, required Word Shooter support, practice and a final
test. Word Match provides adaptive matching practice. The final requires 16/20.

JSON storage remains the default. Neon-compatible repository adapters and account
integration hooks are prepared but no remote database or SaaS app is connected.
See [integration](learning/docs/INTEGRATION.md) and
[debugging](learning/docs/DEBUGGING.md).

Verification:

    python -m unittest discover -s learning/tests -v
    node learning/tests/test_ui_diagnostics.cjs
    node learning/tests/test_daily_dose_cycle.cjs
    node learning/tests/test_shooter_controls.cjs
