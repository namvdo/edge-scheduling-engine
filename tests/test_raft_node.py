import pytest
import time
from services.scheduler.cluster.raft_node import RaftNode, RaftState

def test_single_node_election():
    """A single node should become leader immediately if it has no peers."""
    node = RaftNode("node-1", [])
    node.start()
    
    # Wait for election timeout
    time.sleep(1.0)
    
    try:
        assert node.state == RaftState.LEADER
        assert node.current_term > 0
    finally:
        node.stop()

def test_raft_propose_when_leader():
    """A leader should successfully append an entry to its local log when proposing."""
    node = RaftNode("node-1", [])
    node.start()
    time.sleep(1.0) # wait to become leader
    
    try:
        assert node.state == RaftState.LEADER
        success = node.propose("test_command")
        
        assert success is True
        assert len(node.log) == 2 # Index 0 is dummy, Index 1 is our command
        assert node.log[1].command == "test_command"
    finally:
        node.stop()

def test_raft_propose_when_follower():
    """A follower must reject proposals."""
    node = RaftNode("node-1", ["peer-1"]) # Has a peer, will wait for election, starts as follower
    node.start()
    
    try:
        assert node.state == RaftState.FOLLOWER
        success = node.propose("fail_command")
        assert success is False
        assert len(node.log) == 1 # Only dummy entry
    finally:
        node.stop()
