"""Backward-compatibility shim — the Log facade lives in ``scistacklog``.

This module is kept so one public contract stays intact:

- Python imports: ``from scidb.log import Log`` (used across scidb,
  scistack-gui, and scimatlab's bridge).

**Python callers only.** MATLAB must not reach the class through this path:
``py.scidb.log.Log.info(...)`` fails with "Dot indexing into the result of a
function call requires parentheses after the function name", because MATLAB
resolves ``py.<module>.<Class>.<method>`` statically only when the class is
*defined* in that module, and ``Log.__module__`` is ``"scistacklog"``. MATLAB
code calls ``py.scistacklog.Log.*`` (see ``+scidb/Log.m`` and ``+scifor/Log.m``).

See the ``scistacklog`` package for the implementation and format docs.
"""

from scistacklog import LAYERS, Log

__all__ = ["Log", "LAYERS"]
