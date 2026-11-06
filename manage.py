#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# El puerto se puede cambiar con RUNSERVER_PORT (por ejemplo, la central de prueba en 8260).
RUNSERVER_PORT = os.environ.get('RUNSERVER_PORT', '8250')
RUNSERVER_ADDRPORT = f'0.0.0.0:{RUNSERVER_PORT}'
RUNSERVER_TRUSTED_ORIGINS = f'http://127.0.0.1:{RUNSERVER_PORT},http://localhost:{RUNSERVER_PORT}'


def is_runserver_addrport(arg):
    if arg.startswith('-'):
        return False
    if arg.isdigit():
        return True
    if ':' in arg:
        port = arg.rsplit(':', 1)[-1].strip(']')
        return port.isdigit()
    return False


def normalize_runserver_argv(argv):
    if len(argv) < 2 or argv[1] != 'runserver':
        return argv

    os.environ['ALLOWED_HOSTS'] = '*'
    os.environ.setdefault('CSRF_TRUSTED_ORIGINS', RUNSERVER_TRUSTED_ORIGINS)

    args = [arg for arg in argv[2:] if not is_runserver_addrport(arg)]
    return [argv[0], argv[1], RUNSERVER_ADDRPORT, *args]


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gestion_de_carnicerias.settings')
    sys.argv = normalize_runserver_argv(sys.argv)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
