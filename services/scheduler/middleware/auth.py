"""
Authentication and Authorization Middleware for Network Operators.

This module provides:
1. API key-based authentication for scheduler access
2. Role-based access control (RBAC) for policy operations
3. Request logging for audit trails

In production, this would integrate with:
- OAuth2/OIDC providers
- Certificate-based mTLS
- LDAP/Active Directory
"""

import os
import hashlib
import logging
from functools import wraps
from typing import Callable, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class OperatorRole(Enum):
    """Role-based access control levels."""
    VIEWER = 1      # Can view metrics and logs
    OPERATOR = 2    # Can view + modify slice policies
    ADMIN = 3       # Full access including cluster management


@dataclass
class AuthContext:
    """Authentication context passed through request chain."""
    operator_id: str
    role: OperatorRole
    api_key_hash: str
    authenticated: bool = False


class AuthMiddleware:
    """
    Simple API key authentication middleware.

    In production, replace with:
    - gRPC interceptors with JWT/OAuth2
    - mTLS certificate validation
    - Integration with enterprise IAM
    """

    def __init__(self):
        # In production, load from secure vault (e.g., HashiCorp Vault, AWS Secrets Manager)
        self._api_keys = {
            # Format: api_key_hash -> (operator_id, role)
            self._hash_key("admin-key-12345"): ("admin-001", OperatorRole.ADMIN),
            self._hash_key("operator-key-67890"): ("operator-001", OperatorRole.OPERATOR),
            self._hash_key("viewer-key-11111"): ("viewer-001", OperatorRole.VIEWER),
        }

        # Load additional keys from environment
        env_admin_key = os.getenv("SCHEDULER_ADMIN_API_KEY")
        if env_admin_key:
            self._api_keys[self._hash_key(env_admin_key)] = ("env-admin", OperatorRole.ADMIN)

    @staticmethod
    def _hash_key(key: str) -> str:
        """Hash API key for secure storage comparison."""
        return hashlib.sha256(key.encode()).hexdigest()

    def authenticate(self, api_key: Optional[str]) -> AuthContext:
        """
        Authenticate an API key and return auth context.

        Args:
            api_key: The API key from request headers

        Returns:
            AuthContext with authentication status and role
        """
        if not api_key:
            logger.warning("Authentication failed: No API key provided")
            return AuthContext(
                operator_id="anonymous",
                role=OperatorRole.VIEWER,
                api_key_hash="",
                authenticated=False
            )

        key_hash = self._hash_key(api_key)

        if key_hash in self._api_keys:
            operator_id, role = self._api_keys[key_hash]
            logger.info(f"Authenticated operator: {operator_id} with role: {role.name}")
            return AuthContext(
                operator_id=operator_id,
                role=role,
                api_key_hash=key_hash,
                authenticated=True
            )

        logger.warning(f"Authentication failed: Invalid API key")
        return AuthContext(
            operator_id="invalid",
            role=OperatorRole.VIEWER,
            api_key_hash=key_hash,
            authenticated=False
        )

    def require_role(self, minimum_role: OperatorRole) -> Callable:
        """
        Decorator to enforce minimum role requirement.

        Usage:
            @auth.require_role(OperatorRole.OPERATOR)
            def update_policy(ctx: AuthContext, policy: dict):
                ...
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(auth_ctx: AuthContext, *args, **kwargs):
                if not auth_ctx.authenticated:
                    raise PermissionError("Authentication required")

                if auth_ctx.role.value < minimum_role.value:
                    raise PermissionError(
                        f"Insufficient permissions. Required: {minimum_role.name}, "
                        f"Current: {auth_ctx.role.name}"
                    )

                return func(auth_ctx, *args, **kwargs)
            return wrapper
        return decorator


class PolicyEnforcer:
    """
    Policy enforcement middleware for scheduling decisions.

    Enforces:
    1. Slice-level resource limits
    2. QoS guarantees per slice type
    3. Fair sharing policies
    """

    def __init__(self):
        # Default policy limits (can be updated via cloud orchestrator)
        self.slice_limits = {
            "eMBB": {"max_prb_percent": 60, "min_prb_percent": 10},
            "URLLC": {"max_prb_percent": 40, "min_prb_percent": 20},
            "mMTC": {"max_prb_percent": 30, "min_prb_percent": 5},
        }

        # QoS requirements
        self.qos_requirements = {
            "eMBB": {"min_throughput_kbps": 1000, "max_latency_ms": 100},
            "URLLC": {"min_throughput_kbps": 100, "max_latency_ms": 1},
            "mMTC": {"min_throughput_kbps": 10, "max_latency_ms": 1000},
        }

    def enforce_allocation(self, allocations: list, total_prbs: int) -> list:
        """
        Enforce policy constraints on PRB allocations.

        Args:
            allocations: List of (ue_id, slice_id, prbs) tuples
            total_prbs: Total available PRBs

        Returns:
            Adjusted allocations respecting policy limits
        """
        # Aggregate by slice
        slice_prbs = {"eMBB": 0, "URLLC": 0, "mMTC": 0}
        for ue_id, slice_id, prbs in allocations:
            if slice_id in slice_prbs:
                slice_prbs[slice_id] += prbs

        # Check and log violations
        violations = []
        for slice_id, prbs in slice_prbs.items():
            if slice_id not in self.slice_limits:
                continue

            limits = self.slice_limits[slice_id]
            pct = (prbs / total_prbs) * 100 if total_prbs > 0 else 0

            if pct > limits["max_prb_percent"]:
                violations.append(f"{slice_id} exceeds max ({pct:.1f}% > {limits['max_prb_percent']}%)")
            elif pct < limits["min_prb_percent"]:
                violations.append(f"{slice_id} below min ({pct:.1f}% < {limits['min_prb_percent']}%)")

        if violations:
            logger.warning(f"Policy violations detected: {violations}")

        # In production, would adjust allocations to comply
        # For now, log and pass through (soft enforcement)
        return allocations

    def update_policy(self, auth_ctx: AuthContext, new_limits: dict) -> bool:
        """
        Update slice policy limits (requires OPERATOR role).

        Args:
            auth_ctx: Authentication context
            new_limits: New slice limit configuration

        Returns:
            True if update successful
        """
        if auth_ctx.role.value < OperatorRole.OPERATOR.value:
            logger.error(f"Policy update denied for {auth_ctx.operator_id}")
            return False

        for slice_id, limits in new_limits.items():
            if slice_id in self.slice_limits:
                self.slice_limits[slice_id].update(limits)
                logger.info(f"Policy updated for {slice_id} by {auth_ctx.operator_id}")

        return True


# Global instances
auth_middleware = AuthMiddleware()
policy_enforcer = PolicyEnforcer()
