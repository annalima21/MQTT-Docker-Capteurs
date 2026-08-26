#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings') # Pour pas écraser -> $env:DJANGO_SETTINGS_MODULE = "config.settings_dev"
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc: # Django pas installer
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv) # éxécute les commande taper dans le shell


if __name__ == '__main__':
    main()
