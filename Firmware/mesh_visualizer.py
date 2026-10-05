"""
Aetheria OS — ESP32 Realtime Mesh Visualizer & Control Server
High-performance WebSocket + ThreadingHTTPServer architecture.
Handles bidirectional communication: T1 (COM8) <-> T2 (COM9) <-> Web UI
"""

import sys
import os
import time
import json
import asyncio
import threading
import queue
import re
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import serial
import websockets

sys.stdout.reconfigure(encoding='utf-8')

# Global State
state = {
    "t1_connected": False,
    "t2_connected": False,
    "t1_mac": "28:84:85:35:0A:24",
    "t2_mac": "28:84:85:35:0B:54",
    "t1_id": "node_85350a24",
    "zone": "living_room",
    "mesh_channel": 11,
    "r1_state": False,
    "r2_state": False,
    "vad_energy": 0,
    "is_streaming_audio": False,
    "audio_chunks": 0,
    "audio_bytes": 0,
    "mqtt_connected": False,
    "last_packet": None
}

clients = set()
ws_loop = None
t2_cmd_queue = queue.Queue()

def open_serial_port(port):
    s = serial.Serial()
    s.port = port
    s.baudrate = 115200
    s.timeout = 0.05
    s.write_timeout = 0.5
    s.dtr = False
    s.rts = False
    s.open()
    return s

def broadcast(msg_dict):
    if not ws_loop or not clients:
        return
    msg_str = json.dumps(msg_dict)
    dead = set()
    for ws in list(clients):
        try:
            asyncio.run_coroutine_threadsafe(ws.send(msg_str), ws_loop)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)

# T1 Worker: COM8
def t1_worker():
    ser = None
    while True:
        try:
            if not ser or not ser.is_open:
                ser = open_serial_port('COM8')
                state["t1_connected"] = True
                broadcast({"type": "status", "t1": True})
                print("✅ [T1_COM8] Connected successfully.", flush=True)

            line = ser.readline().decode('utf-8', errors='replace').strip()
            if line:
                # Energy: Mic Diagnostic: ... Energy=77279
                m_energy = re.search(r'Energy=(\d+)', line)
                if m_energy:
                    val = int(m_energy.group(1))
                    state["vad_energy"] = val
                    broadcast({"type": "energy", "value": val})
                else:
                    # Print interesting lines to stdout
                    print(f"📡 [T1_COM8] {line}", flush=True)

                # Voice Streaming Started
                if "Voice streaming started" in line or "AUDIO_START sent" in line:
                    state["is_streaming_audio"] = True
                    broadcast({"type": "stream_state", "active": True, "dir": "t1_to_t2"})
                    broadcast({"type": "packet", "from": "T1", "to": "T2", "kind": "AUDIO_START", "desc": "🎙️ Wake VAD Trigger"})

                # Voice Streaming Stopped
                m_stop = re.search(r'Voice stream ending.*?chunks=(\d+).*?bytes=(\d+)', line)
                if m_stop:
                    state["is_streaming_audio"] = False
                    chunks = int(m_stop.group(1))
                    bytes_count = int(m_stop.group(2))
                    broadcast({"type": "stream_state", "active": False, "chunks": chunks, "bytes": bytes_count})
                    broadcast({"type": "packet", "from": "T1", "to": "T2", "kind": "AUDIO_END", "desc": f"🛑 Audio End ({chunks} chk)"})

                # Hello sent
                if "HELLO sent" in line:
                    broadcast({"type": "packet", "from": "T1", "to": "T2", "kind": "HELLO", "desc": "📡 Mesh Heartbeat (Unicast)"})

                # Relay State change on T1
                m_relay = re.search(r'RL1: (\w+), RL2: (\w+)', line)
                if m_relay:
                    r1 = (m_relay.group(1).upper() == "ON")
                    r2 = (m_relay.group(2).upper() == "ON")
                    state["r1_state"] = r1
                    state["r2_state"] = r2
                    broadcast({"type": "relay_state", "r1": r1, "r2": r2})

                broadcast({"type": "log", "source": "T1", "text": line})

        except Exception as e:
            if ser:
                try: ser.close()
                except Exception: pass
            ser = None
            state["t1_connected"] = False
            broadcast({"type": "status", "t1": False})
            time.sleep(1.0)

