# Pi4 maintenance, 2026-10-02

Host: `pi4@192.168.11.29` (Debian 13, 4 GB RAM).

Completed:

- Removed pip download cache (880 files, 285.7 MB) and APT archives (about 307 MB).
- Removed unused Docker images `influxdb:3-core` and `eclipse-mosquitto:latest`.
- Stopped and disabled `llama-server.service`: the running Gateway configuration has
  `AI_ENABLED=false` and `LLM_MODE=off`. Removed the Gateway unit's automatic Llama dependency.
- Kept all Qwen and speech models, per the user's request.
- Replaced the broken `/usr/local/bin/autohotspot.sh` with the script in this directory.
  Tested Ethernet, saved Wi-Fi and hotspot fallback decisions offline. On the Pi,
  verified the Ethernet branch without changing any network connection.
- No application database, container data, virtual environment or running container was removed.

Verification:

- Root filesystem used bytes: 19,146,436,608 before, 17,773,568,000 after cleanup
  (about 1.37 GB reclaimed, subject to concurrent writes).
- Gateway PID remained 1805; HTTP health checks for Gateway, Grafana, InfluxDB
  and Home Assistant returned 200. EMQX remained running.
- `systemctl --failed` reported zero failed services after the hotspot repair.
- Llama was `inactive` and `disabled`. Its ~2 GB RSS was mostly reclaimable model
  pages; this is not a claim of 2 GB newly available application RAM.
- Temperature approximately 43 C; no thermal throttling detected.
- No reboot or real offline-network failover was performed.

Root-owned backups on the Pi:
`/var/backups/sic-tuning-20261002-TDPNre/` contains the original
`smarthome-gateway.service` and `autohotspot.sh`.

To enable the local model server again:

```sh
sudo systemctl enable --now llama-server.service
```

The Gateway's AI flags must also be enabled separately when local AI is wanted.
To restore the original unit, copy its backup to `/etc/systemd/system/` and run
`sudo systemctl daemon-reload`. The old hotspot script is syntactically broken;
its backup is retained for reference only.
