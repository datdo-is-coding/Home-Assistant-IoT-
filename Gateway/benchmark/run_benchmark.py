#!/usr/bin/env python3
"""
CLI Helper để chạy bộ Benchmark NLU trên Raspberry Pi 4 hoặc máy trạm.
Sử dụng:
    python run_benchmark.py --quick               # Chạy nhanh 14 ca đại diện
    python run_benchmark.py --category Dialect    # Chạy riêng nhóm khẩu ngữ địa phương
    python run_benchmark.py --category Negation   # Chạy riêng nhóm câu bẫy phủ định
    python run_benchmark.py --mode local          # Đánh giá Qwen2.5-3B nội bộ
    python run_benchmark.py --mode cloud          # Đánh giá Gemini 1.5 Flash
    python run_benchmark.py --limit 10            # Chạy 10 ca đầu tiên
"""

import sys
import asyncio
from pathlib import Path

# Đảm bảo đường dẫn module
BENCHMARK_DIR = Path(__file__).resolve().parent
if str(BENCHMARK_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_DIR))

from evaluator import main

if __name__ == "__main__":
    asyncio.run(main())
