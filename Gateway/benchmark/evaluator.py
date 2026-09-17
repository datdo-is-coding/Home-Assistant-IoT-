"""
Hệ Thống Đánh Giá & Đo Lường Độ Chính Xác Toàn Diện Cho Smart Home LLM NLU.
Đánh giá độ chính xác (Accuracy), Chống ảo giác (Anti-Hallucination),
Khả năng hiểu khẩu ngữ (Dialect), và Độ trễ (Latency).
"""

import os
import sys
import time
import json
import asyncio
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# Thêm đường dẫn gateway vào sys.path
GATEWAY_DIR = Path(__file__).resolve().parent.parent / "gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from dataset import TEST_CASES
from registry_manager import RegistryManager, slug
from intent_engine import IntentEngine
import config


def format_table_row(cols: List[str], widths: List[int]) -> str:
    parts = [col.ljust(w) for col, w in zip(cols, widths)]
    return " | ".join(parts)


class BenchmarkRunner:
    def __init__(self, mode: str = "local", output_dir: Optional[str] = None):
        self.mode = mode.lower()
        self.registry = RegistryManager()
        self.intent_engine = IntentEngine(registry=self.registry)
        self.output_dir = Path(output_dir) if output_dir else Path(__file__).resolve().parent / "reports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def evaluate_single(self, tc: Dict[str, Any]) -> Dict[str, Any]:
        """Chạy kiểm thử một câu khẩu lệnh duy nhất."""
        user_text = tc["input"]
        t0 = time.time()
        
        # Chọn engine kiểm thử
        raw_intent = None
        error_msg = None
        engine_name = "Unknown"
        
        try:
            if self.mode == "local":
                engine_name = "Qwen2.5-3B (Local)"
                raw_intent = await self.intent_engine._extract_local(user_text)
            elif self.mode == "cloud":
                engine_name = "Gemini 1.5 Flash (Cloud)"
                raw_intent = await self.intent_engine._extract_gemini(user_text, config.GEMINI_API_KEY)
            else:
                raw_intent = await self.intent_engine.extract(user_text)
                engine_name = getattr(self.intent_engine, "active_engine", "Hybrid")
        except Exception as e:
            error_msg = str(e)
            
        latency = time.time() - t0

        # Phân tích kết quả trích xuất
        pred_action = None
        pred_device = None
        pred_location = None
        pred_node = None
        pred_channel = None
        resolved = False

        if raw_intent and isinstance(raw_intent, dict) and "command" in raw_intent:
            cmd = raw_intent["command"]
            pred_action = cmd.get("action")
            pred_device = cmd.get("device")
            pred_location = cmd.get("location")
            
            # Chuẩn hoá slug để so khớp
            pred_device = slug(pred_device) if pred_device else None
            pred_location = slug(pred_location) if pred_location else None

            # Phân giải Registry Resolver (Lớp 2)
            lookup = self.registry.find_node_by_device(pred_device, pred_location)
            if lookup:
                pred_node, pred_channel = lookup
                resolved = True

        # So khớp Ground Truth
        exp_action = tc.get("expected_action")
        exp_device = tc.get("expected_device")
        exp_location = tc.get("expected_location")
        exp_resolve = tc.get("should_resolve", False)
        exp_node = tc.get("expected_node")
        exp_channel = tc.get("expected_channel")

        # Tiêu chí chấm điểm
        action_match = (pred_action == exp_action)
        
        # Device match: chấp nhận biến thể hoặc alias (den_ngu match den, quat_ngu match quat)
        device_match = False
        if pred_device == exp_device:
            device_match = True
        elif pred_device and exp_device and (exp_device in pred_device or pred_device in exp_device):
            device_match = True

        # Location match: chấp nhận biến thể (phong_ngu match phong_ngu_master)
        location_match = False
        if pred_location == exp_location:
            location_match = True
        elif pred_location and exp_location and (exp_location in pred_location or pred_location in exp_location):
            location_match = True

        # Strict Intent Match (Cả 3 thuộc tính đồng thời đúng)
        strict_intent_match = action_match and device_match and location_match

        # Resolver Match (Đích đến phần cứng đúng)
        resolver_match = False
        if exp_resolve:
            resolver_match = resolved and (pred_node == exp_node) and (pred_channel == exp_channel)
        else:
            resolver_match = (resolved == False)

        return {
            "id": tc["id"],
            "category": tc["category"],
            "input": user_text,
            "latency": latency,
            "engine": engine_name,
            "raw_intent": raw_intent,
            "error": error_msg,
            "predicted": {
                "action": pred_action,
                "device": pred_device,
                "location": pred_location,
                "node": pred_node,
                "channel": pred_channel,
                "resolved": resolved
            },
            "expected": {
                "action": exp_action,
                "device": exp_device,
                "location": exp_location,
                "node": exp_node,
                "channel": exp_channel,
                "should_resolve": exp_resolve
            },
            "scores": {
                "action_match": action_match,
                "device_match": device_match,
                "location_match": location_match,
                "strict_intent_match": strict_intent_match,
                "resolver_match": resolver_match
            }
        }

    async def run_benchmark(
        self,
        category: Optional[str] = None,
        quick: bool = False,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Chạy toàn bộ hoặc một phần bộ benchmark."""
        cases = TEST_CASES

        # Lọc danh mục nếu được chỉ định
        if category and category.lower() != "all":
            cases = [tc for tc in cases if tc["category"].lower() == category.lower()]

        # Chế độ Quick: Chọn đại diện 2 mẫu cho mỗi nhóm danh mục (tổng ~14 test cases)
        if quick:
            by_cat = {}
            for tc in cases:
                by_cat.setdefault(tc["category"], []).append(tc)
            selected = []
            for cat, cat_cases in by_cat.items():
                selected.extend(cat_cases[:2])
            cases = selected

        # Giới hạn số lượng nếu có
        if limit and limit > 0:
            cases = cases[:limit]

        total = len(cases)
        print("=" * 80)
        print(f"🚀 BẮT ĐẦU BENCHMARK NLU — MODE: [{self.mode.upper()}] — TỔNG CỘNG: {total} TEST CASES")
        print("=" * 80)

        results = []
        latencies = []

        widths = [8, 12, 35, 10, 10, 8]
        print(format_table_row(["MÃ", "DANH MỤC", "CÂU LỆNH ĐẦU VÀO", "INTENT", "RESOLVE", "THỜI GIAN"], widths))
        print("-" * 90)

        for i, tc in enumerate(cases, 1):
            res = await self.evaluate_single(tc)
            results.append(res)
            lat = res["latency"]
            latencies.append(lat)

            scores = res["scores"]
            intent_icon = "✅ ĐÚNG" if scores["strict_intent_match"] else "❌ SAI"
            resolve_icon = "✅ ĐÚNG" if scores["resolver_match"] else "❌ SAI"

            input_truncated = (tc["input"][:32] + "...") if len(tc["input"]) > 32 else tc["input"]
            print(format_table_row(
                [tc["id"], tc["category"], input_truncated, intent_icon, resolve_icon, f"{lat:.2f}s"],
                widths
            ))

        # ── Tổng hợp thống kê số liệu ──
        summary = self._calculate_metrics(results, latencies)
        self._print_summary(summary)
        self._save_reports(summary, results)
        return {"summary": summary, "details": results}

    def _calculate_metrics(self, results: List[Dict[str, Any]], latencies: List[float]) -> Dict[str, Any]:
        total = len(results)
        if total == 0:
            return {}

        correct_action = sum(1 for r in results if r["scores"]["action_match"])
        correct_device = sum(1 for r in results if r["scores"]["device_match"])
        correct_location = sum(1 for r in results if r["scores"]["location_match"])
        strict_intent = sum(1 for r in results if r["scores"]["strict_intent_match"])
        correct_resolver = sum(1 for r in results if r["scores"]["resolver_match"])

        # Phân tích theo từng danh mục
        categories = {}
        for r in results:
            cat = r["category"]
            c_dict = categories.setdefault(cat, {
                "total": 0, "strict_intent": 0, "resolver": 0, "latencies": []
            })
            c_dict["total"] += 1
            if r["scores"]["strict_intent_match"]:
                c_dict["strict_intent"] += 1
            if r["scores"]["resolver_match"]:
                c_dict["resolver"] += 1
            c_dict["latencies"].append(r["latency"])

        for cat, d in categories.items():
            t = d["total"]
            d["strict_acc"] = (d["strict_intent"] / t) * 100 if t else 0
            d["resolver_acc"] = (d["resolver"] / t) * 100 if t else 0
            d["avg_latency"] = sum(d["latencies"]) / t if t else 0

        sorted_lat = sorted(latencies)
        p50 = sorted_lat[int(len(sorted_lat) * 0.50)]
        p90 = sorted_lat[min(int(len(sorted_lat) * 0.90), len(sorted_lat) - 1)]

        return {
            "mode": self.mode,
            "timestamp": datetime.now().isoformat(),
            "total_cases": total,
            "overall_accuracy": {
                "action_acc": (correct_action / total) * 100,
                "device_acc": (correct_device / total) * 100,
                "location_acc": (correct_location / total) * 100,
                "strict_intent_acc": (strict_intent / total) * 100,
                "resolver_acc": (correct_resolver / total) * 100
            },
            "latency": {
                "mean": sum(latencies) / total,
                "min": min(latencies),
                "max": max(latencies),
                "p50": p50,
                "p90": p90
            },
            "by_category": categories
        }

    def _print_summary(self, s: Dict[str, Any]):
        acc = s["overall_accuracy"]
        lat = s["latency"]
        print("\n" + "=" * 80)
        print("📊 BÁO CÁO KẾT QUẢ ĐÁNH GIÁ ĐỘ CHÍNH XÁC NLU")
        print("=" * 80)
        print(f" • Động cơ thử nghiệm:          {s['mode'].upper()}")
        print(f" • Tổng số ca kiểm thử:         {s['total_cases']}")
        print(f" • Độ chính xác Hành động:      {acc['action_acc']:.1f}%")
        print(f" • Độ chính xác Thiết bị:       {acc['device_acc']:.1f}%")
        print(f" • Độ chính xác Vị trí phòng:   {acc['location_acc']:.1f}%")
        print(f" • Độ chính xác Toàn diện:      {acc['strict_intent_acc']:.1f}%  (Strict Intent Match)")
        print(f" • Độ chính xác Điều khiển Relay: {acc['resolver_acc']:.1f}%  (Hardware Node Dispatch)")
        print(f" • Thời gian phản hồi trung bình: {lat['mean']:.2f}s (P50: {lat['p50']:.2f}s, P90: {lat['p90']:.2f}s)")
        print("-" * 80)
        print("CHI TIẾT THEO DANH MỤC:")
        w_cat = [18, 10, 15, 18, 12]
        print(format_table_row(["DANH MỤC", "SỐ CA", "INTENT ACC", "RESOLVE ACC", "ĐỘ TRỄ TB"], w_cat))
        print("-" * 80)
        for cat, d in s["by_category"].items():
            print(format_table_row(
                [cat, str(d["total"]), f"{d['strict_acc']:.1f}%", f"{d['resolver_acc']:.1f}%", f"{d['avg_latency']:.2f}s"],
                w_cat
            ))
        print("=" * 80 + "\n")

    def _save_reports(self, summary: Dict[str, Any], results: List[Dict[str, Any]]):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 1. JSON report
        json_file = self.output_dir / f"benchmark_{self.mode}_{ts}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "results": results}, f, indent=2, ensure_ascii=False)
        print(f"📁 Đã lưu kết quả JSON chi tiết: {json_file}")

        # 2. Markdown report
        md_file = self.output_dir / f"BENCHMARK_{self.mode.upper()}_{ts}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(self._build_markdown(summary, results))
        print(f"📄 Đã lập báo cáo Markdown hoàn chỉnh: {md_file}")

    def _build_markdown(self, s: Dict[str, Any], results: List[Dict[str, Any]]) -> str:
        acc = s["overall_accuracy"]
        lat = s["latency"]
        lines = [
            f"# Báo Cáo Đánh Giá Độ Chính Xác NLU Mô Hình {s['mode'].upper()}",
            f"\n*Ngày thực hiện:* {s['timestamp']}  ",
            f"*Tổng số ca kiểm thử:* **{s['total_cases']}** khẩu lệnh  \n",
            "## 1. Tóm Tắt Hiệu Năng Cốt Lõi (Key Metrics)\n",
            "| Chỉ số đo lường | Tỉ lệ đạt (%) | Ghi chú kỹ thuật |",
            "| :--- | :--- | :--- |",
            f"| **Action Accuracy** | **{acc['action_acc']:.1f}%** | Nhận diện đúng turn_on, turn_off, null |",
            f"| **Device Accuracy** | **{acc['device_acc']:.1f}%** | Nhận diện đúng đèn, quạt, alias |",
            f"| **Location Accuracy** | **{acc['location_acc']:.1f}%** | Nhận diện đúng phòng ngủ, phòng khách, bếp |",
            f"| **Strict Intent Accuracy** | **{acc['strict_intent_acc']:.1f}%** | Toàn bộ 3 thuộc tính đồng thời chuẩn xác |",
            f"| **End-to-End Hardware Dispatch** | **{acc['resolver_acc']:.1f}%** | Ánh xạ trúng node_id/channel điều khiển relay |",
            f"| **Thời gian phản hồi P50** | **{lat['p50']:.2f}s** | 50% số lệnh hoàn thành trong khoảng này |",
            f"| **Thời gian phản hồi Trung bình** | **{lat['mean']:.2f}s** | Bao gồm cả suy luận CPU trên Pi 4 |",
            "\n## 2. Kết Quả Chi Tiết Theo Danh Mục (Category Breakdown)\n",
            "| Danh mục kiểm thử | Số ca | Intent Acc (%) | Dispatch Acc (%) | Độ trễ TB |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]
        for cat, d in s["by_category"].items():
            lines.append(f"| **{cat}** | {d['total']} | {d['strict_acc']:.1f}% | {d['resolver_acc']:.1f}% | {d['avg_latency']:.2f}s |")

        # Thống kê các ca thất bại (Error Analysis)
        failures = [r for r in results if not r["scores"]["strict_intent_match"] or not r["scores"]["resolver_match"]]
        if failures:
            lines.append("\n## 3. Phân Tích Các Ca Thất Bại & Ngoại Lệ (Failure Case Analysis)\n")
            lines.append("| Mã | Danh mục | Câu lệnh đầu vào | Dự đoán AI | Kỳ vọng | Lỗi ghi nhận |")
            lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for f_case in failures:
                pred = f_case["predicted"]
                exp = f_case["expected"]
                pred_str = f"({pred['action']}, {pred['device']}, {pred['location']})"
                exp_str = f"({exp['action']}, {exp['device']}, {exp['location']})"
                lines.append(f"| `{f_case['id']}` | {f_case['category']} | *\"{f_case['input']}\"* | `{pred_str}` | `{exp_str}` | {f_case.get('error') or 'Lệch phân loại'} |")

        return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="Voice NLU Benchmark Suite")
    parser.add_argument("--mode", choices=["local", "cloud", "hybrid"], default="local", help="Engine to benchmark")
    parser.add_argument("--category", default="all", help="Category filter: all, Direct, Implicit, Dialect, Negation, Ambiguity, Hallucination, ASR_Noise")
    parser.add_argument("--quick", action="store_true", help="Run quick evaluation (14 cases across all categories)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of test cases")
    args = parser.parse_args()

    runner = BenchmarkRunner(mode=args.mode)
    await runner.run_benchmark(category=args.category, quick=args.quick, limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())
