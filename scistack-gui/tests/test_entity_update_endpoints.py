"""
Endpoint coverage for editing an entity's declaration (plan Stage 6).

The `update_*` endpoints were removed in 066cc53 when entities became
source-declared and read-only; they are back, now backed by
``target_file_service.update_declaration`` (a real source rewrite) rather
than the layout.json writes they used to do.

The parity test below is the important one: ``callBackend`` sends the SAME
params object over REST and over JSON-RPC, so a field-name mismatch between
the two transports is invisible in the browser and only breaks the VS Code
extension. That exact bug (``const_name`` vs ``name``) had to be fixed once
already — see .claude/plan-constant-source-of-truth-26-08-22.md Phase 4.
"""

from __future__ import annotations

import inspect

import scistack_gui.registry as _registry
from scistack_gui import config as config_mod


def _project(tmp_path, body):
    from scistack_gui.db import get_db_path

    entities = tmp_path / "entities.py"
    entities.write_text(body)
    config_mod.set_entities_file(get_db_path(), entities)
    _registry._module_path = None
    _registry.load_from_config(config_mod.load_config(None, get_db_path()))
    return entities


class TestRestEndpoints:
    def test_put_constant_rewrites_source(self, client, tmp_path):
        entities = _project(
            tmp_path, "import scidb\n\nWINDOW = scidb.Parameter(30, description='')\n"
        )

        resp = client.put("/api/parameters/WINDOW", json={"values": [45]})

        assert resp.status_code == 200
        assert resp.json()["ok"], resp.json()
        assert "scidb.Parameter(45" in entities.read_text()

    def test_put_sweep_rewrites_source(self, client, tmp_path):
        entities = _project(tmp_path, "import scidb\n\nW = scidb.Parameter(1, 2)\n")

        resp = client.put("/api/parameters/W", json={"values": [3, 4]})

        assert resp.status_code == 200
        assert resp.json()["ok"], resp.json()
        assert "scidb.Parameter(3, 4, description='')" in entities.read_text()

    def test_put_path_input_rewrites_source(self, client, tmp_path):
        entities = _project(
            tmp_path, "import scidb\n\nRAW = scidb.PathInput('a.csv')\n"
        )

        resp = client.put("/api/path-inputs/RAW", json={"template": "b.csv"})

        assert resp.status_code == 200
        assert resp.json()["ok"], resp.json()
        assert "scidb.PathInput('b.csv')" in entities.read_text()

    def test_put_path_input_alternates_become_an_each_of(self, client, tmp_path):
        """Multiple templates under one name IS an EachOf of PathInputs —
        not a separate concept, and not a new node."""
        entities = _project(
            tmp_path, "import scidb\n\nRAW = scidb.PathInput('a.csv')\n"
        )

        resp = client.put(
            "/api/path-inputs/RAW",
            json={
                "template": "a.csv",
                "alternate_templates": [{"template": "b.csv"}],
            },
        )

        assert resp.json()["ok"], resp.json()
        assert (
            "scidb.EachOf(scidb.PathInput('a.csv'), scidb.PathInput('b.csv'))"
            in entities.read_text()
        )

    def test_read_only_declaration_reports_its_location(self, client, tmp_path):
        """A declaration outside the entities file is refused with the exact
        file:line, so the UI can point at it rather than hint generically."""
        from scistack_gui.db import get_db_path

        other = tmp_path / "params.py"
        other.write_text(
            "import scidb\n\nOUTSIDE = scidb.Parameter(7, description='')\n"
        )
        entities = tmp_path / "entities.py"
        entities.write_text("import scidb\n")
        config_mod.set_entities_file(get_db_path(), entities)
        config_mod.add_path(get_db_path(), tmp_path)
        _registry._module_path = None
        _registry.load_from_config(config_mod.load_config(None, get_db_path()))

        resp = client.put("/api/parameters/OUTSIDE", json={"values": [9]})

        body = resp.json()
        assert resp.status_code == 200
        assert not body["ok"]
        assert body["reason"] == "read_only"
        assert body["file"] == str(other)
        assert body["line"] == 3
        assert "scidb.Parameter(7" in other.read_text()

    def test_empty_sweep_is_rejected(self, client, tmp_path):
        entities = _project(tmp_path, "import scidb\n\nW = scidb.Parameter(1)\n")

        resp = client.put("/api/parameters/W", json={"values": []})

        assert not resp.json()["ok"]
        assert "scidb.Parameter(1)" in entities.read_text()


