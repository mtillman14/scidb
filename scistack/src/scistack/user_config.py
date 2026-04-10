"""
User-global SciStack configuration.

Manages ``~/.scistack/config.toml`` — the per-machine configuration that
stores tapped package indexes. Taps are GitHub repos that list available
scistack libraries and their index URLs.

A tap's local clone lives at ``~/.scistack/taps/{name}/`` and is expected
to contain a ``packages.toml`` listing available packages and their index
URLs. The metadata format inside a tap is deferred until Phase 7 (the
add-library dialog needs it); for now a tap is just a tracked Git clone.

Typical use::

    from scistack.user_config import load_config, add_tap, list_taps

    config = load_config()
    add_tap("https://github.com/mylab/scistack-index.git", name="mylab")
    for tap in list_taps():
        print(tap.name, tap.url)
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    try:
        import tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------
@dataclass
class Tap:
    """A tapped package index."""

    name: str
    """Short identifier (e.g. ``"mylab"``)."""

    url: str
    """Remote Git URL for the tap repository."""

    local_path: Path
    """Absolute path to the local clone under ``~/.scistack/taps/``."""

    @property
    def exists_locally(self) -> bool:
        """True if the local clone directory exists."""
        return self.local_path.is_dir()


@dataclass
class UserConfig:
    """Parsed contents of ``~/.scistack/config.toml``."""

    config_dir: Path
    """``~/.scistack`` (or override)."""

    taps: list[Tap] = field(default_factory=list)
    """All configured taps."""


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def _default_config_dir() -> Path:
    """Return ``~/.scistack``, respecting ``$SCISTACK_CONFIG_DIR`` override."""
    override = os.environ.get("SCISTACK_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".scistack"


def _config_path(config_dir: Path) -> Path:
    return config_dir / "config.toml"


def _taps_dir(config_dir: Path) -> Path:
    return config_dir / "taps"


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------
def load_config(config_dir: Path | None = None) -> UserConfig:
    """Load ``~/.scistack/config.toml``.

    Creates the directory and an empty config file if they don't exist.

    Args:
        config_dir: Override for ``~/.scistack``. Useful for testing.
    """
    config_dir = config_dir or _default_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    cfg_path = _config_path(config_dir)
    if not cfg_path.exists():
        cfg_path.write_text("# SciStack user configuration\n\n[[tap]]\n")
        # The empty [[tap]] header makes TOML parsing return an empty
        # list for "tap" rather than missing key — but that's invalid
        # TOML if we leave it as an empty table header.
        # Write a truly empty config instead.
        cfg_path.write_text("# SciStack user configuration\n")

    try:
        with open(cfg_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        logger.warning("Failed to parse %s — starting from empty config", cfg_path, exc_info=True)
        data = {}

    taps_root = _taps_dir(config_dir)
    taps: list[Tap] = []
    for entry in data.get("tap", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        url = entry.get("url", "")
        if not name or not url:
            continue
        taps.append(
            Tap(
                name=name,
                url=url,
                local_path=taps_root / name,
            )
        )

    return UserConfig(config_dir=config_dir, taps=taps)


def _save_config(config: UserConfig) -> None:
    """Write ``config`` back to ``config.toml``."""
    lines = ["# SciStack user configuration\n"]
    for tap in config.taps:
        lines.append("")
        lines.append("[[tap]]")
        lines.append(f'name = "{tap.name}"')
        lines.append(f'url = "{tap.url}"')
    lines.append("")

    cfg_path = _config_path(config.config_dir)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Tap management
# ---------------------------------------------------------------------------
_TAP_NAME_RE = re.compile(r"[a-z][a-z0-9_-]*")


def _infer_tap_name(url: str) -> str:
    """Derive a short tap name from a Git URL."""
    # Strip .git suffix and take the last path component.
    base = url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
    # Normalise to lowercase with hyphens/underscores only.
    base = re.sub(r"[^a-z0-9_-]", "-", base.lower()).strip("-")
    return base or "tap"


def add_tap(
    url: str,
    name: str | None = None,
    *,
    config_dir: Path | None = None,
    clone: bool = True,
) -> Tap:
    """Add a tapped package index.

    Args:
        url: Git remote URL of the tap repository.
        name: Short identifier. If None, inferred from the URL.
        config_dir: Override for ``~/.scistack``.
        clone: If True (default), ``git clone`` the tap immediately.

    Returns:
        The newly created :class:`Tap`.

    Raises:
        ValueError: If a tap with the same name already exists.
    """
    config = load_config(config_dir)
    if name is None:
        name = _infer_tap_name(url)
    if not _TAP_NAME_RE.fullmatch(name):
        raise ValueError(
            f"Invalid tap name: {name!r}. Must use lowercase letters, digits, "
            f"hyphens, and underscores, starting with a letter."
        )
    existing_names = {t.name for t in config.taps}
    if name in existing_names:
        raise ValueError(f"Tap {name!r} already exists. Remove it first or use a different name.")

    taps_root = _taps_dir(config.config_dir)
    local_path = taps_root / name

    tap = Tap(name=name, url=url, local_path=local_path)
    config.taps.append(tap)
    _save_config(config)

    if clone:
        _clone_tap(tap)

    return tap


def remove_tap(
    name_or_url: str,
    *,
    config_dir: Path | None = None,
    delete_clone: bool = True,
) -> None:
    """Remove a tap by name or URL.

    Args:
        name_or_url: The tap's name or its remote URL.
        config_dir: Override for ``~/.scistack``.
        delete_clone: If True (default), delete the local clone directory.

    Raises:
        KeyError: If no matching tap is found.
    """
    config = load_config(config_dir)
    match = None
    for tap in config.taps:
        if tap.name == name_or_url or tap.url == name_or_url:
            match = tap
            break
    if match is None:
        raise KeyError(f"No tap found matching {name_or_url!r}.")

    config.taps = [t for t in config.taps if t.name != match.name]
    _save_config(config)

    if delete_clone and match.local_path.exists():
        shutil.rmtree(match.local_path)
        logger.info("Deleted local clone for tap %s at %s", match.name, match.local_path)


def list_taps(*, config_dir: Path | None = None) -> list[Tap]:
    """Return all configured taps."""
    return load_config(config_dir).taps


def refresh_tap(
    name: str,
    *,
    config_dir: Path | None = None,
) -> bool:
    """``git pull`` the named tap to get the latest package metadata.

    Returns True on success, False on failure (logged but not raised).
    """
    config = load_config(config_dir)
    tap = None
    for t in config.taps:
        if t.name == name:
            tap = t
            break
    if tap is None:
        raise KeyError(f"No tap named {name!r}.")

    if not tap.exists_locally:
        logger.info("Tap %s not cloned yet; cloning from %s", name, tap.url)
        return _clone_tap(tap)

    return _pull_tap(tap)


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------
def _clone_tap(tap: Tap) -> bool:
    """Clone a tap repository to its local path. Returns True on success."""
    tap.local_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", tap.url, str(tap.local_path)],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        logger.info("Cloned tap %s from %s to %s", tap.name, tap.url, tap.local_path)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("Failed to clone tap %s from %s: %s", tap.name, tap.url, e)
        return False


def _pull_tap(tap: Tap) -> bool:
    """Pull the latest changes for a tap. Returns True on success."""
    try:
        subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(tap.local_path),
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        logger.info("Updated tap %s", tap.name)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("Failed to pull tap %s: %s", tap.name, e)
        return False
