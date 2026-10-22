from django.db import models
from django.contrib.auth.models import AbstractUser

from .crypto import encrypt, decrypt

# Create your models here.

class User(AbstractUser):
    dietInfo = models.TextField(blank=True)
    apiKey = models.CharField(max_length=255, blank=True)

    def set_api_key(self, raw_key):
        self.apiKey = encrypt(raw_key)

    def get_api_key(self):
        return decrypt(self.apiKey)