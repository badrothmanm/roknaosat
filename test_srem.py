import asyncio
from playwright.async_api import async_playwright

async def run_debug():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        page = await browser.new_page()
        
        # إعطاء وقت طويل جداً (60 ثانية)
        page.set_default_navigation_timeout(60000)
        
        print("--- محاولة الدخول الهادئ للموقع ---")
        try:
            # استخدام domcontentloaded لتقليل الانتظار على الملفات الثقيلة
            await page.goto("https://srem.moj.gov.sa/", wait_until="domcontentloaded")
            print("نجاح: تم تحميل محتوى الصفحة الأساسي.")
            
            await page.wait_for_timeout(5000) # انتظر 5 ثواني إضافية يدوياً
            
            # محاولة رؤية أي شيء في الصفحة
            title = await page.title()
            print(f"عنوان الصفحة الحالي: {title}")
            
            table_count = await page.locator("table").count()
            print(f"عدد الجداول المكتشفة: {table_count}")
            
        except Exception as e:
            print(f"فشل الاتصال (Timeout): {e}")
            print("تنبيه: الموقع قد يكون محجوباً عن الروبوتات في شبكتك.")
        
        input("اضغط Enter للإغلاق...")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_debug())
