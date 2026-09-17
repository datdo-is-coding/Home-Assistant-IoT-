"""
AETHERIA OS — Spatial Smart Home Operating System v3.0
=====================================================
Multi-page luxury dashboard, Three.js 3D Digital Twin, OTA Firmware Center,
Device Commissioning & Multi-tenant Device Scoping.
Self-contained async HTTP + SSE server.
"""

import asyncio
import json
import logging
import os
import time
import urllib.parse
from typing import Set, Dict, Any, Optional

import config

logger = logging.getLogger("web_server")

# ── AETHERIA OS SINGLE PAGE APPLICATION (SPA) ────────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AETHERIA OS — Spatial Smart Home Intelligence</title>
<!-- Google Fonts: Inter & Outfit -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<!-- Three.js (r128) -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<style>
:root {
  --bg-deep: #07090e;
  --bg-surface: #0e131f;
  --bg-card: rgba(16, 23, 38, 0.75);
  --bg-card-hover: rgba(22, 32, 54, 0.85);
  --border: rgba(255, 255, 255, 0.08);
  --border-glow: rgba(0, 242, 254, 0.35);
  --accent: #00f2fe;
  --accent-secondary: #4facfe;
  --accent-purple: #8b5cf6;
  --text-main: #f8fafc;
  --text-muted: #94a3b8;
  --text-dim: #64748b;
  --green: #10b981;
  --green-glow: rgba(16, 185, 129, 0.3);
  --orange: #f59e0b;
  --red: #ef4444;
  --sidebar-w: 260px;
  --radius: 14px;
}
* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
h1, h2, h3, .brand-title { font-family: 'Outfit', sans-serif; }
body { background: var(--bg-deep); color: var(--text-main); min-height: 100vh; display: flex; overflow-x: hidden; }

/* ── SIDEBAR NAVIGATION ── */
aside.sidebar {
  width: var(--sidebar-w); background: var(--bg-surface); border-right: 1px solid var(--border);
  display: flex; flex-direction: column; position: fixed; top: 0; bottom: 0; left: 0; z-index: 100;
  backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
}
.brand-box {
  padding: 24px 20px; display: flex; align-items: center; gap: 12px;
  border-bottom: 1px solid var(--border);
}
.brand-logo {
  width: 40px; height: 40px; border-radius: 10px;
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-purple) 100%);
  display: flex; align-items: center; justify-content: center; font-size: 20px; box-shadow: 0 0 16px var(--border-glow);
}
.brand-text h1 { font-size: 1.15rem; font-weight: 800; letter-spacing: 1px; color: #fff; line-height: 1.1; }
.brand-badge {
  display: inline-block; font-size: 0.65rem; font-weight: 700; color: var(--accent);
  text-transform: uppercase; letter-spacing: 1.5px; margin-top: 2px;
}

nav.nav-menu { padding: 18px 12px; flex: 1; display: flex; flex-direction: column; gap: 6px; overflow-y: auto; }
.nav-item {
  display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 10px;
  color: var(--text-muted); font-size: 0.88rem; font-weight: 500; cursor: pointer;
  transition: all 0.2s ease; border: 1px solid transparent;
}
.nav-item:hover { color: #fff; background: rgba(255,255,255,0.04); }
.nav-item.active {
  color: #fff; font-weight: 600; background: linear-gradient(90deg, rgba(0,242,254,0.12) 0%, rgba(139,92,246,0.06) 100%);
  border-color: rgba(0,242,254,0.25); box-shadow: 0 4px 20px rgba(0,242,254,0.08);
}
.nav-icon { font-size: 1.1rem; width: 22px; text-align: center; }

.sidebar-footer {
  padding: 16px; border-top: 1px solid var(--border); background: rgba(0,0,0,0.2);
  display: flex; flex-direction: column; gap: 10px;
}
.sys-status { display: flex; align-items: center; justify-content: space-between; font-size: 0.75rem; color: var(--text-dim); }
.status-pill { display: flex; align-items: center; gap: 6px; font-weight: 600; color: var(--green); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 8px var(--green); }
.dot.offline { background: var(--red); box-shadow: 0 0 8px var(--red); }
.user-pill {
  display: flex; align-items: center; justify-content: space-between; background: rgba(255,255,255,0.03);
  padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border); font-size: 0.8rem;
}

/* ── MAIN CONTENT CANVAS ── */
main.main-viewport {
  margin-left: var(--sidebar-w); flex: 1; min-height: 100vh;
  display: flex; flex-direction: column; width: calc(100% - var(--sidebar-w));
}
header.topbar {
  height: 68px; padding: 0 28px; display: flex; align-items: center; justify-content: space-between;
  background: rgba(7, 9, 14, 0.6); backdrop-filter: blur(12px); border-bottom: 1px solid var(--border);
  position: sticky; top: 0; z-index: 90;
}
.top-title { font-size: 1.1rem; font-weight: 700; display: flex; align-items: center; gap: 10px; }
.top-right { display: flex; align-items: center; gap: 16px; }
.time-badge { font-family: monospace; font-size: 0.85rem; color: var(--accent); background: rgba(0,242,254,0.08); padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(0,242,254,0.2); }

.content-container { padding: 24px 28px; flex: 1; max-width: 1400px; margin: 0 auto; width: 100%; }

/* Tab content view switching */
.view-panel { display: none; animation: viewFade 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
.view-panel.active { display: block; }
@keyframes viewFade { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

/* Cards & Layout */
.grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }
.grid-3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }
.grid-4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }

