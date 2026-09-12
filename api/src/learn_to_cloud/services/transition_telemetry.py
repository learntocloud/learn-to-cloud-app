"""Privacy-preserving identifiers for phase transition measurements."""

import hashlib
import hmac

from learn_to_cloud_shared.core.config import get_web_settings


def build_phase_transition_id(
    user_id: int,
    *,
    source_phase: int,
    target_phase: int,
) -> str:
    """Create an opaque identifier scoped to one learner phase transition."""
    payload = f"phase-transition:v1:{user_id}:{source_phase}:{target_phase}".encode()
    secret = get_web_settings().session.secret_key.encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()[:24]


def is_valid_phase_transition_id(
    transition_id: str,
    user_id: int,
    *,
    source_phase: int,
    target_phase: int,
) -> bool:
    """Validate a transition identifier without exposing learner identity."""
    expected = build_phase_transition_id(
        user_id,
        source_phase=source_phase,
        target_phase=target_phase,
    )
    return hmac.compare_digest(transition_id, expected)
