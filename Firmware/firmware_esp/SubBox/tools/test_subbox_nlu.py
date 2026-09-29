#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SubBox NLU Automated Test Suite & Interactive Tool
Aetheria OS / Smart Home IoT Architecture

Supports:
1. Live Hardware Mode: Communicates with ESP32-S3 SubBox over Serial/UART (COM port)
2. Offline Emulation Mode: 100% faithful Python port of SubBox C++ NLU algorithms
   (VietnameseNormalizer, IntentParser, EntityExtractor, ContextManager)
   Allows running extensive automated tests without needing hardware plugged in.
3. Interactive Console: Type commands and see real-time parsing & routing.
"""

import sys
import os
import re
import time
import argparse
from enum import Enum
from typing import Optional, Tuple, Dict, Any, List

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Colors for terminal output
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ============================================================================
# 1. ENUMS & DATA STRUCTURES (Exact match to SubBox C++ headers)
# ============================================================================

class IntentType(Enum):
    TURN_ON = "TURN_ON"
    TURN_OFF = "TURN_OFF"
    TOGGLE = "TOGGLE"
    SET_TEMPERATURE = "SET_TEMPERATURE"
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    QUERY_STATE = "QUERY_STATE"
    QUERY_CURRENT = "QUERY_CURRENT"
    QUERY_POWER = "QUERY_POWER"
    STOP = "STOP"
    UNKNOWN = "UNKNOWN"
    COMPLEX = "COMPLEX"

class DeviceType(Enum):
    LIGHT = "LIGHT"
    FAN = "FAN"
    AIR_CONDITIONER = "AIR_CONDITIONER"
    SOCKET = "SOCKET"
    OTHER = "OTHER"
    NONE = "NONE"

class RoomType(Enum):
    BEDROOM = "BEDROOM"
    LIVING_ROOM = "LIVING_ROOM"
    KITCHEN = "KITCHEN"
    BALCONY = "BALCONY"
    PORCH = "PORCH"
    OUTDOOR = "OUTDOOR"
    OTHER = "OTHER"
    UNSPECIFIED = "UNSPECIFIED"

# ============================================================================
# 2. SUBBOX NLU PYTHON EMULATOR (1:1 with SubBox C++ Implementation)
# ============================================================================

class VietnameseNormalizer:
    @staticmethod
    def normalize(text: str) -> str:
        if not text:
            return ""
        s = text.lower().strip()
        # Canonicalize common synonyms & ASR speech variations
        s = re.sub(r"\bđiều hoà\b", "điều hòa", s)
        s = re.sub(r"\bmở\b", "bật", s)
        s = re.sub(r"\bđóng\b", "tắt", s)
        s = re.sub(r"\bngắt\b", "tắt", s)
        s = re.sub(r"\bkhởi động\b", "bật", s)
        # Remove punctuation
        s = re.sub(r"[,\.\?!;:\(\)\[\]\"']", " ", s)
        # Collapse spaces
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @staticmethod
    def contains_word(haystack: str, needle: str) -> bool:
        pattern = r"(?<!\w)" + re.escape(needle) + r"(?!\w)"
        return bool(re.search(pattern, haystack, re.IGNORECASE))

class IntentParser:
    COMPLEX_INDICATORS = [
        "nếu ", " khi ", "thì ", "hẹn giờ", "lịch trình", "mỗi ngày", "lúc mấy giờ",
        "tự động", "kịch bản", "về nhà", "đi ngủ", "sau khi", "trước khi",
        "hôm qua", "tuần trước", "tháng trước", "trên 30 độ thì", "dưới 20 độ thì"
    ]

    @classmethod
    def is_complex_command(cls, text: str) -> bool:
        for ind in cls.COMPLEX_INDICATORS:
            if ind in text:
                return True
        return False

    @classmethod
    def parse(cls, norm_text: str) -> IntentType:
        if not norm_text:
            return IntentType.UNKNOWN

        # 1. Complex Condition Detection -> Forward to Pi4
        if cls.is_complex_command(norm_text):
            return IntentType.COMPLEX

        # 2. Query Power / Current / State
        if any(w in norm_text for w in ["công suất", "tiêu thụ", "watt", "oát"]):
            return IntentType.QUERY_POWER

        if any(w in norm_text for w in ["dòng điện", "ampe", "miliampe"]):
            return IntentType.QUERY_CURRENT

        if any(w in norm_text for w in ["trạng thái", "đang bật hay tắt", "đang chạy không", "bật không", "tắt chưa"]):
            return IntentType.QUERY_STATE

        # 3. Temperature Setting
        has_temp_word = (VietnameseNormalizer.contains_word(norm_text, "nhiệt độ") or 
                         VietnameseNormalizer.contains_word(norm_text, "độ"))
        has_set_word = any(VietnameseNormalizer.contains_word(norm_text, w) for w in ["đặt", "chỉnh", "cài", "set", "cho"])
        if has_temp_word and has_set_word:
            return IntentType.SET_TEMPERATURE

        # 4. Increase / Decrease
        if any(w in norm_text for w in ["tăng ", "mạnh hơn", "nhanh hơn", "lên một chút"]):
            return IntentType.INCREASE

        if any(w in norm_text for w in ["giảm ", "yếu hơn", "chậm lại", "xuống một chút"]):
            return IntentType.DECREASE

        if any(w in norm_text for w in ["dừng", "ngừng"]):
            return IntentType.STOP

        # 5. On / Off / Toggle
        if any(w in norm_text for w in ["đổi trạng thái", "chuyển trạng thái", "đảo"]):
            return IntentType.TOGGLE

        if any(w in norm_text for w in ["bật", "bật lên", "bật giùm", "bật hộ"]):
            return IntentType.TURN_ON

        if any(w in norm_text for w in ["tắt", "tắt đi", "tắt giùm", "tắt hộ"]):
            return IntentType.TURN_OFF

        return IntentType.UNKNOWN

class EntityExtractor:
    @staticmethod
    def extract_device(text: str) -> DeviceType:
        if any(w in text for w in ["điều hòa", "máy lạnh", "ac", "nhiệt độ"]):
            return DeviceType.AIR_CONDITIONER
        if any(w in text for w in ["quạt", "quạt trần", "quạt cây", "quạt đứng", "quạt thông gió"]):
            return DeviceType.FAN
        if any(w in text for w in ["đèn", "bóng đèn", "đèn ngủ", "đèn chùm", "chiếu sáng"]):
            return DeviceType.LIGHT
        if any(w in text for w in ["ổ cắm", "công tắc", "nguồn"]):
            return DeviceType.SOCKET
        if "thiết bị" in text:
            return DeviceType.OTHER
        return DeviceType.NONE

    @staticmethod
    def extract_room(text: str) -> RoomType:
        if "phòng khách" in text:
            return RoomType.LIVING_ROOM
        if "phòng ngủ" in text:
            return RoomType.BEDROOM
        if any(w in text for w in ["phòng bếp", "nhà bếp", "bếp"]):
            return RoomType.KITCHEN
        if "ban công" in text:
            return RoomType.BALCONY
        if any(w in text for w in ["hiên", "hành lang"]):
            return RoomType.PORCH
        if any(w in text for w in ["sân", "vườn", "ngoài trời"]):
            return RoomType.OUTDOOR
        return RoomType.UNSPECIFIED

    @staticmethod
    def extract_numeric_value(text: str) -> Tuple[bool, float]:
        # 1. Digits
        match = re.search(r"(\d+(\.\d+)?)", text)
        if match:
            return True, float(match.group(1))

        # 2. Spoken numbers in Vietnamese
        spoken = [
            ("mười sáu", 16.0), ("mười bảy", 17.0), ("mười tám", 18.0), ("mười chín", 19.0),
            ("hai mươi lăm", 25.0), ("hai lăm", 25.0), ("hai mươi", 20.0), ("hai mốt", 21.0),
            ("hai hai", 22.0), ("hai ba", 23.0), ("hai tư", 24.0), ("hai bốn", 24.0),
            ("hai sáu", 26.0), ("hai bảy", 27.0), ("hai tám", 28.0), ("hai chín", 29.0),
            ("ba mươi", 30.0), ("ba mốt", 31.0), ("ba hai", 32.0)
        ]
        for w, val in spoken:
            if w in text:
                return True, val

        return False, 0.0

class ContextManager:
    def __init__(self, subbox_room: RoomType = RoomType.LIVING_ROOM):
        self.subbox_room = subbox_room
        self.last_device = DeviceType.NONE
        self.last_target_room = RoomType.UNSPECIFIED
        self.last_intent = IntentType.UNKNOWN
        self.last_value = 0.0
        self.has_history = False

    def resolve(self, raw_text: str, origin_node_id: str, intent: IntentType, 
                device: DeviceType, room: RoomType, has_val: bool, val: float) -> Dict[str, Any]:
        target_room = room if room != RoomType.UNSPECIFIED else self.subbox_room
        res_device = device
        resolved_via_context = False
        is_valid = True
        error_reason = ""

        # Pronoun check ("nó", "lại", "đó", "cái đó")
        has_pronoun = any(p in raw_text for p in [" nó", " lại", " đó", "cái đó"])
        
        if res_device == DeviceType.NONE:
            if has_pronoun and self.has_history and self.last_device != DeviceType.NONE:
                res_device = self.last_device
                resolved_via_context = True
                if room == RoomType.UNSPECIFIED and self.last_target_room != RoomType.UNSPECIFIED:
                    target_room = self.last_target_room
            elif intent in [IntentType.INCREASE, IntentType.DECREASE, IntentType.STOP]:
                if self.has_history and self.last_device != DeviceType.NONE:
                    res_device = self.last_device
                    resolved_via_context = True
                else:
                    is_valid = False
                    error_reason = "Không rõ thiết bị nào cần điều chỉnh"
            elif intent == IntentType.COMPLEX:
                res_device = DeviceType.NONE
                is_valid = True
            else:
                is_valid = False
                error_reason = "Không xác định được thiết bị mục tiêu"

        return {
            "intent": intent,
            "device": res_device,
            "target_room": target_room,
            "speaker_room": self.subbox_room,
            "origin_node_id": origin_node_id,
            "has_value": has_val,
            "value": val,
            "resolved_via_context": resolved_via_context,
            "is_valid": is_valid,
            "error_reason": error_reason
        }

    def commit(self, resolution: Dict[str, Any]):
        if resolution["is_valid"] and resolution["device"] != DeviceType.NONE:
            self.last_device = resolution["device"]
            self.last_target_room = resolution["target_room"]
            self.last_intent = resolution["intent"]
            self.has_history = True

# ============================================================================
# 3. TEST SUITE & RUNNER
# ============================================================================

def run_offline_unit_tests():
    print(f"\n{BOLD}{CYAN}=============================================================={RESET}")
    print(f"{BOLD}{CYAN}      RUNNING SUBBOX C++ NLU TEST SUITE (OFFLINE EMULATION)   {RESET}")
    print(f"{BOLD}{CYAN}=============================================================={RESET}\n")

    cases = [
        # Phrase, Expected Intent, Expected Device, Expected Room
        ("bật đèn phòng khách", IntentType.TURN_ON, DeviceType.LIGHT, RoomType.LIVING_ROOM),
        ("tắt quạt phòng ngủ", IntentType.TURN_OFF, DeviceType.FAN, RoomType.BEDROOM),
        ("bật điều hòa", IntentType.TURN_ON, DeviceType.AIR_CONDITIONER, RoomType.LIVING_ROOM),
        ("chỉnh nhiệt độ 26 độ", IntentType.SET_TEMPERATURE, DeviceType.AIR_CONDITIONER, RoomType.LIVING_ROOM),
        ("bật đèn phòng bếp", IntentType.TURN_ON, DeviceType.LIGHT, RoomType.KITCHEN),
        ("nếu nhiệt độ phòng khách trên 30 độ thì bật quạt", IntentType.COMPLEX, DeviceType.NONE, RoomType.LIVING_ROOM),
        ("công suất tiêu thụ của đèn", IntentType.QUERY_POWER, DeviceType.LIGHT, RoomType.LIVING_ROOM),
        ("kiểm tra trạng thái quạt", IntentType.QUERY_STATE, DeviceType.FAN, RoomType.LIVING_ROOM),
        ("mở quạt cây", IntentType.TURN_ON, DeviceType.FAN, RoomType.LIVING_ROOM),
        ("đóng công tắc", IntentType.TURN_OFF, DeviceType.SOCKET, RoomType.LIVING_ROOM),
        ("đặt điều hòa hai mươi lăm độ", IntentType.SET_TEMPERATURE, DeviceType.AIR_CONDITIONER, RoomType.LIVING_ROOM),
        ("giảm quạt xuống một chút", IntentType.DECREASE, DeviceType.FAN, RoomType.LIVING_ROOM),
    ]

    passed = 0
    total = len(cases)
    context_mgr = ContextManager(RoomType.LIVING_ROOM)

    for idx, (phrase, exp_intent, exp_dev, exp_room) in enumerate(cases, 1):
        norm = VietnameseNormalizer.normalize(phrase)
        intent = IntentParser.parse(norm)
        dev = EntityExtractor.extract_device(norm)
        room = EntityExtractor.extract_room(norm)
        has_num, num_val = EntityExtractor.extract_numeric_value(norm)

        res = context_mgr.resolve(norm, "TEST_HARNESS", intent, dev, room, has_num, num_val)

        intent_ok = (res["intent"] == exp_intent)
        dev_ok = (exp_dev == DeviceType.NONE) or (res["device"] == exp_dev)
        room_ok = (res["target_room"] == exp_room)

        if intent_ok and dev_ok and room_ok:
            passed += 1
            print(f"  {GREEN}✅ [PASS]{RESET} Test {idx:02d}: \"{phrase}\" -> Intent={res['intent'].value}, Dev={res['device'].value}, Room={res['target_room'].value}")
            context_mgr.commit(res)
        else:
            print(f"  {RED}❌ [FAIL]{RESET} Test {idx:02d}: \"{phrase}\"")
            print(f"         Expected: Intent={exp_intent.value}, Dev={exp_dev.value}, Room={exp_room.value}")
            print(f"         Actual  : Intent={res['intent'].value}, Dev={res['device'].value}, Room={res['target_room'].value}")

    # Pronoun Context Resolution Test ("tắt nó")
    print(f"\n{BOLD}--- Testing Multi-Turn Pronoun Context Resolution (\"tắt nó\") ---{RESET}")
    # Turn 1: Bật quạt phòng ngủ
    s1 = VietnameseNormalizer.normalize("bật quạt phòng ngủ")
    r1 = context_mgr.resolve(s1, "TEST", IntentParser.parse(s1), 
                             EntityExtractor.extract_device(s1), 
                             EntityExtractor.extract_room(s1), False, 0.0)
    context_mgr.commit(r1)

    # Turn 2: "tắt nó"
    s2 = VietnameseNormalizer.normalize("tắt nó")
    r2 = context_mgr.resolve(s2, "TEST", IntentParser.parse(s2), 
                             EntityExtractor.extract_device(s2), 
                             EntityExtractor.extract_room(s2), False, 0.0)

    total += 1
    if r2["intent"] == IntentType.TURN_OFF and r2["device"] == DeviceType.FAN and \
       r2["target_room"] == RoomType.BEDROOM and r2["resolved_via_context"]:
        passed += 1
        print(f"  {GREEN}✅ [PASS]{RESET} Multi-Turn: \"bật quạt phòng ngủ\" -> \"tắt nó\" resolved to TURN_OFF FAN in BEDROOM (Context Active)")
    else:
        print(f"  {RED}❌ [FAIL]{RESET} Multi-Turn: \"tắt nó\" failed! Dev={r2['device'].value}, Room={r2['target_room'].value}")

    print(f"\n{BOLD}{CYAN}=============================================================={RESET}")
    print(f"{BOLD}   SubBox NLU Summary: {passed} / {total} Tests Passed ({passed/total*100:.1f}%){RESET}")
    print(f"{BOLD}{CYAN}=============================================================={RESET}\n")

def run_interactive_mode():
    print(f"\n{BOLD}{YELLOW}SubBox Interactive NLU Console (Type 'exit' to quit){RESET}")
    print("Example: 'bật đèn phòng khách', 'tắt nó', 'chỉnh 25 độ', 'công suất quạt'\n")
    context_mgr = ContextManager(RoomType.LIVING_ROOM)

    while True:
        try:
            line = input(f"{BOLD}SubBox NLU > {RESET}").strip()
            if not line:
                continue
            if line.lower() in ["exit", "quit", "q"]:
                break

            norm = VietnameseNormalizer.normalize(line)
            intent = IntentParser.parse(norm)
            dev = EntityExtractor.extract_device(norm)
            room = EntityExtractor.extract_room(norm)
            has_num, num_val = EntityExtractor.extract_numeric_value(norm)

            res = context_mgr.resolve(norm, "CONSOLE", intent, dev, room, has_num, num_val)

            print(f"  {CYAN}Normalized   :{RESET} {norm}")
            print(f"  {CYAN}Intent       :{RESET} {res['intent'].value}")
            print(f"  {CYAN}Device       :{RESET} {res['device'].value}")
            print(f"  {CYAN}Target Room  :{RESET} {res['target_room'].value}")
            print(f"  {CYAN}Context Used :{RESET} {'YES (Đại từ/Kế thừa)' if res['resolved_via_context'] else 'NO'}")
            if res["has_value"]:
                print(f"  {CYAN}Numeric Value:{RESET} {res['value']}")
            print(f"  {CYAN}Status       :{RESET} {GREEN + 'VALID' if res['is_valid'] else RED + 'INVALID: ' + res['error_reason']}{RESET}\n")

            if res["is_valid"]:
                context_mgr.commit(res)

        except (KeyboardInterrupt, EOFError):
            break

def run_serial_hardware_test(port: str, baud: int = 115200):
    try:
        import serial
    except ImportError:
        print(f"{RED}[ERROR] Thư viện 'pyserial' chưa được cài đặt. Chạy: pip install pyserial{RESET}")
        return

    print(f"{CYAN}Đang kết nối tới SubBox trên cổng {port} @ {baud} baud...{RESET}")
    try:
        ser = serial.Serial(port, baud, timeout=1.0)
        ser.dtr = False
        ser.rts = False
        time.sleep(1)
        print(f"{GREEN}>>> Kết nối thành công! Đang gửi lệnh TEST_NLU...{RESET}\n")

        ser.write(b"TEST_NLU\r\n")
        ser.flush()

        start = time.time()
        while time.time() - start < 5.0:
            line = ser.readline().decode("utf-8", errors="replace").strip()
            if line:
                print(line)
                if "Summary:" in line or "Tests Passed" in line:
                    break

        ser.close()
    except Exception as e:
        print(f"{RED}[ERROR] Lỗi kết nối Serial: {e}{RESET}")

def main():
    parser = argparse.ArgumentParser(description="SubBox NLU Testing & Evaluation Tool")
    parser.add_argument("--test", action="store_true", help="Chạy bộ unit test tự động (Offline mode)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Chạy chế độ tương tác gõ lệnh thủ công")
    parser.add_argument("--port", "-p", type=str, default=None, help="Cổng COM để test trực tiếp trên phần cứng SubBox (ví dụ: COM9)")

    args = parser.parse_args()

    if args.port:
        run_serial_hardware_test(args.port)
    elif args.interactive:
        run_interactive_mode()
    else:
        run_offline_unit_tests()

if __name__ == "__main__":
    main()
