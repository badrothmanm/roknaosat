import os
import django
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def test_cloudinary_upload():
    try:
        # Create a tiny text file to test storage
        file_name = "test_cloudinary_connection.txt"
        content = b"Cloudinary connection test"
        
        path = default_storage.save(file_name, ContentFile(content))
        url = default_storage.url(path)
        
        print(f"Successfully uploaded: {path}")
        print(f"File URL: {url}")
        
        # Cleanup (optional, but good for testing)
        if input("Do you want to delete the test file from Cloudinary? (y/n): ").lower() == 'y':
            default_storage.delete(path)
            print("Test file deleted.")
            
    except Exception as e:
        print(f"Error connecting to Cloudinary: {e}")

if __name__ == "__main__":
    test_cloudinary_upload()
