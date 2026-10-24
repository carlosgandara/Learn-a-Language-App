"""Standalone launcher. SaaS applications register learning.init_learning(app)."""
import os
from learning import create_app

app = create_app()

if __name__ == "__main__":
    from learning.diagnostics import install_process_hooks
    from learning.services.content import LANGUAGES, validate_levels
    install_process_hooks(app)
    with app.app_context():
        for language in LANGUAGES:
            validate_levels(language)
    app.logger.info("application_starting")
    app.run(debug=os.environ.get("APP_DEBUG", "0") == "1")
