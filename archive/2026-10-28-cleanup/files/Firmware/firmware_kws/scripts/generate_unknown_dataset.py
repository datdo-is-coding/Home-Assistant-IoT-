import os
import sys
import asyncio
import io
import numpy as np
import soundfile as sf
import scipy.signal

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import edge_tts

OUTPUT_DIR = "d:/KWS/dataset/unknown"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TARGET_SR = 16000
TARGET_SAMPLES = 16000

WORDS_AND_PHRASES = [

    "tivi", "điều hòa", "cửa", "cửa sổ", "bàn", "ghế", "nhà", "nước", "máy giặt", "rèm",
    "bình nóng lạnh", "loa", "chuông", "tủ lạnh", "ấm nước", "gương", "giường", "ổ cắm",

    "mở", "đóng", "tăng", "giảm", "sáng", "tối", "lạnh", "nóng", "chờ", "hẹn giờ",
    "kéo", "đẩy", "bấm", "nhấn", "chuyển", "dừng", "bắt đầu", "kết thúc", "kiểm tra",

    "xin chào", "alo", "ơi", "dạ", "vâng", "ừ", "không", "được", "biết rồi", "tạm biệt",
    "cảm ơn", "anh", "chị", "em", "bạn", "này", "cái gì", "ai đó", "sao thế", "làm gì",

    "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười",
    "hôm nay", "ngày mai", "bây giờ", "mấy giờ", "thời tiết", "nhiệt độ", "độ ẩm", "phút",

    "sân", "vườn", "ban công", "hành lang", "tầng một", "tầng hai", "toilet", "nhà kho"
]

VOICES = [
    "vi-VN-HoaiMyNeural",
    "vi-VN-NamMinhNeural"
]

RATES = ["-10%", "+0%", "+10%"]

def process_audio(raw_bytes):
    data, sr = sf.read(io.BytesIO(raw_bytes), dtype='float32')
    if data.ndim > 1:
        data = np.mean(data, axis=1)

    if sr != TARGET_SR:
        gcd = np.gcd(sr, TARGET_SR)
        data = scipy.signal.resample_poly(data, TARGET_SR // gcd, sr // gcd)

    if len(data) < TARGET_SAMPLES:
        pad = TARGET_SAMPLES - len(data)

        pad_front = pad // 4
        pad_back = pad - pad_front
        data = np.pad(data, (pad_front, pad_back), mode='constant', constant_values=0)
    elif len(data) > TARGET_SAMPLES:

        frame_len = TARGET_SAMPLES
        hop = 800
        best_energy = -1
        best_idx = 0
        for i in range(0, len(data) - frame_len + 1, hop):
            energy = np.sum(data[i:i+frame_len] ** 2)
            if energy > best_energy:
                best_energy = energy
                best_idx = i
        data = data[best_idx:best_idx+frame_len]

    max_val = np.max(np.abs(data))
    if max_val > 0.01:
        data = data / max_val * 0.9

    return data

async def generate_all():
    tasks = []
    count = 0
    target_count = 360

    print(f"Bắt đầu tổng hợp âm thanh tiếng Việt cho nhãn 'unknown' (Mục tiêu: {target_count} mẫu)...")

    for word in WORDS_AND_PHRASES:
        for voice in VOICES:
            for rate in RATES:
                if count >= target_count:
                    break
                count += 1
                out_path = os.path.join(OUTPUT_DIR, f"{count}.wav")
                tasks.append(generate_one(word, voice, rate, out_path, count))
            if count >= target_count:
                break
        if count >= target_count:
            break

    batch_size = 10
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i+batch_size]
        await asyncio.gather(*batch)
        print(f"-> Đã tạo {min(i + batch_size, len(tasks))}/{len(tasks)} mẫu unknown...")

    print(f"Hoàn thành! Đã tạo {count} mẫu trong {OUTPUT_DIR}")

async def generate_one(text, voice, rate, out_path, idx):
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        audio_stream = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_stream.write(chunk["data"])

        raw_bytes = audio_stream.getvalue()
        if len(raw_bytes) > 0:
            data = process_audio(raw_bytes)
            sf.write(out_path, data, TARGET_SR, subtype='PCM_16')
    except Exception as e:
        print(f"Lỗi tạo mẫu #{idx} ('{text}'): {e}")

if __name__ == "__main__":
    asyncio.run(generate_all())
