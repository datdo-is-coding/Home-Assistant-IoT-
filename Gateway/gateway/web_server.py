"""
DTV Smart Home Gateway v2 — Web GUI đầy đủ
==========================================
Async HTTP + SSE, không dependency ngoài stdlib.

Tính năng:
  • Dashboards: audio pipeline thời gian thực, logs SSE, telemetry
  • THÊM Node: xem node pending (hello mới chưa provision), đăng ký phòng + gán RL1/RL2
  • QUẢN LÝ THIẾT BỊ: nhóm theo phòng, fullname livingroom-node01-fan, bật/tắt relay
  • Phân biệt rõ node online/offline, hiển thị cfg_version, RSSI, trạng thái relay

API endpoints:
  GET  /                          → trang chính
  GET  /api/events                → SSE live
  GET  /api/nodes                 → toàn bộ node + rooms + pending
  POST /api/relay                 → {node_id, channel|ch, action|s}
  POST /api/provision             → {mac, room, rl1, rl2, node_short?}
  POST /api/node/config           → {node_id, room, rl1, rl2} chỉnh lại cấu hình
  POST /api/node/remove           → {mac} xoá node pending
"""

import asyncio
import json
import logging
import time
from typing import Set, Dict, Any, Optional

import config

logger = logging.getLogger("web_server")

