"""
Memory Engine — 3-tier memory system for user behavior learning.

🎯 CORE GOAL: This module enables the system to LEARN and REMEMBER.
Without memory, there is no learning. Without learning, no autonomy.
"""

import sqlite3
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

import config

logger = logging.getLogger("memory")
TZ_VN = timezone(timedelta(hours=7))


class MemoryEngine:
    """Three-tier memory: STM (RAM), MTM (SQLite), LTM (InfluxDB+SQLite)."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.MEMORY_DB
        self.stm = {}  # Short-term memory (RAM)
        self._init_db()
    
    def _init_db(self):
        """Create SQLite tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.executescript("""
            -- Command history log
            CREATE TABLE IF NOT EXISTS command_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hour INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL,
                user_text TEXT,
                action TEXT NOT NULL,
                device TEXT NOT NULL,
                area TEXT NOT NULL,
                node_id TEXT,
                channel TEXT,
                verify_result TEXT,
                power_before REAL,
                power_after REAL
            );
            
            -- User corrections for prompt improvement
            CREATE TABLE IF NOT EXISTS user_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                original_text TEXT,
                original_device TEXT,
                original_area TEXT,
                corrected_device TEXT,
                corrected_area TEXT,
                notes TEXT
            );
            
            -- Learned behavioral patterns
            CREATE TABLE IF NOT EXISTS learned_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                device TEXT NOT NULL,
                area TEXT NOT NULL,
                action TEXT NOT NULL,
                trigger_hour INTEGER,
                trigger_day_of_week INTEGER,
                confidence REAL DEFAULT 0.0,
                occurrence_count INTEGER DEFAULT 0,
                rejection_count INTEGER DEFAULT 0,
                last_occurred TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TEXT NOT NULL
            );
            
            -- Power consumption baselines
            CREATE TABLE IF NOT EXISTS power_baselines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                device_type TEXT NOT NULL,
                avg_watts REAL,
                max_watts REAL,
                min_watts REAL,
                measurement_count INTEGER,
                last_updated TEXT
            );
            
            -- Optimized indexes
            CREATE INDEX IF NOT EXISTS idx_cmd_device_area
                ON command_log(device, area, hour);
            CREATE INDEX IF NOT EXISTS idx_patterns_active
                ON learned_patterns(is_active, trigger_hour);
            CREATE INDEX IF NOT EXISTS idx_baselines_node
                ON power_baselines(node_id, channel);
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Memory database initialized: {self.db_path}")
    
    def record_command(self, user_text: str, action: str, device: str,
                       area: str, node_id: str = None, channel: str = None,
                       verify_result: str = None, power_before: float = None,
                       power_after: float = None):
        """Record a command execution to history."""
        now = datetime.now(TZ_VN)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO command_log 
               (timestamp, hour, day_of_week, user_text, action, device,
                area, node_id, channel, verify_result, power_before, power_after)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now.isoformat(), now.hour, now.weekday(), user_text,
             action, device, area, node_id, channel,
             verify_result, power_before, power_after)
        )
        conn.commit()
        conn.close()
        logger.debug(f"Command logged: {action} {device}@{area}")
    
    def record_correction(self, original_text: str,
                          original_device: str, original_area: str,
                          corrected_device: str, corrected_area: str,
                          notes: str = None):
        """Record when user corrects a misunderstood command."""
        now = datetime.now(TZ_VN)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO user_corrections
               (timestamp, original_text, original_device, original_area,
                corrected_device, corrected_area, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (now.isoformat(), original_text, original_device,
             original_area, corrected_device, corrected_area, notes)
        )
        conn.commit()
        conn.close()
        logger.info(f"Correction logged: {original_device}→{corrected_device}")
    
    def get_active_patterns(self, trigger_hour: int,
                            trigger_day_of_week: int = None) -> list:
        """Get patterns that should trigger at this time."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        if trigger_day_of_week is not None:
            rows = conn.execute(
                """SELECT * FROM learned_patterns
                   WHERE is_active = 1
                   AND trigger_hour = ?
                   AND (trigger_day_of_week IS NULL 
                        OR trigger_day_of_week = ?)
                   ORDER BY confidence DESC""",
                (trigger_hour, trigger_day_of_week)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM learned_patterns
                   WHERE is_active = 1 AND trigger_hour = ?
                   ORDER BY confidence DESC""",
                (trigger_hour,)
            ).fetchall()
        
        conn.close()
        return [dict(r) for r in rows]
    
    def get_baseline_power(self, node_id: str,
                           channel: str) -> Optional[float]:
        """Get average power baseline for a device."""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            """SELECT avg_watts FROM power_baselines
               WHERE node_id = ? AND channel = ?""",
            (node_id, channel)
        ).fetchone()
        conn.close()
        return row[0] if row else None
    
    def get_command_count_today(self) -> int:
        """Get total commands executed today."""
        today = datetime.now(TZ_VN).date().isoformat()
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            """SELECT COUNT(*) FROM command_log
               WHERE timestamp LIKE ?""",
            (f"{today}%",)
        ).fetchone()
        conn.close()
        return row[0] if row else 0
