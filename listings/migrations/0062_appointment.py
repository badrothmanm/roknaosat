from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0061_smartlinkviewlog"),
    ]

    operations = [
        migrations.CreateModel(
            name="Appointment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("client_name", models.CharField(max_length=255, verbose_name="اسم العميل")),
                ("client_email", models.EmailField(max_length=254, verbose_name="البريد الإلكتروني")),
                ("client_phone", models.CharField(max_length=20, verbose_name="رقم الجوال")),
                ("booking_date", models.DateField(verbose_name="تاريخ الموعد")),
                ("booking_time", models.TimeField(verbose_name="وقت الموعد")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "قيد المراجعة"), ("confirmed", "مؤكد"), ("canceled", "ملغي")],
                        db_index=True,
                        default="pending",
                        max_length=20,
                        verbose_name="حالة الموعد",
                    ),
                ),
                (
                    "cancel_token",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="رمز الإلغاء"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")),
                (
                    "property",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="appointments",
                        to="listings.property",
                        verbose_name="العقار",
                    ),
                ),
            ],
            options={
                "verbose_name": "موعد معاينة",
                "verbose_name_plural": "مواعيد المعاينة",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["booking_date", "booking_time"], name="listings_ap_booking_0471fb_idx"),
                    models.Index(fields=["status"], name="listings_ap_status_96d682_idx"),
                ],
            },
        ),
    ]

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0061_smartlinkviewlog"),
    ]

    operations = [
        migrations.CreateModel(
            name="Appointment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("client_name", models.CharField(max_length=255, verbose_name="اسم العميل")),
                ("client_email", models.EmailField(max_length=254, verbose_name="البريد الإلكتروني")),
                ("client_phone", models.CharField(max_length=20, verbose_name="رقم الجوال")),
                ("booking_date", models.DateField(verbose_name="تاريخ الموعد")),
                ("booking_time", models.TimeField(verbose_name="وقت الموعد")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "قيد المراجعة"), ("confirmed", "مؤكد"), ("canceled", "ملغي")],
                        db_index=True,
                        default="pending",
                        max_length=20,
                        verbose_name="حالة الموعد",
                    ),
                ),
                (
                    "cancel_token",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="رمز الإلغاء"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")),
                (
                    "property",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="appointments",
                        to="listings.property",
                        verbose_name="العقار",
                    ),
                ),
            ],
            options={
                "verbose_name": "موعد معاينة",
                "verbose_name_plural": "مواعيد المعاينة",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["booking_date", "booking_time"], name="listings_ap_booking_0471fb_idx"),
                    models.Index(fields=["status"], name="listings_ap_status_96d682_idx"),
                ],
            },
        ),
    ]

