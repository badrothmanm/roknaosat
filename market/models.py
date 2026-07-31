from django.db import models


# =====================================================
# 📊 REAL ESTATE INDEX (بيانات مفصلة لكل حي)
# =====================================================

class RealEstateIndex(models.Model):
    PERIOD_CHOICES = [
        ('day', 'اليوم'),
        ('week', 'الأسبوع'),
        ('month', 'الشهر'),
        ('year', 'السنة'),
    ]

    PROPERTY_TYPE_CHOICES = [
        ('land', 'أرض'),
        ('apartment', 'شقة'),
        ('villa', 'فيلا'),
        ('all', 'الكل'),
    ]

    city = models.CharField(max_length=100, db_index=True)
    neighborhood = models.CharField(max_length=255, db_index=True)

    property_type = models.CharField(
        max_length=20,
        choices=PROPERTY_TYPE_CHOICES,
        default='all'
    )

    num_deals = models.IntegerField(default=0)
    total_value_sar = models.FloatField(default=0.0)
    traded_area_sqm = models.FloatField(default=0.0)

    avg_price_per_m2 = models.FloatField(default=0.0)

    date = models.DateField(db_index=True)

    period = models.CharField(
        max_length=10,
        choices=PERIOD_CHOICES,
        default='day'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "مؤشر بورصة عقارية"
        verbose_name_plural = "مؤشرات البورصة العقارية"
        unique_together = (
            'city',
            'neighborhood',
            'date',
            'period',
            'property_type'
        )
        indexes = [
            models.Index(fields=['city', 'date']),
            models.Index(fields=['neighborhood']),
        ]
        ordering = ["-date", "city", "-num_deals"]

    def __str__(self):
        return f"{self.neighborhood} - {self.city} ({self.property_type})"


# =====================================================
# 📈 AREA STATS (من API مباشرة - Trend Ready)
# =====================================================

class AreaStat(models.Model):
    area_name = models.CharField(max_length=255, db_index=True)
    city_name = models.CharField(max_length=255, null=True, blank=True)

    avg_price = models.FloatField(default=0.0)
    min_price = models.FloatField(default=0.0)
    max_price = models.FloatField(default=0.0)

    total_deals = models.IntegerField(default=0)
    total_value = models.FloatField(default=0.0)
    total_area = models.FloatField(default=0.0)
    price_per_m2 = models.FloatField(null=True, blank=True)

    period = models.CharField(max_length=10, default="day")

    # 🔥 مهم: نخليه مؤقتًا يقبل null عشان المايجريشن
    aggregation_date = models.DateTimeField(null=True, blank=True, db_index=True)

    # وقت التخزين
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            'area_name',
            'aggregation_date',
            'period',
        )
        indexes = [
            models.Index(fields=['area_name', 'aggregation_date']),
        ]
        ordering = ["-aggregation_date"]

    def __str__(self):
        if self.aggregation_date:
            return f"{self.area_name} - {self.aggregation_date.date()}"
        return f"{self.area_name} - No Date"


# =====================================================
# 🏡 DISTRICTS (أحياء - Trending)
# =====================================================

class District(models.Model):
    district_code = models.IntegerField(unique=True)
    name = models.CharField(max_length=255, db_index=True)

    city_name = models.CharField(max_length=100)
    city_code = models.IntegerField()

    region_name = models.CharField(max_length=100)

    total_deals = models.IntegerField(default=0)
    total_price = models.FloatField(default=0.0)
    total_area = models.FloatField(default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-total_deals"]

    def __str__(self):
        return f"{self.name} - {self.city_name}"


# =====================================================
# 🤖 MARKET REPORT (AI + Snapshot)
# =====================================================

class MarketDailyReport(models.Model):
    date = models.DateField(db_index=True, unique=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    raw_snapshot = models.JSONField(null=True, blank=True)

    succeeded = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "تقرير يومي للبورصة"
        verbose_name_plural = "التقارير اليومية للبورصة"
        ordering = ["-date", "-generated_at"]

    def __str__(self):
        status = "✔" if self.succeeded else "✖"
        return f"{status} تقرير {self.date}"