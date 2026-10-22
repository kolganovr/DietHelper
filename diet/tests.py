from importlib import import_module

from cryptography.fernet import Fernet
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse

from unittest.mock import patch

from google.genai import errors

from .crypto import is_token
from .gemini import GeminiError, _classify, normalize_verdict
from .models import Check, User

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

    def test_settings_never_renders_key(self):
        self.user.set_api_key(GEMINI_KEY)
        self.user.save()
        page = self.client.get(reverse("settings")).content.decode()
        self.assertNotIn(GEMINI_KEY, page)
        self.assertNotIn(self.user.apiKey, page)
        self.assertIn(GEMINI_KEY[-4:], page)

    def test_settings_empty_key_field_keeps_key(self):
        self.user.set_api_key(GEMINI_KEY)
        self.user.save()
        self.client.post(reverse("settings"), {"diet_description": "кето", "diet_api_key": ""})
        self.user.refresh_from_db()
        self.assertEqual(self.user.get_api_key(), GEMINI_KEY)
        self.assertEqual(self.user.dietInfo, "кето")

    def test_settings_replace_and_remove_key(self):
        self.client.post(reverse("settings"), {"diet_description": "", "diet_api_key": " NEWKEY "})
        self.user.refresh_from_db()
        self.assertEqual(self.user.get_api_key(), "NEWKEY")
        self.client.post(reverse("settings"), {"diet_description": "", "diet_api_key": "", "remove_key": "1"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.get_api_key(), "")

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

    def register(self, username, password=PASSWORD, confirmation=None, follow=True):
        return self.client.post(reverse("register"), {
            "username": username,
            "password": password,
            "confirmation": password if confirmation is None else confirmation,
        }, follow=follow)

    def test_register_ok(self):
        response = self.register(" Roman ", follow=False)
        self.assertRedirects(response, reverse("settings"), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username="roman").exists())

    def test_register_error_keeps_tab_and_username(self):
        page = self.register("roman", confirmation="other-pass-42").content.decode()
        self.assertIn('value="register" class="visually-hidden" checked', page)
        self.assertIn('value="roman"', page)

    def test_password_errors_in_russian(self):
        self.assertContains(self.register("roman", password="123", confirmation="123"), "Введённый пароль слишком короткий")

    def test_login_error_keeps_username(self):
        response = self.client.post(reverse("login"), {"username": "Ghost", "password": "x"}, follow=True)
        self.assertContains(response, "Неправильный логин или пароль")
        self.assertContains(response, 'value="Ghost"')

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


@override_settings(FERNET_KEY=KEY, DEBUG=False)
class CheckTests(TestCase):
    ANSWER = {"verdict": "Нельзя", "explanation": "Много жира.", "reasons": ["жареное"], "alternatives": ["запечь"]}

    def setUp(self):
        self.user = User.objects.create_user(username="roman", password=PASSWORD, dietInfo="гастрит")
        self.user.set_api_key(GEMINI_KEY)
        self.user.save()
        self.client.force_login(self.user)

    def check(self, product="Шаурма"):
        return self.client.post(reverse("check"), {"product": product}, follow=True)

    def test_verdict_saved_and_shown(self):
        with patch("diet.views.get_verdict", return_value=dict(self.ANSWER)):
            page = self.check().content.decode()
        self.assertIn("verdict--no", page)
        self.assertIn("Чем заменить", page)
        self.assertEqual(Check.objects.get().product, "Шаурма")

    def test_history_survives_reload(self):
        with patch("diet.views.get_verdict", return_value=dict(self.ANSWER)):
            self.check()
        self.assertContains(self.client.get(reverse("home")), "История")

    def test_errors_are_not_verdicts(self):
        self.user.dietInfo = ""
        self.user.save()
        page = self.check().content.decode()
        self.assertIn("error-card", page)
        self.assertNotIn("verdict--", page)
        self.assertIn('value="Шаурма"', page)

    def test_guest_gets_login_prompt(self):
        self.client.logout()
        page = self.check().content.decode()
        self.assertIn("Нужен вход", page)
        self.assertNotIn("verdict--", page)

    def test_bad_key_points_to_settings(self):
        error = GeminiError("key", "Ключ Gemini не подходит", "msg")
        with patch("diet.views.get_verdict", side_effect=error):
            page = self.check().content.decode()
        self.assertIn("Ключ Gemini не подходит", page)
        self.assertIn(reverse("settings"), page)
        self.assertFalse(Check.objects.exists())

    def test_empty_and_long_product(self):
        self.assertContains(self.check("   "), "Введите продукт")
        with patch("diet.views.get_verdict", return_value=dict(self.ANSWER)) as mocked:
            self.check("x" * 500)
        self.assertEqual(len(mocked.call_args.args[0]), 200)

    def test_clear_history(self):
        Check.objects.create(user=self.user, product="a", verdict="Можно")
        self.client.post(reverse("clear_history"))
        self.assertFalse(Check.objects.exists())


class GeminiHelpersTests(TestCase):
    def test_normalize_verdict(self):
        self.assertEqual(normalize_verdict(" можно. "), "Можно")
        self.assertEqual(normalize_verdict("С ОСТОРОЖНОСТЬЮ"), "С осторожностью")
        self.assertIsNone(normalize_verdict("Наверное"))

    def test_classify_errors(self):
        self.assertEqual(_classify(errors.ClientError(400, {"error": {"message": "API key not valid"}})).kind, "key")
        self.assertEqual(_classify(errors.ClientError(429, {"error": {"message": "quota"}})).kind, "quota")
        self.assertEqual(_classify(errors.ServerError(503, {"error": {"message": "overloaded"}})).kind, "unavailable")
