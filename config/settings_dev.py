# =============================================================================
# Settings de DÉVELOPPEMENT LOCAL
# =============================================================================
# Ce fichier surcharge config/settings.py pour utiliser SQLite au lieu de
# PostgreSQL, ce qui permet de développer sans avoir Docker installé.
#
# À utiliser uniquement pour le dev local. Pour l'intégration équipe et la
# soutenance, on basculera sur config/settings.py + PostgreSQL via Docker.
#
# Usage (PowerShell) :
#     $env:DJANGO_SETTINGS_MODULE = "config.settings_dev"
#     python manage.py migrate
#     python manage.py runserver
#
# Usage (Linux/Mac/WSL) :
#     export DJANGO_SETTINGS_MODULE=config.settings_dev
#     python manage.py migrate
#     python manage.py runserver
# =============================================================================

from config.settings import *  # noqa: F401, F403
                               # Ignore les linters : F401 = "import inutilisé", F403 = "wildcard import"
# On remplace UNIQUEMENT la conf base de données.
# Le reste (apps installées, middlewares, AUTH_USER_MODEL...) est hérité.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_dev.sqlite3',
    }
}
