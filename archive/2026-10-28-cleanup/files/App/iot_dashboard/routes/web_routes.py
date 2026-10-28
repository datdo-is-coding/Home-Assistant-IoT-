from flask import Blueprint, send_from_directory
import os
from config import Config

# Blueprint này quản lý việc tải trang Web Flutter
web_bp = Blueprint('web', __name__, static_folder=Config.WEB_BUILD_DIR, static_url_path='')

@web_bp.route('/')
def serve_index():
    return send_from_directory(web_bp.static_folder, 'index.html')

@web_bp.route('/<path:path>')
def serve_static(path):
    file_path = os.path.join(web_bp.static_folder, path)
    if os.path.exists(file_path):
        return send_from_directory(web_bp.static_folder, path)
    return send_from_directory(web_bp.static_folder, 'index.html')
