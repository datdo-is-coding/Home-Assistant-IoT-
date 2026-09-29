import sys
import os
import re
import json
import time
import serial

# Enable ANSI escape sequences on Windows console
if sys.platform == 'win32':
    os.system('')
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def format_duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def render_dashboard(data, last_log="", port="COM10"):
    now_str = time.strftime("%H:%M:%S")
    uptime_str = format_duration(data.get("uptime_s", 0))

    ch1 = data["ch"][1]
    ch2 = data["ch"][2]

    # Current formatting
    c1_ma = ch1.get("current_ma", 0)
    c1_a = c1_ma / 1000.0
    c1_raw = ch1.get("raw_i", 0)
    c1_power = int(c1_a * 220.0) # Estimated active power at 220V

    c2_ma = ch2.get("current_ma", 0)
    c2_a = c2_ma / 1000.0
    c2_raw = ch2.get("raw_i", 0)
    c2_power = int(c2_a * 220.0)

    # Status indicators with colors
    if c1_ma > 100:
        c1_status = "\033[1;32m● LOAD ACTIVE  \033[0m"
        c1_color = "\033[1;33m"
    else:
        c1_status = "\033[1;30m○ NO LOAD      \033[0m"
        c1_color = "\033[0m"

    if c2_ma > 100:
        c2_status = "\033[1;32m● LOAD ACTIVE  \033[0m"
        c2_color = "\033[1;33m"
    else:
        c2_status = "\033[1;30m○ NO LOAD      \033[0m"
        c2_color = "\033[0m"

    pkt_count = data.get("packets", 0)

    out = []
    # Position cursor at row 1, col 1 (in-place rewrite)
    out.append("\033[H")
    out.append("╔══════════════════════════════════════════════════════════════════════════════╗\n")
    out.append(f"║\033[1;36m                     AETHERIA ACTIONBOX — REALTIME MONITOR                    \033[0m║\n")
    out.append(f"║               Port: \033[1;32m{port:<7}\033[0m | Baud: \033[1;32m115200\033[0m | Time: \033[1;37m{now_str}\033[0m | Uptime: \033[1;37m{uptime_str}\033[0m       ║\n")
    out.append("╠══════════════════════════════════════╦═══════════════════════════════════════╣\n")
    out.append("║ \033[1;35mCHANNEL 1 (CT1 SENSOR)\033[0m               ║ \033[1;35mCHANNEL 2 (CT2 SENSOR)\033[0m                ║\n")
    out.append("╠══════════════════════════════════════╬═══════════════════════════════════════╣\n")
    out.append(f"║ Current : {c1_color}{c1_a:6.2f} A ({c1_ma:5d} mA)\033[0m       ║ Current : {c2_color}{c2_a:6.2f} A ({c2_ma:5d} mA)\033[0m        ║\n")
    out.append(f"║ Raw ADC : {c1_raw:<12d}               ║ Raw ADC : {c2_raw:<12d}                ║\n")
    out.append(f"║ Power   : ~{c1_power:<5d} W (@220V)          ║ Power   : ~{c2_power:<5d} W (@220V)           ║\n")
    out.append(f"║ Status  : {c1_status}             ║ Status  : {c2_status}              ║\n")
    out.append("╠══════════════════════════════════════╩═══════════════════════════════════════╣\n")
    short_log = (last_log[:66] + '..') if len(last_log) > 68 else last_log
    out.append(f"║ Log: {short_log:<72} ║\n")
    out.append("╚══════════════════════════════════════════════════════════════════════════════╝\n")
    out.append(f"\033[2K\033[1;30m [Packets: {pkt_count} | Press Ctrl+C to exit monitor]\033[0m\n")

    sys.stdout.buffer.write("".join(out).encode('utf-8'))
    sys.stdout.buffer.flush()

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else 'COM10'
    baud = 115200

    data = {
        "uptime_s": 0,
        "packets": 0,
        "ch": {
            1: {"current_ma": 0, "raw_i": 0, "voltage_v": 0, "power_w": 0},
            2: {"current_ma": 0, "raw_i": 0, "voltage_v": 0, "power_w": 0}
        }
    }

    try:
        ser = serial.Serial(port, baud, timeout=0.2)
        ser.dtr = False
        ser.rts = False
    except Exception as e:
        print(f"\033[1;31mError opening {port}: {e}\033[0m")
        return

    # Clear screen and hide cursor
    sys.stdout.write("\033[2J\033[?25l")
    sys.stdout.flush()

    last_log = "Connected. Reading BL0942 data..."
    last_render = 0

    try:
        while True:
            line = ser.readline()
            if line:
                try:
                    text = line.decode('utf-8', errors='replace').strip()
                except Exception:
                    text = ""

                if text:
                    # Match BL0942 driver log: Ch1: I_RMS=5369 mA (raw_i=5369645, 0x51EF2D), V_RMS=2 V, P=15 W
                    m_bl = re.search(r'Ch([12]):\s*I_RMS=(\d+)\s*mA\s*\(raw_i=(\d+)', text)
                    if m_bl:
                        ch_num = int(m_bl.group(1))
                        i_ma = int(m_bl.group(2))
                        raw = int(m_bl.group(3))
                        if ch_num in data["ch"]:
                            data["ch"][ch_num]["current_ma"] = i_ma
                            data["ch"][ch_num]["raw_i"] = raw
                            data["packets"] += 1
                            last_log = f"Ch{ch_num} update: {i_ma} mA (ADC: {raw})"

                    # Match Telemetry JSON
                    m_json = re.search(r'Telemetry:\s*(\{.*\})', text)
                    if m_json:
                        try:
                            t_obj = json.loads(m_json.group(1))
                            data["uptime_s"] = t_obj.get("uptime_s", data["uptime_s"])
                            for ch_item in t_obj.get("channels", []):
                                c_num = ch_item.get("channel")
                                if c_num in data["ch"] and c_num not in [1, 2]:
                                    data["ch"][c_num]["current_ma"] = ch_item.get("current_ma", data["ch"][c_num]["current_ma"])
                            last_log = "Telemetry sync OK"
                        except Exception:
                            pass

            now = time.time()
            if now - last_render >= 0.15:  # ~7 fps refresh
                render_dashboard(data, last_log=last_log, port=port)
                last_render = now

    except KeyboardInterrupt:
        pass
    except Exception as e:
        last_log = f"Error: {e}"
        render_dashboard(data, last_log=last_log, port=port)
    finally:
        ser.close()
        # Restore cursor and clear below
        sys.stdout.write("\033[?25h\n\n\033[1;32mMonitor stopped.\033[0m\n")
        sys.stdout.flush()

if __name__ == '__main__':
    main()
