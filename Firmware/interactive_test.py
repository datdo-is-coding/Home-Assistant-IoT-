"""
Interactive Test CLI & Dual Serial Monitor for T1 Node (COM8) & T2 Zone Controller (COM9)
Aetheria OS / DTV Smart Home
"""

import sys
import time
import threading
import serial

sys.stdout.reconfigure(encoding='utf-8')

COLOR_T1 = "\033[96m"   # Cyan for T1 (COM8)
COLOR_T2 = "\033[93m"   # Yellow for T2 (COM9)
COLOR_SYS = "\033[92m"  # Green for Menu
COLOR_RESET = "\033[0m"

running = True

def open_port(port):
    s = serial.Serial()
    s.port = port
    s.baudrate = 115200
    s.timeout = 0.2
    s.dtr = False
    s.rts = False
    s.open()
    return s

def read_serial(ser, prefix, color):
    while running:
        try:
            line = ser.readline()
            if line:
                decoded = line.decode('utf-8', errors='ignore').rstrip()
                if decoded:
                    print(f"{color}[{prefix}] {decoded}{COLOR_RESET}")
        except Exception:
            break

def print_menu():
    print(f"""
{COLOR_SYS}=============================================================
  🧪 AETHERIA OS — ESP32 TEST RIG (T1: COM8 | T2: COM9)
=============================================================
  [1] Toggle Relay 1 on T1 (via T2 ESP-NOW)
  [2] Toggle Relay 2 on T1 (via T2 ESP-NOW)
  [3] Show Mesh Nodes Table ('nodes' command)
  [4] Test IR Blaster: Daikin AC On, 24°C ('ir daikin')
  [5] Test IR Blaster: NEC Custom Code ('ir nec')
  [6] Test Speaker: Play Chime on T2 MAX98357A ('chime')
  [A] Run Automated Verification Loop (All tests sequentially)
  [Q] Quit
============================================================={COLOR_RESET}
    """)

def main():
    global running
    print(f"{COLOR_SYS}>>> Connecting to COM8 (T1) and COM9 (T2)...{COLOR_RESET}")

    try:
        ser_t1 = open_port('COM8')
        print(f"✅ COM8 (T1 Actuator Node) connected.")
    except Exception as e:
        print(f"❌ Could not open COM8: {e}")
        ser_t1 = None

    try:
        ser_t2 = open_port('COM9')
        print(f"✅ COM9 (T2 Zone Controller) connected.")
    except Exception as e:
        print(f"❌ Could not open COM9: {e}")
        ser_t2 = None

    if not ser_t1 and not ser_t2:
        print("❌ No serial ports available. Exiting.")
        return

    # Start reader threads
    if ser_t1:
        t1_thread = threading.Thread(target=read_serial, args=(ser_t1, "T1_COM8", COLOR_T1), daemon=True)
        t1_thread.start()

    if ser_t2:
        t2_thread = threading.Thread(target=read_serial, args=(ser_t2, "T2_COM9", COLOR_T2), daemon=True)
        t2_thread.start()

    time.sleep(1.0)
    print_menu()

    r1_state = False
    r2_state = False

    while running:
        try:
            choice = input().strip().lower()
            if not choice:
                continue

            if choice == '1':
                r1_state = not r1_state
                cmd = f"r1 {'on' if r1_state else 'off'}\n"
                print(f"{COLOR_SYS}>>> [Command -> T2] {cmd.strip()}{COLOR_RESET}")
                if ser_t2:
                    ser_t2.write(cmd.encode())

            elif choice == '2':
                r2_state = not r2_state
                cmd = f"r2 {'on' if r2_state else 'off'}\n"
                print(f"{COLOR_SYS}>>> [Command -> T2] {cmd.strip()}{COLOR_RESET}")
                if ser_t2:
                    ser_t2.write(cmd.encode())

            elif choice == '3':
                print(f"{COLOR_SYS}>>> [Command -> T2] nodes{COLOR_RESET}")
                if ser_t2:
                    ser_t2.write(b"nodes\n")

            elif choice == '4':
                print(f"{COLOR_SYS}>>> [Command -> T2] ir daikin (TX 38kHz GPIO 21){COLOR_RESET}")
                if ser_t2:
                    ser_t2.write(b"ir daikin\n")

            elif choice == '5':
                print(f"{COLOR_SYS}>>> [Command -> T2] ir nec (TX 38kHz GPIO 21){COLOR_RESET}")
                if ser_t2:
                    ser_t2.write(b"ir nec\n")

            elif choice == '6':
                print(f"{COLOR_SYS}>>> [Command -> T2] chime (I2S Speaker){COLOR_RESET}")
                if ser_t2:
                    ser_t2.write(b"chime\n")

            elif choice == 'a':
                print(f"{COLOR_SYS}>>> Starting Automated Verification Loop...{COLOR_RESET}")
                if ser_t2:
                    print("--- 1. Query nodes ---")
                    ser_t2.write(b"nodes\n")
                    time.sleep(1.0)

                    print("--- 2. Turn ON Relay 1 on T1 ---")
                    ser_t2.write(b"r1 on\n")
                    time.sleep(1.5)

                    print("--- 3. Turn OFF Relay 1 on T1 ---")
                    ser_t2.write(b"r1 off\n")
                    time.sleep(1.5)

                    print("--- 4. Turn ON Relay 2 on T1 ---")
                    ser_t2.write(b"r2 on\n")
                    time.sleep(1.5)

                    print("--- 5. Turn OFF Relay 2 on T1 ---")
                    ser_t2.write(b"r2 off\n")
                    time.sleep(1.5)

                    print("--- 6. Test IR Daikin ---")
                    ser_t2.write(b"ir daikin\n")
                    time.sleep(1.0)

                    print("--- 7. Test Speaker Chime ---")
                    ser_t2.write(b"chime\n")
                    time.sleep(1.5)
                print(f"{COLOR_SYS}>>> Automated Loop Done.{COLOR_RESET}")

            elif choice == 'q':
                print("Exiting...")
                running = False
                break
            elif choice == 'm' or choice == 'help':
                print_menu()
            else:
                print(f"Unknown key '{choice}'. Press 'm' for menu or 'q' to quit.")

        except (KeyboardInterrupt, EOFError):
            running = False
            break

    time.sleep(0.5)
    if ser_t1:
        ser_t1.close()
    if ser_t2:
        ser_t2.close()
    print("Serial ports closed.")

if __name__ == '__main__':
    main()
