function varargout = entities(project_root)
%SCIDB.ENTITIES  Load the project's declared entities from its TOML file.
%
%   E = scidb.entities() returns a struct whose fields are the declared
%   Parameters and PathInputs, rebuilt as MATLAB scidb.Parameter /
%   scidb.PathInput objects:
%
%       e = scidb.entities();
%       scidb.for_each(@process, inputs=struct('f', e.EMG_FILE), ...
%                      outputs={Filtered()}, window=e.WINDOW_SECONDS);
%
%   scidb.entities() with no output assigns every declared name into the
%   BASE workspace instead, so declared names are simply in scope:
%
%       scidb.entities();
%       scidb.for_each(@process, inputs=struct('f', EMG_FILE), ...);
%
%   This is what the GUI emits into generated commands, and it replaces the
%   old `scistack_entities;` script line. The declarations now live in one
%   language-neutral TOML file that Python and MATLAB both read, rather than
%   a .m script and a .py module that had to be kept in step -- see
%   docs/claude/entity-editability-model.md and scidb/src/scidb/entities.py.
%
%   E = scidb.entities(PROJECT_ROOT) resolves the entities file starting
%   from PROJECT_ROOT rather than the current directory.
%
%   Re-reading is cheap and always fresh: the Python side caches on the
%   file's mtime, so an edit made in the GUI is picked up on the next call
%   with nothing to clear -- the property that made a plain script
%   preferable to a classdef, preserved.
%
%   Variables are NOT returned as fields: a variable is a *type*, and
%   MATLAB requires a real classdef file per type. The GUI materialises a
%   stub classdef for each declared variable (see
%   scistack_gui.matlab_registry.materialize_variable_stubs), so a declared
%   variable is referenced as StepLength() the same way it always was.

    arguments
        project_root string = ""
    end

    if strlength(project_root) == 0
        payload = py.scimatlab.bridge.load_entities();
    else
        payload = py.scimatlab.bridge.load_entities(char(project_root));
    end

    s = struct();

    % --- Parameters: a list of values -> scidb.Parameter(v1, v2, ...) ------
    params = payload{'parameters'};
    param_names = cell(py.builtins.list(params.keys()));
    for i = 1:numel(param_names)
        name = char(param_names{i});
        values = scidb.internal.pylist_to_cell(params{name});
        s.(name) = scidb.Parameter(values{:});
    end

    % --- PathInputs: one arm, or several wrapped in an EachOf -------------
    pis = payload{'path_inputs'};
    pi_names = cell(py.builtins.list(pis.keys()));
    for i = 1:numel(pi_names)
        name = char(pi_names{i});
        arms = scidb.internal.pylist_to_cell(pis{name});
        objs = cell(1, numel(arms));
        for j = 1:numel(arms)
            arm = arms{j};
            if isempty(arm.root_folder)
                objs{j} = scidb.PathInput(arm.template);
            else
                objs{j} = scidb.PathInput(arm.template, arm.root_folder);
            end
        end
        if numel(objs) == 1
            s.(name) = objs{1};
        else
            % Alternate templates are an EachOf of PathInputs -- the same
            % shape Python builds, so for_each fans them out identically.
            s.(name) = scifor.EachOf(objs{:});
        end
    end

    % --- Rejected entries are warnings here too ---------------------------
    % A declaration the parser refused is invisible in MATLAB unless it is
    % surfaced: the GUI shows these in its load-errors panel, and someone
    % running from the MATLAB prompt never sees that panel.
    errors = scidb.internal.pylist_to_cell(payload{'errors'});
    for i = 1:numel(errors)
        warning('scidb:entities:rejected', ...
                'Entities file: %s', char(errors{i}));
    end

    if nargout == 0
        names = fieldnames(s);
        for i = 1:numel(names)
            assignin('base', names{i}, s.(names{i}));
        end
        scidb.Log.info(sprintf( ...
            '[entities] Loaded %d entity declaration(s) from %s', ...
            numel(names), char(payload{'path'})));
    else
        varargout{1} = s;
    end
end
