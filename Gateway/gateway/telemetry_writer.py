"""
Telemetry Writer — Writes device telemetry to InfluxDB.
"""

import logging
from typing import Optional

import config

logger = logging.getLogger("telemetry_writer")

# Lazy import
influxdb_client = None


class TelemetryWriter:
    """Write telemetry data to InfluxDB for historical storage."""
    
    def __init__(self):
        self._client = None
        self._write_api = None
        self._initialized = False
    
    def initialize(self):
        """Initialize InfluxDB connection."""
        global influxdb_client
        try:
            import influxdb_client as _idb
            from influxdb_client.client.write_api import SYNCHRONOUS
            influxdb_client = _idb
            
            if not config.INFLUX_TOKEN:
                logger.warning(
                    "InfluxDB token not configured. "
                    "Set INFLUX_TOKEN in config.py"
                )
                return False
            
            self._client = influxdb_client.InfluxDBClient(
                url=config.INFLUX_URL,
                token=config.INFLUX_TOKEN,
                org=config.INFLUX_ORG,
            )
            self._write_api = self._client.write_api(
                write_options=SYNCHRONOUS
            )
            self._initialized = True
            logger.info("✅ InfluxDB writer initialized")
            return True
            
        except ImportError:
            logger.warning(
                "influxdb-client not installed. "
                "Run: pip install influxdb-client"
            )
            return False
        except Exception as e:
            logger.error(f"InfluxDB init failed: {e}")
            return False
    
    def write_telemetry(self, node_id: str, area: str,
                        device_type: str, channel: str,
                        telemetry: dict):
        """Write a telemetry point to InfluxDB."""
        if not self._initialized:
            return
        
        try:
            point = influxdb_client.Point("device_telemetry") \
                .tag("node_id", node_id) \
                .tag("area", area) \
                .tag("device_type", device_type) \
                .tag("channel", channel) \
                .field("voltage", float(telemetry.get("voltage", 0))) \
                .field("current", float(telemetry.get("current", 0))) \
                .field("power", float(telemetry.get("power", 0))) \
                .field("energy", float(telemetry.get("energy", 0))) \
                .field("frequency", float(telemetry.get("frequency", 50))) \
                .field("pf", float(telemetry.get("pf", 1.0)))
            
            relay = telemetry.get("relay_state")
            if relay is not None:
                point = point.field("relay_state", int(relay))
            
            self._write_api.write(
                config.INFLUX_BUCKET, config.INFLUX_ORG, point
            )
            
        except Exception as e:
            logger.error(f"InfluxDB write error: {e}")
