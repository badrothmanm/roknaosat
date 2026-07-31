from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0054_property_media_controls"),
    ]

    operations = [
        migrations.AddField(
            model_name="propertyoffer",
            name="video_enabled",
            field=models.BooleanField(default=True, verbose_name="تفعيل الفيديو للزوار"),
        ),
    ]

