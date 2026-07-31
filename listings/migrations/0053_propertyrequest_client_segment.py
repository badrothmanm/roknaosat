# Generated manually for client_segment on PropertyRequest

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0052_crmnotification"),
    ]

    operations = [
        migrations.AddField(
            model_name="propertyrequest",
            name="client_segment",
            field=models.CharField(
                choices=[
                    ("search", "طلب بحث — عادي"),
                    ("potential", "عميل محتمل"),
                    ("interested", "مهتم"),
                    ("special", "طلب خاص"),
                ],
                db_index=True,
                default="search",
                help_text="طلب بحث عادي / عميل محتمل / مهتم / طلب خاص — منفصل عن عروض العقارات المنشورة.",
                max_length=32,
                verbose_name="تصنيف العميل",
            ),
        ),
    ]
