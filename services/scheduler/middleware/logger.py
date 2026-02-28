import os
import json
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

class TelemetryLogger:
    """
    Centralized logging middleware for historical Big Data analysis.
    Writes telemetry and scheduling decisions to a JSONL file.
    """
    def __init__(self, log_dir: str = "data/logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "telemetry.jsonl")
        self._lock = threading.Lock()

    def log_decision(self, telemetry: Any, decision: Any, tdd_dl: int, tdd_ul: int):
        """Log a combined JSON record of the state and the decision."""
        try:
            record = {
                "timestamp_ms": telemetry.timestamp_ms,
                "cell_id": telemetry.cell_id,
                "epoch": telemetry.epoch,
                "decision_version": decision.decision_version,
                "tdd": {"dl_percent": tdd_dl, "ul_percent": tdd_ul},
                "ues": []
            }
            
            # Create a lookup for allocations to easily merge them into UE reports
            alloc_map = {a.ue_id: a.prbs for a in decision.allocations}

            for ue in telemetry.ues:
                record["ues"].append({
                    "ue_id": ue.ue_id,
                    "slice_id": ue.slice_id,
                    "cqi": ue.cqi,
                    "sinr_db": ue.sinr_db,
                    "dl_buffer_bytes": ue.dl_buffer_bytes,
                    "ul_buffer_bytes": ue.ul_buffer_bytes,
                    "allocated_prbs": alloc_map.get(ue.ue_id, 0)
                })

            with self._lock:
                with open(self.log_file, "a") as f:
                    f.write(json.dumps(record) + "\n")
                    
        except Exception as e:
            logger.error(f"Failed to write telemetry log: {e}")

