from django import template

from listings.utils.staff_permissions import staff_is_co_admin

register = template.Library()


@register.simple_tag
def jodah_is_co_admin(user):
    return staff_is_co_admin(user)
