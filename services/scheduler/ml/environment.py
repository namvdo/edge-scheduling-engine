import numpy as np
import random

class SchedulingEnv:
    """Simulated Gym-like environment for TDD and allocation scheduling."""
    
    def __init__(self, ues_count=8):
        self.ues_count = ues_count
        self.state_dim = 4 # avg_dl_buf, avg_ul_buf, avg_cqi, avg_sinr
        self.action_dim = 1 # dl_percent [0..1]
        self.reset()
        
    def reset(self):
        self.dl_buffers = np.random.randint(0, 50000, size=self.ues_count)
        self.ul_buffers = np.random.randint(0, 30000, size=self.ues_count)
        self.cqis = np.random.randint(1, 15, size=self.ues_count)
        self.sinrs = np.random.uniform(-5.0, 25.0, size=self.ues_count)
        self.time_step = 0
        return self._get_state()

    def _get_state(self):
        # Normalize roughly
        return np.array([
            np.mean(self.dl_buffers) / 50000.0,
            np.mean(self.ul_buffers) / 30000.0,
            np.mean(self.cqis) / 15.0,
            np.mean(self.sinrs) / 25.0,
        ], dtype=np.float32)

    def step(self, action):
        """
        action: [dl_ratio]
        Returns state, reward, done, info
        """
        dl_ratio = np.clip(action[0], 0.1, 0.9)
        ul_ratio = 1.0 - dl_ratio
        
        # Simulate traffic drain based on TDD ratio
        # A higher DL ratio drains DL buffers faster
        dl_throughput = dl_ratio * np.mean(self.cqis) * 1000
        ul_throughput = ul_ratio * np.mean(self.cqis) * 1000
        
        # Calculate Reward: Penalize large remaining buffers, encourage throughput
        dl_penalty = np.sum(np.maximum(0, self.dl_buffers - dl_throughput))
        ul_penalty = np.sum(np.maximum(0, self.ul_buffers - ul_throughput))
        
        reward = -(dl_penalty + ul_penalty) / 10000.0
        
        # Advance state
        self.dl_buffers = np.maximum(0, self.dl_buffers - dl_throughput) + np.random.randint(0, 20000, size=self.ues_count)
        self.ul_buffers = np.maximum(0, self.ul_buffers - ul_throughput) + np.random.randint(0, 15000, size=self.ues_count)
        self.cqis = np.clip(self.cqis + np.random.randint(-2, 3, size=self.ues_count), 1, 15)
        
        self.time_step += 1
        done = self.time_step >= 50 # 50 epochs per episode
        
        return self._get_state(), reward, done, {}
