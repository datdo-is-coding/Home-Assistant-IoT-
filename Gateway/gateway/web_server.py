"""
DTV Smart Home Gateway — Web Monitor Dashboard
Lightweight, real-time web interface built with standard asyncio HTTP + SSE.
Provides live visual monitoring of ESP32-S3 ↔ Pi4 audio streaming,
node status, relay controls, and event logs.
"""

import asyncio
import json
import logging
import time
from typing import Set, Dict, Any

import config

logger = logging.getLogger("web_server")

HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DTV Smart Home — Live Voice & System Monitor</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(18, 24, 38, 0.85);
      --card-border: rgba(255, 255, 255, 0.08);
      --accent: #00f2fe;
      --accent-glow: rgba(0, 242, 254, 0.35);
      --green: #10b981;
      --orange: #f59e0b;
      --red: #ef4444;
      --purple: #8b5cf6;
      --text: #f3f4f6;
      --text-dim: #9ca3af;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 20px; min-height: 100vh; }
    .container { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }
    
    /* Header */
    header {
      display: flex; justify-content: space-between; align-items: center;
      background: var(--card-bg); border: 1px solid var(--card-border);
      padding: 16px 24px; border-radius: 16px; backdrop-filter: blur(10px);
    }
    .logo { display: flex; align-items: center; gap: 12px; }
    .logo-icon { width: 36px; height: 36px; border-radius: 10px; background: linear-gradient(135deg, #00f2fe, #4facfe); display: flex; align-items: center; justify-content: center; font-size: 20px; }
    .logo-text h1 { font-size: 1.25rem; font-weight: 700; color: #fff; letter-spacing: 0.5px; }
    .logo-text p { font-size: 0.8rem; color: var(--text-dim); }
    .badges { display: flex; gap: 10px; flex-wrap: wrap; }
    .badge { display: flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--card-border); }
    .dot { width: 8px; height: 8px; border-radius: 50%; }
    .dot-green { background: var(--green); box-shadow: 0 0 8px var(--green); }
    .dot-orange { background: var(--orange); box-shadow: 0 0 8px var(--orange); }
    .dot-red { background: var(--red); }
    .dot-pulse { animation: pulse 1.5s infinite; }
    @keyframes pulse { 0% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.3); } 100% { opacity: 1; transform: scale(1); } }

    /* Grid */
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; }
    .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 16px; padding: 20px; backdrop-filter: blur(10px); display: flex; flex-direction: column; gap: 16px; }
    .card-title { font-size: 1rem; font-weight: 600; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.75px; display: flex; align-items: center; gap: 8px; }

    /* Audio Pipeline Section */
    .pipeline { grid-column: 1 / -1; }
    .steps { display: flex; justify-content: space-between; position: relative; margin: 15px 0; gap: 10px; flex-wrap: wrap; }
    .step { flex: 1; min-width: 140px; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--card-border); border-radius: 12px; padding: 14px; text-align: center; transition: all 0.3s ease; }
    .step.active { background: rgba(0, 242, 254, 0.1); border-color: var(--accent); box-shadow: 0 0 20px var(--accent-glow); }
    .step-num { font-size: 0.75rem; color: var(--accent); font-weight: 700; margin-bottom: 4px; }
    .step-name { font-size: 0.9rem; font-weight: 600; }
    .step-sub { font-size: 0.75rem; color: var(--text-dim); margin-top: 4px; }

    /* VU Meter & Waveform */
    .meter-container { background: rgba(0, 0, 0, 0.3); border-radius: 10px; padding: 12px; display: flex; flex-direction: column; gap: 8px; border: 1px solid rgba(255, 255, 255, 0.05); }
    .meter-bar-bg { background: rgba(255, 255, 255, 0.08); height: 16px; border-radius: 8px; overflow: hidden; position: relative; }
    .meter-bar-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #10b981 0%, #f59e0b 70%, #ef4444 100%); transition: width 0.08s ease-out; }
    .meter-labels { display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-dim); }

    /* Text Boxes */
    .bubble { background: rgba(0, 0, 0, 0.25); border-left: 4px solid var(--accent); border-radius: 0 10px 10px 0; padding: 12px 16px; font-size: 0.95rem; line-height: 1.5; }
    .bubble.reply { border-left-color: var(--purple); }
    .bubble-label { font-size: 0.75rem; color: var(--text-dim); margin-bottom: 4px; font-weight: 600; }
    .bubble-text { font-size: 1.05rem; font-weight: 500; color: #fff; }

    /* Relay Switches */
    .relay-item { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--card-border); border-radius: 12px; }
    .relay-info h4 { font-size: 1rem; margin-bottom: 2px; }
    .relay-info p { font-size: 0.8rem; color: var(--text-dim); }
    .btn { padding: 8px 18px; border-radius: 20px; font-weight: 600; font-size: 0.85rem; cursor: pointer; border: none; transition: all 0.2s ease; }
    .btn-on { background: var(--green); color: #fff; box-shadow: 0 0 10px rgba(16, 185, 129, 0.4); }
    .btn-off { background: rgba(255, 255, 255, 0.1); color: var(--text-dim); }
    .btn:hover { transform: translateY(-1px); filter: brightness(1.1); }

    /* Console Logs */
    .log-box { background: #050811; border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 10px; padding: 12px; height: 180px; overflow-y: auto; font-family: monospace; font-size: 0.8rem; display: flex; flex-direction: column; gap: 6px; }
    .log-line { display: flex; gap: 8px; }
    .log-time { color: var(--text-dim); }
    .log-msg { color: #e2e8f0; }
    .log-msg.highlight { color: var(--accent); font-weight: 600; }
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <header>
      <div class="logo">
        <div class="logo-icon">🎙️</div>
        <div class="logo-text">
          <h1>DTV Smart Home — Live Monitor</h1>
          <p>Real-Time Pipeline: ESP32-S3 ⇄ Raspberry Pi 4</p>
        </div>
      </div>
      <div class="badges">
        <div class="badge" id="badge-gw"><span class="dot dot-green"></span>Gateway: Online</div>
        <div class="badge" id="badge-esp"><span class="dot dot-orange dot-pulse"></span>ESP32: Waiting...</div>
        <div class="badge" id="badge-mqtt"><span class="dot dot-green"></span>MQTT: Connected</div>
      </div>
    </header>

    <!-- Full Width: Real-Time Audio Streaming Pipeline -->
    <div class="card pipeline">
      <div class="card-title">🔊 Audio Streaming & AI Voice Pipeline (Real-Time)</div>
      
      <!-- 5-Step Pipeline Indicator -->
      <div class="steps">
        <div class="step" id="step-wakenet">
          <div class="step-num">BƯỚC 1</div>
          <div class="step-name">WakeNet</div>
          <div class="step-sub">Đánh thức "Hi ESP"</div>
        </div>
        <div class="step" id="step-stream">
          <div class="step-num">BƯỚC 2</div>
          <div class="step-name">PCM Stream</div>
          <div class="step-sub">Mic 16kHz ➔ WS</div>
        </div>
        <div class="step" id="step-asr">
          <div class="step-num">BƯỚC 3</div>
          <div class="step-name">Sherpa ASR</div>
          <div class="step-sub">Speech-to-Text</div>
        </div>
        <div class="step" id="step-llm">
          <div class="step-num">BƯỚC 4</div>
          <div class="step-name">Qwen LLM</div>
          <div class="step-sub">Hiểu ý định & MQTT</div>
        </div>
        <div class="step" id="step-tts">
          <div class="step-num">BƯỚC 5</div>
          <div class="step-name">TTS Playback</div>
          <div class="step-sub">EdgeTTS ➔ Loa I2S</div>
        </div>
      </div>

      <!-- Real-Time VU Meter -->
      <div class="meter-container">
        <div class="meter-labels">
          <span>Mic Audio Input (RMS Level)</span>
          <span id="meter-val">0 dB (Im lặng)</span>
        </div>
        <div class="meter-bar-bg">
          <div class="meter-bar-fill" id="meter-fill"></div>
        </div>
      </div>

      <!-- Live Transcripts -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
        <div class="bubble">
          <div class="bubble-label">NHẬN DIỆN GIỌNG NÓI (TRANSCRIPT)</div>
          <div class="bubble-text" id="transcript-text">Chưa có lệnh nào. Hãy nói "Hi ESP"...</div>
        </div>
        <div class="bubble reply">
          <div class="bubble-label">PHẢN HỒI CỦA TRỢ LÝ (TTS VOICE REPLY)</div>
          <div class="bubble-text" id="reply-text">—</div>
        </div>
      </div>
    </div>

    <!-- Grid 2 Columns -->
    <div class="grid">
      <!-- Card: Relay Control -->
      <div class="card">
        <div class="card-title">💡 Điều Khiển 2 Kênh Relay (ESP32-S3)</div>
        <div class="relay-item">
          <div class="relay-info">
            <h4>Kênh 1: Đèn ngủ</h4>
            <p>GPIO 4 &bull; Trạng thái: <b id="ch1-status">TẮT</b></p>
          </div>
          <button class="btn btn-off" id="btn-ch1" onclick="toggleRelay('ch1')">BẬT</button>
        </div>
        <div class="relay-item">
          <div class="relay-info">
            <h4>Kênh 2: Đèn trần</h4>
            <p>GPIO 5 &bull; Trạng thái: <b id="ch2-status">TẮT</b></p>
          </div>
          <button class="btn btn-off" id="btn-ch2" onclick="toggleRelay('ch2')">BẬT</button>
        </div>
      </div>

      <!-- Card: ESP32 Node Telemetry -->
      <div class="card">
        <div class="card-title">⚡ Trạng Thái Node & Điện Năng</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
          <div class="step" style="padding: 10px;">
            <div class="step-num">NODE ID</div>
            <div class="step-name" id="node-id">esp32s3_master</div>
          </div>
          <div class="step" style="padding: 10px;">
            <div class="step-num">CÔNG SUẤT (PZEM)</div>
            <div class="step-name" id="power-val">0.0 W</div>
          </div>
          <div class="step" style="padding: 10px;">
            <div class="step-num">ĐIỆN ÁP</div>
            <div class="step-name" id="volt-val">220.0 V</div>
          </div>
          <div class="step" style="padding: 10px;">
            <div class="step-num">DÒNG ĐIỆN</div>
            <div class="step-name" id="curr-val">0.00 A</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Activity Log -->
    <div class="card">
      <div class="card-title">📋 Nhật Ký Sự Kiện Real-Time (Live Logs)</div>
      <div class="log-box" id="log-box">
        <div class="log-line"><span class="log-time">[System]</span><span class="log-msg highlight">Web Monitor initialized. Connecting to event stream...</span></div>
      </div>
    </div>
  </div>

  <script>
    let relayState = { ch1: false, ch2: false };

    function addLog(msg, isHighlight = false) {
      const box = document.getElementById('log-box');
      const now = new Date().toLocaleTimeString();
      const line = document.createElement('div');
      line.className = 'log-line';
      line.innerHTML = `<span class="log-time">[${now}]</span><span class="log-msg ${isHighlight ? 'highlight' : ''}">${msg}</span>`;
      box.appendChild(line);
      box.scrollTop = box.scrollHeight;
    }

    function setActiveStep(stepId) {
      const steps = ['step-wakenet', 'step-stream', 'step-asr', 'step-llm', 'step-tts'];
      steps.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('active', id === stepId);
      });
    }

    function updateMeter(rms) {
      const fill = document.getElementById('meter-fill');
      const label = document.getElementById('meter-val');
      // Normalize RMS (typical speech 1000 - 8000)
      const pct = Math.min(100, Math.max(0, (rms / 6000) * 100));
      fill.style.width = pct + '%';
      label.innerText = rms > 300 ? `Đang nói (${rms} RMS)` : `Im lặng (${rms} RMS)`;
    }

    function updateRelayUI(ch, state) {
      relayState[ch] = state;
      const btn = document.getElementById(`btn-${ch}`);
      const status = document.getElementById(`${ch}-status`);
      if (state) {
        btn.className = 'btn btn-on';
        btn.innerText = 'TẮT';
        status.innerText = 'ĐANG BẬT';
        status.style.color = 'var(--green)';
      } else {
        btn.className = 'btn btn-off';
        btn.innerText = 'BẬT';
        status.innerText = 'TẮT';
        status.style.color = 'var(--text-dim)';
      }
    }

    async function toggleRelay(ch) {
      const targetAction = relayState[ch] ? 'turn_off' : 'turn_on';
      addLog(`Sending manual command: ${targetAction} ${ch}...`);
      try {
        await fetch('/api/relay', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ channel: ch, action: targetAction })
        });
      } catch (e) {
        addLog(`Error toggling relay: ${e}`);
      }
    }

    // Connect Server-Sent Events (SSE)
    function connectSSE() {
      const es = new EventSource('/api/events');
      es.onopen = () => {
        addLog('Connected to Gateway Live Event Stream!', true);
        document.getElementById('badge-gw').innerHTML = '<span class="dot dot-green"></span>Gateway: Online';
      };

      es.addEventListener('audio_state', (e) => {
        const data = JSON.parse(e.data);
        const state = data.state;
        if (state === 'RECORDING') {
          setActiveStep('step-stream');
          addLog('🎙️ ESP32 streaming mic PCM audio...', true);
        } else if (state === 'PROCESSING') {
          setActiveStep('step-asr');
          updateMeter(0);
          addLog('⚡ Processing speech via Sherpa-ONNX & Qwen...');
        } else if (state === 'PLAYING') {
          setActiveStep('step-tts');
          addLog('🔊 Streaming TTS PCM back to ESP32 speaker...');
        } else if (state === 'IDLE') {
          setActiveStep(null);
          updateMeter(0);
        }
      });

      es.addEventListener('audio_meter', (e) => {
        const data = JSON.parse(e.data);
        updateMeter(data.rms);
      });

      es.addEventListener('transcript', (e) => {
        const data = JSON.parse(e.data);
        document.getElementById('transcript-text').innerText = `"${data.text}"`;
        addLog(`🗣️ Transcript: "${data.text}"`, true);
        setActiveStep('step-llm');
      });

      es.addEventListener('command_result', (e) => {
        const data = JSON.parse(e.data);
        if (data.voice_reply) {
          document.getElementById('reply-text').innerText = `"${data.voice_reply}"`;
        }
        if (data.channel && data.action) {
          updateRelayUI(data.channel, data.action === 'turn_on');
        }
        addLog(`🤖 Assistant: "${data.voice_reply}" (Verify: ${data.verify})`);
      });

      es.addEventListener('node_status', (e) => {
        const data = JSON.parse(e.data);
        document.getElementById('badge-esp').innerHTML = '<span class="dot dot-green"></span>ESP32: Online';
        if (data.ch1 !== undefined) updateRelayUI('ch1', data.ch1 === 1);
        if (data.ch2 !== undefined) updateRelayUI('ch2', data.ch2 === 1);
      });

      es.addEventListener('node_telemetry', (e) => {
        const data = JSON.parse(e.data);
        if (data.power !== undefined) document.getElementById('power-val').innerText = `${data.power.toFixed(1)} W`;
        if (data.voltage !== undefined) document.getElementById('volt-val').innerText = `${data.voltage.toFixed(1)} V`;
        if (data.current !== undefined) document.getElementById('curr-val').innerText = `${data.current.toFixed(2)} A`;
      });

      es.onerror = () => {
        document.getElementById('badge-gw').innerHTML = '<span class="dot dot-red"></span>Gateway: Disconnected';
        es.close();
        setTimeout(connectSSE, 3000);
      };
    }

    connectSSE();
  </script>