# ── Trang HTML (self-contained, không lib ngoài) ─────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DTV Smart Home — Node Manager & Monitor</title>
<style>
:root{
  --bg:#0b0f19; --card-bg:rgba(18,24,38,.85); --border:rgba(255,255,255,.08);
  --accent:#00f2fe; --accent-glow:rgba(0,242,254,.35); --green:#10b981;
  --orange:#f59e0b; --red:#ef4444; --purple:#8b5cf6; --text:#f3f4f6; --dim:#9ca3af;
}
*{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
body{background:var(--bg);color:var(--text);padding:18px;min-height:100vh}
.container{max-width:1280px;margin:0 auto;display:flex;flex-direction:column;gap:18px}
header{display:flex;justify-content:space-between;align-items:center;background:var(--card-bg);border:1px solid var(--border);padding:14px 22px;border-radius:16px;flex-wrap:wrap;gap:10px}
.logo{display:flex;align-items:center;gap:12px}
.logo-icon{width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,#00f2fe,#4facfe);display:flex;align-items:center;justify-content:center;font-size:20px}
.logo-text h1{font-size:1.2rem;font-weight:700;color:#fff;letter-spacing:.5px}
.logo-text p{font-size:.8rem;color:var(--dim)}
.badges{display:flex;gap:10px;flex-wrap:wrap}
.badge{display:flex;align-items:center;gap:6px;padding:6px 12px;border-radius:20px;font-size:.78rem;font-weight:600;background:rgba(255,255,255,.05);border:1px solid var(--border)}
.dot{width:8px;height:8px;border-radius:50%}
.dg{background:var(--green);box-shadow:0 0 8px var(--green)} .do{background:var(--orange);box-shadow:0 0 8px var(--orange)} .dr{background:var(--red)} .dp{animation:pulse 1.5s infinite}
@keyframes pulse{0%{opacity:1}50%{opacity:.35}100%{opacity:1}}

.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px}
.card{background:var(--card-bg);border:1px solid var(--border);border-radius:16px;padding:18px;display:flex;flex-direction:column;gap:14px}
.card.full{grid-column:1/-1}
.ct{font-size:.85rem;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.75px;display:flex;align-items:center;gap:8px}

.steps{display:flex;gap:8px;flex-wrap:wrap}
.step{flex:1;min-width:120px;background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:12px;padding:10px;text-align:center;transition:.3s}
.step.active{background:rgba(0,242,254,.1);border-color:var(--accent);box-shadow:0 0 18px var(--accent-glow)}
.sn{font-size:.68rem;color:var(--accent);font-weight:700;margin-bottom:3px} .sm{font-size:.82rem;font-weight:600} .ss{font-size:.68rem;color:var(--dim);margin-top:2px}

.meter{background:rgba(0,0,0,.3);border-radius:10px;padding:10px;border:1px solid rgba(255,255,255,.05)}
.mbar{background:rgba(255,255,255,.08);height:14px;border-radius:7px;overflow:hidden}
.mfill{height:100%;width:0;background:linear-gradient(90deg,#10b981,#f59e0b 70%,#ef4444);transition:.08s}
.mlab{display:flex;justify-content:space-between;font-size:.7rem;color:var(--dim);margin-bottom:6px}

.bubble{background:rgba(0,0,0,.25);border-left:4px solid var(--accent);border-radius:0 10px 10px 0;padding:10px 14px;font-size:.92rem;line-height:1.5}
.bub2{border-left-color:var(--purple)} .bl{font-size:.7rem;color:var(--dim);margin-bottom:4px;font-weight:600} .bt{font-size:1rem;font-weight:500;color:#fff}

/* Rooms */
.room-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.room{border:1px solid var(--border);border-radius:14px;padding:14px;background:rgba(255,255,255,.02)}
.room-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.room-title{font-weight:700;font-size:.95rem;text-transform:capitalize}
.node{border-top:1px solid rgba(255,255,255,.06);padding:8px 0}
.node-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
.node-id{font-family:ui-monospace,monospace;font-size:.82rem;color:var(--accent);font-weight:600}
.status-tag{font-size:.66rem;padding:3px 8px;border-radius:12px;font-weight:700}
.on{background:rgba(16,185,129,.18);color:var(--green)} .off{background:rgba(239,68,68,.15);color:var(--red)} .pend{background:rgba(245,158,11,.15);color:var(--orange)}
.node-meta{font-size:.7rem;color:var(--dim);margin-top:3px}
.ch-list{margin-top:8px;display:flex;flex-direction:column;gap:6px}
.ch-row{display:flex;justify-content:space-between;align-items:center;background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:9px;padding:6px 10px;font-size:.78rem}
.ch-name{font-family:ui-monospace,monospace;color:#e2e8f0}
.ch-gpio{font-size:.66rem;color:var(--dim)}
.switch{position:relative;width:46px;height:24px;flex-shrink:0}
.switch input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#334;border-radius:24px;transition:.25s}
.slider:before{position:absolute;content:"";height:18px;width:18px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.25s}
input:checked+.slider{background:var(--green)}
input:checked+.slider:before{transform:translateX(22px)}
input:disabled+.slider{opacity:.35;cursor:not-allowed}

/* Pending */
.pending-card{background:linear-gradient(135deg,rgba(245,158,11,.12),rgba(239,68,68,.06));border-color:rgba(245,158,11,.35)}
.pend-item{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:10px;background:rgba(255,255,255,.04);border-radius:10px;border:1px solid var(--border)}
.pend-form{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.inp{background:rgba(255,255,255,.06);border:1px solid var(--border);border-radius:8px;color:#fff;padding:7px 10px;font-size:.82rem;outline:none}
.inp:focus{border-color:var(--accent)} ::placeholder{color:var(--dim)}
.sel{background:rgba(255,255,255,.08);border:1px solid var(--border);color:#fff;border-radius:8px;padding:7px 10px;font-size:.82rem;outline:none}
.btn{padding:8px 14px;border-radius:10px;font-weight:600;font-size:.8rem;cursor:pointer;border:none;transition:.2s;color:#fff}
.btn:disabled{opacity:.4;cursor:not-allowed}
.btn-a{background:var(--accent);color:#000}
.btn-g{background:var(--green)}
.btn-o{background:rgba(255,255,255,.12);border:1px solid var(--border)}
.btn-r{background:var(--red)}
.btn:hover:not(:disabled){transform:translateY(-1px);filter:brightness(1.1)}

.logbox{background:#050811;border:1px solid rgba(255,255,255,.05);border-radius:10px;padding:12px;height:150px;overflow-y:auto;font-family:ui-monospace,monospace;font-size:.76rem;display:flex;flex-direction:column;gap:4px}
.ll{display:flex;gap:8px} .lt{color:var(--dim)} .lm{color:#e2e8f0} .lm.hl{color:var(--accent);font-weight:600}
.hint{font-size:.72rem;color:var(--dim);font-style:italic}
.empty{color:var(--dim);font-size:.82rem;padding:10px;text-align:center}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo"><div class="logo-icon">🏠</div>
      <div class="logo-text"><h1>DTV Smart Home — Node Manager</h1>
      <p>ESP32 ⇄ Gateway · Voice + Relay · Provision tự động</p></div>
    </div>
    <div class="badges">
      <div class="badge" id="bd-gw"><span class="dot dg"></span>Gateway: Online</div>
      <div class="badge" id="bd-mqtt"><span class="dot dg"></span>MQTT</div>
      <div class="badge" id="bd-ai"><span class="dot dg"></span>AI: Hybrid Ready</div>
      <div class="badge" id="bd-nodes"><span class="dot dg"></span>Nodes: –</div>
      <div class="badge" id="bd-pend"><span class="dot dg"></span>Pending: 0</div>
    </div>
  </header>

  <!-- Pending nodes -->
  <div class="card pending-card" id="pending-box" style="display:none">
    <div class="ct">📡 THIẾT BỊ MỚI PHÁT HIỆN — CHƯA ĐĂNG KÝ</div>
    <div id="pending-list"></div>
    <div class="hint">Node mới gửi HELLO → tự xuất hiện ở đây. Chọn phòng + gán tên RL1/RL2, Gateway sẽ ghi cấu hình vào bộ nhớ ESP32 (NVS) và node lưu vĩnh viễn.</div>
  </div>

  <!-- Audio pipeline -->
  <div class="card full" id="voice-card" style="display:none">
    <div class="ct">🎙️ VOICE & AI PIPELINE</div>
    <div class="steps">
      <div class="step" id="s1"><div class="sn">1</div><div class="sm">WakeNet</div><div class="ss">"Hi ESP"</div></div>
      <div class="step" id="s2"><div class="sn">2</div><div class="sm">PCM Stream</div><div class="ss">Mic 16kHz → WS</div></div>
      <div class="step" id="s3"><div class="sn">3</div><div class="sm">Sherpa ASR</div><div class="ss">Speech→Text</div></div>
      <div class="step" id="s4"><div class="sn">4</div><div class="sm">AI Engine</div><div class="ss" id="s4-sub">Gemini / Qwen 3B</div></div>
      <div class="step" id="s5"><div class="sn">5</div><div class="sm">TTS Playback</div><div class="ss">EdgeTTS → Loa</div></div>
    </div>
    <div class="meter">
      <div class="mlab"><span>Mic Input (RMS)</span><span id="mval">Im lặng</span></div>
      <div class="mbar"><div class="mfill" id="mfill"></div></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div class="bubble"><div class="bl">TRANSCRIPT</div><div class="bt" id="trans">Chưa có lệnh nào...</div></div>
      <div class="bubble bub2"><div class="bl">TRỢ LÝ PHẢN HỒI</div><div class="bt" id="reply">—</div></div>
    </div>
  </div>

  <!-- Rooms / nodes -->
  <div class="card full">
    <div class="ct">💡 THIẾT BỊ THEO PHÒNG (RELAY CONTROL)</div>
    <div id="rooms-box"><div class="empty">Chưa có node nào. Kết nối ESP32 hoặc thêm node mới...</div></div>
  </div>

  <!-- Logs -->
  <div class="card full">
    <div class="ct">📋 NHẬT KÝ SỰ KIỆN</div>
    <div class="logbox" id="log"></div>
  </div>
</div>

<script>
let nodes={}, pending={}, rooms={};
let nodeCount=0;

const $=id=>document.getElementById(id);
function addLog(msg,hl=false){
  const b=$('log'), d=document.createElement('div');
  d.className='ll';
  d.innerHTML=`<span class="lt">[${new Date().toLocaleTimeString()}]</span><span class="lm ${hl?'hl':''}">${msg}</span>`;
  b.appendChild(d); b.scrollTop=b.scrollHeight;
  if(b.children.length>200) b.removeChild(b.firstChild);
}
function statusTag(st){
  if(st==='pending')return '<span class="status-tag pend">CHỜ ĐĂNG KÝ</span>';
  return st==='online'?'<span class="status-tag on">ONLINE</span>':'<span class="status-tag off">OFFLINE</span>';
}

/* ── Thay đổi switch relay ── */
async function toggleRelay(nodeId,ch,el){
  const s=el.checked?1:0;
  el.disabled=true;
  addLog(`👉 ${nodeId}/${ch} → ${s?'BẬT':'TẮT'}`);
  try{
    const r=await fetch('/api/relay',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({node_id:nodeId,ch,s})});
    const j=await r.json();
    if(!j.success) addLog(`⚠️ ${j.error||'null'}`,true);
  }catch(e){ addLog(`⚠️ Relay error: ${e}`); }
  // UI sẽ được đồng bộ lại qua SSE ack (không hard-set)
  const watchdog=setTimeout(()=>{el.disabled=false;},4000);
  el._wd=watchdog;
}

/* ── Render theo phòng ── */
function renderRooms(){
  const box=$('rooms-box');
  const rmKeys=Object.keys(rooms||{});
  if(!rmKeys.length){ box.innerHTML='<div class="empty">Chưa có node nào. Kết nối ESP32 hoặc thêm node mới...</div>'; return; }
  let html='<div class="room-grid">';
  for(const room of rmKeys){
    html+=`<div class="room"><div class="room-head"><span class="room-title">🏠 ${room} (${(rooms[room]||[]).length})</span></div>`;
    for(const nid of (rooms[room]||[])){
      const n=nodes[nid]||{};
      const st=n.status||'offline';
      html+=`<div class="node"><div class="node-top"><span class="node-id">${nid}</span>${statusTag(st)}</div>`;
      html+=`<div class="node-meta">MAC ${(n.mac||'?')} · cfg v${n.cfg_version||1}${n.rssi!=null?' · RSSI '+n.rssi+'dB':''} ${n.ip?'· '+n.ip:''}</div>`;
      html+='<div class="ch-list">';
      for(const [ch,ci] of Object.entries(n.channels||{})){
        const fn=ci.fullname||nid+'-?';
        const gpio=ci.gpio!=null?` · GPIO ${ci.gpio}`:'';
        const rlState=(n.relay_state&&n.relay_state[(ch==='ch1'?0:1)])||0;
        const off=st!=='online';
        html+=`<div class="ch-row"><span><span class="ch-name">${fn}</span> <span class="ch-gpio">(${ch}${gpio})</span></span>
          <label class="switch"><input type="checkbox" onclick="toggleRelay('${nid}','${ch}',this)"
          ${rlState?'checked':''} ${off?'disabled':''}><span class="slider"></span></label></div>`;
      }
      html+='</div></div>';
    }
    html+='</div>';
  }
  html+='</div>';
  box.innerHTML=html;
}

/* ── Render pending ── */
function renderPending(){
  const box=$('pending-box'), list=$('pending-list');
  const keys=Object.keys(pending||{});
  box.style.display=keys.length?'':'none';
  if(!keys.length){ list.innerHTML=''; return; }
  $('bd-pend').innerHTML=`<span class="dot do dp"></span>Pending: ${keys.length}`;
  list.innerHTML=keys.map(mac=>{
    const p=pending[mac]||{};
    return `<div class="pend-item">
      <div><b style="font-family:monospace">${mac}</b>
      <div class="hint">cfg=${p.cfg!=null?p.cfg:'chưa gán'} · IP ${p.ip||'?'} ${p.rssi!=null?'· RSSI '+p.rssi+'dB':''}</div></div>
      <div class="pend-form">
        <input class="inp" id="room-${mac}" placeholder="Phòng e.g. livingroom" list="room-opt">
        <input class="inp" id="short-${mac}" placeholder="node01" style="width:90px">
        <select class="sel" id="r1-${mac}"><option value="light">RL1 = light (đèn)</option><option value="fan">RL1 = fan (quạt)</option><option value="pump">RL1 = pump</option><option value="curtain">RL1 = curtain</option></select>
        <select class="sel" id="r2-${mac}" ><option value="fan">RL2 = fan (quạt)</option><option value="light">RL2 = light (đèn)</option><option value="pump">RL2 = pump</option><option value="">RL2 = bỏ trống</option></select>
        <button class="btn btn-a" onclick="provision('${mac}')">ĐĂNG KÝ</button>
        <button class="btn btn-r" onclick="removePending('${mac}')">✕</button>
      </div>
    </div>`;
  }).join('');
}

async function provision(mac){
  const room=$('room-'+mac).value.trim()||'unknowm';
  const short=$('short-'+mac).value.trim()||null;
  const rl1=$('r1-'+mac).value, rl2=$('r2-'+mac).value;
  addLog(`📝 Đăng ký ${mac}: phòng=${room}, RL1=${rl1}, RL2=${rl2}`,true);
  try{
    const r=await fetch('/api/provision',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({mac,room,rl1,rl2,node_short:short})});
    const j=await r.json();
    addLog(j.success?`✅ Thành công → ${j.node_id}`:`⚠️ ${j.error||'Lỗi'}`,true);
    if(j.success) loadAll();
  }catch(e){addLog('⚠️ '+e,true);}
}

async function removePending(mac){
  try{ await fetch('/api/node/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mac})}); loadAll(); }catch(e){}
}

/* ── Data load + SSE ── */
async function loadAll(){
  try{
    const r=await fetch('/api/nodes');
    const j=await r.json();
    nodes=j.nodes||{}; rooms=j.rooms||{}; pending=j.pending||{};
    nodeCount=Object.keys(nodes).length;
    $('bd-nodes').innerHTML=`<span class="dot dg"></span>Nodes: ${nodeCount}`;
    $('bd-pend').innerHTML=`<span class="dot ${Object.keys(pending).length?'do dp':'dg'}"></span>Pending: ${Object.keys(pending).length}`;
    renderRooms(); renderPending();
  }catch(e){ addLog('⚠️ Không đọc được /api/nodes',true); }
}

function setStep(id){
  ['s1','s2','s3','s4','s5'].forEach(x=>$(x).classList.toggle('active',x===id));
}
function updMeter(rms){
  $('mfill').style.width=Math.min(100,Math.max(0,(rms/6000)*100))+'%';
  $('mval').textContent=rms>300?`Đang nói (${rms})`:'Im lặng';
}

function connectSSE(){
  const es=new EventSource('/api/events');
  es.onopen=()=>{$('bd-gw').innerHTML='<span class="dot dg"></span>Gateway: Online';$('voice-card').style.display='';};
  es.addEventListener('init',e=>{ const d=JSON.parse(e.data); if(d.pending!==undefined){pending=d.pending;renderPending();} });

  es.addEventListener('pending_node',e=>{
    const d=JSON.parse(e.data); if(d.mac)pending[d.mac]=d.hello||{};
    renderPending();
    addLog(`📡 Node mới: ${d.mac} — cần đăng ký`,true);
  });
  es.addEventListener('pending_remove',e=>{
    const d=JSON.parse(e.data); if(d.mac)delete pending[d.mac]; renderPending(); loadAll();
  });
  es.addEventListener('node_provisioned',e=>{
    const d=JSON.parse(e.data); addLog(`✅ Provisioned: ${d.node_id}`,true); loadAll();
  });
  es.addEventListener('node_hello',e=>{ /* keepalive, không cần render liên tục */ });

  es.addEventListener('node_status',e=>{
    const d=JSON.parse(e.data);
    if(d.node_id && nodes[d.node_id]){
      if(d.online!==undefined) nodes[d.node_id].status=d.online?'online':'offline';
      if(d.rl_state){ nodes[d.node_id].relay_state=d.rl_state; }
      if(d.ch1!==undefined||d.ch2!==undefined){
        const rl=[d.ch1!==undefined?d.ch1:0,d.ch2!==undefined?d.ch2:0];
        if(!nodes[d.node_id].relay_state)nodes[d.node_id].relay_state=rl;
      }
    }
    renderRooms();
  });

  es.addEventListener('node_telemetry',e=>{
    const d=JSON.parse(e.data);
    if(d.node_id && nodes[d.node_id]){
      nodes[d.node_id].power=d.power; nodes[d.node_id].voltage=d.voltage;
    }
    // chỉ render telemetry kèm cập nhật relay_state nếu có
  });

  es.addEventListener('command_result',e=>{
    const d=JSON.parse(e.data);
    if(d.voice_reply) $('reply').textContent=`"${d.voice_reply}"`;
    if(d.engine) {
      $('bd-ai').innerHTML=`<span class="dot dg"></span>AI: ${d.engine}`;
      const s4sub=$('s4-sub'); if(s4sub) s4sub.textContent=d.engine;
    }
    if(d.fullname) addLog(`🤖 [${d.engine||'AI'}] ${d.fullname}: ${d.action} → ${d.verify}`);
    loadAll();
  });

  ['audio_state'].forEach(ev=>{
    es.addEventListener(ev,e=>{
      const d=JSON.parse(e.data), st=d.state;
      if(st==='RECORDING'){setStep('s2');updMeter(1200);}
      else if(st==='PROCESSING'){setStep('s3');updMeter(0);}
      else if(st==='PLAYING'){setStep('s5');}
      else if(st==='IDLE'){setStep('');updMeter(0);}
    });
  });
  es.addEventListener('transcript',e=>{const d=JSON.parse(e.data);$('trans').textContent=`"${d.text}"`;setStep('s4');});
  es.addEventListener('audio_meter',e=>{const d=JSON.parse(e.data);updMeter(d.rms);});

  es.onerror=()=>{ $('bd-gw').innerHTML='<span class="dot dr"></span>Gateway: Disconnected'; es.close(); setTimeout(connectSSE,3000); };
}

// doanh nghiệp: 1 datalist phòng phổ biến
window.addEventListener('DOMContentLoaded',()=>{
  document.body.insertAdjacentHTML('beforeend',`<datalist id="room-opt">
    <option value="livingroom"><option value="bedroom"><option value="kitchen"><option value="bathroom"><option value="balcony"><option value="garden">
    <option value="phong_khach"><option value="phong_ngu"><option value="phong_bep"></datalist>`);
  loadAll(); connectSSE();
  setInterval(loadAll,15000); // refresh định kỳ cho node tới
});
</script>
</body>
</html>
"""

# Đồng bộ: dữ liệu gốc (không cần thay đổi gì thêm)
class WebServer:
    """Async HTTP + SSE dashboard & node manager."""

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
            logger.info(f"🌐 Web Manager: http://{self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Web server failed on {self.port}: {e}")

    async def stop(self):
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Web server stopped")

    def broadcast_event(self, event_name: str, data: Dict[str, Any]):
        if not self.sse_queues: return
        payload = f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for q in list(self.sse_queues):
            try: q.put_nowait(payload)
            except Exception: pass

    # ── helpers ──
    def _nodes_snapshot(self) -> dict:
        r = self.gateway.registry
        return {
            "nodes": r.get_all_nodes(),
            "rooms": r.get_rooms(),
            "pending": r.get_pending(),
        }

    async def _handle_client(self, reader, writer):
        try:
            request_line = await reader.readline()
            if not request_line: writer.close(); return
            parts = request_line.decode("utf-8", errors="ignore").split()
            if len(parts) < 2: writer.close(); return
            method, path = parts[0].upper(), parts[1]

            headers = {}; content_length = 0
            while True:
                line = await reader.readline()
                if not line or line == b"\r\n": break
                ls = line.decode("utf-8", errors="ignore").strip()
                if ":" in ls:
                    k, v = ls.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
                    if k.strip().lower() == "content-length":
                        try: content_length = int(v.strip())
                        except ValueError: content_length = 0

            async def _read_body():
                if content_length > 0:
                    return await reader.readexactly(content_length)
                return b""

            # GET /
            if method == "GET" and path in ("/", "/index.html"):
                body = HTML_PAGE.encode("utf-8")
                resp = (f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode()+body
                writer.write(resp); await writer.drain(); writer.close(); return

            # GET /api/nodes
            if method == "GET" and path == "/api/nodes":
                data = self._nodes_snapshot()
                body = json.dumps(data, ensure_ascii=False).encode()
                resp = (f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                        f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                        f"Connection: close\r\n\r\n").encode()+body
                writer.write(resp); await writer.drain(); writer.close(); return

            # GET /api/events (SSE)
            if method == "GET" and path.startswith("/api/events"):
                writer.write(("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                              "Cache-Control: no-cache\r\nConnection: keep-alive\r\n"
                              "Access-Control-Allow-Origin: *\r\n\r\n").encode())
                await writer.drain()
                q = asyncio.Queue(maxsize=200)
                self.sse_queues.add(q)
                logger.info(f"SSE client connected (total {len(self.sse_queues)})")
                try:
                    # gửi init snapshot
                    snap = self._nodes_snapshot()
                    writer.write(f"event: init\ndata: {json.dumps(snap, ensure_ascii=False)}\n\n".encode())
                    await writer.drain()
                    while self._running:
                        msg = await q.get()
                        writer.write(msg.encode()); await writer.drain()
                except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
                    pass
                finally:
                    self.sse_queues.discard(q); writer.close()
                return

            # POST /api/relay
            if method == "POST" and path == "/api/relay":
                body = await _read_body()
                try:
                    data = json.loads(body.decode() or "{}")
                    node_id = data.get("node_id") or data.get("node")
                    channel = data.get("channel") or (f"ch{data['ch']}" if data.get("ch") in (1,2,"1","2") else None)
                    action = data.get("action")
                    s = data.get("s")
                    if action is None and s is not None:
                        action = "turn_on" if int(s)==1 else "turn_off"
                    if not node_id or not channel or not action:
                        resp_data = {"success": False, "error": "Thiếu node_id/channel/action"}
                    else:
                        # ưu tiên WS, fallback MQTT (verifier sử dụng audio_server nhưng ở đây gọi trực tiếp)
                        ok = False
                        r = self.gateway.registry
                        seq = r.next_seq(node_id)
                        if hasattr(self.gateway.audio_server, "has_ws") and self.gateway.audio_server.has_ws(node_id):
                            ok = await self.gateway.audio_server.send_relay_ws(node_id, channel, action, seq) if hasattr(self.gateway.audio_server,"send_relay_ws") else False
                        if not ok:
                            ok = await self.gateway.mqtt.send_command(node_id, channel, action, seq=seq)
                        resp_data = {"success": ok, "node_id": node_id, "channel": channel, "action": action}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                              f"Connection: close\r\n\r\n").encode()+body)
                await writer.drain(); writer.close(); return

            # POST /api/provision
            if method == "POST" and path == "/api/provision":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    mac = d.get("mac","").upper()
                    if not mac or mac not in self.gateway.registry.get_pending():
                        resp_data = {"success": False, "error": f"MAC {mac} không nằm trong pending"}
                    else:
                        res = await self.gateway.provision_pending(
                            mac, d.get("room",""), d.get("rl1",""), d.get("rl2",""),
                            node_short=d.get("node_short")
                        )
                        resp_data = res
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nAccess-Control-Allow-Origin: *\r\n"
                              f"Connection: close\r\n\r\n").encode()+body)
                await writer.drain(); writer.close(); return

            # POST /api/node/remove (xoá pending)
            if method == "POST" and path == "/api/node/remove":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    mac = d.get("mac","").upper()
                    r = self.gateway.registry
                    if mac in r.get_pending():
                        r.data["pending"].pop(mac, None)
                        r.save()
                        resp_data = {"success": True}
                    else:
                        resp_data = {"success": False, "error": "Không có trong pending"}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode()+body)
                await writer.drain(); writer.close(); return

            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            await writer.drain(); writer.close()
        except Exception as e:
            logger.debug(f"HTTP handler exception: {e}")
            try: writer.close()
            except Exception: pass

    # backwards compat với old broadcast ở main
    def _legacy_broadcast(self):
        pass