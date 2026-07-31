from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0062_appointment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="appointment",
            name="client_email",
            field=models.EmailField(blank=True, max_length=254, null=True, verbose_name="البريد الإلكتروني"),
        ),
    ]

