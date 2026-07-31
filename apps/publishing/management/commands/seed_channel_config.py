"""
Seed or update ChannelConfig from built-in provider templates.

Examples:
    python manage.py seed_channel_config --tenant demo-tenant --provider haraj
    python manage.py seed_channel_config --tenant etmam-digital --provider haraj --overwrite
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.publishing.configs.channel_templates import get_channel_template
from apps.publishing.models import ChannelConfig


class Command(BaseCommand):
    help = "إنشاء/تحديث قالب ChannelConfig جاهز لقناة نشر (حراج حالياً)"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="company_key للشركة (مثال: etmam-digital)")
        parser.add_argument("--provider", required=True, help="اسم القناة (مثال: haraj)")
        parser.add_argument("--name", default="default", help="اسم الإعداد (افتراضي: default)")
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="استبدال selectors/settings_json إذا كان الإعداد موجودًا.",
        )
        parser.add_argument(
            "--inactive",
            action="store_true",
            help="إنشاء الإعداد بحالة غير مفعلة.",
        )

    def handle(self, *args, **options):
        tenant = str(options["tenant"]).strip()
        provider = str(options["provider"]).strip().lower()
        name = str(options["name"]).strip() or "default"
        overwrite = bool(options["overwrite"])
        is_active = not bool(options["inactive"])

        if not tenant:
            raise CommandError("--tenant is required.")

        template = get_channel_template(provider)

        obj, created = ChannelConfig.objects.get_or_create(
            company_key=tenant,
            provider=provider,
            name=name,
            defaults={
                "is_active": is_active,
                "selectors": template["selectors"],
                "settings_json": template["settings_json"],
            },
        )

        if not created and overwrite:
            obj.selectors = template["selectors"]
            obj.settings_json = template["settings_json"]
            obj.is_active = is_active
            obj.save(update_fields=["selectors", "settings_json", "is_active", "updated_at"])

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created ChannelConfig: tenant={tenant}, provider={provider}, name={name}, active={is_active}"
                )
            )
            return

        if overwrite:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated ChannelConfig from template: tenant={tenant}, provider={provider}, name={name}"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"ChannelConfig already exists (no overwrite): tenant={tenant}, provider={provider}, name={name}"
                )
            )

