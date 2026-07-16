from django.db import models
from django.contrib.auth.models import AbstractUser
from cryptography.fernet import Fernet
from django.conf import settings

# Create your models here.

class User(AbstractUser):
    dietInfo = models.TextField(blank=True)
    apiKey = models.CharField(max_length=255, blank=True)

    def set_api_key(self, raw_key):
        if raw_key and getattr(settings, 'FERNET_KEY', None):
            f = Fernet(settings.FERNET_KEY.encode('utf-8'))
            self.apiKey = f.encrypt(raw_key.encode('utf-8')).decode('utf-8')
        else:
            self.apiKey = raw_key

    def get_api_key(self):
        if self.apiKey and getattr(settings, 'FERNET_KEY', None):
            try:
                f = Fernet(settings.FERNET_KEY.encode('utf-8'))
                return f.decrypt(self.apiKey.encode('utf-8')).decode('utf-8')
            except Exception:
                return self.apiKey
        return self.apiKey