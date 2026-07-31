# ... (نفس البداية في ملف app.py) ...

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    # ... (نفس كود التواصل دون تغيير) ...
    return render_template('contact.html')

@app.route('/submit-property')
def submit_property():
    return render_template('submit-property.html')

# 6. واجهة برمجة التطبيقات (API) المعدلة لتشمل حالة السعر
@app.route('/api/offer-property/', methods=['POST'])
def api_offer_property():
    """تسجيل عقار جديد من قبل مالك مع خيار إخفاء السعر"""
    try:
        # استقبال البيانات من الفورم
        data = {
            "action": "offer", # أو الأكشن المناسب لسكربت قوقل لديك
            "key": APPS_SCRIPT_KEY,
            "owner_name": request.form.get('owner_name'),
            "phone": request.form.get('phone'),
            "city": request.form.get('city'),
            "neighborhood": request.form.get('neighborhood'),
            "property_type": request.form.get('property_type'),
            "listing_type": request.form.get('listing_type'),
            "price": request.form.get('price'),
            "area": request.form.get('area'),
            # إضافة حالة إظهار السعر (إذا لم يتم التأشير عليها تكون 0)
            "show_price": 1 if request.form.get('show_price') == 'on' else 0,
            "owner_notes": request.form.get('owner_notes'),
            "images_link": request.form.get('images_link'),
            "google_map": request.form.get('google_map')
        }

        # إرسال البيانات لـ Apps Script
        headers = {'Content-Type': 'application/json'}
        response = requests.post(APPS_SCRIPT_URL, json=data, timeout=15)
        
        if response.ok:
            return jsonify({"status": "success", "message": "تم استلام عرضك بنجاح"})
        else:
            return jsonify({"status": "error", "message": "فشل الإرسال لسيرفر البيانات"}), 500

    except Exception as e:
        app.logger.error(f"Error in offer-property: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ... (بقية الملف كما هو) ...
import os
import logging
import datetime
import requests
from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
from flask_compress import Compress
from flask_cors import CORS
from dotenv import load_dotenv

# 1. تحميل متغيرات البيئة وإعداد التطبيق
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'luxury_jodah_secret_9922')

# تحسينات الأداء والأمان
Compress(app)
CORS(app)

# 2. إعداد سجلات الأخطاء (Logs)
if not os.path.exists('logs'):
    os.mkdir('logs')

logging.basicConfig(
    filename='logs/jodah_app.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]',
    encoding='utf-8'
)

# 3. إعداد Google Apps Script API
APPS_SCRIPT_URL = os.getenv('APPS_SCRIPT_URL')
SUBMISSION_URL = os.getenv('SUBMISSION_URL')
APPS_SCRIPT_KEY = os.getenv('APPS_SCRIPT_KEY')
CRM_URL = os.getenv('CRM_URL', APPS_SCRIPT_URL)
CRM_KEY = os.getenv('CRM_KEY', APPS_SCRIPT_KEY)


# 4. المتغيرات العامة للموقع
@app.context_processor
def inject_global_vars():
    return {
        'company_name': 'شركة جودة المستقبل للتسويق العقاري',
        'license_number': '1200012345',
        'whatsapp_number': '966530460992',
        'location': 'جدة، المملكة العربية السعودية',
        'current_year': datetime.datetime.now().year,
        'apps_script_url': APPS_SCRIPT_URL,
        'apps_script_url': APPS_SCRIPT_URL,
        'apps_script_key': APPS_SCRIPT_KEY,
        'crm_url': CRM_URL,
        'crm_key': CRM_KEY,
        'submission_url': SUBMISSION_URL
    }

# 5. المسارات البرمجية (Routes)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        if request.form.get('website'):
            return redirect(url_for('contact'))
        
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        message = request.form.get('message', '').strip()

        if not name or not phone:
            flash('يرجى تعبئة الاسم ورقم الجوال.', 'error')
            return render_template('contact.html')

        try:
            # إرسال البيانات إلى Apps Script API
            payload = {
                "action": "lead",
                "type": "general",
                "key": APPS_SCRIPT_KEY,
                "listingId": "Contact-Page",
                "title": "General Inquiry",
                "district": "-",
                "price": "-",
                "name": name,
                "phone": phone,
                "message": message,
                "notes": message
            }
            requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
            flash('تم استلام رسالتك بنجاح، سنتواصل معك قريباً.', 'success')
        except Exception as e:
            app.logger.error(f"Failed to log contact form via API: {e}")
            flash('تم استلام رسالتك، وسنتواصل معك قريباً.', 'success')

        return redirect(url_for('contact'))

    return render_template('contact.html')

@app.route('/submit-property')
def submit_property():
    return render_template('submit-property.html')

# 6. واجهة برمجة التطبيقات (API)

@app.route('/api/listings')
def api_listings():
    """جلب قائمة العقارات من Apps Script API"""
    try:
        params = {
            "action": "listings",
            "key": APPS_SCRIPT_KEY
        }
        # جلب البيانات من قوقل سكربت
        response = requests.get(APPS_SCRIPT_URL, params=params, timeout=15)
        response.raise_for_status()
        
        try:
            data = response.json()
            return jsonify(data)
        except (ValueError, json.JSONDecodeError) as json_err:
            app.logger.error(f"Failed to parse JSON from Apps Script. Response was likely HTML. Content: {response.text[:500]}")
            return jsonify({"error": "تعذر تحليل البيانات من السيرفر (تنسيق غير مدعوم)", "details": "Response was not JSON"}), 502
    except Exception as e:
        app.logger.exception("API Listings Error")
        return jsonify({"error": f"حدث خطأ في جلب البيانات من السيرفر: {str(e)}"}), 500

@app.route('/api/lead', methods=['POST'])
def api_lead():
    """تسجيل طلب استفسار جديد عبر Apps Script API"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "لا توجد بيانات مرسلة"}), 400

        # إضافة المفتاح والأكشن للـ Payload
        data['action'] = 'lead'
        data['key'] = APPS_SCRIPT_KEY
        
        # إرسال الطلب لـ Apps Script باستخدام النص الصرف (Text/Plain) لتفادي مشاكل CORS
        import json
        headers = {'Content-Type': 'text/plain;charset=utf-8'}
        response = requests.post(APPS_SCRIPT_URL, data=json.dumps(data), headers=headers, timeout=10)
        response.raise_for_status()
        
        return jsonify({"ok": True, "message": "تم تسجيل الطلب بنجاح"})

    except Exception as e:
        app.logger.exception("Lead API Error")
        return jsonify({"error": f"فشل تسجيل الطلب في السجل: {str(e)}"}), 500

if __name__ == '__main__':
    # تشغيل السيرفر
    app.run(host='0.0.0.0', port=5000, debug=True)