import os
import django
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from market.models import RealEstateIndex

today = date.today()
periods = ['day', 'week', 'month', 'year']

print(f"Checking data for {today}:")
for p in periods:
    count = RealEstateIndex.objects.filter(date=today, period=p).count()
    print(f"- {p}: {count} records")

# Check if there's any data at all
total = RealEstateIndex.objects.count()
print(f"\nTotal records in DB: {total}")
if total > 0:
    last = RealEstateIndex.objects.order_by('-date').first()
    print(f"Latest record date: {last.date}")
