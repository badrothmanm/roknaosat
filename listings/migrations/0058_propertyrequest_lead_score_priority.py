# Lead scoring fields + composite index for duplicate detection

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0057_propertyrequest_unified_api_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="propertyrequest",
            name="score",
            field=models.FloatField(
                default=0.0,
                help_text="0–100 حسب الميزانية، اكتمال البيانات، والحي.",
                verbose_name="درجة الصلاحية (Lead)",
            ),
        ),
        migrations.AddField(
            model_name="propertyrequest",
            name="priority",
            field=models.CharField(
                choices=[
                    ("high", "High"),
                    ("medium", "Medium"),
                    ("low", "Low"),
                ],
                db_index=True,
                default="low",
                max_length=16,
                verbose_name="الأولوية",
            ),
        ),
        migrations.AddIndex(
            model_name="propertyrequest",
            index=models.Index(
                fields=["phone", "property_type", "district", "budget"],
                name="listings_pr_dedup_fp_idx",
            ),
        ),
    ]
