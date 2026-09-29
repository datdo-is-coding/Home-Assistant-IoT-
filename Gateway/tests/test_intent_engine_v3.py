"""
Test Suite: Intent Engine v3 for Smart Home System
===================================================
Kiểm thử toàn diện 10 danh mục tính năng và Benchmark hiệu năng trên Pi 4:
1. Basic Commands
2. Temperature & Numbers (Số từ tiếng Việt)
3. Context Resolution & Multi-Turn (với TTL & kiểm tra ranh giới kế thừa)
4. ASR Phonetic Normalization
5. Negation Detection (Chặn triệt để lệnh phủ định)
6. Query vs Command (query_state, query_sensor)
7. Ambiguous Phrases & Slot Checking
8. Anti-Hallucination & Strict Validation
9. Multi-Command (Compound Sentences)
10. Latency Benchmark (< 5ms Fast-Path, < 1ms Context)
"""

import sys
import os
import asyncio
import time
import json
from typing import List, Dict, Any

# Thêm đường dẫn Gateway/gateway vào sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gateway"))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from intent_engine import IntentEngine, Target, IntentResult, ASRNormalizer, StrictValidator, slug
from registry_manager import RegistryManager


class MockRegistry:
    """Mock Registry phục vụ kiểm thử cô lập."""
    def allowed_rooms(self) -> List[str]:
        return ["phong_khach", "phong_ngu", "phong_ngu_master", "phong_bep", "phong_tam", "ban_cong", "san_vuon"]

    def allowed_devices(self) -> List[str]:
        return ["light", "fan", "air_conditioner", "pump", "curtain", "tivi", "binh_nong_lanh", "may_hut_mui"]


