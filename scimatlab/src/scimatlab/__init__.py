"""MATLAB bridge for SciStack.

Runs scidb's ``for_each`` on behalf of MATLAB and provides
:class:`MatlabLineageFcn`, a lightweight MATLAB function handle for
``scidb.check_node_state`` node coloring.

Usage from MATLAB (via py. interface):
    py.scimatlab.bridge.MatlabLineageFcn(source_hash, 'my_func', false)
"""

from .bridge import (
    MatlabLineageFcn,
    get_surrogate_class,
    register_matlab_variable,
)

__all__ = [
    "MatlabLineageFcn",
    "register_matlab_variable",
    "get_surrogate_class",
]
