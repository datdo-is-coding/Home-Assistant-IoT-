import os
import subprocess
import sys
Import("env")

project_dir = env.get("PROJECT_DIR")
build_dir = env.subst("$BUILD_DIR")
srmodels_bin = os.path.join(build_dir, "srmodels", "srmodels.bin")

# Pack models if srmodels.bin doesn't exist
if not os.path.exists(srmodels_bin):
    print(">>> Packing ESP-SR models into srmodels.bin...")
    movemodel_py = os.path.join(project_dir, "managed_components", "espressif__esp-sr", "model", "movemodel.py")
    sdkconfig = os.path.join(project_dir, "sdkconfig.4d_systems_esp32s3_gen4_r8n16")
    esp_sr_dir = os.path.join(project_dir, "managed_components", "espressif__esp-sr")
    subprocess.run([
        sys.executable, movemodel_py,
        "-d1", sdkconfig,
        "-d2", esp_sr_dir,
        "-d3", build_dir
    ], check=True)

# Register srmodels.bin to be flashed to partition 'model' at offset 0x610000
if os.path.exists(srmodels_bin):
    print(f">>> Registered ESP-SR model partition: 0x610000 -> {srmodels_bin}")
    env.Append(
        FLASH_EXTRA_IMAGES=[
            ("0x610000", srmodels_bin)
        ]
    )
