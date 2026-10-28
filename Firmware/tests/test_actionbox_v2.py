"""Compile and exercise the real ActionBox drivers without connected hardware."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "firmware_esp/ActionBox_V2/src"
V1_BASELINE = HERE.parents[1] / "archive/2026-10-28-cleanup/files/Firmware/firmware_esp/ActionBox/src"

class ActionBoxV2Test(unittest.TestCase):
    def run_driver(self, name, sources, v2=True, json=False):
        source_root = SRC if v2 else V1_BASELINE
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for header in ("esp_err.h", "esp_log.h", "esp_timer.h", "esp_attr.h", "esp_system.h",
                           "sdkconfig.h", "freertos/FreeRTOS.h", "freertos/task.h",
                           "freertos/semphr.h", "driver/gpio.h", "driver/uart.h",
                           "nvs.h", "nvs_flash.h", "esp_mac.h", "esp_random.h", "esp_task_wdt.h"):
                path = root / header
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#include "host_idf.h"\n')
            (root / "driver/gpio.h").write_text('#include "host_idf.h"\n' +
                "\n".join(f"constexpr int GPIO_NUM_{i} = {i};" for i in range(49)))

            with (root / "driver/gpio.h").open("r+") as file:
                content = file.read()
                file.seek(0)
                file.write("#pragma once\n" + content)
            (root / "hc_runtime.h").write_text("#pragma once\nbool hc_runtime_enabled(void);\n")
            includes = [SRC.parent.parent, SRC.parent.parent / "common", source_root, *[p for p in source_root.rglob("*") if p.is_dir()], root, HERE / "actionbox_host"]
            command = ["g++", "-std=c++17", "-pthread", "-g", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections", "-o", str(root / "check")]
            command += [f"-I{path}" for path in includes]
            command += [str(source_root / source) for source in sources]
            if json:
                cjson = SRC.parent / "managed_components/espressif__cjson/cJSON"
                self.assertTrue((cjson / "cJSON.c").is_file(), "Build ActionBox_V2 first to fetch its pinned cJSON dependency")
                command += [f"-I{cjson}", str(cjson / "cJSON.c")]
            command += [str(HERE / "actionbox_host" / name)]
            build = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root / "check")], capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_registration_requires_presence_and_durable_save(self):
        self.run_driver("registration.cpp", ["system/registration.cpp"])

    def test_setup_button_opens_pairing_without_reset_or_relay_change(self):
        self.run_driver("button_setup.cpp", ["device/device_manager.cpp"])

    def test_latching_pulses_boot_faults_and_emergency_serialization(self):
        self.run_driver("relay.cpp", ["drivers/relay/relay_driver.cpp", "drivers/led/led_driver.cpp"])

    def test_three_meter_rx_routes_and_invalid_samples(self):
        self.run_driver("meter.cpp", ["drivers/current_sensor/bl0942.cpp"])

    def test_v1_retains_two_monostable_relays(self):
        self.run_driver("relay_v1.cpp", ["drivers/relay/relay_driver.cpp", "drivers/led/led_driver.cpp"], v2=False)

    def test_channel_three_storage_protocol_and_safety(self):
        self.run_driver("integration.cpp", ["storage/nvs_storage.cpp", "protocol/actionbox_protocol.cpp",
                        "safety/safety_supervisor.cpp", "drivers/relay/relay_driver.cpp",
                        "drivers/led/led_driver.cpp"], json=True)

if __name__ == "__main__":
    unittest.main()
