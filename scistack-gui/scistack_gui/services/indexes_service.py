"""
Indexes service — delegates to api/indexes.py.
"""

from __future__ import annotations


def list_indexes() -> dict:
    from scistack_gui.api.indexes import list_indexes
    return list_indexes()


def search_index_packages(name: str, q: str = "") -> dict:
    from scistack_gui.api.indexes import search_index_packages
    return search_index_packages(name, q=q)


def add_library(body: dict) -> dict:
    from scistack_gui.api.indexes import add_library
    return add_library(body)


def remove_library(name: str) -> dict:
    from scistack_gui.api.indexes import remove_library
    return remove_library(name)
