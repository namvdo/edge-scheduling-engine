from __future__ import annotations

import enum
import json
import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


class RaftState(enum.Enum):
    FOLLOWER = 1
    CANDIDATE = 2
    LEADER = 3


@dataclass
class LogEntry:
    term: int
    index: int
    command: str  # JSON payload of the decision


class RaftNode:
    """Core Raft Consensus Logic.
    
    This class manages the Raft state machine, leader election, and log replication.
    It is decoupled from gRPC so it can be tested independently.
    """
    def __init__(self, node_id: str, peers: list[str], state_prefix: str = "/edge-scheduler"):
        self.node_id = node_id
        self.peers = peers
        self.state_prefix = state_prefix

        # Persistent state
        self.current_term = 0
        self.voted_for: str | None = None
        self.log: list[LogEntry] = [LogEntry(term=0, index=0, command="")] # dummy entry
        
        # Volatile state
        self.state = RaftState.FOLLOWER
        self.commit_index = 0
        self.last_applied = 0
        
        # Volatile state on leaders
        self.next_index: dict[str, int] = {p: 1 for p in self.peers}
        self.match_index: dict[str, int] = {p: 0 for p in self.peers}

        # Timers
        self.election_timeout_range = (0.150, 0.300) # 150ms to 300ms
        self.heartbeat_interval = 0.050 # 50ms
        
        self.last_heartbeat_time = time.time()
        
        # Callbacks (to be injected by the gRPC Server)
        self.send_request_vote: Callable[[str, int, str, int, int], tuple[int, bool]] | None = None
        self.send_append_entries: Callable[[str, int, str, int, int, list[LogEntry], int], tuple[int, bool]] | None = None
        self.on_commit: Callable[[LogEntry], None] | None = None

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._election_thread = threading.Thread(target=self._election_loop, daemon=True)
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)

    def start(self):
        self._election_thread.start()
        self._heartbeat_thread.start()
        logger.info(f"[{self.node_id}] RaftNode started.")

    def stop(self):
        self._stop_event.set()
        self._election_thread.join()
        self._heartbeat_thread.join()

    # --- Core Raft RPC Handlers ---
    def handle_request_vote(self, term: int, candidate_id: str, last_log_index: int, last_log_term: int) -> tuple[int, bool]:
        with self._lock:
            if term > self.current_term:
                self._become_follower(term)
                
            if term < self.current_term:
                return self.current_term, False

            # Check if log is up-to-date
            my_last_log = self.log[-1]
            log_ok = (last_log_term > my_last_log.term) or (last_log_term == my_last_log.term and last_log_index >= my_last_log.index)

            if (self.voted_for is None or self.voted_for == candidate_id) and log_ok:
                self.voted_for = candidate_id
                self.last_heartbeat_time = time.time()
                return self.current_term, True
                
            return self.current_term, False

    def handle_append_entries(self, term: int, leader_id: str, prev_log_index: int, prev_log_term: int, entries: list[LogEntry], leader_commit: int) -> tuple[int, bool]:
        with self._lock:
            if term > self.current_term:
                self._become_follower(term)

            if term < self.current_term:
                return self.current_term, False

            self._become_follower(term) # Recognize leader
            self.last_heartbeat_time = time.time()

            # Rule 2: Reply false if log doesn't contain an entry at prevLogIndex whose term matches prevLogTerm
            if prev_log_index >= len(self.log):
                return self.current_term, False
            if self.log[prev_log_index].term != prev_log_term:
                return self.current_term, False

            # Rule 3 & 4: Delete conflicting entries and append new ones
            for idx, entry in enumerate(entries):
                log_idx = prev_log_index + 1 + idx
                if log_idx < len(self.log):
                    if self.log[log_idx].term != entry.term:
                        self.log = self.log[:log_idx]
                        self.log.append(entry)
                else:
                    self.log.append(entry)

            # Rule 5: Update commit_index
            if leader_commit > self.commit_index:
                self.commit_index = min(leader_commit, len(self.log) - 1)
                self._apply_commits()

            return self.current_term, True

    # --- Client API ---
    def propose(self, command: str) -> bool:
        """Propose a new command. Returns True if this node is leader, False otherwise."""
        with self._lock:
            if self.state != RaftState.LEADER:
                return False
            
            entry = LogEntry(
                term=self.current_term, 
                index=len(self.log), 
                command=command
            )
            self.log.append(entry)
            self.match_index[self.node_id] = len(self.log) - 1
            # Next heartbeat will replicate it
            return True

    def get_latest_committed(self) -> str | None:
        with self._lock:
            if self.commit_index > 0:
                return self.log[self.commit_index].command
            return None

    # --- Internal Logic ---
    def _become_follower(self, term: int):
        self.state = RaftState.FOLLOWER
        self.current_term = term
        self.voted_for = None

    def _apply_commits(self):
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            if self.on_commit:
                self.on_commit(self.log[self.last_applied])

    def _election_loop(self):
        while not self._stop_event.is_set():
            timeout = random.uniform(*self.election_timeout_range)
            time.sleep(timeout)
            
            with self._lock:
                if self.state == RaftState.LEADER:
                    continue
                if time.time() - self.last_heartbeat_time >= timeout:
                    self._start_election()

    def _start_election(self):
        self.state = RaftState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.last_heartbeat_time = time.time()
        
        votes = 1
        term = self.current_term
        last_log = self.log[-1]

        logger.info(f"[{self.node_id}] starting election for term {term}")

        if not self.peers:
            # Single node cluster fast-path
            self._become_leader()
            return

        def request_vote_thread(peer: str):
            nonlocal votes
            if not self.send_request_vote: return
            
            try:
                resp_term, vote_granted = self.send_request_vote(
                    peer, term, self.node_id, last_log.index, last_log.term
                )
                
                with self._lock:
                    if self.state != RaftState.CANDIDATE or self.current_term != term:
                        return
                    if resp_term > self.current_term:
                        self._become_follower(resp_term)
                        return
                    if vote_granted:
                        votes += 1
                        if votes > (len(self.peers) + 1) // 2:
                            self._become_leader()
            except Exception as e:
                logger.debug(f"Failed to request vote from {peer}: {e}")

        for peer in self.peers:
            threading.Thread(target=request_vote_thread, args=(peer,), daemon=True).start()

    def _become_leader(self):
        self.state = RaftState.LEADER
        self.next_index = {p: len(self.log) for p in self.peers}
        self.match_index = {p: 0 for p in self.peers}
        self.match_index[self.node_id] = len(self.log) - 1
        logger.info(f"[{self.node_id}] became LEADER for term {self.current_term}")
        self._send_heartbeats()

    def _heartbeat_loop(self):
        while not self._stop_event.is_set():
            time.sleep(self.heartbeat_interval)
            with self._lock:
                if self.state == RaftState.LEADER:
                    self._send_heartbeats()

    def _send_heartbeats(self):
        term = self.current_term
        leader_commit = self.commit_index
        
        def send_append_entries_thread(peer: str):
            with self._lock:
                if self.state != RaftState.LEADER or self.current_term != term:
                    return
                next_idx = self.next_index[peer]
                prev_log_idx = next_idx - 1
                prev_log_term = self.log[prev_log_idx].term
                entries = self.log[next_idx:]
            
            if not self.send_append_entries: return
            try:
                resp_term, success = self.send_append_entries(
                    peer, term, self.node_id, prev_log_idx, prev_log_term, entries, leader_commit
                )
                
                with self._lock:
                    if self.state != RaftState.LEADER or self.current_term != term:
                        return
                    
                    if resp_term > self.current_term:
                        self._become_follower(resp_term)
                        return
                        
                    if success:
                        self.match_index[peer] = prev_log_idx + len(entries)
                        self.next_index[peer] = self.match_index[peer] + 1
                        
                        # Advance commit index
                        for i in range(len(self.log) - 1, self.commit_index, -1):
                            if self.log[i].term == self.current_term:
                                match_count = sum(1 for p in self.match_index.values() if self.match_index[p] >= i)
                                if match_count > (len(self.peers) + 1) // 2:
                                    self.commit_index = i
                                    self._apply_commits()
                                    break
                    else:
                        self.next_index[peer] = max(1, self.next_index[peer] - 1)
            except Exception as e:
                logger.debug(f"Failed to append entries to {peer}: {e}")

        for peer in self.peers:
            threading.Thread(target=send_append_entries_thread, args=(peer,), daemon=True).start()