.card {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 20px; position: relative; overflow: hidden; backdrop-filter: blur(16px);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.card:hover { border-color: rgba(255,255,255,0.14); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.card-title { font-size: 0.95rem; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }

/* KPI Stat Badges */
.stat-kpi { font-size: 1.8rem; font-weight: 800; font-family: 'Outfit'; color: #fff; margin-top: 4px; }
.stat-sub { font-size: 0.78rem; color: var(--text-dim); margin-top: 2px; }

/* ── THREE.JS 3D CANVAS STYLING ── */
.three-container {
  width: 100%; height: 380px; position: relative; border-radius: var(--radius);
  overflow: hidden; background: radial-gradient(circle at center, #111a2f 0%, #07090e 100%);
  border: 1px solid var(--border); margin-bottom: 22px;
}
#three-canvas { width: 100%; height: 100%; display: block; }
.three-overlay {
  position: absolute; top: 16px; left: 16px; z-index: 10; pointer-events: none;
}
.three-overlay h3 { font-size: 0.95rem; font-weight: 700; color: #fff; text-shadow: 0 2px 8px rgba(0,0,0,0.8); }
.three-overlay p { font-size: 0.75rem; color: var(--accent); }
.three-controls-hint {
  position: absolute; bottom: 12px; right: 16px; z-index: 10; font-size: 0.72rem; color: var(--text-dim);
  background: rgba(0,0,0,0.5); padding: 4px 8px; border-radius: 6px; pointer-events: none;
}

/* Switches & Buttons */
.switch { position: relative; display: inline-block; width: 44px; height: 24px; flex-shrink: 0; }
.switch input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; inset: 0; background: rgba(255,255,255,0.15); border-radius: 24px; transition: .25s; }
.slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: .25s; }
input:checked + .slider { background: var(--accent); box-shadow: 0 0 12px var(--border-glow); }
input:checked + .slider:before { transform: translateX(20px); background: #07090e; }
input:disabled + .slider { opacity: 0.3; cursor: not-allowed; }

.btn {
  padding: 8px 16px; font-size: 0.82rem; font-weight: 600; border-radius: 8px; border: none;
  cursor: pointer; transition: all 0.15s ease; display: inline-flex; align-items: center; gap: 6px; justify-content: center;
}
.btn-primary { background: linear-gradient(135deg, var(--accent) 0%, var(--accent-secondary) 100%); color: #07090e; }
.btn-primary:hover { filter: brightness(1.1); transform: translateY(-1px); }
.btn-ghost { background: rgba(255,255,255,0.06); color: #fff; border: 1px solid var(--border); }
.btn-ghost:hover { background: rgba(255,255,255,0.1); }
.btn-danger { background: rgba(239,68,68,0.15); color: #fca5a5; border: 1px solid rgba(239,68,68,0.3); }
.btn-danger:hover { background: var(--red); color: #fff; }

.inp, .sel {
  width: 100%; padding: 10px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border);
  border-radius: 8px; color: #fff; font-size: 0.85rem; outline: none; transition: border-color 0.2s;
}
.inp:focus, .sel:focus { border-color: var(--accent); }

/* Room Device Tiles */
.room-section { margin-bottom: 24px; }
.room-header { font-size: 1.05rem; font-weight: 700; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
.device-tile {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 16px; display: flex; flex-direction: column; gap: 12px; transition: transform 0.15s, border-color 0.15s;
}
.device-tile:hover { border-color: rgba(255,255,255,0.18); transform: translateY(-2px); }
.device-tile-top { display: flex; justify-content: space-between; align-items: center; }
.device-name { font-weight: 600; font-size: 0.9rem; }
.device-meta { font-size: 0.75rem; color: var(--text-dim); }

/* OTA Hub Specifics */
.dropzone {
  border: 2px dashed var(--border); border-radius: var(--radius); padding: 32px 20px;
  text-align: center; cursor: pointer; transition: all 0.2s; background: rgba(0,0,0,0.2);
}
.dropzone:hover, .dropzone.dragover { border-color: var(--accent); background: rgba(0,242,254,0.04); }
.progress-bar { width: 100%; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; margin-top: 10px; display: none; }
.progress-fill { width: 0%; height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent-purple)); transition: width 0.3s; }

/* Timeline Log */
.log-box { max-height: 280px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; font-size: 0.8rem; }
.log-item { padding: 6px 10px; border-radius: 6px; background: rgba(255,255,255,0.02); display: flex; gap: 8px; align-items: baseline; }
.log-ts { color: var(--text-dim); font-family: monospace; font-size: 0.72rem; }

/* Toast Notifications */
#toast {
  position: fixed; bottom: 24px; right: 24px; z-index: 9999;
  background: var(--bg-surface); border: 1px solid var(--border-glow);
  padding: 12px 20px; border-radius: 10px; font-size: 0.85rem; font-weight: 500;
  box-shadow: 0 10px 30px rgba(0,0,0,0.5); transform: translateY(100px); opacity: 0;
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s;
}
#toast.show { transform: translateY(0); opacity: 1; }

@media (max-width: 900px) {
  aside.sidebar { width: 72px; }
  .brand-text, .nav-text, .sys-status, .user-pill span { display: none; }
  .brand-box { justify-content: center; padding: 18px 0; }
  .nav-item { justify-content: center; padding: 14px 0; }
  main.main-viewport { margin-left: 72px; width: calc(100% - 72px); }
  .content-container { padding: 16px; }
}
</style>
</head>
<body>

<!-- ── SIDEBAR ── -->
<aside class="sidebar">
  <div class="brand-box">
    <div class="brand-logo">🌌</div>
    <div class="brand-text">
      <h1>AETHERIA</h1>
      <span class="brand-badge">Spatial OS v3</span>
    </div>
  </div>

  <nav class="nav-menu">
    <div class="nav-item active" onclick="switchView('dashboard')">
      <span class="nav-icon">📊</span><span class="nav-text">Tổng Quan 3D</span>
    </div>
    <div class="nav-item" onclick="switchView('devices')">
      <span class="nav-icon">🏠</span><span class="nav-text">Thiết Bị & Phòng</span>
    </div>
    <div class="nav-item" onclick="switchView('provision')">
      <span class="nav-icon">➕</span><span class="nav-text">Gán Thiết Bị Mới</span>
    </div>
    <div class="nav-item" onclick="switchView('ota')">
      <span class="nav-icon">🚀</span><span class="nav-text">Firmware & OTA</span>
    </div>
    <div class="nav-item" onclick="switchView('voice')">
      <span class="nav-icon">🌸</span><span class="nav-text">Trợ Lý Giọng Nói</span>
    </div>
    <div class="nav-item" onclick="switchView('auth')">
      <span class="nav-icon">🔐</span><span class="nav-text">Tài Khoản</span>
    </div>
  </nav>

  <div class="sidebar-footer">
    <div class="sys-status">
      <span>Hệ Thống:</span>
      <span class="status-pill" id="gw-status-pill"><span class="dot" id="gw-dot"></span> Online</span>
    </div>
    <div class="user-pill" id="sidebar-user-pill">
      <span>👤 <b id="user-display-name">Admin</b></span>
      <button class="btn btn-ghost" style="padding:2px 8px;font-size:0.7rem" onclick="switchView('auth')">Đổi</button>
    </div>
  </div>
</aside>

<!-- ── MAIN VIEWPORT ── -->
<main class="main-viewport">
  <header class="topbar">
    <div class="top-title" id="page-title">
      <span>📊 Tổng Quan Không Gian 3D</span>
    </div>
    <div class="top-right">
      <span class="time-badge" id="clock-display">00:00:00</span>
    </div>
  </header>

  <div class="content-container">

    <!-- ── TAB 1: DASHBOARD & 3D DIGITAL TWIN ── -->
    <section id="view-dashboard" class="view-panel active">
      <!-- 3D Three.js Interactive Twin Canvas -->
      <div class="three-container">
        <canvas id="three-canvas"></canvas>
        <div class="three-overlay">
          <h3>Mô Hình Bản Sao Không Gian 3D (Spatial Digital Twin)</h3>
          <p id="three-room-status">Rê chuột hoặc chạm để xoay · Đèn phát sáng theo thời gian thực</p>
        </div>
        <div class="three-controls-hint">Chuột trái: Xoay · Chuột phải: Di chuyển · Cuộn: Thu phóng</div>
      </div>

      <!-- KPI Metrics -->
      <div class="grid-4" style="margin-bottom:22px">
        <div class="card">
          <div class="card-header"><span class="card-title">🔌 Thiết Bị Bật</span><span>⚡</span></div>
          <div class="stat-kpi" id="kpi-active-relays">0</div>
          <div class="stat-sub">Công tắc / Đèn đang chạy</div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">📡 Node Phần Cứng</span><span>🌐</span></div>
          <div class="stat-kpi" id="kpi-nodes-count">0</div>
          <div class="stat-sub" id="kpi-nodes-detail">Đã kết nối an toàn</div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">💡 Công Suất Tiêu Thụ</span><span>⚡</span></div>
          <div class="stat-kpi" id="kpi-total-watts">0.0 W</div>
          <div class="stat-sub">Đo lường thời gian thực</div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">🤖 Trợ Lý Âm Thanh</span><span>🗣️</span></div>
          <div class="stat-kpi" style="font-size:1.3rem" id="kpi-voice-mode">EdgeTTS</div>
          <div class="stat-sub" id="kpi-voice-sub">Hoài My Neural (Ngọt ngào)</div>
        </div>
      </div>

      <!-- Live Activity Stream & Proactive AI Feed -->
      <div class="grid-2">
        <div class="card">
          <div class="card-header">
            <span class="card-title">🎙️ Khẩu Lệnh Gần Nhất (ASR & NLU)</span>
          </div>
          <div id="latest-transcript" style="font-size:1.1rem;font-weight:600;color:var(--accent);margin-bottom:8px">"Chưa có khẩu lệnh..."</div>
          <div id="latest-reply" style="font-size:0.9rem;color:var(--text-muted);font-style:italic">"Dạ em đang lắng nghe anh ạ..."</div>
          <div style="display:flex;gap:8px;margin-top:12px;font-size:0.75rem;color:var(--text-dim)">
            <span>Thời gian xử lý: <b id="kpi-latency" style="color:var(--green)">0.00s</b></span>
            <span>· Động cơ: <b id="kpi-ai-engine">Fast-Path V3</b></span>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <span class="card-title">📜 Nhật Ký Hoạt Động Căn Nhà</span>
          </div>
          <div class="log-box" id="activity-log-box">
            <div class="log-item"><span class="log-ts">SYS</span><span>Hệ thống Aetheria OS đã sẵn sàng phục vụ.</span></div>
          </div>
        </div>
      </div>
    </section>

    <!-- ── TAB 2: THIẾT BỊ & PHÒNG (DEVICE CONTROL) ── -->
    <section id="view-devices" class="view-panel">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;flex-wrap:wrap;gap:12px">
        <div style="display:flex;gap:8px" id="room-filter-bar">
          <button class="btn btn-primary" onclick="filterRoom('all')">Tất Cả</button>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-ghost" onclick="batchToggle('turn_on')">💡 Bật Tất Cả</button>
          <button class="btn btn-ghost" onclick="batchToggle('turn_off')">🌙 Tắt Tất Cả</button>
        </div>
      </div>
      <div id="devices-container">
        <!-- Rendered dynamically -->
      </div>
    </section>

    <!-- ── TAB 3: GÁN THIẾT BỊ MỚI (COMMISSIONING) ── -->
    <section id="view-provision" class="view-panel">
      <div class="card" style="margin-bottom:24px">
        <div class="card-header">
          <span class="card-title">➕ Hàng Đợi Công Tắc Mới (Pending ESP-NOW / MQTT)</span>
        </div>
        <p style="font-size:0.85rem;color:var(--text-muted);margin-bottom:16px">
          Khi cấp nguồn cho công tắc ESP32 mới, thiết bị sẽ tự phát sóng tín hiệu Hello. Bạn chỉ cần chọn phòng và gán tên thiết bị bên dưới để đưa vào nhà:
        </p>
        <div id="pending-nodes-list">
          <div style="color:var(--text-dim);font-size:0.85rem;text-align:center;padding:24px">Không có thiết bị mới nào đang chờ. Hãy bật nguồn công tắc ESP32!</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">✨ Tự Động Phát Hiện Home Assistant Discovery</span>
        </div>
        <p style="font-size:0.85rem;color:var(--text-muted);margin-bottom:16px">
          Các thiết bị Home Assistant gửi gói tin cấu hình discovery qua MQTT sẽ hiển thị tại đây:
        </p>
        <div id="ha-discovery-list">
          <div style="color:var(--text-dim);font-size:0.85rem;text-align:center;padding:24px">Chưa phát hiện thiết bị MQTT Discovery mới.</div>
        </div>
      </div>
    </section>

    <!-- ── TAB 4: FIRMWARE & OTA HUB ── -->
    <section id="view-ota" class="view-panel">
      <div class="grid-2" style="margin-bottom:24px">
        <!-- Upload Binary -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">📦 Tải Lên Firmware Mới (.bin)</span>
          </div>
          <div class="dropzone" id="ota-dropzone" onclick="$('ota-file-input').click()">
            <div style="font-size:2rem;margin-bottom:8px">⬆️</div>
            <div style="font-weight:600;font-size:0.9rem">Kéo thả file firmware .bin vào đây</div>
            <div style="font-size:0.75rem;color:var(--text-dim);margin-top:4px">hoặc bấm để chọn file từ máy tính</div>
            <input type="file" id="ota-file-input" accept=".bin" style="display:none" onchange="handleFileSelect(event)">
          </div>
          <div class="progress-bar" id="ota-progress-bar"><div class="progress-fill" id="ota-progress-fill"></div></div>
          <div id="ota-upload-status" style="margin-top:8px;font-size:0.8rem;color:var(--text-muted)">—</div>
        </div>

        <!-- Flashing Controls -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">🚀 Nạp Firmware Từ Xa (Remote Flash)</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:12px">
            <div>
              <label style="font-size:0.78rem;color:var(--text-dim)">Chọn phiên bản Firmware:</label>
              <select class="sel" id="ota-firmware-select" style="margin-top:4px">
                <option value="">-- Chưa có firmware nào --</option>
              </select>
            </div>
            <div>
              <label style="font-size:0.78rem;color:var(--text-dim)">Chọn thiết bị đích cần nạp:</label>
              <select class="sel" id="ota-node-select" style="margin-top:4px">
                <option value="esp32s3_master">esp32s3_master (ESP32-S3 Master Board)</option>
                <option value="all">Tất cả thiết bị online</option>
              </select>
            </div>
            <button class="btn btn-primary" style="margin-top:6px;padding:12px" onclick="triggerOtaFlash()">
              🚀 Bắt Đầu Nạp Firmware OTA
            </button>
            <div id="ota-flash-status" style="font-size:0.8rem;color:var(--text-muted);font-style:italic">—</div>
          </div>
        </div>
      </div>

      <!-- Stored Firmware Repository -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">📁 Kho Lưu Trữ Bản Nạp Firmware</span>
        </div>
        <div id="firmware-table-container">
          <!-- Rendered dynamically -->
        </div>
      </div>
    </section>

    <!-- ── TAB 5: TRỢ LÝ GIỌNG NÓI & AI ── -->
    <section id="view-voice" class="view-panel">
      <div class="grid-2">
        <!-- Voice Tuner -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">🌸 Âm Sắc Giọng Nói Nữ (Voice & Prosody)</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:14px">
            <div>
              <label style="font-size:0.78rem;color:var(--text-dim)">Động cơ phát âm (TTS Engine):</label>
              <select class="sel" id="tts-provider" style="margin-top:4px" onchange="onProviderChange()">
                <option value="edgetts" selected>☁️ EdgeTTS Cloud (Hoài My Neural — Mặc định ngọt ngào, mượt mà)</option>
                <option value="vieneu">🤖 VieNeu-TTS Local (Offline trên CPU Pi 4, 0 token)</option>
              </select>
            </div>

            <div id="vieneu-voice-box" style="display:none">
              <label style="font-size:0.78rem;color:var(--text-dim)">Giọng đọc VieNeu Local:</label>
              <select class="sel" id="vieneu-voice" style="margin-top:4px">
                <option value="Ái Hân" selected>Ái Hân (Nữ miền Nam dịu dàng, ấm áp)</option>
                <option value="Trúc Ly">Trúc Ly (Nữ miền Bắc tự nhiên, ngọt ngào)</option>
                <option value="Mỹ Duyên">Mỹ Duyên (Nữ miền Bắc đọc truyện)</option>
                <option value="Mai Anh">Mai Anh (Nữ miền Bắc truyền cảm)</option>
                <option value="Adam">Adam (Nam miền Nam tự nhiên)</option>
                <option value="Minh Quân">Minh Quân (Nam miền Bắc tự nhiên)</option>
              </select>
            </div>

            <div id="edgetts-controls">
              <div style="display:flex;justify-content:space-between;font-size:0.75rem;margin-bottom:4px">
                <span>Tốc độ đọc (Rate - thong thả hơn để dịu dàng):</span>
                <span id="rate-val" style="color:var(--accent);font-weight:600">-4%</span>
              </div>
              <input type="range" id="voice-rate" min="-20" max="10" step="1" value="-4" style="width:100%;accent-color:var(--accent)" oninput="$('rate-val').textContent=(this.value>0?'+':'')+this.value+'%'">

              <div style="display:flex;justify-content:space-between;font-size:0.75rem;margin-top:12px;margin-bottom:4px">
                <span>Cao độ (Pitch - nâng nhẹ để giọng trẻ trung, ngọt ngào):</span>
                <span id="pitch-val" style="color:var(--accent);font-weight:600">+2Hz</span>
              </div>
              <input type="range" id="voice-pitch" min="-5" max="10" step="1" value="2" style="width:100%;accent-color:var(--accent)" oninput="$('pitch-val').textContent=(this.value>0?'+':'')+this.value+'Hz'">
            </div>

            <div style="display:flex;gap:8px;margin-top:6px">
              <button class="btn btn-primary" style="flex:1" onclick="saveVoiceSettings()">💾 Lưu Cài Đặt</button>
              <button class="btn btn-ghost" onclick="testSpeaker('chào')">📢 Phát Ra Loa ESP</button>
            </div>

            <button class="btn btn-ghost" style="width:100%" onclick="previewInBrowser(event)">
              🔊 Nghe Thử Trực Tiếp Trên Trình Duyệt
            </button>
            <audio id="browser-audio-player" controls style="display:none;width:100%;margin-top:4px"></audio>
            <div id="voice-save-status" style="font-size:0.8rem;color:var(--green);font-weight:600">—</div>
          </div>
        </div>

        <!-- Proactive & Gemini Persona -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">✨ Giao Tiếp Chủ Động & Trò Chuyện (Lumi)</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:14px">
            <div style="display:flex;align-items:center;justify-content:space-between">
              <div>
                <div style="font-weight:600;font-size:0.9rem">Bật Giao Tiếp Chủ Động</div>
                <div style="font-size:0.75rem;color:var(--text-dim)">Chào buổi sáng, nhắc đi ngủ, canh an toàn bình nóng lạnh</div>
              </div>
              <label class="switch">
                <input type="checkbox" id="proactive-toggle" onchange="toggleProactive(this)">
                <span class="slider"></span>
              </label>
            </div>

            <div>
              <label style="font-size:0.78rem;color:var(--text-dim)">Google Gemini 1.5 Flash API Key:</label>
              <div style="display:flex;gap:6px;margin-top:4px">
                <input type="password" class="inp" id="gemini-key" placeholder="AIzaSy... (để trống dùng Persona Offline)">
                <button class="btn btn-primary" onclick="saveGeminiKey()">Lưu Key</button>
              </div>
              <div id="gemini-status" style="font-size:0.75rem;color:var(--text-dim);margin-top:4px">Đang kiểm tra...</div>
            </div>

            <div>
              <label style="font-size:0.78rem;color:var(--text-dim)">Thử phát các kịch bản mẫu ra loa:</label>
              <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
                <button class="btn btn-ghost" onclick="testSpeaker('hát')">🎵 Hát một bài</button>
                <button class="btn btn-ghost" onclick="testSpeaker('hài')">😂 Chuyện cười</button>
                <button class="btn btn-ghost" onclick="testSpeaker('chào')">👋 Chào hỏi</button>
                <button class="btn btn-danger" onclick="testSpeaker('an_toan')">⚠️ Báo an toàn</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Acoustic Sound System -->
        <div class="card" style="grid-column: span 2">
          <div class="card-header">
            <span class="card-title">🎵 Hệ Thống Âm Thanh Báo Hiệu (Acoustic Soundscapes)</span>
          </div>
          <p style="font-size:0.8rem;color:var(--text-dim);margin-bottom:12px">
            Bộ 5 âm thanh hệ thống đặc quyền được mã hóa PCM 16kHz truyền tải thời gian thực tới loa ESP32:
          </p>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px">
            <div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:10px;padding:12px">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <b style="font-size:0.88rem">🌅 Báo Thức & Buổi Sáng</b>
                <span class="badge" style="background:rgba(245,158,11,0.2);color:var(--orange)">34.8s · morning_sound</span>
              </div>
              <div style="font-size:0.75rem;color:var(--text-dim);margin:6px 0">Phát khi báo thức hoặc chào buổi sáng sớm (06:30 - 08:30).</div>
              <div style="display:flex;gap:6px;margin-top:8px">
                <button class="btn btn-ghost" style="flex:1;font-size:0.75rem" onclick="playWebSound('morning_sound')">🔊 Nghe Thử</button>
                <button class="btn btn-primary" style="flex:1;font-size:0.75rem" onclick="playSpeakerSound('morning_sound')">📡 Phát Ra Loa</button>
              </div>
            </div>

            <div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:10px;padding:12px">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <b style="font-size:0.88rem">🚀 Khởi Động Hệ Thống</b>
                <span class="badge" style="background:rgba(16,185,129,0.2);color:var(--green)">1.9s · bootup_sound</span>
              </div>
              <div style="font-size:0.75rem;color:var(--text-dim);margin:6px 0">Phát khi Gateway và ESP32 khởi động thành công và hệ thống ổn định.</div>
              <div style="display:flex;gap:6px;margin-top:8px">
                <button class="btn btn-ghost" style="flex:1;font-size:0.75rem" onclick="playWebSound('bootup_sound')">🔊 Nghe Thử</button>
                <button class="btn btn-primary" style="flex:1;font-size:0.75rem" onclick="playSpeakerSound('bootup_sound')">📡 Phát Ra Loa</button>
              </div>
            </div>

            <div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:10px;padding:12px">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <b style="font-size:0.88rem">🎙️ Nhận Dạng Thành Công</b>
                <span class="badge" style="background:rgba(0,242,254,0.2);color:var(--accent)">1.1s · listen_success</span>
              </div>
              <div style="font-size:0.75rem;color:var(--text-dim);margin:6px 0">Phát ngay sau khi ASR nhận diện chính xác khẩu lệnh của người dùng.</div>
              <div style="display:flex;gap:6px;margin-top:8px">
                <button class="btn btn-ghost" style="flex:1;font-size:0.75rem" onclick="playWebSound('listen_success')">🔊 Nghe Thử</button>
                <button class="btn btn-primary" style="flex:1;font-size:0.75rem" onclick="playSpeakerSound('listen_success')">📡 Phát Ra Loa</button>
              </div>
            </div>

            <div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:10px;padding:12px">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <b style="font-size:0.88rem">🔔 Cảnh Báo & Thông Báo</b>
                <span class="badge" style="background:rgba(139,92,246,0.2);color:var(--accent-purple)">2.4s · new_noti</span>
              </div>
              <div style="font-size:0.75rem;color:var(--text-dim);margin:6px 0">Phát trước khi Lumi đọc cảnh báo an toàn (bình nóng lạnh lâu, thiết bị mới).</div>
              <div style="display:flex;gap:6px;margin-top:8px">
                <button class="btn btn-ghost" style="flex:1;font-size:0.75rem" onclick="playWebSound('new_noti')">🔊 Nghe Thử</button>
                <button class="btn btn-primary" style="flex:1;font-size:0.75rem" onclick="playSpeakerSound('new_noti')">📡 Phát Ra Loa</button>
              </div>
            </div>

            <div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:10px;padding:12px">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <b style="font-size:0.88rem">⚠️ Lệnh Sai / Chưa Hiểu</b>
                <span class="badge" style="background:rgba(239,68,68,0.2);color:var(--red)">1.3s · wrong_sound</span>
              </div>
              <div style="font-size:0.75rem;color:var(--text-dim);margin:6px 0">Phát khi câu lệnh không rõ, không tìm thấy thiết bị hoặc nhận diện lỗi.</div>
              <div style="display:flex;gap:6px;margin-top:8px">
                <button class="btn btn-ghost" style="flex:1;font-size:0.75rem" onclick="playWebSound('wrong_sound')">🔊 Nghe Thử</button>
                <button class="btn btn-primary" style="flex:1;font-size:0.75rem" onclick="playSpeakerSound('wrong_sound')">📡 Phát Ra Loa</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ── TAB 6: TÀI KHOẢN & BẢO MẬT ── -->
    <section id="view-auth" class="view-panel">
      <div class="grid-2">
        <!-- Current Profile -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">👤 Thông Tin Tài Khoản Đang Đăng Nhập</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:10px">
            <div style="display:flex;justify-content:space-between">
              <span style="color:var(--text-dim)">Tài khoản:</span>
              <b id="prof-username">admin</b>
            </div>
            <div style="display:flex;justify-content:space-between">
              <span style="color:var(--text-dim)">Họ và tên:</span>
              <span id="prof-fullname">Chủ Hộ (Admin)</span>
            </div>
            <div style="display:flex;justify-content:space-between">
              <span style="color:var(--text-dim)">Vai trò:</span>
              <span id="prof-role" style="color:var(--accent);font-weight:700">ADMINISTRATOR</span>
            </div>
            <div style="display:flex;justify-content:space-between">
              <span style="color:var(--text-dim)">Thiết bị được quản lý:</span>
              <span id="prof-device-count" style="color:var(--green)">Toàn bộ hệ thống</span>
            </div>
            <button class="btn btn-danger" style="margin-top:12px" onclick="logout()">Đăng Xuất</button>
          </div>
        </div>

        <!-- Login / Register Form -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">🔑 Đăng Nhập Hoặc Đăng Ký Tài Khoản Khác</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:12px">
            <input type="text" class="inp" id="auth-user" placeholder="Tên đăng nhập (username)">
            <input type="password" class="inp" id="auth-pass" placeholder="Mật khẩu">
            <input type="text" class="inp" id="auth-fullname" placeholder="Họ và tên (chỉ cần khi đăng ký)">
            <div style="display:flex;gap:8px;margin-top:6px">
              <button class="btn btn-primary" style="flex:1" onclick="login()">Đăng Nhập</button>
              <button class="btn btn-ghost" style="flex:1" onclick="register()">Đăng Ký Mới</button>
            </div>
            <div id="auth-status" style="font-size:0.8rem;color:var(--orange)">—</div>
          </div>
        </div>
      </div>
    </section>

  </div>
</main>

<div id="toast">Thông báo</div>

<!-- ── JAVASCRIPT LOGIC & THREE.JS 3D DIGITAL TWIN ── -->
<script>
const $ = id => document.getElementById(id);
let nodes = {}, rooms = {}, pending = {}, discovered = {}, currentFilter = 'all';
let currentUser = { username: 'admin', role: 'admin' };
let currentView = 'dashboard';
let threeScene, threeCamera, threeRenderer, roomMeshes = {}, roomLights = {};

/* ── Toast Helper ── */
function showToast(msg, isSuccess = true) {
  const t = $('toast');
  t.textContent = msg;
  t.style.borderColor = isSuccess ? 'var(--border-glow)' : 'var(--red)';
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3500);
}

/* ── SPA View Switching ── */
function switchView(viewId) {
  currentView = viewId;
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.view-panel').forEach(el => el.classList.remove('active'));

  const navMap = {
    'dashboard': 0, 'devices': 1, 'provision': 2, 'ota': 3, 'voice': 4, 'auth': 5
  };
  const navItems = document.querySelectorAll('.nav-item');
  if (navItems[navMap[viewId]]) navItems[navMap[viewId]].classList.add('active');

  const panel = $('view-' + viewId);
  if (panel) panel.classList.add('active');

  const titles = {
    'dashboard': '📊 Tổng Quan Không Gian 3D',
    'devices': '🏠 Quản Lý Thiết Bị & Công Tắc',
    'provision': '➕ Gán & Tích Hợp Thiết Bị Mới',
    'ota': '🚀 Trung Tâm Cập Nhật Firmware OTA',
    'voice': '🌸 Trợ Lý Giọng Nói & Ngữ Điệu Nữ',
    'auth': '🔐 Tài Khoản & Phân Quyền Thiết Bị'
  };
  $('page-title').innerHTML = `<span>${titles[viewId] || 'Aetheria OS'}</span>`;

  if (viewId === 'ota') loadFirmwares();
  if (viewId === 'dashboard') requestAnimationFrame(animateThree);
}

/* ── THREE.JS 3D SPATIAL DIGITAL TWIN ── */
function initThree() {
  const container = document.querySelector('.three-container');
  const canvas = $('three-canvas');
  if (!container || !canvas || typeof THREE === 'undefined') return;

  const w = container.clientWidth;
  const h = container.clientHeight;

  threeScene = new THREE.Scene();
  threeScene.fog = new THREE.FogExp2(0x07090e, 0.035);

  threeCamera = new THREE.PerspectiveCamera(42, w / h, 0.1, 100);
  threeCamera.position.set(0, 11, 13);
  threeCamera.lookAt(0, 0, 0);

  threeRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  threeRenderer.setSize(w, h);
  threeRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  // Ambient & Grid floor
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
  threeScene.add(ambientLight);

  const grid = new THREE.GridHelper(18, 18, 0x00f2fe, 0x1f293d);
  grid.position.y = -0.01;
  threeScene.add(grid);

  // 4 Architectural Rooms
  const roomDefs = [
    { id: 'phong_khach', name: 'Phòng Khách', x: -3.6, z: -2.8, color: 0x00f2fe },
    { id: 'phong_ngu',   name: 'Phòng Ngủ',   x:  3.6, z: -2.8, color: 0x8b5cf6 },
    { id: 'phong_bep',   name: 'Phòng Bếp',   x: -3.6, z:  2.8, color: 0x10b981 },
    { id: 'ban_cong',    name: 'Ban Công',    x:  3.6, z:  2.8, color: 0xf59e0b }
  ];

  roomDefs.forEach(r => {
    // Glass floor block
    const geo = new THREE.BoxGeometry(6.2, 0.3, 4.8);
    const mat = new THREE.MeshStandardMaterial({
      color: 0x111827, roughness: 0.2, metalness: 0.8,
      transparent: true, opacity: 0.85
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(r.x, 0, r.z);
    threeScene.add(mesh);
    roomMeshes[r.id] = mesh;

    // Glowing dynamic room light
    const pLight = new THREE.PointLight(r.color, 0.2, 8);
    pLight.position.set(r.x, 1.8, r.z);
    threeScene.add(pLight);
    roomLights[r.id] = pLight;

    // Light fixture orb
    const orbGeo = new THREE.SphereGeometry(0.25, 16, 16);
    const orbMat = new THREE.MeshBasicMaterial({ color: 0x334155 });
    const orb = new THREE.Mesh(orbGeo, orbMat);
    orb.position.set(r.x, 1.6, r.z);
    threeScene.add(orb);
    pLight.orb = orb;
  });

  // Mouse interaction controls
  let isDragging = false, prevX = 0, prevY = 0;
  canvas.addEventListener('mousedown', e => { isDragging = true; prevX = e.clientX; prevY = e.clientY; });
  window.addEventListener('mouseup', () => isDragging = false);
  canvas.addEventListener('mousemove', e => {
    if (!isDragging) return;
    const dx = e.clientX - prevX;
    const dy = e.clientY - prevY;
    threeCamera.position.x += dx * 0.02;
    threeCamera.position.y -= dy * 0.02;
    threeCamera.lookAt(0, 0, 0);
    prevX = e.clientX; prevY = e.clientY;
  });
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    threeCamera.position.z += e.deltaY * 0.01;
    threeCamera.position.z = Math.max(7, Math.min(22, threeCamera.position.z));
    threeCamera.lookAt(0, 0, 0);
  });

  window.addEventListener('resize', () => {
    if (!container || !threeCamera || !threeRenderer) return;
    const nw = container.clientWidth, nh = container.clientHeight;
    threeCamera.aspect = nw / nh;
    threeCamera.updateProjectionMatrix();
    threeRenderer.setSize(nw, nh);
  });

  animateThree();
}

function animateThree() {
  if (currentView !== 'dashboard' || !threeRenderer || !threeScene || !threeCamera) return;
  requestAnimationFrame(animateThree);
  threeRenderer.render(threeScene, threeCamera);
}

function updateThreeLights() {
  let anyOn = false;
  for (const [nid, n] of Object.entries(nodes)) {
    const rm = (n.room || 'phong_khach').toLowerCase();
    const st = n.relay_state || [0, 0];
    const isRelayOn = st.some(v => v === 1);
    const light = roomLights[rm];
    if (light) {
      if (isRelayOn) {
        light.intensity = 2.4;
        if (light.orb) light.orb.material.color.setHex(0x00f2fe);
        anyOn = true;
      } else {
        light.intensity = 0.2;
        if (light.orb) light.orb.material.color.setHex(0x334155);
      }
    }
  }
}

/* ── Live Data Loading & SSE ── */
async function loadAll() {
  try {
    const r = await fetch('/api/nodes');
    const d = await r.json();
    nodes = d.nodes || {};
    rooms = d.rooms || {};
    pending = d.pending || {};
    discovered = d.discovered || {};

    renderDashboardKPIs();
    renderDevices();
    renderProvisioning();
    updateThreeLights();
  } catch(e) {
    console.warn('loadAll error:', e);
  }
}

function renderDashboardKPIs() {
  let activeRelays = 0, totalWatts = 0, onlineCount = 0;
  for (const [nid, n] of Object.entries(nodes)) {
    if (n.status === 'online') onlineCount++;
    const st = n.relay_state || [0, 0];
    activeRelays += st.filter(v => v === 1).length;
    if (n.power) totalWatts += parseFloat(n.power);
  }

  $('kpi-active-relays').textContent = activeRelays;
  $('kpi-nodes-count').textContent = Object.keys(nodes).length;
  $('kpi-nodes-detail').textContent = `${onlineCount} đang online · ${Object.keys(nodes).length - onlineCount} offline`;
  $('kpi-total-watts').textContent = totalWatts > 0 ? `${totalWatts.toFixed(1)} W` : '0.0 W';
}

function renderDevices() {
  const box = $('devices-container');
  const rBar = $('room-filter-bar');
  const rmKeys = Object.keys(rooms);

  // Filter bar buttons
  let filterHtml = `<button class="btn ${currentFilter==='all'?'btn-primary':'btn-ghost'}" onclick="filterRoom('all')">Tất Cả (${Object.keys(nodes).length})</button>`;
  rmKeys.forEach(rm => {
    const cnt = (rooms[rm] || []).length;
    filterHtml += `<button class="btn ${currentFilter===rm?'btn-primary':'btn-ghost'}" onclick="filterRoom('${rm}')">${rm} (${cnt})</button>`;
  });
  rBar.innerHTML = filterHtml;

  if (!Object.keys(nodes).length) {
    box.innerHTML = `<div class="card" style="text-align:center;padding:40px;color:var(--text-dim)">
      Chưa có thiết bị nào trong phòng này. Hãy cấp nguồn cho công tắc ESP32 hoặc bấm vào tab <b>Gán Thiết Bị Mới</b>.
    </div>`;
    return;
  }

  let html = '';
  const displayRooms = currentFilter === 'all' ? rmKeys : [currentFilter];

  displayRooms.forEach(rm => {
    const nList = rooms[rm] || [];
    if (!nList.length && currentFilter !== 'all') return;
    html += `<div class="room-section">
      <div class="room-header">🏠 ${rm.toUpperCase()} (${nList.length})</div>
      <div class="grid-3">`;

    nList.forEach(nid => {
      const n = nodes[nid] || {};
      const isOnline = n.status === 'online';
      const rState = n.relay_state || [0, 0];

      html += `<div class="device-tile">
        <div class="device-tile-top">
          <div>
            <div class="device-name">${nid}</div>
            <div class="device-meta">MAC: ${n.mac || 'ESP32'} · RSSI: ${n.rssi != null ? n.rssi + ' dB' : 'N/A'}</div>
          </div>
          <span class="status-pill"><span class="dot ${isOnline?'':'offline'}"></span>${isOnline?'Online':'Offline'}</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px;margin-top:4px">`;

      const channels = n.channels || { ch1: { fullname: nid + '-ch1' }, ch2: { fullname: nid + '-ch2' } };
      Object.entries(channels).forEach(([ch, cinfo]) => {
        const idx = ch === 'ch1' ? 0 : 1;
        const isOn = rState[idx] === 1;
        const fn = cinfo.fullname || `${nid}-${ch}`;
        html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-top:1px solid rgba(255,255,255,0.04)">
          <div>
            <div style="font-size:0.85rem;font-weight:500">${fn}</div>
            <div style="font-size:0.72rem;color:var(--text-dim)">Kênh ${ch.toUpperCase()} ${cinfo.gpio != null ? '· GPIO ' + cinfo.gpio : ''}</div>
          </div>
          <label class="switch">
            <input type="checkbox" onchange="toggleRelay('${nid}', '${ch}', this)" ${isOn?'checked':''} ${!isOnline?'disabled':''}>
            <span class="slider"></span>
          </label>
        </div>`;
      });

      html += `</div></div>`;
    });

    html += `</div></div>`;
  });

  box.innerHTML = html;
}

function filterRoom(rm) {
  currentFilter = rm;
  renderDevices();
}

async function toggleRelay(nodeId, channel, cb) {
  const action = cb.checked ? 'turn_on' : 'turn_off';
  addLog(`⚡ Điều khiển [${nodeId}]: ${channel} → ${action}`);
  try {
    const r = await fetch('/api/relay', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: nodeId, channel, action })
    });
    const j = await r.json();
    if (j.success) {
      showToast(`Đã ${action==='turn_on'?'bật':'tắt'} ${channel} (${nodeId})`);
      setTimeout(loadAll, 400);
    } else {
      showToast('Lỗi: ' + (j.error || 'Thao tác thất bại'), false);
      cb.checked = !cb.checked;
    }
  } catch(e) {
    showToast('Lỗi kết nối tới Gateway', false);
    cb.checked = !cb.checked;
  }
}

async function batchToggle(action) {
  addLog(`⚡ Chạy thao tác đồng loạt: ${action}`);
  for (const [nid, n] of Object.entries(nodes)) {
    if (n.status === 'online') {
      ['ch1', 'ch2'].forEach(ch => {
        fetch('/api/relay', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ node_id: nid, channel: ch, action })
        }).catch(()=>{});
      });
    }
  }
  setTimeout(loadAll, 800);
  showToast(`Đang thực hiện ${action==='turn_on'?'bật':'tắt'} toàn bộ thiết bị`);
}

function renderProvisioning() {
  const pBox = $('pending-nodes-list');
  const pKeys = Object.keys(pending);
  if (!pKeys.length) {
    pBox.innerHTML = '<div style="color:var(--text-dim);font-size:0.85rem;text-align:center;padding:24px">Không có thiết bị mới nào đang chờ. Hãy cấp nguồn cho công tắc ESP32!</div>';
  } else {
    pBox.innerHTML = pKeys.map(mac => {
      const p = pending[mac] || {};
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:12px;background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:10px;margin-bottom:8px;flex-wrap:wrap;gap:12px">
        <div>
          <b style="font-family:monospace;font-size:0.95rem;color:var(--accent)">${mac}</b>
          <div style="font-size:0.75rem;color:var(--text-dim)">IP: ${p.ip||'chưa gán'} · RSSI: ${p.rssi!=null?p.rssi+' dB':'N/A'}</div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <input class="inp" id="prov-room-${mac}" placeholder="Tên phòng (ví dụ: livingroom)" style="width:160px" value="livingroom">
          <select class="sel" id="prov-r1-${mac}" style="width:130px">
            <option value="light" selected>RL1: Đèn</option>
            <option value="fan">RL1: Quạt</option>
            <option value="switch">RL1: Công tắc</option>
          </select>
          <select class="sel" id="prov-r2-${mac}" style="width:130px">
            <option value="fan" selected>RL2: Quạt</option>
            <option value="light">RL2: Đèn</option>
            <option value="switch">RL2: Công tắc</option>
          </select>
          <button class="btn btn-primary" onclick="pairNode('${mac}')">➕ Gán Vào Nhà</button>
        </div>
      </div>`;
    }).join('');
  }
}

async function pairNode(mac) {
  const room = ($('prov-room-' + mac)?.value || 'livingroom').trim();
  const rl1 = $('prov-r1-' + mac)?.value || 'light';
  const rl2 = $('prov-r2-' + mac)?.value || 'fan';
  try {
    const r = await fetch('/api/provision', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mac, room, rl1, rl2 })
    });
    const j = await r.json();
    if (j.success) {
      showToast(`Đã gán công tắc ${mac} vào phòng ${room} thành công!`);
      setTimeout(loadAll, 600);
    } else {
      showToast('Lỗi: ' + (j.error || ''), false);
    }
  } catch(e) { showToast('Lỗi gửi lệnh gán thiết bị', false); }
}

/* ── OTA Firmware Hub ── */
async function loadFirmwares() {
  try {
    const r = await fetch('/api/ota/list');
    const d = await r.json();
    const items = d.firmwares || [];
    const select = $('ota-firmware-select');
    const tableBox = $('firmware-table-container');

    if (!items.length) {
      select.innerHTML = '<option value="">-- Chưa có firmware nào trong kho --</option>';
      tableBox.innerHTML = '<div style="color:var(--text-dim);font-size:0.85rem;text-align:center;padding:24px">Chưa có bản build firmware nào. Kéo thả file .bin bên trên để tải lên!</div>';
      return;
    }

    select.innerHTML = items.map(f => `<option value="${f.filename}">${f.filename} (${f.size_mb} MB - ${f.chip})</option>`).join('');

    let tHtml = `<div style="overflow-x:auto"><table style="width:100%;font-size:0.82rem;text-align:left;border-collapse:collapse">
      <thead><tr style="border-bottom:1px solid var(--border);color:var(--text-dim)">
        <th style="padding:10px 8px">File Name</th>
        <th style="padding:10px 8px">Chipset</th>
        <th style="padding:10px 8px">Dung lượng</th>
        <th style="padding:10px 8px">MD5 Checksum</th>
        <th style="padding:10px 8px">Ngày tải lên</th>
        <th style="padding:10px 8px;text-align:right">Thao tác</th>
      </tr></thead><tbody>`;

    items.forEach(f => {
      tHtml += `<tr style="border-bottom:1px solid rgba(255,255,255,0.03)">
        <td style="padding:10px 8px;font-weight:600"><b style="color:var(--accent)">${f.filename}</b></td>
        <td style="padding:10px 8px"><span style="background:rgba(0,242,254,0.1);color:var(--accent);padding:2px 6px;border-radius:4px">${f.chip}</span></td>
        <td style="padding:10px 8px">${f.size_mb} MB</td>
        <td style="padding:10px 8px;font-family:monospace;font-size:0.75rem;color:var(--text-dim)">${f.md5.substring(0,12)}...</td>
        <td style="padding:10px 8px;color:var(--text-dim)">${f.modified}</td>
        <td style="padding:10px 8px;text-align:right">
          <button class="btn btn-danger" style="padding:4px 10px;font-size:0.75rem" onclick="deleteFirmware('${f.filename}')">Xóa</button>
        </td>
      </tr>`;
    });
    tHtml += '</tbody></table></div>';
    tableBox.innerHTML = tHtml;

  } catch(e) { console.warn('loadFirmwares error:', e); }
}

function handleFileSelect(e) {
  const file = e.target.files[0];
  if (file) uploadBinary(file);
}

// Drag & drop handlers
const dropzone = $('ota-dropzone');
['dragenter', 'dragover'].forEach(ev => dropzone?.addEventListener(ev, e => { e.preventDefault(); dropzone.classList.add('dragover'); }));
['dragleave', 'drop'].forEach(ev => dropzone?.addEventListener(ev, e => { e.preventDefault(); dropzone.classList.remove('dragover'); }));
dropzone?.addEventListener('drop', e => {
  const dt = e.dataTransfer;
  if (dt && dt.files.length) uploadBinary(dt.files[0]);
});

async function uploadBinary(file) {
  if (!file.name.endsWith('.bin')) {
    showToast('Chỉ chấp nhận file định dạng .bin (ESP32 Firmware)', false);
    return;
  }
  const status = $('ota-upload-status');
  const bar = $('ota-progress-bar');
  const fill = $('ota-progress-fill');
  status.textContent = `⏳ Đang tải lên ${file.name} (${(file.size/1024/1024).toFixed(2)} MB)...`;
  bar.style.display = 'block';
  fill.style.width = '40%';

  try {
    const formData = new FormData();
    formData.append('firmware', file, file.name);

    const r = await fetch('/api/ota/upload', {
      method: 'POST',
      body: file,
      headers: { 'X-Filename': file.name }
    });
    const j = await r.json();
    fill.style.width = '100%';
    if (j.success) {
      status.textContent = `✅ Đã lưu ${j.filename} (MD5: ${j.md5?.substring(0,8)}... Chip: ${j.chip})`;
      showToast(`Upload firmware ${j.filename} thành công!`);
      loadFirmwares();
    } else {
      status.textContent = `⚠️ Lỗi: ${j.error || ''}`;
      showToast('Lỗi upload: ' + (j.error || ''), false);
    }
  } catch(e) {
    status.textContent = `⚠️ Lỗi mạng khi upload: ${e}`;
    showToast('Lỗi mạng khi upload firmware', false);
  } finally {
    setTimeout(() => { bar.style.display = 'none'; fill.style.width = '0%'; }, 2000);
  }
}

async function triggerOtaFlash() {
  const filename = $('ota-firmware-select')?.value;
  const targetNode = $('ota-node-select')?.value || 'esp32s3_master';
  if (!filename) {
    showToast('Vui lòng chọn file firmware trước khi nạp!', false);
    return;
  }
  const status = $('ota-flash-status');
  status.textContent = `🚀 Đang gửi lệnh nạp ${filename} tới ${targetNode}...`;
  addLog(`🚀 [OTA Trigger] Bắt đầu nạp firmware ${filename} cho ${targetNode}`);

  try {
    const r = await fetch('/api/ota/flash', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, node_id: targetNode })
    });
    const j = await r.json();
    if (j.success) {
      status.textContent = `✨ ${j.message || 'Lệnh nạp OTA đã phát ra thành công! Đang chờ ESP32...'}`;
      showToast('Lệnh OTA đã gửi đi thành công!');
    } else {
      status.textContent = `❌ Lỗi: ${j.error || ''}`;
      showToast('Lỗi nạp OTA: ' + (j.error || ''), false);
    }
  } catch(e) {
    status.textContent = `❌ Lỗi mạng: ${e}`;
    showToast('Lỗi kết nối tới Gateway', false);
  }
}

async function deleteFirmware(filename) {
  if (!confirm(`Bạn có chắc muốn xóa file firmware ${filename}?`)) return;
  try {
    const r = await fetch('/api/ota/delete', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename })
    });
    const j = await r.json();
    if (j.success) {
      showToast(`Đã xóa ${filename}`);
      loadFirmwares();
    }
  } catch(e) { showToast('Lỗi khi xóa file', false); }
}

