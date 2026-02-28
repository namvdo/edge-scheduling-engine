import logging
import threading
from concurrent import futures
import grpc

import raft_pb2
import raft_pb2_grpc
from .raft_node import RaftNode, LogEntry

logger = logging.getLogger(__name__)

class RaftGrpcServer(raft_pb2_grpc.RaftServiceServicer):
    def __init__(self, node: RaftNode, port: int):
        self.node = node
        self.port = port
        self.server = None
        self.peers_stubs = {}
        
        # Inject callbacks into the node
        self.node.send_request_vote = self._send_request_vote
        self.node.send_append_entries = self._send_append_entries

    def start(self):
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        raft_pb2_grpc.add_RaftServiceServicer_to_server(self, self.server)
        listen_addr = f"0.0.0.0:{self.port}"
        self.server.add_insecure_port(listen_addr)
        self.server.start()
        logger.info(f"[{self.node.node_id}] Raft gRPC server listening on {listen_addr}")
        
    def stop(self):
        if self.server:
            self.server.stop(0)
            
    # --- RPC Handlers (Receiver) ---
    def AppendEntries(self, request, context):
        entries = [LogEntry(term=e.term, index=e.index, command=e.command) for e in request.entries]
        term, success = self.node.handle_append_entries(
            request.term, request.leader_id, request.prev_log_index, 
            request.prev_log_term, entries, request.leader_commit
        )
        return raft_pb2.AppendEntriesResponse(term=term, success=success)

    def RequestVote(self, request, context):
        term, granted = self.node.handle_request_vote(
            request.term, request.candidate_id, 
            request.last_log_index, request.last_log_term
        )
        return raft_pb2.RequestVoteResponse(term=term, vote_granted=granted)

    # --- RPC Clients (Sender) ---
    def _get_stub(self, peer: str):
        if peer not in self.peers_stubs:
            channel = grpc.insecure_channel(peer)
            self.peers_stubs[peer] = raft_pb2_grpc.RaftServiceStub(channel)
        return self.peers_stubs[peer]

    def _send_request_vote(self, peer: str, term: int, candidate_id: str, last_log_index: int, last_log_term: int) -> tuple[int, bool]:
        stub = self._get_stub(peer)
        req = raft_pb2.RequestVoteRequest(
            term=term,
            candidate_id=candidate_id,
            last_log_index=last_log_index,
            last_log_term=last_log_term
        )
        resp = stub.RequestVote(req, timeout=0.1)  # short timeout to prevent blocking
        return resp.term, resp.vote_granted

    def _send_append_entries(self, peer: str, term: int, leader_id: str, prev_log_index: int, prev_log_term: int, entries: list[LogEntry], leader_commit: int) -> tuple[int, bool]:
        stub = self._get_stub(peer)
        pb_entries = [raft_pb2.LogEntry(term=e.term, index=e.index, command=e.command) for e in entries]
        req = raft_pb2.AppendEntriesRequest(
            term=term,
            leader_id=leader_id,
            prev_log_index=prev_log_index,
            prev_log_term=prev_log_term,
            entries=pb_entries,
            leader_commit=leader_commit
        )
        resp = stub.AppendEntries(req, timeout=0.1)
        return resp.term, resp.success
