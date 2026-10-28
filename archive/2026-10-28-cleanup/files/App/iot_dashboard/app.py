from flask import Flask
from config import Config
from routes.web_routes import web_bp
from routes.api_routes import api_bp

def create_app():
    app = Flask(__name__)
    # Nối file cấu hình Config
    app.config.from_object(Config)

    # Đăng ký các Module (Blueprint)
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    return app

app = create_app()

if __name__ == '__main__':
    print(f"🚀 Server Flask đang chạy tại: http://localhost:{Config.PORT}")
    print(f"📌 Kiểm tra API tại: http://localhost:{Config.PORT}/api/status")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
