"""Host test runner for device safe reset, power-cut resumption, and NVS migration."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
FIRMWARE_ROOT = HERE.parent / "firmware_esp"
ACTIONBOX_V2_SRC = FIRMWARE_ROOT / "ActionBox_V2/src"
SUBBOX_SRC = FIRMWARE_ROOT / "SubBox/src"
COMMON_SRC = FIRMWARE_ROOT / "common"


class TestDeviceResetHost(unittest.TestCase):
    def test_safe_device_reset_and_nvs_migration(self):
        host_cpp = HERE / "test_device_reset_host.cpp"
        self.assertTrue(host_cpp.is_file(), f"Host test source missing: {host_cpp}")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            # Generate host mock header redirects
            for header in (
                "esp_err.h", "esp_log.h", "esp_timer.h", "esp_attr.h",
                "sdkconfig.h", "freertos/FreeRTOS.h", "freertos/task.h",
                "freertos/semphr.h", "driver/gpio.h", "driver/uart.h",
                "nvs.h", "nvs_flash.h", "esp_mac.h", "esp_random.h", "esp_task_wdt.h"
            ):
                path = root / header
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#include "host_idf.h"\n')

            gpio_h = root / "driver/gpio.h"
            gpio_h.write_text(
                '#pragma once\n#include "host_idf.h"\n' +
                "\n".join(f"constexpr int GPIO_NUM_{i} = {i};" for i in range(49)) +
                "\n"
            )

            # Object compilation paths
            obj_dir = root / "obj"
            obj_dir.mkdir(parents=True, exist_ok=True)

            actionbox_includes = [
                f"-I{ACTIONBOX_V2_SRC}",
                *[f"-I{p}" for p in ACTIONBOX_V2_SRC.rglob("*") if p.is_dir()],
                f"-I{COMMON_SRC}",
                f"-I{root}",
                f"-I{HERE / 'actionbox_host'}"
            ]

            subbox_includes = [
                f"-I{SUBBOX_SRC}",
                *[f"-I{p}" for p in SUBBOX_SRC.rglob("*") if p.is_dir()],
                f"-I{COMMON_SRC}",
                f"-I{root}",
                f"-I{HERE / 'actionbox_host'}"
            ]

            # 1. Compile ActionBox objects
            actionbox_sources = [
                ("nvs_storage.o", ACTIONBOX_V2_SRC / "storage/nvs_storage.cpp"),
                ("relay_driver.o", ACTIONBOX_V2_SRC / "drivers/relay/relay_driver.cpp"),
                ("led_driver.o", ACTIONBOX_V2_SRC / "drivers/led/led_driver.cpp"),
                ("device_reset.o", COMMON_SRC / "device_reset.cpp"),
            ]
            objects = []
            for obj_name, src_file in actionbox_sources:
                out_obj = obj_dir / obj_name
                cmd = ["g++", "-std=c++17", "-c", str(src_file), "-o", str(out_obj)] + actionbox_includes
                proc = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, f"Failed compiling {src_file}:\n{proc.stderr}")
                objects.append(out_obj)

            # 2. Compile SubBox objects
            subbox_sources = [
                ("security_config.o", SUBBOX_SRC / "storage/security_config.cpp"),
                ("nvs_manager.o", SUBBOX_SRC / "storage/nvs_manager.cpp"),
            ]
            for obj_name, src_file in subbox_sources:
                out_obj = obj_dir / obj_name
                cmd = ["g++", "-std=c++17", "-c", str(src_file), "-o", str(out_obj)] + subbox_includes
                proc = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, f"Failed compiling {src_file}:\n{proc.stderr}")
                objects.append(out_obj)

            # 3. Compile test runner host source
            test_obj = obj_dir / "test_device_reset_host.o"
            runner_includes = [
                f"-I{ACTIONBOX_V2_SRC}",
                *[f"-I{p}" for p in ACTIONBOX_V2_SRC.rglob("*") if p.is_dir()],
                f"-I{SUBBOX_SRC}",
                f"-I{SUBBOX_SRC}/storage",
                f"-I{SUBBOX_SRC}/nlu",
                f"-I{COMMON_SRC}",
                f"-I{root}",
                f"-I{HERE / 'actionbox_host'}"
            ]
            cmd = ["g++", "-std=c++17", "-c", str(host_cpp), "-o", str(test_obj)] + runner_includes
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"Failed compiling test runner:\n{proc.stderr}")
            objects.append(test_obj)

            # 4. Link everything
            bin_path = root / "test_device_reset"
            link_cmd = ["g++", "-std=c++17", "-pthread", "-o", str(bin_path)] + [str(o) for o in objects]
            link_proc = subprocess.run(link_cmd, capture_output=True, text=True)
            self.assertEqual(link_proc.returncode, 0, f"Failed linking binary:\n{link_proc.stderr}")

            # 5. Run binary
            run_proc = subprocess.run([str(bin_path)], capture_output=True, text=True, timeout=15)
            print(run_proc.stdout)
            self.assertEqual(run_proc.returncode, 0, f"Execution failed:\nSTDERR:\n{run_proc.stderr}\nSTDOUT:\n{run_proc.stdout}")
            self.assertIn("ALL DEVICE RESET HOST TESTS PASSED!", run_proc.stdout)


if __name__ == "__main__":
    unittest.main()
