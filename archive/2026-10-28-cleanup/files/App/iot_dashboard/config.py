import os

class Config:
    # Đường dẫn tự động tới thư mục build/web của dự án
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    WEB_BUILD_DIR = os.path.join(BASE_DIR, 'build', 'web')
    
    # Cấu hình Flask
    SECRET_KEY = 'iot-dashboard-secret-key'
    DEBUG = True
    PORT = 5000
    HOST = '0.0.0.0'
