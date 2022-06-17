"""
Module left for backwards compatibility.
Do not use in new code
Will be deprecated and eventually removed.
"""

from .instrument import (
    Instrument,
    InstrumentMeta,
    InstrumentProtocol,
    find_or_create_instrument,
)
from .instrument_base import InstrumentBase

__all__ = [
    "InstrumentBase",
    "InstrumentMeta",
    "InstrumentProtocol",
    "Instrument",
    "find_or_create_instrument",
]
