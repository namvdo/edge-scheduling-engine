import os
import sys
import time
import math
import random
import threading
import grpc

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "gen"))

import scheduler_pb2
import scheduler_pb2_grpc
import telemetry_pb2


class StatefulUE:
    """Represents a single User Equipment (UE) with physical traits and moving buffers."""
    def __init__(self, ue_id: str):
        self.ue_id = ue_id
        self.slice_id = random.choice(["eMBB", "URLLC", "mMTC"])
        # Position in a 500x500 meter grid around base station (0,0)
        self.x = random.uniform(-250, 250)
        self.y = random.uniform(-250, 250)
        
        # Buffers
        self.dl_buffer_bytes = random.randint(0, 100000)
        self.ul_buffer_bytes = random.randint(0, 50000)
        
        self.avg_throughput_kbps = 100

    def move(self):
        """Random walk mobility model."""
        self.x += random.uniform(-5, 5) # Moves max 5 meters per epoch
        self.y += random.uniform(-5, 5)

        # Restrict to cell boundaries
        self.x = max(-250, min(250, self.x))
        self.y = max(-250, min(250, self.y))

    def get_cqi_and_sinr(self) -> tuple[int, float]:
        """
        Convert physical distance to path loss, SINR, and CQI index.

        Uses simplified 3GPP-like urban microcell path loss model:
        - PL(d) = PL_0 + 10*n*log10(d/d_0), where n=2.5 (urban micro)
        - PL_0 = 38 dB at d_0 = 1m reference distance
        - Tx Power = 30 dBm, Noise Floor = -100 dBm
        """
        distance = math.sqrt(self.x**2 + self.y**2)
        distance = max(distance, 1.0)  # Minimum 1m to avoid log(0)

        # Path loss model parameters (urban microcell approximation)
        pl_0 = 38.0           # Reference path loss at 1m (dB)
        n = 2.5               # Path loss exponent (urban micro)
        tx_power = 30.0       # Transmit power (dBm)
        noise_floor = -100.0  # Thermal noise + interference (dBm)

        # Path loss: PL = PL_0 + 10*n*log10(d)
        path_loss = pl_0 + 10.0 * n * math.log10(distance)

        # Received power = Tx - PL
        rx_power = tx_power - path_loss

        # SINR = Rx - Noise Floor
        base_sinr = rx_power - noise_floor

        # Add log-normal shadow fading (std dev ~4dB in urban environments)
        shadow_fading = random.gauss(0, 4.0)
        sinr = base_sinr + shadow_fading
        sinr = max(-5.0, min(30.0, sinr))

        # CQI mapping: linear approximation of 3GPP TS 38.214 Table 5.2.2.1-3
        # This is a simplification; real CQI uses BLER-based lookup tables
        # CQI 1 ~ SINR -6dB, CQI 15 ~ SINR 22dB (approximate)
        cqi = int(max(1, min(15, round((sinr + 6) / 2))))

        return cqi, round(sinr, 2)

    def generate_traffic(self):
        """Poisson traffic arrival."""
        if self.slice_id == "eMBB":
            self.dl_buffer_bytes += int(random.expovariate(1/50000.0))
            self.ul_buffer_bytes += int(random.expovariate(1/10000.0))
        elif self.slice_id == "URLLC":
            self.dl_buffer_bytes += random.randint(0, 5000)
            self.ul_buffer_bytes += random.randint(0, 5000)
        else: # mMTC
            if random.random() < 0.2: # Bursty uplink
                self.ul_buffer_bytes += random.randint(500, 2000)

    def drain_buffers(self, allocated_prbs: int, cqi: int, tdd_dl_pct: float):
        """
        Drain buffers based on the granted PRBs, TDD split, and spectral efficiency (CQI).
        CQI roughly translates to bits/symbol. We simplify by mapping CQI to bytes/PRB.
        """
        tdd_ul_pct = 1.0 - tdd_dl_pct
        
        # Example mapping: CQI 15 = ~100 bytes/PRB, CQI 1 = ~10 bytes/PRB
        bytes_per_prb = max(10, cqi * 7)
        
        # Total bytes this UE could transmit this epoch
        total_capacity_bytes = allocated_prbs * bytes_per_prb
        
        dl_capacity = int(total_capacity_bytes * tdd_dl_pct)
        ul_capacity = int(total_capacity_bytes * tdd_ul_pct)

        # Drain and record throughput
        actual_dl_tx = min(self.dl_buffer_bytes, dl_capacity)
        actual_ul_tx = min(self.ul_buffer_bytes, ul_capacity)
        
        self.dl_buffer_bytes -= actual_dl_tx
        self.ul_buffer_bytes -= actual_ul_tx
        
        # Update running average throughput (kbps)
        tx_bits = (actual_dl_tx + actual_ul_tx) * 8
        throughput_kbps = tx_bits / 1000.0 / 0.1 # 100ms epoch
        self.avg_throughput_kbps = int(0.9 * self.avg_throughput_kbps + 0.1 * throughput_kbps)


