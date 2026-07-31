from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Property

class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = 'daily'

    def items(self):
        return ['listings:home', 'listings:contact', 'listings:submit-property', 'listings:request-property', 'listings:privacy', 'listings:terms']

    def location(self, item):
        return reverse(item)

class PropertySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Property.objects.filter(visibility='منشور')

    def lastmod(self, obj):
        return obj.created_at
