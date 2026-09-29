import sys
import time
import threading
import serial

def reset_board(ser):
    try:
        # ESP32 auto-reset sequence via RTS/DTR
        ser.setDTR(False)
        ser.setRTS(True)
        time.sleep(0.1)
        ser.setDTR(True)
        ser.setRTS(False)
        time.sleep(0.05)
        ser.setDTR(False)
    except Exception as e:
        pass

def read_port(port_name, prefix, color_code, should_reset=False):
    while True:
        try:
            ser = serial.Serial(port_name, 115200, timeout=0.2)
            print(f"\033[1;32m[MONITOR] Connected to {port_name} ({prefix})\033[0m", flush=True)
            if should_reset:
                reset_board(ser)
            while True:
                line = ser.readline()
                if line:
                    try:
                        decoded = line.decode('utf-8', errors='replace').rstrip('\r\n')
                        if decoded:
                            print(f"\033[{color_code}m[{prefix}]\033[0m {decoded}", flush=True)
                    except Exception:
                        pass
        except Exception as e:
            print(f"\033[1;31m[MONITOR] {port_name} error: {e}. Retrying in 2s...\033[0m", flush=True)
            time.sleep(2)

def main():
    # Only reset on first connection if desired, or just read
    t_subbox = threading.Thread(target=read_port, args=("COM9", "SubBox:COM9", "36", False), daemon=True) # cyan
    t_action = threading.Thread(target=read_port, args=("COM10", "ActionBox:COM10", "33", False), daemon=True) # yellow

    t_subbox.start()
    t_action.start()

    print("\033[1;35m>>> Dual Serial Monitor Started (COM9 SubBox & COM10 ActionBox). Press Ctrl+C to stop. <<<\033[0m", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting monitor...")

if __name__ == "__main__":
    main()
