from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0053_propertyrequest_client_segment"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="video_enabled",
            field=models.BooleanField(default=True, verbose_name="تفعيل الفيديو للزوار"),
        ),
        migrations.AddField(
            model_name="property",
            name="cover_image_slot",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="اختر رقم الصورة التي تريدها كغلاف (سيتم عرضها أولاً في المعرض).",
                null=True,
                verbose_name="صورة الغلاف (رقم الصورة)",
            ),
        ),
    ]

