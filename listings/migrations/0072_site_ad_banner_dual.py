# Generated manually for dual listing banners

from django.db import migrations, models


def forwards_migrate_banner(apps, schema_editor):
    SiteAdBanner = apps.get_model("listings", "SiteAdBanner")
    for obj in SiteAdBanner.objects.all():
        old_image = getattr(obj, "image", None)
        if old_image and getattr(old_image, "name", "") and not obj.image_1:
            obj.image_1 = old_image.name
        old_link = getattr(obj, "link_url", "") or ""
        if old_link and not obj.link_url_1:
            obj.link_url_1 = old_link
        old_alt = getattr(obj, "alt_text", "") or ""
        if old_alt and not obj.alt_text_1:
            obj.alt_text_1 = old_alt
        obj.insert_every = 4
        obj.max_banners = 2
        obj.theme_1 = obj.theme_1 or "services"
        obj.theme_2 = obj.theme_2 or "request"
        if not obj.link_url_2:
            obj.link_url_2 = "/request-property/"
        obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0071_general_contact"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteadbanner",
            name="insert_every",
            field=models.PositiveSmallIntegerField(
                default=4,
                help_text="مثال: 4 يعني بعد العرض 4 ثم بعد العرض 8.",
                verbose_name="يظهر كل كم عرض",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="max_banners",
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text="الحد الأقصى لظهور البنر (افتراضياً مرتان).",
                verbose_name="عدد مرات الظهور",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="theme_1",
            field=models.CharField(
                choices=[
                    ("services", "تصميم الخدمات (شعار + تأجير/بيع/إدارة/تطوير)"),
                    ("request", "تصميم اطلب عقارك (دعوة للتواصل)"),
                ],
                default="services",
                help_text="يُستخدم إن لم تُرفع صورة مخصصة للبنر الأول.",
                max_length=20,
                verbose_name="تصميم البنر الأول",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="image_1",
            field=models.ImageField(
                blank=True,
                help_text="اختياري — إن رُفعت تستبدل التصميم الجاهز. مستحسن 1080×540.",
                null=True,
                upload_to="ad_banners/",
                verbose_name="صورة البنر الأول",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="title_1",
            field=models.CharField(
                blank=True,
                default="الركن الأوسط",
                max_length=120,
                verbose_name="عنوان البنر الأول",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="slogan_1",
            field=models.CharField(
                blank=True,
                default="في كل زاوية، فرصة استثمارية.",
                max_length=200,
                verbose_name="شعار البنر الأول",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="link_url_1",
            field=models.CharField(
                blank=True,
                default="",
                help_text="اختياري — رابط كامل أو مسار مثل /contact/",
                max_length=500,
                verbose_name="رابط البنر الأول",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="alt_text_1",
            field=models.CharField(
                blank=True,
                default="الركن الأوسط للعقارات — تأجير · بيع · إدارة أملاك · تطوير عقاري",
                max_length=200,
                verbose_name="النص البديل — البنر الأول",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="theme_2",
            field=models.CharField(
                choices=[
                    ("services", "تصميم الخدمات (شعار + تأجير/بيع/إدارة/تطوير)"),
                    ("request", "تصميم اطلب عقارك (دعوة للتواصل)"),
                ],
                default="request",
                help_text="يُستخدم إن لم تُرفع صورة مخصصة للبنر الثاني.",
                max_length=20,
                verbose_name="تصميم البنر الثاني",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="image_2",
            field=models.ImageField(
                blank=True,
                help_text="اختياري — إن رُفعت تستبدل التصميم الجاهز.",
                null=True,
                upload_to="ad_banners/",
                verbose_name="صورة البنر الثاني",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="title_2",
            field=models.CharField(
                blank=True,
                default="ما لقيت طلبك؟",
                max_length=120,
                verbose_name="عنوان البنر الثاني",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="slogan_2",
            field=models.CharField(
                blank=True,
                default="أرسل مواصفاتك ونبحث لك عن العقار الأنسب.",
                max_length=200,
                verbose_name="شعار البنر الثاني",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="cta_2",
            field=models.CharField(
                blank=True,
                default="اطلب عقاراً الآن",
                max_length=80,
                verbose_name="نص زر البنر الثاني",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="link_url_2",
            field=models.CharField(
                blank=True,
                default="/request-property/",
                help_text="افتراضياً صفحة طلب عقار. يمكن وضع رابط خارجي أو مسار داخلي.",
                max_length=500,
                verbose_name="رابط البنر الثاني",
            ),
        ),
        migrations.AddField(
            model_name="siteadbanner",
            name="alt_text_2",
            field=models.CharField(
                blank=True,
                default="اطلب عقاراً بمواصفاتك — الركن الأوسط للعقارات",
                max_length=200,
                verbose_name="النص البديل — البنر الثاني",
            ),
        ),
        migrations.RunPython(forwards_migrate_banner, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="siteadbanner",
            name="alt_text",
        ),
        migrations.RemoveField(
            model_name="siteadbanner",
            name="image",
        ),
        migrations.RemoveField(
            model_name="siteadbanner",
            name="insert_after",
        ),
        migrations.RemoveField(
            model_name="siteadbanner",
            name="link_url",
        ),
        migrations.AlterField(
            model_name="siteadbanner",
            name="is_enabled",
            field=models.BooleanField(
                default=True,
                help_text="فعّل لإظهار البنرات داخل قائمة العروض العقارية.",
                verbose_name="إظهار البنر",
            ),
        ),
    ]