/* ── Voice & Persona Tuner ── */
function onProviderChange() {
  const p = $('tts-provider')?.value;
  if ($('vieneu-voice-box')) $('vieneu-voice-box').style.display = p === 'vieneu' ? 'block' : 'none';
  if ($('edgetts-controls')) $('edgetts-controls').style.display = p === 'edgetts' ? 'block' : 'none';
}

async function loadVoiceStatus() {
  try {
    const r = await fetch('/api/proactive/status');
    const j = await r.json();
    if (j) {
      if ($('tts-provider')) $('tts-provider').value = j.tts_provider || 'edgetts';
      if ($('vieneu-voice')) $('vieneu-voice').value = j.vieneu_voice || 'Ái Hân';
      if ($('voice-rate')) $('voice-rate').value = parseInt(j.tts_rate || '-4');
      if ($('rate-val')) $('rate-val').textContent = j.tts_rate || '-4%';
      if ($('voice-pitch')) $('voice-pitch').value = parseInt(j.tts_pitch || '2');
      if ($('pitch-val')) $('pitch-val').textContent = j.tts_pitch || '+2Hz';
      if ($('proactive-toggle')) $('proactive-toggle').checked = !!j.enabled;

      onProviderChange();

      // Update KPI banner
      $('kpi-voice-mode').textContent = j.tts_provider === 'vieneu' ? 'VieNeu Local' : 'EdgeTTS Cloud';
      $('kpi-voice-sub').textContent = j.tts_provider === 'vieneu' ? `Offline 0 token (${j.vieneu_voice})` : 'Hoài My Neural (Ngọt ngào)';
      if ($('gemini-status')) $('gemini-status').textContent = j.has_gemini_key ? '✅ Đã lưu Google Gemini Key' : 'Offline Persona (Chưa nhập key)';
    }
  } catch(e) {}
}