class StatefulSimulator:
    def __init__(self, target="localhost:50051", cell_id="cell-1", total_prbs=100, ue_count=20):
        self.target = target
        self.cell_id = cell_id
        self.total_prbs = total_prbs
        self.ues = {f"ue-{i+1}": StatefulUE(f"ue-{i+1}") for i in range(ue_count)}
        self.epoch = 0
        self.lock = threading.Lock()
        
        # Initial TDD assumption until scheduler dictates
        self.last_tdd_dl_pct = 0.5 
        self.last_allocations = {}

    def _generate_telemetry(self):
        with self.lock:
            reports = []
            for ue in self.ues.values():
                cqi, sinr = ue.get_cqi_and_sinr()
                reports.append(
                    telemetry_pb2.UeReport(
                        ue_id=ue.ue_id,
                        slice_id=ue.slice_id,
                        cqi=cqi,
                        sinr_db=sinr,
                        dl_buffer_bytes=ue.dl_buffer_bytes,
                        ul_buffer_bytes=ue.ul_buffer_bytes,
                        avg_throughput_kbps=ue.avg_throughput_kbps,
                    )
                )

            msg = telemetry_pb2.CellTelemetry(
                cell_id=self.cell_id,
                epoch=self.epoch,
                timestamp_ms=int(time.time() * 1000),
                total_prbs=self.total_prbs,
                prb_utilization=0.0,
                ues=reports,
            )
            self.epoch += 1
            return msg

    def _apply_decision(self, decision: scheduler_pb2.ScheduleDecision):
        with self.lock:
            self.last_tdd_dl_pct = decision.tdd.dl_percent / 100.0
            
            for alloc in decision.allocations:
                if alloc.ue_id in self.ues:
                    ue = self.ues[alloc.ue_id]
                    cqi, _ = ue.get_cqi_and_sinr()
                    ue.drain_buffers(alloc.prbs, cqi, self.last_tdd_dl_pct)

            # Move and generate new traffic for the next epoch
            for ue in self.ues.values():
                ue.move()
                ue.generate_traffic()

    def telemetry_iterator(self):
        """Generator that continuously yields telemetry at exactly 10Hz (100ms epochs)"""
        while True:
            yield self._generate_telemetry()
            time.sleep(0.1)

    def run(self):
        print(f"Connecting to scheduler at {self.target}...")
        with grpc.insecure_channel(self.target) as channel:
            stub = scheduler_pb2_grpc.SchedulerServiceStub(channel)

            # Bidirectional stream
            decisions = stub.Schedule(self.telemetry_iterator())
            
            try:
                for d in decisions:
                    self._apply_decision(d)
                    
                    top3 = sorted(d.allocations, key=lambda x: x.prbs, reverse=True)[:3]
                    top3_str = ", ".join([f"{a.ue_id}:{a.prbs}" for a in top3])
                    
                    if self.epoch % 10 == 0:
                        total_dl = sum(ue.dl_buffer_bytes for ue in self.ues.values()) / 1024.0 / 1024.0
                        total_ul = sum(ue.ul_buffer_bytes for ue in self.ues.values()) / 1024.0 / 1024.0
                        
                        print(
                            f"[BS] epoch={d.epoch:<4} ver={d.decision_version:<3} "
                            f"TDD={d.tdd.dl_percent}/{d.tdd.ul_percent} | "
                            f"System Buffers: DL={total_dl:.2f}MB, UL={total_ul:.2f}MB | "
                            f"Top Alloc={top3_str}"
                        )
            except grpc.RpcError as e:
                print(f"Connection lost: {e}")

if __name__ == "__main__":
    import os
    scheduler_url = os.getenv("SCHEDULER_URL", "localhost:50051")
    sim = StatefulSimulator(target=scheduler_url, ue_count=20)
    sim.run()