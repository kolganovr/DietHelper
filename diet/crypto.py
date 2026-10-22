from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# Fernet-токены всегда начинаются с версии 0x80 + timestamp, в base64 это "gAAAAA"
TOKEN_PREFIX = "gAAAAA"


@lru_cache(maxsize=None)
def _fernet(key):
    try:
        return Fernet(key.encode('utf-8'))
    except ValueError as e:
        raise ImproperlyConfigured(f"FERNET_KEY is invalid: {e}") from e


def get_fernet():
    """Fernet по FERNET_KEY. Без ключа: None в DEBUG, ошибка в проде."""
    key = getattr(settings, 'FERNET_KEY', None)
    if not key:
        if settings.DEBUG:
            return None
        raise ImproperlyConfigured("FERNET_KEY is not set")
    return _fernet(key)


def is_token(value):
    return bool(value) and value.startswith(TOKEN_PREFIX)


def encrypt(raw):
    f = get_fernet()
    if not raw or f is None:
        return raw
    return f.encrypt(raw.encode('utf-8')).decode('utf-8')


def decrypt(stored):
    """Расшифровать значение из БД. Старый открытый ключ вернуть как есть,
    токен, который не расшифровался (сменили FERNET_KEY), считать пустым."""
    if not is_token(stored):
        return stored
    f = get_fernet()
    if f is None:
        return ""
    try:
        return f.decrypt(stored.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        return ""