async function saveVoiceSettings() {
  const provider = $('tts-provider')?.value || 'edgetts';
  const vieneuVoice = $('vieneu-voice')?.value || 'Ái Hân';
  const rateVal = $('rate-val')?.textContent?.trim() || '-4%';
  const pitchVal = $('pitch-val')?.textContent?.trim() || '+2Hz';

  try {
    const r = await fetch('/api/settings/voice', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, vieneu_voice: vieneuVoice, rate: rateVal, pitch: pitchVal })
    });
    const j = await r.json();
    if (j.success) {
      showToast(`Đã lưu cấu hình giọng [${provider.toUpperCase()}] thành công!`);
      $('voice-save-status').textContent = `✨ Đang sử dụng ${provider==='edgetts'?'EdgeTTS Hoài My Neural':'VieNeu Local 0 token'}!`;
      loadVoiceStatus();
    }
  } catch(e) { showToast('Lỗi lưu cài đặt giọng nói', false); }
}

async function previewInBrowser(e) {
  const btn = e.target;
  const oldText = btn.textContent;
  btn.textContent = '⏳ Đang tạo âm thanh...';
  btn.disabled = true;

  try {
    const player = $('browser-audio-player');
    const text = encodeURIComponent("Dạ em đã bật đèn phòng khách cho anh rồi nè~");
    player.src = `/api/tts/preview?text=${text}&t=${Date.now()}`;
    player.style.display = 'block';
    await player.play();
    showToast('🔊 Đang phát âm thanh thử nghiệm...');
  } catch(err) {
    showToast('Không thể phát thử âm thanh: ' + err, false);
  } finally {
    btn.textContent = oldText;
    btn.disabled = false;
  }
}

