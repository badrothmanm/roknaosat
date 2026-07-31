from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("listings", "0065_useraccessprofile_verbose_security_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="fastrequest",
            name="assigned_to",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_fast_requests",
                to=settings.AUTH_USER_MODEL,
                verbose_name="مسند إلى",
            ),
        ),
    ]