</body>
</html>
"""


class WebServer:
    """Async HTTP server + SSE for real-time gateway dashboard."""

    def __init__(self, gateway):
        self.gateway = gateway
        self.host = getattr(config, "WEB_HOST", "0.0.0.0")
        self.port = getattr(config, "WEB_PORT", 8000)
        self.server = None
        self.sse_queues: Set[asyncio.Queue] = set()
        self._running = False

    async def start(self):
        """Start the async HTTP server."""
        self._running = True
        try:
            self.server = await asyncio.start_server(
                self._handle_client,
                self.host,
                self.port
            )
            logger.info(f"🌐 Web Monitor Dashboard running at http://{self.host}:{self.port} (open in browser)")
        except Exception as e:
            logger.error(f"Failed to start Web Monitor server on port {self.port}: {e}")

    async def stop(self):
        """Stop the server."""
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Web Monitor server stopped")

    def broadcast_event(self, event_name: str, data: Dict[str, Any]):
        """Broadcast an event to all connected web browser SSE clients."""
        if not self.sse_queues:
            return
        payload = f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for q in list(self.sse_queues):
            try:
                q.put_nowait(payload)
            except Exception:
                pass

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming HTTP requests."""
        try:
            request_line = await reader.readline()
            if not request_line:
                writer.close()
                return

            parts = request_line.decode("utf-8", errors="ignore").split()
            if len(parts) < 2:
                writer.close()
                return

            method = parts[0].upper()
            path = parts[1]

            # Read headers
            headers = {}
            content_length = 0
            while True:
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break
                line_str = line.decode("utf-8", errors="ignore").strip()
                if ":" in line_str:
                    k, v = line_str.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
                    if k.strip().lower() == "content-length":
                        try:
                            content_length = int(v.strip())
                        except ValueError:
                            content_length = 0

            # Route: GET /
            if method == "GET" and (path == "/" or path == "/index.html"):
                body = HTML_PAGE.encode("utf-8")
                resp = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: text/html; charset=utf-8\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"Connection: close\r\n"
                    f"\r\n"
                ).encode("utf-8") + body
                writer.write(resp)
                await writer.drain()
                writer.close()
                return

            # Route: GET /api/events (SSE)
            elif method == "GET" and path.startswith("/api/events"):
                header_resp = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: text/event-stream\r\n"
                    "Cache-Control: no-cache\r\n"
                    "Connection: keep-alive\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    "\r\n"
                ).encode("utf-8")
                writer.write(header_resp)
                await writer.drain()

                client_q = asyncio.Queue(maxsize=100)
                self.sse_queues.add(client_q)
                logger.info(f"Browser client connected to Web Monitor SSE (Total: {len(self.sse_queues)})")

                try:
                    # Send initial node status
                    init_data = {"status": "connected"}
                    writer.write(f"event: init\ndata: {json.dumps(init_data)}\n\n".encode("utf-8"))
                    await writer.drain()

                    while self._running:
                        msg = await client_q.get()
                        writer.write(msg.encode("utf-8"))
                        await writer.drain()
                except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
                    pass
                finally:
                    self.sse_queues.discard(client_q)
                    writer.close()
                return

            # Route: POST /api/relay
            elif method == "POST" and path == "/api/relay":
                body_bytes = b""
                if content_length > 0:
                    body_bytes = await reader.readexactly(content_length)

                try:
                    data = json.loads(body_bytes.decode("utf-8"))
                    channel = data.get("channel", "ch1")
                    action = data.get("action", "toggle")
                    node_id = "esp32s3_master"

                    if self.gateway and hasattr(self.gateway, "mqtt"):
                        asyncio.create_task(
                            self.gateway.mqtt.send_command(node_id, channel, action)
                        )
                        resp_data = {"success": True, "channel": channel, "action": action}
                    else:
                        resp_data = {"success": False, "error": "MQTT not ready"}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}

                resp_body = json.dumps(resp_data).encode("utf-8")
                resp = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(resp_body)}\r\n"
                    f"Access-Control-Allow-Origin: *\r\n"
                    f"Connection: close\r\n"
                    f"\r\n"
                ).encode("utf-8") + resp_body
                writer.write(resp)
                await writer.drain()
                writer.close()
                return

            # 404
            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                writer.close()

        except Exception as e:
            logger.debug(f"HTTP handler exception: {e}")
            try:
                writer.close()
            except Exception:
                pass
