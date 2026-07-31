from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0063_alter_appointment_client_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccessprofile",
            name="allow_add_users",
            field=models.BooleanField(
                default=True,
                help_text="إن أُلغيَ التحديد: لا يمكن لهذا الحساب إنشاء مستخدمين جدد من الإدارة.",
                verbose_name="إضافة مستخدمين",
            ),
        ),
        migrations.AddField(
            model_name="useraccessprofile",
            name="allow_change_passwords",
            field=models.BooleanField(
                default=True,
                help_text="إن أُلغيَ التحديد: لا يمكنه تغيير كلمة المرور لنفسه أو لمستخدمين آخرين (يشمل صفحة «تغيير كلمة المرور» في الأدمن).",
                verbose_name="تغيير كلمات المرور",
            ),
        ),
    ]
