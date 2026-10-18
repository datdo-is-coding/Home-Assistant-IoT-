import os
import sys
import glob

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import numpy as np
import soundfile as sf
import scipy.signal

DATASET_DIR = "d:/KWS/dataset"
TARGET_SR = 16000
TARGET_SAMPLES = 16000

def preprocess():
    total_files = 0
    corrupt_files = 0
    resampled_files = 0
    mono_converted = 0
    length_adjusted = 0

    wav_files = glob.glob(os.path.join(DATASET_DIR, "*", "*.wav"))
    print(f"Bắt đầu kiểm tra và chuẩn hóa {len(wav_files)} files...")

    for path in wav_files:
        total_files += 1
        try:

            if os.path.getsize(path) <= 44:
                print(f"[Xóa file lỗi rỗng] {path}")
                os.remove(path)
                corrupt_files += 1
                continue

            data, sr = sf.read(path, dtype='float32')

            if len(data) == 0:
                print(f"[Xóa file 0 frames] {path}")
                os.remove(path)
                corrupt_files += 1
                continue

            if data.ndim > 1:
                data = np.mean(data, axis=1)
                mono_converted += 1

            if sr != TARGET_SR:
                gcd = np.gcd(sr, TARGET_SR)
                up = TARGET_SR // gcd
                down = sr // gcd
                data = scipy.signal.resample_poly(data, up, down)
                resampled_files += 1

            if len(data) != TARGET_SAMPLES:
                length_adjusted += 1
                if len(data) < TARGET_SAMPLES:
                    pad_width = TARGET_SAMPLES - len(data)
                    data = np.pad(data, (0, pad_width), mode='constant', constant_values=0)
                else:
                    data = data[:TARGET_SAMPLES]

            sf.write(path, data, TARGET_SR, subtype='PCM_16')

        except Exception as e:
            print(f"[Lỗi đọc file] {path}: {e}")
            if os.path.exists(path):
                os.remove(path)
            corrupt_files += 1

    print("\n--- KẾT QUẢ CHUẨN HÓA DATASET HIỆN TẠI ---")
    print(f"Tổng file quét: {total_files}")
    print(f"File hỏng đã xóa: {corrupt_files}")
    print(f"File đã resample về 16kHz: {resampled_files}")
    print(f"File chuyển thành Mono: {mono_converted}")
    print(f"File cân chỉnh thời lượng 1.0s: {length_adjusted}")
    print(f"File hợp lệ còn lại: {total_files - corrupt_files}")

if __name__ == "__main__":
    preprocess()
