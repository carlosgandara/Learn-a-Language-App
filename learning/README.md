# Learning package

The repository's app.py is a small standalone launcher. A SaaS host calls
`learning.init_learning(app)` on its existing Flask app; no second server is created.

| Location | Responsibility |
| --- | --- |
| `__init__.py` | Factory, blueprint registration, identity and request-policy hooks |
| `routes/menu.py` | Language selection, menu and landing page |
| `routes/lessons.py` | Lesson pages, answers and progression |
| `routes/course.py` | Daily Dose, practice and final tests |
| `routes/word_shooter.py` | Required missed-word support |
| `routes/word_match.py` | Matching boards and flips |
| `routes/study.py` | Study time and daily goals |
| `routes/shortcuts.py` | Existing activity shortcut URLs |
| `services/` | Content, progress, mastery rules and adaptive word selection |
| `storage/` | Contracts, JSON repositories and optional database adapters |
| `data/` | Concepts, translations, lessons, curriculum and local progress |
| `templates/learning/` | Templates namespaced to coexist with host templates |
| `static/` | Scripts, styles and images served at /learning/static/ |
| `tests/` | Feature, repository, package and browser-client checks |
| `diagnostics.py`, `logs/` | Standalone diagnostics and runtime logs |
| `legacy/` | Preserved older JSON files, unused by active features |
| `docs/` | Integration and debugging guides |

Page URLs remain the same; Flask endpoint names begin with learning.
Feature routes read content through repositories, not directly from JSON paths.
See [integration](docs/INTEGRATION.md) and [debugging](docs/DEBUGGING.md).
