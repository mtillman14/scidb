"""Tests for :mod:`scistack.user_config` — user-global configuration & taps."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scistack.user_config import (
    Tap,
    UserConfig,
    _infer_tap_name,
    add_tap,
    list_taps,
    load_config,
    refresh_tap,
    remove_tap,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def config_dir(tmp_path):
    """Return a fresh temporary config directory."""
    d = tmp_path / ".scistack"
    d.mkdir()
    return d


@pytest.fixture
def fake_git(monkeypatch):
    """
    Patch subprocess.run to intercept git clone / pull calls.
    Returns a controller with recorded calls.
    """

    class Controller:
        def __init__(self):
            self.calls: list[dict] = []
            self.fail_next = False

        def _run(self, cmd, **kwargs):
            self.calls.append({"cmd": tuple(cmd), "kwargs": kwargs})
            if self.fail_next:
                raise subprocess.CalledProcessError(1, cmd, output="", stderr="fake error")
            # For git clone, create the target directory so exists_locally works.
            if len(cmd) >= 2 and cmd[1] == "clone":
                # Last arg is the target path.
                target = Path(cmd[-1])
                target.mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    ctl = Controller()
    monkeypatch.setattr("scistack.user_config.subprocess.run", ctl._run)
    return ctl


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------
class TestLoadConfig:
    def test_creates_dir_and_empty_config(self, tmp_path):
        cfg_dir = tmp_path / "fresh_scistack"
        config = load_config(config_dir=cfg_dir)
        assert isinstance(config, UserConfig)
        assert config.config_dir == cfg_dir
        assert config.taps == []
        assert (cfg_dir / "config.toml").is_file()

    def test_roundtrip_with_taps(self, config_dir):
        (config_dir / "config.toml").write_text(
            '# config\n\n'
            '[[tap]]\nname = "mylab"\nurl = "https://github.com/mylab/index.git"\n\n'
            '[[tap]]\nname = "shared"\nurl = "https://github.com/shared/index.git"\n'
        )
        config = load_config(config_dir=config_dir)
        assert len(config.taps) == 2
        assert config.taps[0].name == "mylab"
        assert config.taps[0].url == "https://github.com/mylab/index.git"
        assert config.taps[1].name == "shared"

    def test_local_path_under_taps_dir(self, config_dir):
        (config_dir / "config.toml").write_text(
            '[[tap]]\nname = "mylab"\nurl = "https://example.com/index.git"\n'
        )
        config = load_config(config_dir=config_dir)
        assert config.taps[0].local_path == config_dir / "taps" / "mylab"

    def test_malformed_config_falls_back_to_empty(self, config_dir):
        (config_dir / "config.toml").write_text("!!! not valid toml !!!")
        config = load_config(config_dir=config_dir)
        assert config.taps == []

    def test_skips_incomplete_tap_entries(self, config_dir):
        # Missing url on first entry — should be skipped.
        (config_dir / "config.toml").write_text(
            '[[tap]]\nname = "no_url"\n\n'
            '[[tap]]\nname = "ok"\nurl = "https://example.com"\n'
        )
        config = load_config(config_dir=config_dir)
        assert len(config.taps) == 1
        assert config.taps[0].name == "ok"


# ---------------------------------------------------------------------------
# add_tap
# ---------------------------------------------------------------------------
class TestAddTap:
    def test_add_tap_with_explicit_name(self, config_dir, fake_git):
        tap = add_tap(
            "https://github.com/mylab/index.git",
            name="mylab",
            config_dir=config_dir,
        )
        assert tap.name == "mylab"
        assert tap.url == "https://github.com/mylab/index.git"
        # Verify it was persisted.
        taps = list_taps(config_dir=config_dir)
        assert len(taps) == 1
        assert taps[0].name == "mylab"
        # Verify git clone was called.
        assert len(fake_git.calls) == 1
        assert fake_git.calls[0]["cmd"][1] == "clone"

    def test_add_tap_infers_name_from_url(self, config_dir, fake_git):
        tap = add_tap(
            "https://github.com/mylab/scistack-index.git",
            config_dir=config_dir,
        )
        assert tap.name == "scistack-index"

    def test_add_tap_duplicate_raises(self, config_dir, fake_git):
        add_tap("https://example.com/a.git", name="mylab", config_dir=config_dir)
        with pytest.raises(ValueError, match="already exists"):
            add_tap("https://example.com/b.git", name="mylab", config_dir=config_dir)

    def test_add_tap_invalid_name_raises(self, config_dir, fake_git):
        with pytest.raises(ValueError, match="Invalid tap name"):
            add_tap("https://example.com/a.git", name="My Lab!", config_dir=config_dir)

    def test_add_tap_without_clone(self, config_dir, fake_git):
        tap = add_tap(
            "https://example.com/a.git",
            name="noclone",
            config_dir=config_dir,
            clone=False,
        )
        assert not tap.exists_locally
        assert len(fake_git.calls) == 0

    def test_add_tap_clone_failure_still_saves(self, config_dir, fake_git):
        fake_git.fail_next = True
        tap = add_tap(
            "https://example.com/a.git",
            name="fails",
            config_dir=config_dir,
        )
        # Tap is saved in config even though clone failed.
        taps = list_taps(config_dir=config_dir)
        assert len(taps) == 1
        assert taps[0].name == "fails"


# ---------------------------------------------------------------------------
# remove_tap
# ---------------------------------------------------------------------------
class TestRemoveTap:
    def test_remove_by_name(self, config_dir, fake_git):
        add_tap("https://example.com/a.git", name="mylab", config_dir=config_dir)
        remove_tap("mylab", config_dir=config_dir)
        assert list_taps(config_dir=config_dir) == []

    def test_remove_by_url(self, config_dir, fake_git):
        add_tap("https://example.com/a.git", name="mylab", config_dir=config_dir)
        remove_tap("https://example.com/a.git", config_dir=config_dir)
        assert list_taps(config_dir=config_dir) == []

    def test_remove_nonexistent_raises(self, config_dir):
        with pytest.raises(KeyError, match="No tap found"):
            remove_tap("ghost", config_dir=config_dir)

    def test_remove_deletes_clone_dir(self, config_dir, fake_git):
        tap = add_tap("https://example.com/a.git", name="mylab", config_dir=config_dir)
        assert tap.exists_locally  # fake_git creates the directory
        remove_tap("mylab", config_dir=config_dir)
        assert not tap.local_path.exists()

    def test_remove_without_deleting_clone(self, config_dir, fake_git):
        tap = add_tap("https://example.com/a.git", name="mylab", config_dir=config_dir)
        remove_tap("mylab", config_dir=config_dir, delete_clone=False)
        assert tap.local_path.exists()  # still there


# ---------------------------------------------------------------------------
# refresh_tap
# ---------------------------------------------------------------------------
class TestRefreshTap:
    def test_refresh_pulls(self, config_dir, fake_git):
        add_tap("https://example.com/a.git", name="mylab", config_dir=config_dir)
        ok = refresh_tap("mylab", config_dir=config_dir)
        assert ok
        # First call is clone (from add_tap), second is pull (from refresh_tap).
        assert fake_git.calls[-1]["cmd"][:2] == ("git", "pull")

    def test_refresh_clones_if_not_cloned(self, config_dir, fake_git):
        add_tap("https://example.com/a.git", name="mylab", config_dir=config_dir, clone=False)
        ok = refresh_tap("mylab", config_dir=config_dir)
        assert ok
        assert fake_git.calls[-1]["cmd"][1] == "clone"

    def test_refresh_nonexistent_raises(self, config_dir):
        with pytest.raises(KeyError, match="No tap named"):
            refresh_tap("ghost", config_dir=config_dir)

    def test_refresh_failure_returns_false(self, config_dir, fake_git):
        add_tap("https://example.com/a.git", name="mylab", config_dir=config_dir)
        fake_git.fail_next = True
        ok = refresh_tap("mylab", config_dir=config_dir)
        assert not ok


# ---------------------------------------------------------------------------
# list_taps
# ---------------------------------------------------------------------------
class TestListTaps:
    def test_empty(self, config_dir):
        assert list_taps(config_dir=config_dir) == []

    def test_multiple(self, config_dir, fake_git):
        add_tap("https://example.com/a.git", name="alpha", config_dir=config_dir)
        add_tap("https://example.com/b.git", name="beta", config_dir=config_dir)
        taps = list_taps(config_dir=config_dir)
        assert len(taps) == 2
        names = {t.name for t in taps}
        assert names == {"alpha", "beta"}


# ---------------------------------------------------------------------------
# _infer_tap_name
# ---------------------------------------------------------------------------
class TestInferTapName:
    def test_github_url(self):
        assert _infer_tap_name("https://github.com/mylab/scistack-index.git") == "scistack-index"

    def test_trailing_slash(self):
        assert _infer_tap_name("https://github.com/mylab/index/") == "index"

    def test_no_git_suffix(self):
        assert _infer_tap_name("https://github.com/mylab/my-packages") == "my-packages"

    def test_weird_chars_stripped(self):
        name = _infer_tap_name("https://example.com/My Packages!!")
        assert name == "my-packages"


# ---------------------------------------------------------------------------
# Tap dataclass
# ---------------------------------------------------------------------------
class TestTap:
    def test_exists_locally(self, tmp_path):
        tap = Tap(name="x", url="", local_path=tmp_path)
        assert tap.exists_locally

    def test_not_exists_locally(self, tmp_path):
        tap = Tap(name="x", url="", local_path=tmp_path / "nope")
        assert not tap.exists_locally


# ---------------------------------------------------------------------------
# SCISTACK_CONFIG_DIR environment variable
# ---------------------------------------------------------------------------
class TestConfigDirEnvVar:
    def test_env_var_overrides_default(self, tmp_path, monkeypatch):
        custom_dir = tmp_path / "custom_scistack"
        monkeypatch.setenv("SCISTACK_CONFIG_DIR", str(custom_dir))
        from scistack.user_config import _default_config_dir

        assert _default_config_dir() == custom_dir

    def test_env_var_not_set_uses_home(self, monkeypatch):
        monkeypatch.delenv("SCISTACK_CONFIG_DIR", raising=False)
        from scistack.user_config import _default_config_dir

        result = _default_config_dir()
        assert result == Path.home() / ".scistack"


# ---------------------------------------------------------------------------
# _save_config roundtrip accuracy
# ---------------------------------------------------------------------------
class TestSaveConfigRoundtrip:
    def test_save_and_reload_preserves_taps(self, config_dir, fake_git):
        """Adding taps, saving, and reloading should preserve all data."""
        add_tap("https://example.com/a.git", name="alpha", config_dir=config_dir)
        add_tap("https://example.com/b.git", name="beta", config_dir=config_dir)

        # Reload from disk
        config = load_config(config_dir=config_dir)
        assert len(config.taps) == 2
        names = [t.name for t in config.taps]
        assert "alpha" in names
        assert "beta" in names

        urls = [t.url for t in config.taps]
        assert "https://example.com/a.git" in urls
        assert "https://example.com/b.git" in urls

    def test_save_after_remove_persists(self, config_dir, fake_git):
        add_tap("https://example.com/a.git", name="alpha", config_dir=config_dir)
        add_tap("https://example.com/b.git", name="beta", config_dir=config_dir)
        remove_tap("alpha", config_dir=config_dir)

        config = load_config(config_dir=config_dir)
        assert len(config.taps) == 1
        assert config.taps[0].name == "beta"


# ---------------------------------------------------------------------------
# Config edge cases
# ---------------------------------------------------------------------------
class TestConfigEdgeCases:
    def test_config_with_only_comment(self, config_dir):
        """A config file with just comments and no tap entries."""
        (config_dir / "config.toml").write_text("# Just a comment\n")
        config = load_config(config_dir=config_dir)
        assert config.taps == []

    def test_config_with_extra_keys_ignored(self, config_dir):
        """Extra keys in tap entries should be silently ignored."""
        (config_dir / "config.toml").write_text(
            '[[tap]]\nname = "ok"\nurl = "https://example.com"\nextra = "ignored"\n'
        )
        config = load_config(config_dir=config_dir)
        assert len(config.taps) == 1
        assert config.taps[0].name == "ok"

    def test_config_with_empty_tap_table(self, config_dir):
        """An empty [[tap]] table (no name, no url) should be skipped."""
        (config_dir / "config.toml").write_text("[[tap]]\n\n")
        config = load_config(config_dir=config_dir)
        assert config.taps == []


# ---------------------------------------------------------------------------
# Multiple add/remove cycles
# ---------------------------------------------------------------------------
class TestAddRemoveCycles:
    def test_add_remove_readd_same_name(self, config_dir, fake_git):
        add_tap("https://example.com/a.git", name="cycling", config_dir=config_dir)
        remove_tap("cycling", config_dir=config_dir)
        # Re-adding with same name should work
        tap = add_tap("https://example.com/b.git", name="cycling", config_dir=config_dir)
        assert tap.name == "cycling"
        assert tap.url == "https://example.com/b.git"
        taps = list_taps(config_dir=config_dir)
        assert len(taps) == 1

    def test_add_multiple_remove_all(self, config_dir, fake_git):
        for i in range(5):
            add_tap(f"https://example.com/{i}.git", name=f"tap{i}", config_dir=config_dir)
        assert len(list_taps(config_dir=config_dir)) == 5

        for i in range(5):
            remove_tap(f"tap{i}", config_dir=config_dir)
        assert len(list_taps(config_dir=config_dir)) == 0


# ---------------------------------------------------------------------------
# Tap name validation edge cases
# ---------------------------------------------------------------------------
class TestTapNameEdgeCases:
    def test_tap_name_with_digits(self, config_dir, fake_git):
        tap = add_tap("https://example.com/a.git", name="lab42", config_dir=config_dir)
        assert tap.name == "lab42"

    def test_tap_name_starts_with_digit_rejected(self, config_dir, fake_git):
        with pytest.raises(ValueError, match="Invalid tap name"):
            add_tap("https://example.com/a.git", name="42lab", config_dir=config_dir)

    def test_tap_name_with_hyphen(self, config_dir, fake_git):
        tap = add_tap("https://example.com/a.git", name="my-lab", config_dir=config_dir)
        assert tap.name == "my-lab"

    def test_tap_name_with_underscore(self, config_dir, fake_git):
        tap = add_tap("https://example.com/a.git", name="my_lab", config_dir=config_dir)
        assert tap.name == "my_lab"


# ---------------------------------------------------------------------------
# _infer_tap_name edge cases
# ---------------------------------------------------------------------------
class TestInferTapNameEdgeCases:
    def test_empty_url_returns_tap(self):
        assert _infer_tap_name("") == "tap"

    def test_url_with_only_slashes(self):
        # Edge case: just protocol and slashes
        name = _infer_tap_name("https:///")
        assert isinstance(name, str)
        assert len(name) > 0

    def test_url_with_uppercase_chars(self):
        name = _infer_tap_name("https://github.com/MyLab/MyIndex.git")
        assert name == name.lower()
        assert name == "myindex"
