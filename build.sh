#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
# لا تشغّل makemigrations هنا — الترحيلات تُلتزَم في Git فقط.
# بعد كل نشر يجب تطبيق الترحيلات على قاعدة الإنتاج:
python manage.py migrate --noinput
