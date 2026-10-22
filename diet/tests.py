from importlib import import_module

from cryptography.fernet import Fernet
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse

from .crypto import is_token
from .models import User

KEY = Fernet.generate_key().decode()
OTHER_KEY = Fernet.generate_key().decode()
GEMINI_KEY = "AIzaSyTestKey1234567890"
PASSWORD = "Strong-pass-42"


@override_settings(FERNET_KEY=KEY, DEBUG=False)
class ApiKeyEncryptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="roman", password=PASSWORD)
        self.client.force_login(self.user)

    def test_roundtrip(self):
        self.user.set_api_key(GEMINI_KEY)
        self.assertTrue(is_token(self.user.apiKey))
        self.assertEqual(self.user.get_api_key(), GEMINI_KEY)

    def test_settings_resave_keeps_key(self):
        self.user.set_api_key(GEMINI_KEY)
        self.user.save()
        page = self.client.get(reverse("settings")).content.decode()
        self.assertIn(GEMINI_KEY, page)
        self.assertNotIn(self.user.apiKey, page)
        self.client.post(reverse("settings"), {"diet_description": "кето", "diet_api_key": GEMINI_KEY})
        self.user.refresh_from_db()
        self.assertEqual(self.user.get_api_key(), GEMINI_KEY)

    def test_legacy_plaintext_is_returned(self):
        self.user.apiKey = GEMINI_KEY
        self.assertEqual(self.user.get_api_key(), GEMINI_KEY)

    def test_wrong_key_gives_empty(self):
        self.user.set_api_key(GEMINI_KEY)
        with override_settings(FERNET_KEY=OTHER_KEY):
            self.assertEqual(self.user.get_api_key(), "")

    @override_settings(FERNET_KEY=None)
    def test_missing_key_in_prod_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            self.user.set_api_key(GEMINI_KEY)

    @override_settings(FERNET_KEY="not-a-key")
    def test_invalid_key_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            self.user.set_api_key(GEMINI_KEY)

    def test_migration_encrypts_plaintext(self):
        User.objects.filter(pk=self.user.pk).update(apiKey=GEMINI_KEY)
        migration = import_module("diet.migrations.0002_encrypt_api_keys")
        migration.encrypt_plaintext_keys(apps, None)
        migration.encrypt_plaintext_keys(apps, None)  # повторный запуск не шифрует дважды
        self.user.refresh_from_db()
        self.assertTrue(is_token(self.user.apiKey))
        self.assertEqual(self.user.get_api_key(), GEMINI_KEY)


class AuthTests(TestCase):
    def test_legacy_mixed_case_login(self):
        User.objects.create_user(username="Roman", password=PASSWORD)
        self.client.post(reverse("login"), {"username": "Roman", "password": PASSWORD})
        self.assertIn("_auth_user_id", self.client.session)

    def register(self, username, password=PASSWORD, confirmation=None):
        return self.client.post(reverse("register"), {
            "username": username,
            "password": password,
            "confirmation": password if confirmation is None else confirmation,
        })

    def test_register_ok(self):
        self.assertEqual(self.register(" Roman ").status_code, 302)
        self.assertTrue(User.objects.filter(username="roman").exists())

    def test_register_blank_username(self):
        self.assertContains(self.register("   "), "Введите логин")

    def test_register_mismatch(self):
        self.assertContains(self.register("roman", confirmation="other-pass-42"), "Пароли не совпадают")

    def test_register_weak_password(self):
        self.register("roman", password="123")
        self.assertFalse(User.objects.exists())

    def test_register_duplicate_case_insensitive(self):
        User.objects.create_user(username="Roman", password=PASSWORD)
        self.assertContains(self.register("roman"), "уже существует")
