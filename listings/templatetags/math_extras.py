"""فلاتر بسيطة للعمليات الحسابية في القوالب."""
from django import template

register = template.Library()


@register.filter
def mul(value, arg):
    """ضرب قيمتين (مثال: {{ a|mul:b }})."""
    try:
        return float(value) * float(arg)
    except (TypeError, ValueError):
        return 0.0
