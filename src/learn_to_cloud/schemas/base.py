"""Immutable base models."""

from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """Base class for immutable Pydantic models (replaces frozen dataclasses)."""

    model_config = ConfigDict(frozen=True)


class StrictFrozenModel(BaseModel):
    """Immutable model that rejects unknown YAML fields.

    Use for curriculum entities so authoring mistakes (typos, stale
    fields) fail at load time instead of being silently ignored.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
