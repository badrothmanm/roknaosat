"""DRF throttle scopes for listings APIs."""
from rest_framework.throttling import AnonRateThrottle


class PropertyRequestCreateThrottle(AnonRateThrottle):
    """Anonymous IP-based throttle for POST /api/property-requests/."""

    scope = "property_request"
