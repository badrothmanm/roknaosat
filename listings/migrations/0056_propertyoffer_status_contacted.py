# إضافة حالة «تم التواصل» منفصلة عن «قيد المراجعة»

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0055_propertyoffer_video_enabled"),
    ]

    operations = [
        migrations.AlterField(
            model_name="propertyoffer",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "جديد"),
                    ("contacted", "تم التواصل"),
                    ("under_review", "قيد المراجعة"),
                    ("approved", "مقبول"),
                    ("rejected", "مرفوض"),
                    ("owner_review", "مراجعة صاحب العقار"),
                    ("published", "تم نشره"),
                ],
                db_index=True,
                default="new",
                max_length=20,
                verbose_name="الحالة",
            ),
        ),
    ]
