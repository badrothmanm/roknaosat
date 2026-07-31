import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from listings.models import Property
from listings.x_utils import post_property_to_x

p = Property.objects.first()
if getattr(p, 'image1', None):
    # just in case it fails without a request object mapped
    pass
success, msg = post_property_to_x(p, request=None)
print("Twitter Test:", success, msg)