async function testSpeaker(type) {
  try {
    const r = await fetch('/api/proactive/test_speak', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type })
    });
    const j = await r.json();
    if (j.success) showToast(`Đã gửi mẫu phát "${j.text}" ra loa!`);
    else showToast('Đã tạo câu thoại nhưng loa ESP32 chưa kết nối audio WebSocket', false);
  } catch(e) { showToast('Lỗi phát thử loa', false); }
}

async function saveGeminiKey() {
  const k = $('gemini-key')?.value?.trim();
  if (!k) return;
  try {
    const r = await fetch('/api/settings/gemini_key', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gemini_key: k })
    });
    const j = await r.json();
    if (j.success) {
      showToast('Đã lưu Gemini API Key thành công!');
      loadVoiceStatus();
    }
  } catch(e) { showToast('Lỗi lưu API Key', false); }
}

async function toggleProactive(cb) {
  try {
    await fetch('/api/proactive/toggle', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: cb.checked })
    });
    showToast(`Đã ${cb.checked?'bật':'tắt'} giao tiếp chủ động`);
  } catch(e) {}
}

/* ── Acoustic Sound System ── */
function playWebSound(name) {
  const p = $('browser-audio-player');
  if (p) {
    p.src = `/api/sound/${name}?t=${Date.now()}`;
    p.style.display = 'block';
    p.play().catch(e => showToast('Trình duyệt chặn autoplay, vui lòng bấm Play', false));
    showToast(`Đang phát thử "${name}"...`);
  }
}

