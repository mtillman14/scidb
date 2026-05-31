classdef Variant
%SCIDB.VARIANT  Pin a for_each input to a specific branch_param variant.
%
%   branch_param pinning is an orthogonal, load-time filter: it selects which
%   branch_param variant of a variable to load, distinct from the other input
%   wrappers' concerns:
%
%       scidb.Fixed(..., session="BL") - which schema metadata (per-combo)
%       MyVar("col")                   - which columns (after load)
%       scidb.Merge(...)               - join several inputs (top level)
%       scidb.Variant(..., low_hz=20)  - which branch_param variant (load time)
%
%   Because branch_param pinning is threaded as a separate filter through the
%   loader (like where=), composition with the other wrappers is order-agnostic:
%
%       scidb.Fixed(scidb.Variant(X, low_hz=20), session="BL")
%         == scidb.Variant(scidb.Fixed(X, session="BL"), low_hz=20)
%
%   Variant may also be a Merge constituent for per-constituent pinning:
%
%       scidb.Merge(scidb.Variant(A, low_hz=20), B)
%
%   branch_params are namespaced per producing function (e.g. bandpass.low_hz);
%   a bare name (low_hz) is matched by suffix at load time.
%
%   Properties:
%       var_type      - Variable instance (e.g. FilteredEMG()), a column
%                       selection (FilteredEMG("col")), or a scidb.Fixed
%       branch_params - Struct of branch_param key/value pairs to pin
%
%   Example:
%       % Run fn over only the low_hz=20 variant of FilteredEMG
%       scidb.for_each(@fn, ...
%           struct('x', scidb.Variant(FilteredEMG(), low_hz=20)), ...
%           {Out()}, ...
%           subject=[1 2]);

    properties (SetAccess = private)
        var_type        % BaseVariable instance / column selection / scidb.Fixed
        branch_params  struct  % branch_param pins
    end

    methods
        function obj = Variant(var_type, varargin)
        %VARIANT  Construct a Variant branch_param pinning wrapper.
        %
        %   V = scidb.Variant(TypeInstance(), Name, Value, ...)
        %
        %   Arguments:
        %       var_type - A BaseVariable instance, a column selection
        %                  (MyVar("col")), or a scidb.Fixed wrapper.
        %
        %   Name-Value Arguments:
        %       branch_param keys and their pinned values

            if isa(var_type, 'scidb.Merge')
                error('scidb:Variant', ...
                    ['Variant cannot wrap a Merge. branch_params are namespaced ', ...
                     'per producing function, so one branch_param cannot ', ...
                     'sensibly broadcast across Merge constituents. Pin per ', ...
                     'constituent instead: Merge(Variant(A, low_hz=20), B).']);
            end

            if mod(numel(varargin), 2) ~= 0
                error('scidb:Variant', ...
                    'Variant branch_params must be name-value pairs.');
            end
            if isempty(varargin)
                error('scidb:Variant', ...
                    ['Variant requires at least one branch_param to pin, ', ...
                     'e.g. scidb.Variant(FilteredEMG(), low_hz=20).']);
            end

            s = struct();
            for i = 1:2:numel(varargin)
                s.(string(varargin{i})) = varargin{i+1};
            end

            % Nested Variant: merge the dicts; raise on conflicting key value.
            if isa(var_type, 'scidb.Variant')
                inner_bp = var_type.branch_params;
                inner_fields = fieldnames(inner_bp);
                for i = 1:numel(inner_fields)
                    k = inner_fields{i};
                    if isfield(s, k) && ~isequal(s.(k), inner_bp.(k))
                        error('scidb:Variant', ...
                            'Conflicting branch_param "%s" in nested Variant.', k);
                    end
                    if ~isfield(s, k)
                        s.(k) = inner_bp.(k);
                    end
                end
                var_type = var_type.var_type;
            end

            obj.var_type = var_type;
            obj.branch_params = s;
        end

        function disp(obj)
        %DISP  Display the Variant wrapper.
            type_name = class(obj.var_type);
            fields = fieldnames(obj.branch_params);
            parts = cell(1, numel(fields));
            for i = 1:numel(fields)
                val = obj.branch_params.(fields{i});
                if isnumeric(val)
                    parts{i} = sprintf('%s=%g', fields{i}, val);
                else
                    parts{i} = sprintf('%s="%s"', fields{i}, string(val));
                end
            end
            fprintf('  scidb.Variant(%s, %s)\n', type_name, strjoin(parts, ', '));
        end
    end
end
