from django.db import models
from django.contrib.auth.models import AbstractUser

from .crypto import encrypt, decrypt

# Create your models here.

# Вердикт -> (модификатор CSS, иконка Material Symbols)
VERDICT_STYLES = {
    "Можно": ("ok", "check_circle"),
    "С осторожностью": ("caution", "warning"),
    "Нельзя": ("no", "block"),
}

class User(AbstractUser):
    dietInfo = models.TextField(blank=True)
    apiKey = models.CharField(max_length=255, blank=True)

    def set_api_key(self, raw_key):
        self.apiKey = encrypt(raw_key)

    def get_api_key(self):
        return decrypt(self.apiKey)


class Check(models.Model):
    """Одна проверка продукта, для истории на главной."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="checks")
    product = models.CharField(max_length=200)
    verdict = models.CharField(max_length=32)
    explanation = models.TextField(blank=True)
    reasons = models.JSONField(default=list, blank=True)
    alternatives = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.product}: {self.verdict}"

    @property
    def tone(self):
        return VERDICT_STYLES.get(self.verdict, ("no", "block"))[0]

    @property
    def icon(self):
        return VERDICT_STYLES.get(self.verdict, ("no", "block"))[1]