class TestTransportParity:
    """Every update_* must exist on BOTH transports and take the same params."""

    def test_handlers_are_registered(self):
        from scistack_gui.server import METHODS

        for method in ("update_parameter", "update_path_input"):
            assert method in METHODS, f"{method} missing from the JSON-RPC table"

    def test_json_rpc_handlers_accept_the_rest_param_names(self, tmp_path, populated_db):
        """The params the frontend sends must satisfy both transports. Driving
        the RPC handler with exactly the REST body + `name` is what catches a
        field rename on one side only."""
        from scistack_gui.server import METHODS

        entities = _project(
            tmp_path,
            "import scidb\n\n"
            "WINDOW = scidb.Parameter(30, description='')\n"
            "W = scidb.Parameter(1, 2)\n"
            "RAW = scidb.PathInput('a.csv')\n",
        )

        assert METHODS["update_parameter"](
            {"name": "WINDOW", "values": [45], "description": ""}
        )["ok"]
        assert METHODS["update_parameter"]({"name": "W", "values": [3, 4]})["ok"]
        assert METHODS["update_path_input"](
            {"name": "RAW", "template": "b.csv", "root_folder": None}
        )["ok"]

        text = entities.read_text()
        assert "scidb.Parameter(45" in text
        assert "scidb.Parameter(3, 4, description='')" in text
        assert "scidb.PathInput('b.csv')" in text

    def test_optional_params_really_are_optional_over_rpc(
        self, tmp_path, populated_db
    ):
        """The REST models default description/root_folder/alternates, so the
        RPC handlers must too — otherwise a minimal frontend call KeyErrors
        only in the VS Code extension."""
        from scistack_gui.server import METHODS

        _project(
            tmp_path,
            "import scidb\n\n"
            "WINDOW = scidb.Parameter(30, description='')\n"
            "RAW = scidb.PathInput('a.csv')\n",
        )

        assert METHODS["update_parameter"]({"name": "WINDOW", "values": [45]})["ok"]
        assert METHODS["update_path_input"]({"name": "RAW", "template": "b.csv"})["ok"]

    def test_service_signatures_match_between_layers(self):
        """layout_service is a thin pass-through; a drifted signature there
        silently drops an argument."""
        from scistack_gui.services import layout_service, path_input_service
        from scistack_gui.services import parameter_service

        for wrapper, impl in (
            (layout_service.update_parameter, parameter_service.update_parameter),
            (
                layout_service.update_path_input,
                path_input_service.update_path_input,
            ),
        ):
            assert list(inspect.signature(wrapper).parameters) == list(
                inspect.signature(impl).parameters
            ), f"{wrapper.__name__} drifted from its implementation"


