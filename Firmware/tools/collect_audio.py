#!/usr/bin/env python3
"""
DTV Smart Home — USB Audio Dataset Collector
Communicates with ESP32-S3 over Native USB / Serial (COM8) to capture
clean 16kHz 16-bit mono audio directly into standard WAV files.

Usage:
    python collect_audio.py --port COM8 --label bat_den
    python collect_audio.py --auto-port
"""

import sys
import os
import time
import struct
import wave
import argparse
import serial
import serial.tools.list_ports

# USB Protocol Definitions (matches app_config.h)
MAGIC_0 = 0xAA
MAGIC_1 = 0x55

PKT_TYPE_AUDIO  = 0x01
PKT_TYPE_START  = 0x02
PKT_TYPE_END    = 0x03
PKT_TYPE_STATUS = 0x04

FLAG_VAD_ACTIVE = 0x01
FLAG_BUTTON_DN  = 0x02

SAMPLE_RATE = 16000
CHANNELS    = 1
SAMPLE_WIDTH= 2 # 16-bit = 2 bytes


def find_esp32s3_port():
    """Auto-detect ESP32-S3 USB port by Espressif VID (0x303A)."""
    for p in serial.tools.list_ports.comports():
        if p.vid == 0x303A:
            return p.device
    return None


def calculate_rms(pcm_bytes):
    """Calculate RMS volume level of 16-bit PCM bytes."""
    count = len(pcm_bytes) // 2
    if count == 0:
        return 0
    samples = struct.unpack(f"<{count}h", pcm_bytes)
    sum_sq = sum(s * s for s in samples)
    return int((sum_sq / count) ** 0.5)


def render_vu_meter(rms, max_rms=2000, width=20):
    """Render a text VU-meter bar."""
    val = min(rms, max_rms)
    filled = int((val / max_rms) * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {rms:4d}"


def save_wav_file(filepath, pcm_data, sample_rate=16000):
    """Save raw PCM bytes to standard RIFF WAV file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


def main():
    parser = argparse.ArgumentParser(description="ESP32-S3 USB Audio Dataset Collector")
    parser.add_argument("--port", type=str, default=None, help="Serial port (e.g. COM8 or /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--label", type=str, default="sample", help="Current voice label/class (e.g. bat_den)")
    parser.add_argument("--outdir", type=str, default="dataset", help="Output directory for WAV files")
    parser.add_argument("--auto-port", action="store_true", help="Auto-detect ESP32-S3 port")
    args = parser.parse_args()

    port = args.port
    if not port or args.auto_port:
        detected = find_esp32s3_port()
        if detected:
            print(f"🔍 Auto-detected ESP32-S3 on port: {detected}")
            port = detected
        elif not port:
            port = "COM8"

    print("=" * 65)
    print("   🎙️  DTV SMART HOME — USB AUDIO DATASET RECORDER")
    print(f"   Target Port : {port} | Label: '{args.label}'")
    print(f"   Storage Dir : {os.path.abspath(args.outdir)}")
    print("=" * 65)
    print("👉 Hướng dẫn sử dụng:")
    print("   • Bấm nút BUT1/BOOT trên board để BẮT ĐẦU / DỪNG thu âm.")
    print("   • Hoặc gõ phím 'r' rồi bấm Enter để thu, 's' để dừng.")
    print("   • Đổi nhãn bằng cách gõ: label <tên_mới> (VD: label bat_dieu_hoa)")
    print("   • Bấm Ctrl+C để thoát chương trình.")
    print("-" * 65)

    try:
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = args.baud
        ser.timeout = 0.05
        ser.dtr = False
        ser.rts = False
        ser.open()
    except Exception as e:
        print(f"❌ Không thể mở cổng {port}: {e}")
        sys.exit(1)

    current_label = args.label
    sample_index = 1
    # Find next available index for this label
    label_dir = os.path.join(args.outdir, current_label)
    if os.path.exists(label_dir):
        existing = [f for f in os.listdir(label_dir) if f.endswith(".wav")]
        sample_index = len(existing) + 1

    recording_buffer = bytearray()
    is_recording = False
    start_time = 0.0

    sync_state = 0
    hdr_buf = bytearray()

    try:
        while True:
            # Check for data from ESP32
            b = ser.read(1)
            if b:
                byte_val = b[0]
                if sync_state == 0:
                    if byte_val == MAGIC_0:
                        sync_state = 1
                    else:
                        # Print plain text log messages from firmware
                        try:
                            sys.stdout.write(b.decode("utf-8", errors="ignore"))
                            sys.stdout.flush()
                        except Exception:
                            pass
                elif sync_state == 1:
                    if byte_val == MAGIC_1:
                        sync_state = 2
                        hdr_buf = bytearray()
                    else:
                        sync_state = 0
                elif sync_state == 2:
                    hdr_buf.append(byte_val)
                    if len(hdr_buf) == 6: # type(1), flags(1), length(2), seq(2)
                        pkt_type, pkt_flags, pkt_len, pkt_seq = struct.unpack("<BBHH", hdr_buf)
                        # Read payload
                        payload = ser.read(pkt_len)
                        while len(payload) < pkt_len:
                            chunk = ser.read(pkt_len - len(payload))
                            if not chunk:
                                break
                            payload += chunk
                        # Read 1-byte checksum
                        chk_byte = ser.read(1)
                        if chk_byte:
                            # Verify checksum
                            expected_chk = 0
                            for x in [MAGIC_0, MAGIC_1] + list(hdr_buf) + list(payload):
                                expected_chk ^= x
                            
                            if expected_chk == chk_byte[0]:
                                # Packet verified!
                                if pkt_type == PKT_TYPE_START:
                                    is_recording = True
                                    recording_buffer.clear()
                                    start_time = time.time()
                                    print(f"\n🔴 [RECORDING START] Đang thu âm cho nhãn '{current_label}'...")

                                elif pkt_type == PKT_TYPE_AUDIO and is_recording:
                                    recording_buffer.extend(payload)
                                    rms = calculate_rms(payload)
                                    dur = len(recording_buffer) / (SAMPLE_RATE * SAMPLE_WIDTH)
                                    vu = render_vu_meter(rms)
                                    is_vad = "🗣️ " if (pkt_flags & FLAG_VAD_ACTIVE) else "   "
                                    sys.stdout.write(f"\r{is_vad} [REC] {vu} | {dur:.2f}s ({len(recording_buffer)}B)  ")
                                    sys.stdout.flush()

                                elif pkt_type == PKT_TYPE_END:
                                    if is_recording and len(recording_buffer) > 0:
                                        dur = len(recording_buffer) / (SAMPLE_RATE * SAMPLE_WIDTH)
                                        filename = f"{current_label}_{sample_index:04d}.wav"
                                        filepath = os.path.join(args.outdir, current_label, filename)
                                        save_wav_file(filepath, bytes(recording_buffer))
                                        print(f"\n💾 [SAVED] Đã lưu: {filepath} ({dur:.2f}s, {len(recording_buffer)} bytes)")
                                        sample_index += 1
                                    is_recording = False
                                    recording_buffer.clear()
                        sync_state = 0
            else:
                time.sleep(0.005)

    except KeyboardInterrupt:
        print("\n👋 Đang đóng chương trình...")
    finally:
        ser.close()
        print("Đã đóng kết nối cổng COM.")


if __name__ == "__main__":
    main()
