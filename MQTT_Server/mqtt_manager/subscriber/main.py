import os
import json
import time
import paho.mqtt.client as mqtt
import psycopg2

# Lấy thông số cấu hình từ biến môi trường
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "esp32/sensor/data")

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "iot_db")
DB_USER = os.getenv("DB_USER", "iot_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "iot_password")

def get_db_connection():
    while True:
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            print(" [DB] Kết nối PostgreSQL Database thành công!")
            ensure_columns_exist(conn)
            return conn
        except Exception as e:
            print(f" [DB Error] Kết nối thất bại: {e}. Thử lại sau 3 giây...")
            time.sleep(3)

def ensure_columns_exist(conn):
    """Tự động nâng cấp bảng sensor_logs để hỗ trợ các cột điện năng"""
    columns = [
        ("voltage", "NUMERIC(6,2)"),
        ("current", "NUMERIC(6,2)"),
        ("power", "NUMERIC(8,2)"),
        ("energy", "NUMERIC(10,2)"),
        ("power_factor", "NUMERIC(4,2)"),
        ("frequency", "NUMERIC(5,2)")
    ]
    with conn.cursor() as cur:
        for col, col_type in columns:
            cur.execute(f"ALTER TABLE sensor_logs ADD COLUMN IF NOT EXISTS {col} {col_type};")
        conn.commit()

db_conn = get_db_connection()

def save_to_database(data):
    global db_conn
    try:
        if db_conn.closed:
            db_conn = get_db_connection()
            
        device_id = data.get("device_id") or data.get("device", "esp32_unknown")
        voltage = data.get("voltage")
        current = data.get("current")
        power = data.get("power")
        energy = data.get("energy")
        power_factor = data.get("power_factor")
        frequency = data.get("frequency")

        with db_conn.cursor() as cur:
            sql = """
                INSERT INTO sensor_logs 
                (device_id, voltage, current, power, energy, power_factor, frequency) 
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
            cur.execute(sql, (device_id, voltage, current, power, energy, power_factor, frequency))
            db_conn.commit()
            print(f" ⚡ [LƯU THÀNH CÔNG] Device: '{device_id}' | U: {voltage}V | I: {current}A | P: {power}W | E: {energy}Wh")
    except Exception as e:
        print(f" ❌ [DB Save Error] Lỗi ghi dữ liệu: {e}")
        db_conn.rollback()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f" [MQTT] Đã kết nối Broker '{MQTT_BROKER}:{MQTT_PORT}'")
        client.subscribe(MQTT_TOPIC)
        print(f" [MQTT] Đã đăng ký (Subscribe) topic: '{MQTT_TOPIC}'")
    else:
        print(f" [MQTT Error] Kết nối thất bại, mã lỗi: {rc}")

def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode("utf-8")
        print(f"\n📩 [MQTT Message] Nhận dữ liệu từ '{msg.topic}': {payload_str}")
        data = json.loads(payload_str)
        save_to_database(data)
    except Exception as e:
        print(f" ❌ Lỗi xử lý tin nhắn: {e}")

client = mqtt.Client("MQTT_DB_Subscriber")
client.on_connect = on_connect
client.on_message = on_message

while True:
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        break
    except Exception as e:
        print(f" [MQTT Error] Không thể nối Mosquitto: {e}. Thử lại sau 3s...")
        time.sleep(3)

client.loop_forever()
