"""
نماذج إدارة المستخدمين — حقول صلاحية إضافية تُخزَّن في UserAccessProfile.
"""
from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from listings.models import UserAccessProfile


class JodahUserChangeForm(UserChangeForm):
    allow_add_users = forms.BooleanField(
        label="إضافة مستخدمين",
        required=False,
        help_text="السماح لهذا الحساب بإنشاء مستخدمين جدد من لوحة الإدارة.",
    )
    allow_change_passwords = forms.BooleanField(
        label="تغيير كلمات المرور والصلاحيات",
        required=False,
        help_text="السماح بتغيير كلمة المرور، وصلاحيات المستخدم، والمجموعات، وحالة الموظف/المدير. أزل التحديد لمنع ذلك.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            try:
                prof = self.instance.access_profile
                self.fields["allow_add_users"].initial = prof.allow_add_users
                self.fields["allow_change_passwords"].initial = prof.allow_change_passwords
            except UserAccessProfile.DoesNotExist:
                pass

    def save(self, commit=True):
        # حفظ حقول UserAccessProfile يتم في CustomUserAdmin.save_related بعد نماذج الـ inline
        # حتى لا يُستبدل الحفظ لاحقاً بقيم افتراضية (True) من كائن الملف في الذاكرة.
        return super().save(commit=commit)


class JodahAdminUserCreationForm(AdminUserCreationForm):
    allow_add_users = forms.BooleanField(
        label="إضافة مستخدمين",
        required=False,
        initial=True,
        help_text="السماح لهذا الحساب بإنشاء مستخدمين جدد من لوحة الإدارة.",
    )
    allow_change_passwords = forms.BooleanField(
        label="تغيير كلمات المرور والصلاحيات",
        required=False,
        initial=True,
        help_text="السماح بتغيير كلمة المرور، وصلاحيات المستخدم، والمجموعات، وحالة الموظف/المدير. أزل التحديد لمنع ذلك.",
    )

    def save(self, commit=True):
        return super().save(commit=commit)
