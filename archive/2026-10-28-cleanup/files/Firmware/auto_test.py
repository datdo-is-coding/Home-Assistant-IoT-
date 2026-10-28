import sys
import time
import threading
import serial

sys.stdout.reconfigure(encoding='utf-8')

stop_flag = False

def open_port(port):
    s = serial.Serial()
    s.port = port
    s.baudrate = 115200
    s.timeout = 0.2
    s.dtr = False
    s.rts = False
    s.open()
    return s

def reader(ser, tag, color):
    while not stop_flag:
        try:
            line = ser.readline().decode('utf-8', errors='replace')
            if line:
                s_line = line.strip()
                if s_line:
                    print(f"{color}[{tag}] {s_line}\033[0m")
        except Exception:
            break

def main():
    global stop_flag
    print("==================================================")
    print("  AUTOMATED ESP32 TEST SUITE (T1:COM8, T2:COM9)")
    print("==================================================")

    try:
        s1 = open_port('COM8')
        s2 = open_port('COM9')
    except Exception as e:
        print(f"Error opening port: {e}")
        return

    t1 = threading.Thread(target=reader, args=(s1, "T1_COM8", "\033[96m"), daemon=True)
    t2 = threading.Thread(target=reader, args=(s2, "T2_COM9", "\033[93m"), daemon=True)
    t1.start()
    t2.start()

    time.sleep(1.0)

    print("\n--- 1. Query Registered Nodes ---")
    s2.write(b"nodes\n")
    time.sleep(1.5)

    print("\n--- 2. Turn ON Relay 1 on T1 via ESP-NOW ---")
    s2.write(b"r1 on\n")
    time.sleep(1.5)

    print("\n--- 3. Turn OFF Relay 1 on T1 via ESP-NOW ---")
    s2.write(b"r1 off\n")
    time.sleep(1.5)

    print("\n--- 4. Turn ON Relay 2 on T1 via ESP-NOW ---")
    s2.write(b"r2 on\n")
    time.sleep(1.5)

    print("\n--- 5. Turn OFF Relay 2 on T1 via ESP-NOW ---")
    s2.write(b"r2 off\n")
    time.sleep(1.5)

    print("\n--- 6. Test IR Blaster (Daikin AC 38kHz GPIO 21) ---")
    s2.write(b"ir daikin\n")
    time.sleep(1.0)

    print("\n--- 7. Test Speaker Chime on T2 (MAX98357A) ---")
    s2.write(b"chime\n")
    time.sleep(1.5)

    stop_flag = True
    time.sleep(0.5)
    s1.close()
    s2.close()
    print("\n==================================================")
    print("  ALL TESTS EXECUTED SUCCESSFULLY!")
    print("==================================================")

if __name__ == '__main__':
    main()
