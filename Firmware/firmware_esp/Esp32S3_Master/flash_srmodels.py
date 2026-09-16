import os
import sys
import json
import subprocess
Import("env")

project_dir = env.get("PROJECT_DIR")
build_dir = env.subst("$BUILD_DIR")
srmodels_dir = os.path.join(build_dir, "srmodels")
srmodels_bin = os.path.join(srmodels_dir, "srmodels.bin")

# 1. Ensure srmodels.bin is packed
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

# 2. Update flasher_args.json so PlatformIO flashes srmodels.bin to 0x610000 on "pio run -t upload"
flasher_args_path = os.path.join(build_dir, "flasher_args.json")
if os.path.exists(flasher_args_path) and os.path.exists(srmodels_bin):
    try:
        with open(flasher_args_path, "r") as f:
            flasher_args = json.load(f)

        flash_files = flasher_args.get("flash_files", {})
        if "0x610000" not in flash_files:
            flash_files["0x610000"] = "srmodels/srmodels.bin"
            flasher_args["flash_files"] = flash_files
            flasher_args["model"] = {
                "offset": "0x610000",
                "file": "srmodels/srmodels.bin",
                "encrypted": "false"
            }
            with open(flasher_args_path, "w") as f:
                json.dump(flasher_args, f, indent=4)
            print(">>> Added 0x610000 (model partition) to flasher_args.json")
    except Exception as e:
        print(f">>> Note: Could not update flasher_args.json: {e}")

# 3. Also append to FLASH_EXTRA_IMAGES for SCons
if os.path.exists(srmodels_bin):
    env.Append(
        FLASH_EXTRA_IMAGES=[
            ("0x610000", srmodels_bin)
        ]
    )
