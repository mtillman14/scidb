"""Path template input for for_each."""

import json
import os
import re
import string as _string
from pathlib import Path
from typing import Any

from scistacklog import Log


def _numeric_like(value: Any) -> bool:
    """True when *value* denotes an integer regardless of representation.

    Covers Python ints, integral floats (MATLAB doubles cross the bridge as
    ``1.0``), and digit strings (the MATLAB wrapper's ``num2str`` marshaling
    produces ``"1"``).  Bools are excluded — ``True`` is not the number 1 in
    a filename.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    if isinstance(value, str):
        return value.isdigit()
    return False


def _find_project_root(start: Path | None = None) -> Path:
    """Walk up from *start* (or cwd) to find the nearest project root.

    The root is the first ancestor directory that contains ``pyproject.toml``
    or ``scistack.toml``.  Falls back to *start* (or cwd) when neither file
    is found anywhere in the hierarchy.
    """
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        if (directory / "pyproject.toml").exists() or (directory / "scistack.toml").exists():
            return directory
    return current


class PathInput:
    """
    Resolve a path template using iteration metadata.

    Works as an input to for_each: on each iteration, .load() substitutes
    the current metadata values into the template and returns the resolved
    file path.  The user's function receives the path and handles file
    reading itself.

    Args:
        path_template: A format string with {key} placeholders, e.g.
                      "{subject}/trial_{trial}.mat"
        root_folder: Optional root directory.  If provided, paths are
                    resolved relative to it.  If None and the template is
                    a relative path, the nearest ancestor directory
                    containing ``pyproject.toml`` or ``scistack.toml`` is
                    used; falls back to the current working directory when
                    neither file is found.

    Example:
        for_each(
            process_file,
            inputs={
                "filepath": PathInput("{subject}/trial_{trial}.mat",
                                      root_folder="/data"),
            },
            outputs=[ProcessedSignal],
            subject=[1, 2, 3],
            trial=[0, 1, 2],
        )
    """

    def __init__(
        self,
        path_template: str,
        root_folder: str | Path | None = None,
        regex: bool = False,
    ):
        self.path_template = path_template
        self.root_folder = Path(root_folder) if root_folder is not None else None
        self.regex = bool(regex)
        self.__name__ = f"PathInput({path_template!r})"
        # Numeric-fallback caches (see load()): learned zero-pad width per
        # placeholder key, and per-directory listings validated by mtime.
        self._pad_width: dict[str, int] = {}
        self._dir_cache: dict[str, tuple[int, list[str]]] = {}

    def to_key(self) -> str:
        """Return a structured JSON string for version_keys serialization.

        ``regex`` is only included when ``True`` so existing non-regex
        version keys remain byte-identical to records saved before this
        flag existed.
        """
        payload: dict = {
            "__type": "PathInput",
            "template": self.path_template,
            "root_folder": str(self.root_folder) if self.root_folder is not None else None,
        }
        if self.regex:
            payload["regex"] = True
        return json.dumps(payload)

    def load(self, db=None, **metadata: Any) -> Path:
        """Resolve the template with the given metadata and return the path.

        Args:
            db: Accepted for compatibility with for_each's uniform db= passthrough.
                Ignored since PathInput resolves file paths, not database records.
            **metadata: Template substitution values.

        Substitution is literal — only ``{key}`` patterns where ``key`` is
        one of the metadata names get replaced.  Anything else (e.g. a
        regex quantifier like ``{0,2}``) passes through untouched, which
        keeps the regex= path safe and matches MATLAB's ``strrep``
        semantics so the two layers stay in sync.

        When ``regex=True`` was passed at construction, the final path
        segment is then treated as a regular expression rather than a
        literal filename.  The last segment is matched against
        ``^pattern$`` over the files (not directories) in the parent
        directory.  Exactly one file must match — zero matches raise
        ``FileNotFoundError`` and multiple matches raise ``RuntimeError``.

        Zero-padded numeric filenames are handled natively in non-regex
        mode: when the literally-resolved path does not exist and at least
        one metadata value is numeric-like (int, integral float, or digit
        string), the template is re-matched against the filesystem with
        each numeric placeholder matching any digit run of equal integer
        value — so ``trial=1`` finds ``6MWT-001.mat``.  Exactly one such
        match is returned; multiple numerically-equal matches raise
        ``RuntimeError``; zero matches fall back to returning the literal
        path unchanged (preserving the historical non-checking behavior).
        """
        resolved_str = self.path_template
        for key, value in metadata.items():
            resolved_str = resolved_str.replace("{" + key + "}", str(value))
        resolved_path = Path(resolved_str)

        if not self.regex:
            literal = self._absolutize(resolved_path)
            if literal.exists():
                return literal

            numeric_keys = {k: int(v) for k, v in metadata.items()
                            if _numeric_like(v)}
            if not numeric_keys:
                return literal

            # Shortcut: re-render with previously learned pad widths and
            # try a single stat before scanning any directory.
            padded = self._padded_literal(metadata, numeric_keys)
            if padded is not None and padded != literal and padded.exists():
                Log.debug(
                    "pathinput_numeric_fallback: pad-width cache hit: %s",
                    padded, layer="scifor",
                )
                return padded

            Log.debug(
                "pathinput_numeric_fallback: literal path missing, scanning "
                "for numeric-equivalent match: %s", literal, layer="scifor",
            )
            matches = self._numeric_fallback_scan(metadata, numeric_keys)
            if len(matches) == 1:
                path, bindings = matches[0]
                for key, captured in bindings.items():
                    self._pad_width[key] = len(captured)
                Log.debug(
                    "pathinput_numeric_fallback: matched %s (captures: %s)",
                    path, bindings, layer="scifor",
                )
                return path.resolve()
            if len(matches) > 1:
                names = ", ".join(sorted(str(p) for p, _ in matches))
                raise RuntimeError(
                    f"PathInput numeric fallback matched {len(matches)} files "
                    f"for template {self.path_template!r} with metadata "
                    f"{metadata!r}: {names}"
                )
            Log.debug(
                "pathinput_numeric_fallback: no numeric-equivalent match, "
                "returning literal path %s", literal, layer="scifor",
            )
            return literal

        # regex=True: treat the last segment as a regex.  Split on '/'
        # only — backslashes belong to the regex pattern (e.g. ``\d``,
        # ``\.``) and must not be confused with Windows path separators.
        # Templates that need Windows-style directories should use '/'.
        if "/" in resolved_str:
            dir_part, pattern = resolved_str.rsplit("/", 1)
        else:
            dir_part, pattern = "", resolved_str

        if Path(dir_part).is_absolute():
            dir_path = Path(dir_part)
        elif self.root_folder is not None:
            dir_path = self.root_folder / dir_part if dir_part else self.root_folder
        else:
            dir_path = _find_project_root() / dir_part if dir_part else _find_project_root()
        dir_path = dir_path.resolve()

        try:
            entries = [e for e in dir_path.iterdir() if e.is_file()]
        except OSError:
            entries = []

        matches = [e for e in entries if re.fullmatch(pattern, e.name)]

        if not matches:
            raise FileNotFoundError(
                f"PathInput regex pattern {pattern!r} matched no files in {dir_path}"
            )
        if len(matches) > 1:
            names = ", ".join(sorted(m.name for m in matches))
            raise RuntimeError(
                f"PathInput regex pattern {pattern!r} matched {len(matches)} files "
                f"in {dir_path}: {names}"
            )
        return matches[0].resolve()

    def _absolutize(self, resolved_path: Path) -> Path:
        """Anchor a substituted template path exactly like the historical
        non-regex resolution: root_folder, else project root, else as-is."""
        if self.root_folder is not None:
            return (self.root_folder / resolved_path).resolve()
        if not resolved_path.is_absolute():
            return (_find_project_root() / resolved_path).resolve()
        return resolved_path.resolve()

    def _padded_literal(self, metadata: dict, numeric_keys: dict) -> "Path | None":
        """Render the template with cached zero-pad widths applied to numeric
        keys.  Returns None when no width has been learned yet."""
        if not any(k in self._pad_width for k in numeric_keys):
            return None
        rendered = self.path_template
        for key, value in metadata.items():
            if key in numeric_keys:
                text = str(numeric_keys[key]).zfill(self._pad_width.get(key, 0))
            else:
                text = str(value)
            rendered = rendered.replace("{" + key + "}", text)
        return self._absolutize(Path(rendered))

    def _fallback_root_and_segments(self) -> "tuple[Path, list[str]]":
        """Split the template for the numeric-fallback walk, mirroring the
        literal resolution's anchoring (absolute template wins, then
        root_folder, then project root)."""
        normalised = self.path_template.replace("\\", "/")
        segments = [s for s in normalised.split("/") if s]
        if normalised.startswith("/"):
            return Path("/"), segments
        if segments and re.fullmatch(r"[A-Za-z]:", segments[0]):
            return Path(segments[0] + "/"), segments[1:]
        if self.root_folder is not None:
            return self.root_folder, segments
        return _find_project_root(), segments

    def _fallback_segment_regex(
        self, segment: str, metadata: dict, numeric_keys: dict
    ) -> "tuple[str, list, bool] | None":
        """Compile one template segment for the numeric fallback.

        Returns ``(regex, checks, has_numeric)`` where *checks* is a list of
        ``(group_name, key, int_value)`` equality constraints, or ``None``
        when the segment cannot be Formatter-parsed (caller substitutes it
        literally, matching load()'s tolerance of regex-ish braces).
        """
        try:
            parts = list(_string.Formatter().parse(segment))
        except ValueError:
            return None
        regex = ""
        checks: list = []
        has_numeric = False
        key_counts: dict[str, int] = {}
        for literal, field_name, _, _ in parts:
            if literal:
                regex += re.escape(literal)
            if field_name is None:
                continue
            if field_name in numeric_keys:
                key_counts[field_name] = key_counts.get(field_name, 0) + 1
                count = key_counts[field_name]
                group = field_name if count == 1 else f"{field_name}_{count}"
                regex += f"(?P<{group}>\\d+)"
                checks.append((group, field_name, numeric_keys[field_name]))
                has_numeric = True
            elif field_name in metadata:
                regex += re.escape(str(metadata[field_name]))
            else:
                # Unknown key: literal-resolution leaves "{key}" untouched.
                regex += re.escape("{" + field_name + "}")
        return regex, checks, has_numeric

    def _list_dir(self, directory: Path) -> list[str]:
        """Directory listing memoized per instance, invalidated by mtime."""
        key = str(directory)
        try:
            mtime = directory.stat().st_mtime_ns
        except OSError:
            return []
        cached = self._dir_cache.get(key)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        try:
            entries = sorted(os.listdir(directory))
        except OSError:
            return []
        self._dir_cache[key] = (mtime, entries)
        return entries

    def _numeric_fallback_scan(
        self, metadata: dict, numeric_keys: dict
    ) -> "list[tuple[Path, dict[str, str]]]":
        """Walk the template segments matching numeric placeholders by
        integer value.  Returns complete matches as ``(path, captures)``
        where *captures* maps each numeric key to the digit string found on
        disk (used to learn pad widths)."""
        root, segments = self._fallback_root_and_segments()
        if not segments:
            return []
        results: list = []

        def _substitute_literal(segment: str) -> str:
            for key, value in metadata.items():
                segment = segment.replace("{" + key + "}", str(value))
            return segment

        def _walk(current_dir: Path, seg_idx: int, captures: dict) -> None:
            segment = segments[seg_idx]
            is_last = seg_idx == len(segments) - 1
            compiled = self._fallback_segment_regex(segment, metadata, numeric_keys)

            if compiled is None or not compiled[2]:
                # No numeric placeholder in this segment: descend literally.
                candidate = current_dir / _substitute_literal(segment)
                if is_last:
                    if candidate.exists():
                        results.append((candidate, dict(captures)))
                elif candidate.is_dir():
                    _walk(candidate, seg_idx + 1, captures)
                return

            regex, checks, _ = compiled
            for entry in self._list_dir(current_dir):
                m = re.fullmatch(regex, entry)
                if m is None:
                    continue
                if any(int(m.group(g)) != v for g, _, v in checks):
                    continue
                new_captures = dict(captures)
                for g, key, _ in checks:
                    new_captures[key] = m.group(g)
                entry_path = current_dir / entry
                if is_last:
                    results.append((entry_path, new_captures))
                elif entry_path.is_dir():
                    _walk(entry_path, seg_idx + 1, new_captures)

        _walk(root, 0, {})
        return results

    def placeholder_keys(self) -> list[str]:
        """Return the list of unique placeholder keys in the template."""
        seen: set[str] = set()
        keys: list[str] = []
        for _, field_name, _, _ in _string.Formatter().parse(self.path_template):
            if field_name is not None and field_name not in seen:
                seen.add(field_name)
                keys.append(field_name)
        return keys

    def apply_discovery(
        self,
        metadata_iterables: dict,
        user_explicit_keys: "set | None" = None,
        log=None,
    ) -> "tuple[dict, list[dict] | None]":
        """Fill empty metadata iterables from filesystem discovery.

        Canonical PathInput discovery-orchestration shared by the scidb and
        scifor layers (see scidb.foreach Step 3 and scifor.foreach standalone
        resolution).  Runs ``discover()`` and decides how the discovered combos
        relate to the caller-supplied ``metadata_iterables``:

        * **Empty discovery** — nothing on disk matched; returns the iterables
          unchanged with ``discovered_combos=None``.
        * **Case A — no metadata iterables at all**: adopt every discovered key
          with all of its discovered values and return the discovered combos so
          they drive iteration directly.
        * **Case B — keys provided (some may be ``[]``)**: fill each empty
          template key from disk.  If the caller passed an *explicit*
          (non-empty) value for any template key (``user_explicit_keys``), that
          asserts intent — the Cartesian product of the iterables drives
          iteration, so ``discovered_combos=None``.  Otherwise every template
          key was auto-filled from disk, so the discovered combos are returned
          directly to avoid inventing non-existent Cartesian combos (e.g.
          ``{sub1,sub2} x {sessA,sessB}`` producing ``{sub2,sessB}`` when only
          three of the four files exist).

        Args:
            metadata_iterables: Mutable mapping of key -> list of values.
                Mutated in place (empty lists filled) and also returned.
            user_explicit_keys: Keys the caller passed with explicit non-empty
                values (i.e. NOT delegated to DB/filesystem resolution).  These
                suppress the discovered-combos shortcut in Case B.
            log: Optional ``log(msg)`` callback for parity with the layer-level
                logging around this decision.

        Returns:
            ``(metadata_iterables, discovered_combos | None)``.
        """
        if user_explicit_keys is None:
            user_explicit_keys = set()

        def _log(msg: str) -> None:
            if log is not None:
                log(msg)

        combos = self.discover()
        _log(
            f"PathInput discovery: template={self.path_template!r}, "
            f"root_folder={self.root_folder!r}, matching_files={len(combos)}"
        )
        if not combos:
            return metadata_iterables, None

        combo_keys = list(combos[0].keys())

        # Case A: no metadata keys passed at all -> adopt every discovered key.
        if not metadata_iterables:
            for key in combo_keys:
                metadata_iterables[key] = list(dict.fromkeys(c[key] for c in combos))
                _log(f"discovered {key} -> {len(metadata_iterables[key])} values from filesystem")
            return metadata_iterables, combos

        # Case B: keys provided (some may be []).  Fill empty template keys
        # from disk; explicit user-provided values are left alone.
        user_filter_seen = False
        for key in combo_keys:
            if key not in metadata_iterables:
                continue
            user_vals = metadata_iterables[key]
            if not user_vals:
                metadata_iterables[key] = list(dict.fromkeys(c[key] for c in combos))
                _log(f"discovered {key} -> {len(metadata_iterables[key])} values from filesystem")
            elif key in user_explicit_keys:
                user_filter_seen = True

        if user_filter_seen:
            # User asserted intent for at least one template key; let the
            # Cartesian product of the iterables drive iteration.  Combos with
            # missing files surface at runtime rather than being dropped here.
            _log(
                "explicit user values for template keys; skipping discovery "
                "filter — Cartesian product of iterables will drive combos"
            )
            return metadata_iterables, None

        # All template keys filled from disk -> use discovered combos directly.
        _log(f"no user-explicit template keys; using {len(combos)} disk combos directly")
        return metadata_iterables, combos

    def discover(self) -> list[dict[str, str]]:
        """Walk the filesystem and return all metadata combos matching the template.

        Splits the path template into segments and recursively matches each
        segment against actual directory entries.  Literal segments must match
        exactly, segments with ``{key}`` placeholders are converted to regexes
        with named capture groups.

        Returns a list of dicts (one per valid complete path), where each dict
        maps placeholder keys to their string values.
        """
        root = Path(self.root_folder) if self.root_folder is not None else _find_project_root()

        # Split template into path segments
        # Normalise separators to '/'
        normalised = self.path_template.replace("\\", "/")
        segments = [s for s in normalised.split("/") if s]

        if not segments:
            return []

        results: list[dict[str, str]] = []
        self._walk(root, segments, 0, {}, results)
        return results

    # ------------------------------------------------------------------
    # Internal recursive walker
    # ------------------------------------------------------------------

    def _walk(
        self,
        current_dir: Path,
        segments: list[str],
        seg_idx: int,
        bindings: dict[str, str],
        results: list[dict[str, str]],
    ) -> None:
        """Recursively descend through *segments*, matching filesystem entries."""
        if seg_idx >= len(segments):
            return

        segment = segments[seg_idx]
        is_last = seg_idx == len(segments) - 1

        # Check if segment contains any placeholders
        has_placeholder = "{" in segment and "}" in segment

        if not has_placeholder:
            # Literal segment — must match exactly
            candidate = current_dir / segment
            if is_last:
                if candidate.exists():
                    results.append(dict(bindings))
            else:
                if candidate.is_dir():
                    self._walk(candidate, segments, seg_idx + 1, bindings, results)
            return

        # Segment has placeholder(s) — build a regex
        pattern = self._segment_to_regex(segment)

        try:
            entries = os.listdir(current_dir)
        except OSError:
            return

        for entry in sorted(entries):
            m = re.fullmatch(pattern, entry)
            if m is None:
                continue

            # Validate captured values against existing bindings
            captured = m.groupdict()
            # Strip numbered suffixes we added for duplicate keys
            clean_captured: dict[str, str] = {}
            for raw_key, val in captured.items():
                # Keys are like "key" or "key_2", "key_3" etc.
                key = re.sub(r"_\d+$", "", raw_key)
                clean_captured[key] = val

            consistent = True
            for key, val in clean_captured.items():
                if key in bindings and bindings[key] != val:
                    consistent = False
                    break
            if not consistent:
                continue

            new_bindings = {**bindings, **clean_captured}
            entry_path = current_dir / entry

            if is_last:
                if entry_path.exists():
                    results.append(dict(new_bindings))
            else:
                if entry_path.is_dir():
                    self._walk(entry_path, segments, seg_idx + 1, new_bindings, results)

    @staticmethod
    def _segment_to_regex(segment: str) -> str:
        """Convert a template segment like ``{subject}_XSENS_{session}`` to a regex."""
        parts = _string.Formatter().parse(segment)
        regex = ""
        key_counts: dict[str, int] = {}
        for literal, field_name, _, _ in parts:
            if literal:
                regex += re.escape(literal)
            if field_name is not None:
                # Handle duplicate keys in the same segment by numbering
                key_counts[field_name] = key_counts.get(field_name, 0) + 1
                count = key_counts[field_name]
                group_name = field_name if count == 1 else f"{field_name}_{count}"
                regex += f"(?P<{group_name}>[^/\\\\]+)"
        return regex

    def __repr__(self) -> str:
        return (
            f"PathInput({self.path_template!r}, "
            f"root_folder={self.root_folder!r})"
        )
