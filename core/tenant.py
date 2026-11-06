import threading

_thread_locals = threading.local()

def set_current_user(user):
    _thread_locals.user = user

def get_current_user():
    return getattr(_thread_locals, 'user', None)

def clear_current():
    for attr in ('user',):
        if hasattr(_thread_locals, attr):
            delattr(_thread_locals, attr)
