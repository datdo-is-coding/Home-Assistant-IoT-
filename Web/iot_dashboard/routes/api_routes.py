from flask import Blueprint, jsonify

# Blueprint quản lý riêng tất cả các đường dẫn bắt đầu bằng /api
api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/status')
def get_status():
    return jsonify({
        "status": "online",
        "system": "IoT Dashboard Flask Backend",
        "version": "1.0.0"
    })
