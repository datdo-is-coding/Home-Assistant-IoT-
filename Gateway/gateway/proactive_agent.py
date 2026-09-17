"""
Proactive Agent Daemon — Autonomous House Sentry & Lifelike Companion
======================================================================
1. Thu thập dữ liệu nền & ghi nhớ lâu dài vào SSD (SQLite smart_journal).
2. Canh gác an toàn (Safety Sentry): Cảnh báo khi bình nóng lạnh / thiết bị công suất cao chạy quá 30 phút.
3. Chủ động tương tác như người thật (Morning greeting, Night reminder, Random Singing/Banter).
4. Tuân thủ nghiêm ngặt giờ yên tĩnh (Quiet Hours 22:30 - 07:00) và cơ chế giãn cách (Cooldown).
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple

import config

logger = logging.getLogger("proactive_agent")
TZ_VN = timezone(timedelta(hours=7))

SPONTANEOUS_PROMPTS = [
    "🎶 Tình tính tang tang tính tình... Cuộc đời vẫn đẹp sao, tình yêu vẫn đẹp sao! Anh làm việc vất vả rồi, nhớ uống ngụm nước nghỉ ngơi chút nha! 🎵",
    "🎵 Một con vịt xòe ra hai cái cánh, nó kêu rằng cáp cáp cáp cạp cạp cạp... Em hát một câu tặng anh cho vui cửa vui nhà nhé! 😊",
    "🎶 Kìa con bướm vàng, kìa con bướm vàng, xòe đôi cánh, xòe đôi cánh... Em ngân nga chút cho ngôi nhà mình thêm ấm cúng nè anh!",
    "Hôm nay các thiết bị trong nhà mình đều hoạt động rất tốt và tiết kiệm điện đấy ạ. Anh có cần em hỗ trợ gì thêm không?",
    "Anh ơi, làm việc chăm chỉ nhưng cũng đừng quên giữ gìn sức khỏe nhé! Em luôn ở đây đồng hành cùng anh nè.",
    "Dạo này nhà mình ngăn nắp và ấm cúng ghê anh ha! Em rất vui khi được làm trợ lý cho gia đình mình đó ạ!"
]


class ProactiveAgent:
    """Tác vụ chạy ngầm quản lý hành vi tự chủ và tương tác chủ động của Gateway."""

    def __init__(self, gateway=None):
        self.gateway = gateway
        self._running = False
        self._task: Optional[asyncio.Task] = None

        self.last_speech_time: float = 0.0
        self.today_morning_greeted: Optional[str] = None
        self.today_evening_greeted: Optional[str] = None
        self.last_journal_time: float = 0.0

        # Theo dõi thời gian bật của các thiết bị công suất cao: (node_id, channel) -> start_time
        self._active_device_timers: Dict[Tuple[str, str], float] = {}

    @property
    def enabled(self) -> bool:
        return getattr(config, "PROACTIVE_ENABLED", True)

    @enabled.setter
    def enabled(self, val: bool):
        config.PROACTIVE_ENABLED = bool(val)

    def start(self):
        """Khởi chạy daemon chủ động."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._main_loop())
        logger.info("🚀 Proactive Agent started in background")

    async def stop(self):
        """Dừng daemon chủ động."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Proactive Agent stopped")

    def notify_user_activity(self, text: str = None):
        """Ghi nhận khi người dùng vừa ra lệnh hoặc tương tác để cập nhật trạng thái."""
        # Nếu là buổi sáng sớm và chưa chào, có thể kích hoạt lời chào sớm
        now = datetime.now(TZ_VN)
        today_str = now.date().isoformat()
        if 7 <= now.hour < 9 and self.today_morning_greeted != today_str:
            # Sẽ được xử lý trong vòng lặp tiếp theo
            pass

    async def _main_loop(self):
        """Vòng lặp định kỳ mỗi 30 giây để kiểm tra các điều kiện chủ động."""
        # Chờ 15s sau khi khởi động để hệ thống ổn định kết nối
        await asyncio.sleep(15)

        while self._running:
            try:
                now = datetime.now(TZ_VN)
                current_time = time.time()

                # 1. Tác vụ Ghi nhớ SSD (Mỗi 15 phút ghi snapshot một lần)
                if current_time - self.last_journal_time >= 900:
                    await self._record_ssd_snapshot(now)
                    self.last_journal_time = current_time

                # 2. Canh gác an toàn (Safety Sentry)
                await self._check_safety_sentry(current_time)

                # 3. Kiểm tra tương tác chủ động (Chào hỏi, Hát, Tâm sự)
                if getattr(config, "PROACTIVE_ENABLED", True):
                    await self._check_proactive_interaction(now, current_time)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in ProactiveAgent loop: {e}", exc_info=True)

            await asyncio.sleep(30)

    async def _record_ssd_snapshot(self, now: datetime):
        """Thu thập thông số hiện tại của nhà và ghi vào bộ nhớ SSD SQLite."""
        if not self.gateway or not hasattr(self.gateway, "memory") or not self.gateway.memory:
            return

        registry = getattr(self.gateway, "registry", None)
        active_nodes_count = 0
        active_relays_count = 0
        total_power = 0.0

        if registry:
            online_nodes = registry.get_online_nodes()
            active_nodes_count = len(online_nodes)
            for nid, node in online_nodes.items():
                r_states = node.get("relay_state", [0, 0])
                active_relays_count += sum(1 for s in r_states if s == 1)
                # Tính công suất ước tính hoặc từ cảm biến
                for cid, ch in node.get("channels", {}).items():
                    ch_idx = 0 if "1" in cid else 1
                    if ch_idx < len(r_states) and r_states[ch_idx] == 1:
                        total_power += ch.get("rated_watts", 40)

        notes = f"Đang hoạt động: {active_nodes_count} node, {active_relays_count} thiết bị bật. Tổng công suất: {total_power:.1f}W."
        self.gateway.memory.record_journal(
            notes=notes, total_power=total_power,
            active_nodes=active_nodes_count, active_relays=active_relays_count
        )
        logger.info(f"💾 [SSD Memory Journal] Recorded: {notes}")

        if hasattr(self.gateway, "broadcast_event"):
            self.gateway.broadcast_event("proactive_journal", {
                "timestamp": now.isoformat(),
                "notes": notes,
                "power": total_power
            })

    async def _check_safety_sentry(self, current_time: float):
        """Giám sát thiết bị công suất cao bật quá lâu để cảnh báo an toàn."""
        if not self.gateway or not hasattr(self.gateway, "registry"):
            return

        registry = self.gateway.registry
        online_nodes = registry.get_online_nodes()

        for nid, node in online_nodes.items():
            r_states = node.get("relay_state", [0, 0])
            for cid, ch in node.get("channels", {}).items():
                ch_idx = 0 if "1" in cid else 1
                is_on = (ch_idx < len(r_states) and r_states[ch_idx] == 1)
                key = (nid, cid)
                dev_type = str(ch.get("device_type", "")).lower()

                # Kiểm tra thiết bị cần giám sát: bình nóng lạnh, máy bơm, sưởi
                needs_watch = any(w in dev_type for w in ("binh_nong_lanh", "heater", "pump", "bom", "nuoc_nong"))

                if is_on and needs_watch:
                    if key not in self._active_device_timers:
                        self._active_device_timers[key] = current_time
                    else:
                        duration_mins = (current_time - self._active_device_timers[key]) / 60.0
                        # Nếu bật quá 35 phút liên tục
                        if duration_mins >= 35.0:
                            dev_name = ch.get("fullname", dev_type)
                            alert_text = f"Anh ơi, {dev_name} đã bật liên tục hơn 35 phút rồi. Em nhắc anh kiểm tra để đảm bảo an toàn và tiết kiệm điện nhé!"
                            logger.warning(f"⚠️ Safety Alert triggered: {alert_text}")
                            await self._speak_if_allowed(alert_text, event_type="safety_alert", node_id=nid)
                            # Reset timer sau khi cảnh báo để không lặp lại liên tục
                            self._active_device_timers[key] = current_time + 1800  # nhắc lại sau 30p nếu vẫn bật
                else:
                    self._active_device_timers.pop(key, None)

    async def _check_proactive_interaction(self, now: datetime, current_time: float):
        """Kiểm tra điều kiện để chủ động chào hỏi hoặc thi thoảng hát/trò chuyện."""
        hour = now.hour
        today_str = now.date().isoformat()

        # 1. Tuân thủ Quiet Hours: Không bao giờ nói chuyện bâng quơ lúc 22:30 - 07:00
        quiet_start = getattr(config, "PROACTIVE_QUIET_START", 22)
        quiet_end = getattr(config, "PROACTIVE_QUIET_END", 7)
        is_quiet = (hour >= quiet_start or hour < quiet_end)
        if is_quiet:
            return

        # 2. Lời chào buổi sáng (07:15 - 08:30)
        if 7 <= hour < 9 and self.today_morning_greeted != today_str:
            # Kiểm tra xem đã có node online nào hoạt động
            text = "Chào buổi sáng anh! Chúc anh một ngày mới tràn đầy năng lượng và làm việc thật vui vẻ nhé!"
            sent = await self._speak_if_allowed(text, event_type="morning_greeting", force=True)
            if sent:
                self.today_morning_greeted = today_str
                return

        # 3. Lời nhắc nghỉ ngơi buổi tối (21:45 - 22:25)
        if 21 <= hour < 23 and self.today_evening_greeted != today_str and now.minute >= 45:
            text = "Đã gần 10 giờ đêm rồi, anh nhớ chuẩn bị nghỉ ngơi sớm để giữ gìn sức khỏe nhé. Chúc anh ngủ ngon ạ!"
            sent = await self._speak_if_allowed(text, event_type="night_reminder", force=True)
            if sent:
                self.today_evening_greeted = today_str
                return

        # 4. Ngân nga hát hoặc trò chuyện ngẫu nhiên (Giữa 09:30 và 20:30)
        cooldown_sec = getattr(config, "PROACTIVE_COOLDOWN_HOURS", 2.0) * 3600
        if current_time - self.last_speech_time >= cooldown_sec:
            # Tỷ lệ 40% mỗi lần kiểm tra nếu đã đủ cooldown
            if random.random() < 0.40:
                speech = random.choice(SPONTANEOUS_PROMPTS)
                await self._speak_if_allowed(speech, event_type="spontaneous_banter")

    async def _speak_if_allowed(self, text: str, event_type: str = "banter",
                                node_id: str = None, force: bool = False) -> bool:
        """Phát âm thanh ra loa ESP32 nếu đủ điều kiện."""
        if not self.gateway or not hasattr(self.gateway, "audio_server"):
            return False

        current_time = time.time()
        # Cooldown tối thiểu giữa 2 lần phát bất kỳ là 15 phút (tránh nói liên tục)
        if not force and (current_time - self.last_speech_time < 900):
            return False

        audio_server = self.gateway.audio_server
        if not hasattr(audio_server, "speak_proactive"):
            return False

        logger.info(f"🗣️ [Proactive Speech] ({event_type}): {text}")
        success = await audio_server.speak_proactive(text, node_id=node_id)
        if success:
            self.last_speech_time = current_time
            # Ghi vào nhật ký bộ nhớ SSD
            if hasattr(self.gateway, "memory") and self.gateway.memory:
                self.gateway.memory.record_proactive_speech(event_type, text, node_id)
            if hasattr(self.gateway, "broadcast_event"):
                self.gateway.broadcast_event("proactive_speech", {
                    "event_type": event_type,
                    "text": text,
                    "timestamp": datetime.now(TZ_VN).isoformat()
                })
            return True
        return False
