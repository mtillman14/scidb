"""
Project service — delegates to api/project.py.
"""

from __future__ import annotations


def get_project_code() -> dict:
    from scistack_gui.api.project import get_project_code
    return get_project_code()


def get_project_libraries() -> dict:
    from scistack_gui.api.project import get_project_libraries
    return get_project_libraries()


def refresh_project() -> dict:
    from scistack_gui.api.project import refresh_project
    return refresh_project()
