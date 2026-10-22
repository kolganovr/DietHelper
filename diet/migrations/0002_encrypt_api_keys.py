from django.db import migrations

from diet.crypto import encrypt, get_fernet, is_token


def encrypt_plaintext_keys(apps, schema_editor):
    # Без FERNET_KEY в DEBUG шифровать нечем, ключи останутся как есть
    if get_fernet() is None:
        return
    User = apps.get_model('diet', 'User')
    for user in User.objects.exclude(apiKey='').only('id', 'apiKey'):
        if not is_token(user.apiKey):
            user.apiKey = encrypt(user.apiKey)
            user.save(update_fields=['apiKey'])


class Migration(migrations.Migration):

    dependencies = [
        ('diet', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(encrypt_plaintext_keys, migrations.RunPython.noop),
    ]