class TestMatlabEntitiesPreamble:
    """A generated command must run the entities script after addpath, so
    declared names are in scope — and re-run it every time, which is what
    makes an edit visible to a kept-warm sidecar session."""

    def test_entities_script_runs_after_addpath(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            "process",
            "/tmp/x.duckdb",
            ["subject"],
            addpath_dirs=["/proj/src"],
            entities_script="/proj/src/scistack_entities.m",
        )

        assert "scistack_entities;" in cmd
        assert cmd.index("addpath('/proj/src');") < cmd.index("scistack_entities;")

    def test_runs_before_the_database_is_configured(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            "process",
            "/tmp/x.duckdb",
            ["subject"],
            entities_script="/proj/src/scistack_entities.m",
        )

        assert cmd.index("scistack_entities;") < cmd.index("configure_database")

    def test_omitted_when_no_entities_file_configured(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command("process", "/tmp/x.duckdb", ["subject"])

        assert "scistack_entities" not in cmd

    def test_pipeline_command_also_runs_it(self):
        """Wiring only the single-function generator would leave WHOLE-pipeline
        runs unable to resolve a declared entity by name."""
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        cmd = generate_matlab_pipeline_command(
            pipeline_id="main",
            steps=[
                {
                    "function_name": "load_csv",
                    "variants": [
                        {
                            "input_types": {},
                            "output_type": "RawSignal",
                            "constants": {},
                        }
                    ],
                }
            ],
            db_path="/tmp/x.duckdb",
            schema_keys=["subject"],
            addpath_dirs=["/proj/src"],
            entities_script="/proj/src/scistack_entities.m",
        )

        assert "scistack_entities;" in cmd
        assert cmd.index("addpath('/proj/src');") < cmd.index("scistack_entities;")
        assert cmd.index("scistack_entities;") < cmd.index("scidb.Pipeline")


class TestMatlabTomlEntitiesPreamble:
    """The TOML entities file reaches MATLAB through ``scidb.entities()``
    (plan Stage 5). Same placement rules as the legacy script."""

    def test_entities_call_runs_after_addpath(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            "process",
            "/tmp/x.duckdb",
            ["subject"],
            addpath_dirs=["/proj/src"],
            entities_file="/proj/src/scistack_entities.toml",
        )

        assert "scidb.entities();" in cmd
        assert cmd.index("addpath('/proj/src');") < cmd.index("scidb.entities();")
        assert cmd.index("scidb.entities();") < cmd.index("configure_database")

    def test_project_root_is_passed_when_known(self):
        """Without it MATLAB resolves the project by walking up from its own
        cwd: outside the project that finds nothing, the load logs
        ``0 variable(s), 0 parameter(s), 0 path input(s) ... from .``, and
        every declared entity is silently out of scope."""
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            "process",
            "/tmp/x.duckdb",
            ["subject"],
            entities_file="/proj/src/scistack_entities.toml",
            project_root="/proj",
        )

        assert "scidb.entities('/proj');" in cmd

    def test_project_root_is_escaped(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            "process",
            "/tmp/x.duckdb",
            ["subject"],
            entities_file="/proj/src/scistack_entities.toml",
            project_root="/it's/a/proj",
        )

        assert "scidb.entities('/it''s/a/proj');" in cmd

    def test_pipeline_command_passes_the_project_root_too(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        cmd = generate_matlab_pipeline_command(
            pipeline_id="main",
            steps=[
                {
                    "function_name": "load_csv",
                    "variants": [
                        {
                            "input_types": {},
                            "output_type": "RawSignal",
                            "constants": {},
                        }
                    ],
                }
            ],
            db_path="/tmp/x.duckdb",
            schema_keys=["subject"],
            entities_file="/proj/src/scistack_entities.toml",
            project_root="/proj",
        )

        assert "scidb.entities('/proj');" in cmd

    def test_both_sources_are_emitted_when_both_configured(self):
        """They declare different names; dropping either would leave a name
        undefined at the point the command uses it."""
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            "process",
            "/tmp/x.duckdb",
            ["subject"],
            entities_script="/proj/src/scistack_entities.m",
            entities_file="/proj/src/scistack_entities.toml",
        )

        assert "scidb.entities();" in cmd
        assert "scistack_entities;" in cmd

    def test_omitted_when_no_entities_file_configured(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command("process", "/tmp/x.duckdb", ["subject"])

        assert "scidb.entities()" not in cmd

    def test_pipeline_command_also_loads_it(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        cmd = generate_matlab_pipeline_command(
            pipeline_id="main",
            steps=[
                {
                    "function_name": "load_csv",
                    "variants": [
                        {
                            "input_types": {},
                            "output_type": "RawSignal",
                            "constants": {},
                        }
                    ],
                }
            ],
            db_path="/tmp/x.duckdb",
            schema_keys=["subject"],
            addpath_dirs=["/proj/src"],
            entities_file="/proj/src/scistack_entities.toml",
        )

        assert cmd.index("addpath('/proj/src');") < cmd.index("scidb.entities();")
        assert cmd.index("scidb.entities();") < cmd.index("scidb.Pipeline")
