from django.shortcuts import render

def request_property(request):
    return render(request, "request-property.html")
