from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time


class RealEstateScraper:

    @staticmethod
    def fetch_jeddah_data():
        options = Options()
        options.add_argument("--headless")  # تشغيل بدون متصفح
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

        try:
            # 🔥 رابط جدة (عدل الرابط إذا عندك رابط مباشر)
            url = "PUT_YOUR_JEDDAH_URL_HERE"
            driver.get(url)

            time.sleep(5)  # ننتظر تحميل البيانات

            cards = driver.find_elements(By.CSS_SELECTOR, "div")  # بنحددها لاحقًا بدقة

            results = []

            for card in cards:
                text = card.text

                if "جدة" in text:
                    results.append(text)

            return results

        finally:
            driver.quit()