async function playSpeakerSound(name) {
  try {
    showToast(`Đang truyền "${name}" tới loa ESP32...`);
    const r = await fetch('/api/sound/play', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sound: name, node_id: 'esp32s3_master' })
    });
    const j = await r.json();
    if (j.success) showToast(`Đã phát "${name}" thành công trên loa ESP32!`);
    else showToast('Loa ESP32 chưa kết nối audio WebSocket', false);
  } catch(e) { showToast('Lỗi phát âm thanh ra loa', false); }
}

/* ── Auth Management ── */
async function login() {
  const u = $('auth-user')?.value?.trim();
  const p = $('auth-pass')?.value;
  if (!u || !p) { showToast('Vui lòng nhập tài khoản và mật khẩu', false); return; }
  try {
    const r = await fetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: p })
    });
    const j = await r.json();
    if (j.success) {
      localStorage.setItem('aetheria_token', j.token);
      showToast(`Xin chào, ${j.user.fullname || j.user.username}!`);
      checkSession();
      switchView('dashboard');
    } else {
      $('auth-status').textContent = j.error || 'Đăng nhập thất bại';
      showToast(j.error || 'Đăng nhập thất bại', false);
    }
  } catch(e) { showToast('Lỗi đăng nhập', false); }
}

async function register() {
  const u = $('auth-user')?.value?.trim();
  const p = $('auth-pass')?.value;
  const fn = $('auth-fullname')?.value?.trim();
  if (!u || !p) { showToast('Vui lòng nhập tài khoản và mật khẩu', false); return; }
  try {
    const r = await fetch('/api/auth/register', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: p, fullname: fn })
    });
    const j = await r.json();
    if (j.success) {
      showToast('Đăng ký tài khoản thành công! Hãy đăng nhập');
      $('auth-status').textContent = '✅ Đăng ký thành công! Hãy bấm Đăng Nhập.';
    } else {
      $('auth-status').textContent = j.error || 'Lỗi đăng ký';
      showToast(j.error || 'Lỗi đăng ký', false);
    }
  } catch(e) { showToast('Lỗi đăng ký', false); }
}