async def run_all_tests():
    print("=" * 70)
    print("🚀 BẮT ĐẦU TEST SUITE INTENT ENGINE V3 — KIỂM THỬ 10 DANH MỤC")
    print("=" * 70)

    registry = MockRegistry()
    engine = IntentEngine(registry=registry)

    passed_tests = 0
    total_tests = 0

    def assert_eq(actual, expected, msg=""):
        nonlocal passed_tests, total_tests
        total_tests += 1
        if actual == expected:
            passed_tests += 1
            print(f"  ✅ [PASS] {msg} -> {actual}")
        else:
            print(f"  ❌ [FAIL] {msg} -> Expected: {expected}, Got: {actual}")

    def assert_true(cond, msg=""):
        nonlocal passed_tests, total_tests
        total_tests += 1
        if cond:
            passed_tests += 1
            print(f"  ✅ [PASS] {msg}")
        else:
            print(f"  ❌ [FAIL] {msg}")

    # ── 1. BASIC COMMANDS ───────────────────────────────────────────────────
    print("\n--- 1. BASIC COMMANDS ---")
    r1 = await engine.extract("bật đèn phòng ngủ")
    assert_eq(r1.intent, "turn_on", "Bật đèn: intent=turn_on")
    assert_eq(r1.target.device_type, "light", "Bật đèn: device=light")
    assert_eq(r1.target.room, "phong_ngu", "Bật đèn: room=phong_ngu")
    assert_true(r1.confidence >= 0.95, "Bật đèn: confidence >= 0.95")
    # Kiểm tra tương thích ngược dictionary
    assert_eq(r1["command"]["action"], "turn_on", "Compat dict: action=turn_on")
    assert_eq(r1["command"]["device"], "light", "Compat dict: device=light")
    assert_eq(r1["command"]["location"], "phong_ngu", "Compat dict: location=phong_ngu")

    r2 = await engine.extract("tắt đèn phòng ngủ")
    assert_eq(r2.intent, "turn_off", "Tắt đèn: intent=turn_off")
    assert_eq(r2.target.device_type, "light", "Tắt đèn: device=light")
    assert_eq(r2.target.room, "phong_ngu", "Tắt đèn: room=phong_ngu")

    r3 = await engine.extract("bật quạt phòng khách")
    assert_eq(r3.intent, "turn_on", "Bật quạt phòng khách: intent=turn_on")
    assert_eq(r3.target.device_type, "fan", "Bật quạt phòng khách: device=fan")
    assert_eq(r3.target.room, "phong_khach", "Bật quạt phòng khách: room=phong_khach")

    r4 = await engine.extract("tắt quạt")
    assert_eq(r4.intent, "turn_off", "Tắt quạt: intent=turn_off")
    assert_eq(r4.target.device_type, "fan", "Tắt quạt: device=fan")

    r5 = await engine.extract("bật điều hòa")
    assert_eq(r5.intent, "turn_on", "Bật điều hòa: intent=turn_on")
    assert_eq(r5.target.device_type, "air_conditioner", "Bật điều hòa: device=air_conditioner")

    # ── 2. TEMPERATURE & NUMBERS (VIETNAMESE WORDS & DIGITS) ────────────────
    print("\n--- 2. TEMPERATURE & NUMBERS ---")
    t1 = await engine.extract("cài điều hòa 25 độ")
    assert_eq(t1.intent, "set_temperature", "Cài điều hòa 25 độ: intent=set_temperature")
    assert_eq(t1.value, 25, "Cài điều hòa 25 độ: value=25")
    assert_eq(t1.target.device_type, "air_conditioner", "Cài điều hòa 25 độ: device=air_conditioner")

    t2 = await engine.extract("đặt 26 độ")
    assert_eq(t2.intent, "set_temperature", "Đặt 26 độ: intent=set_temperature")
    assert_eq(t2.value, 26, "Đặt 26 độ: value=26")

    t3 = await engine.extract("cho điều hòa xuống 24 độ")
    assert_eq(t3.intent, "set_temperature", "Cho điều hòa xuống 24 độ: intent=set_temperature")
    assert_eq(t3.value, 24, "Cho điều hòa xuống 24 độ: value=24")

    t4 = await engine.extract("hai mươi lăm độ")
    assert_eq(t4.intent, "set_temperature", "Số từ 'hai mươi lăm độ': intent=set_temperature")
    assert_eq(t4.value, 25, "Số từ 'hai mươi lăm độ': value=25")

    t5 = await engine.extract("hai lăm độ")
    assert_eq(t5.value, 25, "Số từ 'hai lăm độ': value=25")

    t6 = await engine.extract("hai mươi tám độ")
    assert_eq(t6.value, 28, "Số từ 'hai mươi tám độ': value=28")

    # ── 3. CONTEXT RESOLUTION & MULTI-TURN (WITH TTL) ────────────────────────
    print("\n--- 3. MULTI-TURN CONTEXT RESOLUTION ---")
    engine.context_manager.clear()

    # Turn 1: Thiết lập ngữ cảnh
    c1 = await engine.extract("Bật điều hòa phòng ngủ")
    assert_eq(c1.target.device_type, "air_conditioner", "Turn 1: device=air_conditioner")
    assert_eq(c1.target.room, "phong_ngu", "Turn 1: room=phong_ngu")

    # Turn 2: Kế thừa slot từ Turn 1
    c2 = await engine.extract("Cài 25 độ")
    assert_eq(c2.intent, "set_temperature", "Turn 2: intent=set_temperature")
    assert_eq(c2.value, 25, "Turn 2: value=25")
    assert_eq(c2.target.device_type, "air_conditioner", "Turn 2: Kế thừa device=air_conditioner")
    assert_eq(c2.target.room, "phong_ngu", "Turn 2: Kế thừa room=phong_ngu")
    assert_eq(c2.source, "context", "Turn 2: source=context")

    # Turn 3: Tăng lên 26 độ
    c3 = await engine.extract("Tăng lên 26 độ")
    assert_eq(c3.value, 26, "Turn 3: value=26")
    assert_eq(c3.target.device_type, "air_conditioner", "Turn 3: device=air_conditioner")
    assert_eq(c3.target.room, "phong_ngu", "Turn 3: room=phong_ngu")

    # Turn 4: Đại từ "nó"
    c4 = await engine.extract("Tắt nó đi")
    assert_eq(c4.intent, "turn_off", "Turn 4: intent=turn_off")
    assert_eq(c4.target.device_type, "air_conditioner", "Turn 4: Đại từ 'nó' -> device=air_conditioner")
    assert_eq(c4.target.room, "phong_ngu", "Turn 4: Đại từ 'nó' -> room=phong_ngu")

    # Kiểm tra ranh giới kế thừa an toàn:
    # "Bật đèn phòng ngủ" -> "Bật quạt" (quạt KHÔNG được tự ý gán vào phòng ngủ nếu không nói)
    engine.context_manager.clear()
    await engine.extract("Bật đèn phòng ngủ")
    c5 = await engine.extract("Bật quạt")
    assert_true(c5.target.room != "phong_ngu", "Safety: Thiết bị mới (quạt) KHÔNG tự kế thừa room từ đèn")

    # Kiểm tra Context Expiry sau TTL
    engine.context_manager.clear()
    await engine.extract("Bật điều hòa phòng khách")
    # Mô phỏng quá hạn TTL
    engine.context_manager.updated_at = time.time() - 100.0  # > 60s
    c6 = await engine.extract("Cài 25 độ")
    assert_true(c6.source != "context", "TTL Expired: Lệnh thiếu slot KHÔNG được kế thừa khi context hết hạn")

    # ── 4. ASR PHONETIC NORMALIZATION ───────────────────────────────────────
    print("\n--- 4. ASR PHONETIC NORMALIZATION ---")
    a1 = await engine.extract("bạn bè phòng ngủ")
    assert_eq(a1.intent, "turn_on", "'bạn bè phòng ngủ' -> turn_on")
    assert_eq(a1.target.device_type, "light", "'bạn bè' -> light")
    assert_eq(a1.target.room, "phong_ngu", "'phòng ngủ' -> phong_ngu")

    a2 = await engine.extract("bất quá phòng khách")
    assert_eq(a2.intent, "turn_on", "'bất quá' -> turn_on")
    assert_eq(a2.target.device_type, "fan", "'bất quá' -> fan")
    assert_eq(a2.target.room, "phong_khach", "'phòng khách' -> phong_khach")

    a3 = await engine.extract("bật quà")
    assert_eq(a3.target.device_type, "fan", "'bật quà' -> fan")

    a4 = await engine.extract("máy lặng")
    assert_eq(a4.target.device_type, "air_conditioner", "'máy lặng' -> air_conditioner")

    a5 = await engine.extract("bật đèn phòng ngue")
    assert_eq(a5.target.room, "phong_ngu", "'phòng ngue' -> phong_ngu")

    # ── 5. NEGATION DETECTION ───────────────────────────────────────────────
    print("\n--- 5. NEGATION DETECTION ---")
    n1 = await engine.extract("đừng bật đèn")
    assert_true(n1.negated, "'đừng bật đèn': negated=True")
    assert_true(n1.intent != "turn_on", "'đừng bật đèn': KHÔNG được là turn_on")

    n2 = await engine.extract("không bật quạt")
    assert_true(n2.negated, "'không bật quạt': negated=True")
    assert_true(n2.intent != "turn_on", "'không bật quạt': KHÔNG được là turn_on")

    n3 = await engine.extract("tôi không muốn bật điều hòa")
    assert_true(n3.negated, "'tôi không muốn bật điều hòa': negated=True")
    assert_true(n3.intent != "turn_on", "'tôi không muốn bật điều hòa': KHÔNG được là turn_on")

    n4 = await engine.extract("trời nóng quá nhưng đừng bật điều hòa")
    assert_true(n4.negated, "'trời nóng quá nhưng đừng bật điều hòa': negated=True")
    assert_true(n4.intent != "turn_on", "'nhưng đừng bật': KHÔNG được tự ý bật điều hòa")

    # ── 6. QUERY VS COMMAND ─────────────────────────────────────────────────
    print("\n--- 6. QUERY VS COMMAND ---")
    q1 = await engine.extract("đèn phòng ngủ đang bật không")
    assert_eq(q1.intent, "query_state", "'đèn phòng ngủ đang bật không' -> query_state")
    assert_eq(q1.target.device_type, "light", "query_state: device=light")
    assert_eq(q1.target.room, "phong_ngu", "query_state: room=phong_ngu")

    q2 = await engine.extract("phòng ngủ bao nhiêu độ")
    assert_eq(q2.intent, "query_sensor", "'phòng ngủ bao nhiêu độ' -> query_sensor")
    assert_eq(q2.target.room, "phong_ngu", "query_sensor: room=phong_ngu")
    assert_eq(q2.value, "temperature", "query_sensor: value=temperature")

    q3 = await engine.extract("quạt phòng khách đang chạy không")
    assert_eq(q3.intent, "query_state", "'quạt phòng khách đang chạy không' -> query_state")
    assert_eq(q3.target.device_type, "fan", "query_state: device=fan")

    # ── 7. AMBIGUOUS & INCOMPLETE PHRASES ───────────────────────────────────
    print("\n--- 7. AMBIGUOUS & INCOMPLETE PHRASES ---")
    engine.context_manager.clear()
    amb1 = await engine.extract("bật nó lên")
    assert_true(amb1.needs_clarification, "'bật nó lên' khi không có context -> needs_clarification=True")

    amb2 = await engine.extract("cho mát một chút")
    assert_true(amb2.confidence < 0.95, "'cho mát một chút' -> confidence < 0.95 (MEDIUM)")

    # ── 8. ANTI-HALLUCINATION & STRICT VALIDATION ───────────────────────────
    print("\n--- 8. ANTI-HALLUCINATION & STRICT VALIDATION ---")
    validator = StrictValidator(registry=registry)

    # Thử nghiệm thiết bị và phòng bịa
    fake_intent = IntentResult(
        intent="turn_on",
        target=Target(device_type="robot_kitchen", room="phòng của ông ngoại"),
        confidence=0.95
    )
    validated = validator.validate(fake_intent)
    assert_true(validated.target.device_type is None, "Anti-hallucination: device 'robot_kitchen' -> None")
    assert_true(validated.target.room is None, "Anti-hallucination: room 'phòng của ông ngoại' -> None")
    assert_true(validated.needs_clarification, "Bị loại bỏ do hallucination -> needs_clarification=True")

    # ── 9. MULTI-COMMAND (COMPOUND SENTENCES) ───────────────────────────────
    print("\n--- 9. MULTI-COMMAND HANDLING ---")
    multi = await engine.extract("tắt đèn phòng ngủ và bật quạt phòng khách")
    assert_eq(multi.intent, "multi_command", "Compound command: intent=multi_command")
    assert_eq(len(multi.commands), 2, "Compound command: trích xuất 2 sub-commands")
    assert_eq(multi.commands[0]["command"]["action"], "turn_off", "Sub-command 1: turn_off")
    assert_eq(multi.commands[0]["command"]["device"], "light", "Sub-command 1: light")
    assert_eq(multi.commands[0]["command"]["location"], "phong_ngu", "Sub-command 1: phong_ngu")
    assert_eq(multi.commands[1]["command"]["action"], "turn_on", "Sub-command 2: turn_on")
    assert_eq(multi.commands[1]["command"]["device"], "fan", "Sub-command 2: fan")
    assert_eq(multi.commands[1]["command"]["location"], "phong_khach", "Sub-command 2: phong_khach")

    # ── 10. LATENCY BENCHMARK ON FAST-PATH ──────────────────────────────────
    print("\n--- 10. LATENCY BENCHMARK ---")
    test_cases = [
        "bật đèn phòng ngủ",
        "tắt quạt phòng khách",
        "cài điều hòa 25 độ",
        "bạn bè phòng khách",
        "đèn phòng ngủ đang bật không"
    ]

    # Benchmark Fast Path
    n_runs = 200
    t_start = time.perf_counter()
    for _ in range(n_runs):
        for tc in test_cases:
            await engine.extract(tc)
    t_total = time.perf_counter() - t_start
    avg_fast_path_ms = (t_total / (n_runs * len(test_cases))) * 1000

    print(f"  ⚡ Fast-Path Average Latency ({n_runs * len(test_cases)} iterations): {avg_fast_path_ms:.3f} ms")
    assert_true(avg_fast_path_ms < 5.0, f"Fast-Path Latency < 5ms Target (Actual: {avg_fast_path_ms:.3f} ms)")

    # Benchmark Context Resolution (< 1ms target)
    engine.context_manager.clear()
    await engine.extract("Bật điều hòa phòng ngủ")
    sample_raw = IntentResult(
        intent="set_temperature",
        target=Target(),
        value=26,
        confidence=0.45,
        source="fast_path"
    )
    t_start = time.perf_counter()
    for _ in range(1000):
        engine.context_manager.resolve(sample_raw, "Tăng lên 26 độ")
    avg_context_ms = ((time.perf_counter() - t_start) / 1000) * 1000
    print(f"  🧠 Pure Context Resolution Average Latency (1000 iterations): {avg_context_ms:.4f} ms")
    assert_true(avg_context_ms < 1.0, f"Context Resolution Latency < 1ms Target (Actual: {avg_context_ms:.4f} ms)")

    # Benchmark Registry Resolution / Strict Validator (< 5ms target)
    sample_intent = IntentResult(
        intent="turn_on",
        target=Target(device_type="light", room="phong_ngu"),
        confidence=0.98
    )
    t_start = time.perf_counter()
    for _ in range(1000):
        engine.validator.validate(sample_intent)
    avg_registry_ms = ((time.perf_counter() - t_start) / 1000) * 1000
    print(f"  🛡️ Strict Validator / Registry Latency (1000 iterations): {avg_registry_ms:.4f} ms")
    assert_true(avg_registry_ms < 5.0, f"Registry Resolution Latency < 5ms Target (Actual: {avg_registry_ms:.4f} ms)")

    # ── TỔNG KẾT TEST ───────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"📊 KẾT QUẢ TEST: {passed_tests}/{total_tests} PASSED ({passed_tests/total_tests*100:.1f}%)")
    print("=" * 70)
    return passed_tests == total_tests


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
