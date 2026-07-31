# PropertyRequest: unified API fields (rooms, furnished, category, conversation_id)
# + normalize legacy free-text source → SOURCE_CHOICES + indexes

from django.db import migrations, models


def normalize_propertyrequest_source(apps, schema_editor):
    PropertyRequest = apps.get_model("listings", "PropertyRequest")
    valid = frozenset({"website", "ai_chat", "whatsapp", "manual"})
    for pr in PropertyRequest.objects.all().iterator(chunk_size=500):
        raw = (pr.source or "").strip().lower()
        if not raw:
            new = "website"
        elif raw in valid:
            new = raw
        else:
            new = "manual"
        if pr.source != new:
            pr.source = new
            pr.save(update_fields=["source"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0056_propertyoffer_status_contacted"),
    ]

    operations = [
        migrations.AddField(
            model_name="propertyrequest",
            name="rooms",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="عدد الغرف"
            ),
        ),
        migrations.AddField(
            model_name="propertyrequest",
            name="furnished",
            field=models.BooleanField(blank=True, null=True, verbose_name="مفروش"),
        ),
        migrations.AddField(
            model_name="propertyrequest",
            name="category",
            field=models.CharField(
                blank=True,
                choices=[("family", "عائلي"), ("single", "فردي")],
                help_text="عائلي / فردي — اختياري.",
                max_length=16,
                null=True,
                verbose_name="تصنيف السكن",
            ),
        ),
        migrations.AddField(
            model_name="propertyrequest",
            name="conversation_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="مثلاً جلسة بوت أو واتساب.",
                max_length=128,
                null=True,
                verbose_name="معرف المحادثة",
            ),
        ),
        migrations.RunPython(normalize_propertyrequest_source, noop_reverse),
        migrations.AlterField(
            model_name="propertyrequest",
            name="source",
            field=models.CharField(
                choices=[
                    ("website", "Website"),
                    ("ai_chat", "AI Chat"),
                    ("whatsapp", "WhatsApp"),
                    ("manual", "Manual"),
                ],
                db_index=True,
                default="website",
                help_text="مصدر إنشاء الطلب.",
                max_length=20,
                verbose_name="المصدر",
            ),
        ),
        migrations.AddIndex(
            model_name="propertyrequest",
            index=models.Index(fields=["property_type"], name="listings_pr_proptype_idx"),
        ),
        migrations.AddIndex(
            model_name="propertyrequest",
            index=models.Index(fields=["district"], name="listings_pr_district_idx"),
        ),
        migrations.AddIndex(
            model_name="propertyrequest",
            index=models.Index(fields=["budget"], name="listings_pr_budget_idx"),
        ),
        migrations.AddIndex(
            model_name="propertyrequest",
            index=models.Index(fields=["source"], name="listings_pr_source_idx"),
        ),
    ]