async function checkSession() {
  const t = localStorage.getItem('aetheria_token');
  try {
    const r = await fetch('/api/auth/me', { headers: { 'Authorization': `Bearer ${t||''}` } });
    const j = await r.json();
    if (j.authenticated && j.user) {
      currentUser = j.user;
      $('user-display-name').textContent = currentUser.fullname || currentUser.username;
      $('prof-username').textContent = currentUser.username;
      $('prof-fullname').textContent = currentUser.fullname || '—';
      $('prof-role').textContent = (currentUser.role || 'member').toUpperCase();
    }
  } catch(e) {}
}

async function logout() {
  const t = localStorage.getItem('aetheria_token');
  try {
    await fetch('/api/auth/logout', { method: 'POST', headers: { 'Authorization': `Bearer ${t||''}` } });
  } catch(e) {}
  localStorage.removeItem('aetheria_token');
  showToast('Đã đăng xuất');
  setTimeout(() => location.reload(), 500);
}

/* ── Realtime SSE Events & Logs ── */
function connectSSE() {
  const es = new EventSource('/api/events');
  es.addEventListener('node_status', e => {
    try {
      const d = JSON.parse(e.data);
      if (d.node_id && nodes[d.node_id]) {
        if (d.rl_state) nodes[d.node_id].relay_state = d.rl_state;
        if (d.online != null) nodes[d.node_id].status = d.online ? 'online' : 'offline';
      }
      renderDashboardKPIs();
      renderDevices();
      updateThreeLights();
    } catch(err) {}
  });

  es.addEventListener('command_result', e => {
    try {
      const d = JSON.parse(e.data);
      if (d.voice_reply) $('latest-reply').textContent = `"${d.voice_reply}"`;
      if (d.transcript) $('latest-transcript').textContent = `"${d.transcript}"`;
      if (d.latency) $('kpi-latency').textContent = d.latency + 's';
      if (d.engine) $('kpi-ai-engine').textContent = d.engine;
      addLog(`🤖 [${d.engine||'AI'}] ${d.fullname||''}: ${d.action} → ${d.verify||'OK'}`);
      loadAll();
    } catch(err) {}
  });

  es.addEventListener('transcript', e => {
    try {
      const d = JSON.parse(e.data);
      $('latest-transcript').textContent = `"${d.text}"`;
    } catch(err) {}
  });

  es.addEventListener('ota_progress', e => {
    try {
      const d = JSON.parse(e.data);
      showToast(`OTA [${d.node_id}]: ${d.progress}% - ${d.message || d.status}`);
      addLog(`🚀 [OTA Progress] ${d.node_id}: ${d.progress}% (${d.status})`);
      if ($('ota-flash-status')) $('ota-flash-status').textContent = `Đang nạp: ${d.progress}% (${d.message || d.status})`;
    } catch(err) {}
  });

  es.onerror = () => {
    $('gw-status-pill').innerHTML = '<span class="dot offline"></span> Mất kết nối';
    es.close();
    setTimeout(connectSSE, 3000);
  };
}

function addLog(msg) {
  const box = $('activity-log-box');
  if (!box) return;
  const d = new Date();
  const ts = d.toTimeString().split(' ')[0];
  const div = document.createElement('div');
  div.className = 'log-item';
  div.innerHTML = `<span class="log-ts">${ts}</span><span>${msg}</span>`;
  box.prepend(div);
  while (box.children.length > 25) box.removeChild(box.lastChild);
}

// Clock tick
setInterval(() => {
  const d = new Date();
  $('clock-display').textContent = d.toTimeString().split(' ')[0];
}, 1000);

