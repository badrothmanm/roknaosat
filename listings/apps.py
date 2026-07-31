from django.apps import AppConfig


class ListingsConfig(AppConfig):
    name = "listings"
    verbose_name = "إدارة العقارات والطلبات"

    def ready(self):
        import listings.signals  # noqa: F401 - connect post_save reverse matching
        import listings.signals_staff_notify  # noqa: F401 - email alerts for CRM events