# T2 Worker: COM9 (Read + Write from Queue)
def t2_worker():
    ser = None
    while True:
        try:
            if not ser or not ser.is_open:
                ser = open_serial_port('COM9')
                state["t2_connected"] = True
                broadcast({"type": "status", "t2": True})
                print("✅ [T2_COM9] Connected successfully.", flush=True)

            # Write pending commands
            while not t2_cmd_queue.empty():
                cmd = t2_cmd_queue.get_nowait()
                try:
                    print(f"⚡ [WEB -> T2_COM9] Sending: {cmd.decode().strip()}", flush=True)
                    ser.write(cmd)
                except Exception as ex:
                    print(f"⚠️ [T2_COM9] Command write failed: {ex}", flush=True)

            # Read response lines
            line = ser.readline().decode('utf-8', errors='replace').strip()
            if line:
                print(f"📟 [T2_COM9] {line}", flush=True)

                if "LISTEN_SUCCESS" in line or "Playing sound:" in line:
                    broadcast({"type": "chime", "sound": "LISTEN_SUCCESS"})

                if "Audio stream started by T1" in line:
                    state["is_streaming_audio"] = True
                    broadcast({"type": "stream_state", "active": True, "dir": "t1_to_t2"})

                if "Audio stream ended by T1" in line:
                    state["is_streaming_audio"] = False
                    broadcast({"type": "stream_state", "active": False})

                if "MQTT Connected to Gateway" in line:
                    state["mqtt_connected"] = True
                    broadcast({"type": "mqtt", "connected": True})

                if "Sending Relay CH" in line:
                    m_cmd = re.search(r'CH(\d)=(\d)', line)
                    if m_cmd:
                        ch = int(m_cmd.group(1))
                        st = (int(m_cmd.group(2)) == 1)
                        if ch == 1: state["r1_state"] = st
                        if ch == 2: state["r2_state"] = st
                        broadcast({"type": "relay_state", "r1": state["r1_state"], "r2": state["r2_state"]})
                        broadcast({"type": "packet", "from": "T2", "to": "T1", "kind": f"RELAY_CH{ch}", "desc": f"⚡ Relay CH{ch} -> {'ON' if st else 'OFF'}"})

                if "Daikin AC" in line or "ir daikin" in line:
                    broadcast({"type": "ir", "protocol": "Daikin AC (38kHz)", "desc": "Power ON, 24°C, Cool Mode"})

                if "ir nec" in line or "NEC" in line:
                    broadcast({"type": "ir", "protocol": "NEC Code", "desc": "Addr: 0x1234, Cmd: 0x01"})

                broadcast({"type": "log", "source": "T2", "text": line})

        except Exception as e:
            if ser:
                try: ser.close()
                except Exception: pass
            ser = None
            state["t2_connected"] = False
            broadcast({"type": "status", "t2": False})
            time.sleep(1.0)


# Fast Threading HTTP Server
class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ['/', '/index.html']:
            html_path = os.path.join(os.path.dirname(__file__), 'visualizer_ui.html')
            with open(html_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass

# Bidirectional WebSocket Handler
async def ws_handler(websocket):
    clients.add(websocket)
    # Send snapshot on connect
    await websocket.send(json.dumps({
        "type": "init",
        "state": state
    }))
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                action = data.get("action")
                if action == 'r1_toggle':
                    state["r1_state"] = not state["r1_state"]
                    cmd = f"r1 {'on' if state['r1_state'] else 'off'}\n"
                    t2_cmd_queue.put(cmd.encode())
                elif action == 'r2_toggle':
                    state["r2_state"] = not state["r2_state"]
                    cmd = f"r2 {'on' if state['r2_state'] else 'off'}\n"
                    t2_cmd_queue.put(cmd.encode())
                elif action == 'ir_daikin':
                    t2_cmd_queue.put(b"ir daikin\n")
                elif action == 'ir_nec':
                    t2_cmd_queue.put(b"ir nec\n")
                elif action == 'chime':
                    t2_cmd_queue.put(b"chime\n")
                elif action == 'nodes':
                    t2_cmd_queue.put(b"nodes\n")
            except Exception:
                pass
    finally:
        clients.discard(websocket)

def run_http():
    httpd = ThreadingHTTPServer(('0.0.0.0', 8080), DashboardHandler)
    print("🌐 Dashboard UI served at: http://localhost:8080")
    httpd.serve_forever()

async def run_ws():
    global ws_loop
    ws_loop = asyncio.get_running_loop()
    async with websockets.serve(ws_handler, "0.0.0.0", 8766):
        print("⚡ Realtime WebSocket Live at: ws://localhost:8766")
        await asyncio.Future()

def main():
    print("================================================================")
    print("  🚀 AETHERIA OS — ESP32 LIVE MESH VISUALIZER (T1 & T2)")
    print("================================================================")

    # Start Serial Background Workers
    threading.Thread(target=t1_worker, daemon=True).start()
    threading.Thread(target=t2_worker, daemon=True).start()

    # Start HTTP Server
    threading.Thread(target=run_http, daemon=True).start()

    # Auto open browser
    def auto_open_browser():
        time.sleep(1.0)
        print("🌐 Opening Web Visualizer in browser: http://localhost:8080 ...", flush=True)
        try:
            os.system("start http://localhost:8080")
        except Exception:
            webbrowser.open("http://localhost:8080")

    threading.Thread(target=auto_open_browser, daemon=True).start()


    # Run WebSocket Event Loop
    try:
        asyncio.run(run_ws())
    except KeyboardInterrupt:
        print("\nStopping Visualizer Server...")

if __name__ == '__main__':
    main()
