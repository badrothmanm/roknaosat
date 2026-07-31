from __future__ import annotations

from datetime import date, time

from django import forms
from django.utils import timezone

from .models import Appointment


def build_appointment_time_choices():
    """
    فترات ثابتة من 4:00 م إلى 10:00 م كل 30 دقيقة.
    """
    slots = []
    hour = 16
    minute = 0
    while hour < 22 or (hour == 22 and minute == 0):
        t = time(hour=hour, minute=minute)
        label = timezone.datetime.combine(date.today(), t).strftime("%I:%M %p")
        label = label.replace("AM", "ص").replace("PM", "م")
        slots.append((t.strftime("%H:%M"), label))
        minute += 30
        if minute >= 60:
            minute = 0
            hour += 1
    return tuple(slots)


APPOINTMENT_TIME_CHOICES = build_appointment_time_choices()
APPOINTMENT_TIME_VALUES = {v for v, _ in APPOINTMENT_TIME_CHOICES}


class AppointmentBookingForm(forms.ModelForm):
    client_email = forms.EmailField(
        label="البريد الإلكتروني",
        required=False,
        widget=forms.EmailInput(
            attrs={"class": "appointment-input", "placeholder": "example@email.com (اختياري)"}
        ),
    )
    booking_time = forms.ChoiceField(
        label="وقت الموعد",
        choices=(("", "اختر الوقت"),) + APPOINTMENT_TIME_CHOICES,
        widget=forms.Select(attrs={"class": "appointment-input"}),
    )
    booking_date = forms.DateField(
        label="تاريخ الموعد",
        widget=forms.DateInput(
            attrs={
                "class": "appointment-input js-flatpickr-date",
                "autocomplete": "off",
                "placeholder": "اختر التاريخ",
            }
        ),
    )

    class Meta:
        model = Appointment
        fields = ("client_name", "client_email", "client_phone", "booking_date", "booking_time")
        widgets = {
            "client_name": forms.TextInput(
                attrs={"class": "appointment-input", "placeholder": "الاسم الكامل"}
            ),
            "client_phone": forms.TextInput(
                attrs={"class": "appointment-input", "placeholder": "05XXXXXXXX"}
            ),
        }

    def clean_booking_date(self):
        booking_date = self.cleaned_data["booking_date"]
        today = timezone.localdate()
        if booking_date < today:
            raise forms.ValidationError("لا يمكن اختيار تاريخ سابق.")
        # Friday = 4 (Mon=0)
        if booking_date.weekday() == 4:
            raise forms.ValidationError("الحجز غير متاح يوم الجمعة.")
        return booking_date

    def clean_booking_time(self):
        value = (self.cleaned_data.get("booking_time") or "").strip()
        if value not in APPOINTMENT_TIME_VALUES:
            raise forms.ValidationError("الرجاء اختيار وقت متاح من القائمة.")
        return value

