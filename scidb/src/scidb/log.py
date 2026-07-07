"""Backward-compatibility shim — the Log facade lives in ``scistacklog``.

This module is kept so two public contracts stay intact:

- Python imports: ``from scidb.log import Log`` (used across scidb,
  scistack-gui, and scimatlab's bridge).
- MATLAB delegation: ``+scidb/Log.m`` calls ``py.scidb.log.Log.*``.

See the ``scistacklog`` package for the implementation and format docs.
"""

from scistacklog import LAYERS, Log

__all__ = ["Log", "LAYERS"]