/* ── DOM Init ── */
window.addEventListener('DOMContentLoaded', () => {
  initThree();
  loadAll();
  loadVoiceStatus();
  checkSession();
  connectSSE();
  setInterval(loadAll, 12000);
});
</script>
</body>
</html>
"""

# ── WEB SERVER CLASS ─────────────────────────────────────────────────────────
class WebServer:
    """Async HTTP + SSE dashboard & Aetheria OS manager."""

    def __init__(self, gateway):
        self.gateway = gateway
        self.host = getattr(config, "WEB_HOST", "0.0.0.0")
        self.port = getattr(config, "WEB_PORT", 8000)
        self.server = None
        self.sse_queues: Set[asyncio.Queue] = set()
        self._running = False

    async def start(self):
        self._running = True
        try:
            self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
            logger.info(f"🌐 AETHERIA OS Web Dashboard: http://{self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Web server failed on {self.port}: {e}")

    async def stop(self):
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Web server stopped")

    def broadcast_event(self, event_name: str, data: Dict[str, Any]):
        if not self.sse_queues:
            return
        payload = f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for q in list(self.sse_queues):
            try:
                q.put_nowait(payload)
            except Exception:
                pass

    def broadcast(self, event_name: str, data: Dict[str, Any]):
        self.broadcast_event(event_name, data)

    def _nodes_snapshot(self, user: Optional[Dict[str, Any]] = None) -> dict:
        r = self.gateway.registry
        all_nodes = r.get_all_nodes()
        if hasattr(self.gateway, "auth") and self.gateway.auth:
            all_nodes = self.gateway.auth.filter_nodes(user, all_nodes)

        disc = self.gateway.discovery.get_discovered_devices() if hasattr(self.gateway, "discovery") else {}
        return {
            "nodes": all_nodes,
            "rooms": r.get_rooms(),
            "pending": r.get_pending(),
            "discovered": disc,
        }

    async def _handle_client(self, reader, writer):
        try:
            request_line = await reader.readline()
            if not request_line:
                writer.close(); return
            parts = request_line.decode("utf-8", errors="ignore").split()
            if len(parts) < 2:
                writer.close(); return
            method, full_path = parts[0].upper(), parts[1]

            # Parse path and query
            parsed_url = urllib.parse.urlparse(full_path)
            path = parsed_url.path
            query = urllib.parse.parse_qs(parsed_url.query)

            headers = {}
            content_length = 0
            while True:
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break
                ls = line.decode("utf-8", errors="ignore").strip()
                if ":" in ls:
                    k, v = ls.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
                    if k.strip().lower() == "content-length":
                        try:
                            content_length = int(v.strip())
                        except ValueError:
                            content_length = 0

            # Extract user from token or API Key
            current_user = None
            auth_header = headers.get("authorization", "")
            api_key_header = headers.get("x-api-key", "")
            token = None
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            elif api_key_header:
                token = api_key_header.strip()
            elif "token" in query:
                token = query["token"][0]
            elif "api_key" in query:
                token = query["api_key"][0]

            if hasattr(self.gateway, "auth") and self.gateway.auth and token:
                current_user = self.gateway.auth.authenticate_token(token)

            async def _read_body():
                if content_length > 0:
                    return await reader.readexactly(content_length)
                return b""

            # ── SPA Main View ──
            if method == "GET" and path in ("/", "/index.html"):
                body = HTML_PAGE.encode("utf-8")
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            # ── API: Nodes Snapshot ──
            if method == "GET" and path == "/api/nodes":
                data = self._nodes_snapshot(current_user)
                body = json.dumps(data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            # ── API: SSE Events ──
            if method == "GET" and path.startswith("/api/events"):
                writer.write(("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                              "Cache-Control: no-cache\r\nConnection: keep-alive\r\n"
                              "Access-Control-Allow-Origin: *\r\n\r\n").encode())
                await writer.drain()
                q = asyncio.Queue()
                self.sse_queues.add(q)
                try:
                    init_d = json.dumps(self._nodes_snapshot(current_user), ensure_ascii=False)
                    writer.write(f"event: init\ndata: {init_d}\n\n".encode())
                    await writer.drain()
                    while self._running:
                        msg = await asyncio.wait_for(q.get(), timeout=30.0)
                        writer.write(msg.encode())
                        await writer.drain()
                except (asyncio.TimeoutError, Exception):
                    pass
                finally:
                    self.sse_queues.discard(q)
                    try: writer.close()
                    except Exception: pass
                return

            # ── API: Relay Control ──
            if method == "POST" and path == "/api/relay":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    node_id = d.get("node_id")
                    channel = d.get("channel") or d.get("ch", "ch1")
                    action = d.get("action") or d.get("s", "turn_on")
                    
                    # Relay control via verifier or mqtt
                    if hasattr(self.gateway, "verifier") and self.gateway.verifier:
                        success = await self.gateway.verifier.execute_action(node_id, channel, action)
                    else:
                        success = False
                        
                    resp_data = {"success": success, "node_id": node_id, "channel": channel, "action": action}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            # ── API: Provisioning ──
            if method == "POST" and path == "/api/provision":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    mac = d.get("mac", "").upper()
                    if not mac or mac not in self.gateway.registry.get_pending():
                        resp_data = {"success": False, "error": f"MAC {mac} không nằm trong pending"}
                    else:
                        res = await self.gateway.provision_pending(
                            mac, d.get("room", "livingroom"), d.get("rl1", "light"), d.get("rl2", "fan"),
                            node_short=d.get("node_short")
                        )
                        # Auto assign ownership to current user
                        if current_user and hasattr(self.gateway, "auth"):
                            nid = res.get("node_id")
                            if nid:
                                self.gateway.auth.assign_device_to_user(current_user["id"], nid)
                        resp_data = res
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            # ── API: Proactive & Voice Status ──
            if method == "GET" and path == "/api/proactive/status":
                has_gemini = bool(getattr(self.gateway, "persona", None) and self.gateway.persona.has_api_key)
                proactive_en = bool(getattr(self.gateway, "proactive", None) and self.gateway.proactive.enabled)
                resp_data = {
                    "enabled": proactive_en,
                    "has_gemini_key": has_gemini,
                    "tts_provider": getattr(config, "TTS_PROVIDER", "edgetts"),
                    "vieneu_voice": getattr(config, "VIENEU_VOICE", "Ái Hân"),
                    "tts_rate": getattr(config, "TTS_RATE", "-4%"),
                    "tts_pitch": getattr(config, "TTS_PITCH", "+2Hz")
                }
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            # ── API: Save Voice Settings ──
            if method == "POST" and path == "/api/settings/voice":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    provider = d.get("provider", "edgetts").lower().strip()
                    config.TTS_PROVIDER = provider
                    if "vieneu_voice" in d:
                        config.VIENEU_VOICE = str(d["vieneu_voice"]).strip()
                    if "rate" in d:
                        config.TTS_RATE = str(d["rate"]).strip()
                    if "pitch" in d:
                        config.TTS_PITCH = str(d["pitch"]).strip()

                    # Save to local_config.json
                    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_config.json")
                    cfg_data = {}
                    if os.path.exists(cfg_path):
                        try:
                            with open(cfg_path, "r", encoding="utf-8") as f:
                                cfg_data = json.load(f)
                        except Exception: pass
                    cfg_data["TTS_PROVIDER"] = config.TTS_PROVIDER
                    cfg_data["VIENEU_VOICE"] = config.VIENEU_VOICE
                    cfg_data["TTS_RATE"] = config.TTS_RATE
                    cfg_data["TTS_PITCH"] = config.TTS_PITCH
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        json.dump(cfg_data, f, ensure_ascii=False, indent=2)

                    resp_data = {"success": True, "provider": provider}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            # ── API: Sounds Catalog ──
            if method == "GET" and path == "/api/sounds":
                data = self.gateway.sound.list_sounds() if hasattr(self.gateway, "sound") else {"sounds": []}
                body = json.dumps(data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            # ── API: Stream/Download Sound MP3 ──
            if method in ("GET", "HEAD") and path.startswith("/api/sound/"):
                sound_name = path.replace("/api/sound/", "").strip()
                audio_bytes = self.gateway.sound.get_mp3_data(sound_name) if hasattr(self.gateway, "sound") else None
                if audio_bytes:
                    writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: audio/mpeg\r\n"
                                  f"Content-Length: {len(audio_bytes)}\r\nAccess-Control-Allow-Origin: *\r\n"
                                  f"Connection: close\r\n\r\n").encode() + audio_bytes)
                    await writer.drain(); writer.close(); return
                else:
                    writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain(); writer.close(); return

            # ── API: Play Sound on Speaker ──
            if method == "POST" and path == "/api/sound/play":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    s_name = d.get("sound", "bootup_sound")
                    node_id = d.get("node_id", "esp32s3_master")
                    ok = False
                    if hasattr(self.gateway, "sound") and self.gateway.sound:
                        ok = await self.gateway.sound.play_sound(s_name, target_node=node_id)
                    resp_data = {"success": ok, "sound": s_name, "node_id": node_id}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            # ── API: In-Browser Audio Preview ──
            if method in ("GET", "HEAD") and path.startswith("/api/tts/preview"):
                test_text = query.get("text", ["Dạ em đã bật đèn phòng khách cho anh rồi nè~"])[0]
                audio_bytes = None
                if hasattr(self.gateway, "tts") and self.gateway.tts:
                    audio_bytes = await self.gateway.tts.synthesize(test_text)
                if audio_bytes:
                    mime = "audio/wav" if audio_bytes.startswith(b"RIFF") else "audio/mpeg"
                    writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: {mime}\r\n"
                                  f"Content-Length: {len(audio_bytes)}\r\nAccess-Control-Allow-Origin: *\r\n"
                                  f"Connection: close\r\n\r\n").encode() + audio_bytes)
                    await writer.drain(); writer.close(); return
                else:
                    writer.write(b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain(); writer.close(); return

            # ── API: Proactive Test Speak ──
            if method == "POST" and path == "/api/proactive/test_speak":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    t = d.get("type", "chào")
                    if t == "hát":
                        text = "Một con vịt xòe ra hai cái cánh, nó kêu rằng quác quác quác quạc quạc quác! Em ngân nga chút cho ngôi nhà thêm vui tươi nè anh ơi~"
                    elif t == "hài":
                        text = "Tại sao con cua không bao giờ đi thẳng? Vì nó thích đi ngang đó nha anh!"
                    elif t == "an_toan":
                        text = "Dạ anh ơi~ Em thấy bình nóng lạnh ở phòng tắm đã bật hơn 35 phút rồi đó ạ. Anh nhớ tắt giúp em để vừa an toàn vừa tiết kiệm điện nha anh!"
                    else:
                        text = "Dạ, em chào anh ạ! Em là Lumi, cô trợ lý nhỏ luôn sẵn sàng hỗ trợ anh nè~ Anh có mệt không, để em bật chút nhạc cho anh thư giãn nha?"

                    ok = False
                    if hasattr(self.gateway, "audio_server") and self.gateway.audio_server:
                        ok = await self.gateway.audio_server.speak_proactive(text)
                    if not ok and hasattr(self.gateway, "tts") and self.gateway.tts:
                        pcm = await self.gateway.tts.synthesize_pcm(text)
                        if pcm: ok = True
                    resp_data = {"success": ok, "text": text, "type": t}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            # ── API: Save Gemini Key ──
            if method == "POST" and path == "/api/settings/gemini_key":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    k = d.get("gemini_key", "").strip()
                    config.GEMINI_API_KEY = k
                    if hasattr(self.gateway, "persona") and self.gateway.persona:
                        self.gateway.persona.set_api_key(k)
                    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_config.json")
                    cfg_data = {}
                    if os.path.exists(cfg_path):
                        try:
                            with open(cfg_path, "r", encoding="utf-8") as f:
                                cfg_data = json.load(f)
                        except Exception: pass
                    cfg_data["GEMINI_API_KEY"] = k
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        json.dump(cfg_data, f, ensure_ascii=False, indent=2)
                    resp_data = {"success": True}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            # ── API: Proactive Toggle ──
            if method == "POST" and path == "/api/proactive/toggle":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    enabled = bool(d.get("enabled", True))
                    if hasattr(self.gateway, "proactive") and self.gateway.proactive:
                        self.gateway.proactive.enabled = enabled
                    config.PROACTIVE_ENABLED = enabled
                    resp_data = {"success": True, "enabled": enabled}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            # ── API: OTA Firmware Management ──
            if method == "GET" and path == "/api/ota/list":
                items = []
                if hasattr(self.gateway, "ota") and self.gateway.ota:
                    items = self.gateway.ota.list_firmwares()
                body = json.dumps({"firmwares": items}, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/ota/upload":
                raw_bytes = await _read_body()
                filename = headers.get("x-filename", f"firmware_{int(time.time())}.bin")
                if hasattr(self.gateway, "ota") and self.gateway.ota:
                    res = self.gateway.ota.save_firmware(filename, raw_bytes)
                    resp_data = {"success": True, **res}
                else:
                    resp_data = {"success": False, "error": "OTA manager not available"}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/ota/delete":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    fn = d.get("filename")
                    ok = self.gateway.ota.delete_firmware(fn) if hasattr(self.gateway, "ota") else False
                    resp_data = {"success": ok}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/ota/flash":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    fn = d.get("filename")
                    node_id = d.get("node_id", "esp32s3_master")
                    
                    # Find node IP
                    node_info = self.gateway.registry.get_all_nodes().get(node_id, {})
                    target_ip = node_info.get("ip")
                    
                    if target_ip and hasattr(self.gateway, "ota"):
                        res = await self.gateway.ota.flash_via_http(target_ip, fn, node_id=node_id)
                    elif hasattr(self.gateway, "ota"):
                        # Fallback to MQTT pull
                        my_ip = self.host if self.host != "0.0.0.0" else "192.168.11.29"
                        res = await self.gateway.ota.trigger_via_mqtt(node_id, fn, my_ip)
                    else:
                        res = {"success": False, "error": "OTA manager not available"}
                    resp_data = res
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "GET" and path.startswith("/api/ota/download/"):
                fn = os.path.basename(path)
                data = self.gateway.ota.get_firmware_bytes(fn) if hasattr(self.gateway, "ota") else None
                if data:
                    writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n"
                                  f"Content-Length: {len(data)}\r\nAccess-Control-Allow-Origin: *\r\n"
                                  f"Connection: close\r\n\r\n").encode() + data)
                    await writer.drain(); writer.close(); return
                else:
                    writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain(); writer.close(); return

            # ── API: Auth & Multi-Tenant ──
            if method == "POST" and path == "/api/auth/login":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    u = d.get("username", "")
                    p = d.get("password", "")
                    res = self.gateway.auth.login(u, p) if hasattr(self.gateway, "auth") else {"success": False, "error": "Auth disabled"}
                    resp_data = res
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/auth/register":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    u = d.get("username", "")
                    p = d.get("password", "")
                    fn = d.get("fullname", "")
                    res = self.gateway.auth.register(u, p, fn) if hasattr(self.gateway, "auth") else {"success": False, "error": "Auth disabled"}
                    resp_data = res
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "GET" and path == "/api/auth/me":
                if current_user:
                    resp_data = {"authenticated": True, "user": current_user}
                else:
                    resp_data = {"authenticated": False}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/auth/logout":
                if token and hasattr(self.gateway, "auth"):
                    self.gateway.auth.logout(token)
                body = b'{"success":true}'
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            # 404 Fallthrough
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            await writer.drain(); writer.close()
        except Exception as e:
            logger.debug(f"HTTP handler exception: {e}")
            try: writer.close()
            except Exception: pass