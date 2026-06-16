classdef LineageFcnResult < handle
%SCIDB.LINEAGEFCNRESULT  Result of a lineage-tracked computation.
%
%   A LineageFcnResult carries both the MATLAB result data and a Python
%   shadow (a real scilineage.core.LineageFcnResult instance) that encodes
%   the full lineage graph.
%
%   When passed to Type().save(), the Python shadow is handed directly
%   to Python's save_variable(), so isinstance checks pass and lineage
%   extraction works unchanged.
%
%   When passed as input to another scidb.LineageFcn call, the Python
%   shadow is placed in the inputs dict so that classify_inputs() sees a
%   real LineageFcnResult and records the lineage chain.
%
%   Properties:
%       data         - The MATLAB result (double array, scalar, etc.)
%       py_obj       - Python scilineage.core.LineageFcnResult (internal use)

    properties
        data            % MATLAB data (the actual computation result)
        py_obj          % Python LineageFcnResult (lineage shadow)
    end

    methods
        function obj = LineageFcnResult(matlab_data, py_lineage_result)
        %LINEAGEFCNRESULT  Construct a LineageFcnResult.
        %
        %   obj = scidb.LineageFcnResult(DATA, PY_OBJ)
        %
        %   This constructor is called internally by scidb.LineageFcn.
        %   Users do not create LineageFcnResult objects directly.

            if nargin > 0
                obj.data = matlab_data;
                obj.py_obj = py_lineage_result;
            end
        end

        function disp(obj)
        %DISP  Display the LineageFcnResult.

            if isempty(obj.data)
                fprintf('  scidb.LineageFcnResult (empty)\n');
            else
                fprintf('  scidb.LineageFcnResult containing %s\n', ...
                    class(obj.data));
                disp(obj.data);
            end
        end
    end

    methods (Static)
        function objs = empty()
        %EMPTY  Create an empty LineageFcnResult array (for preallocation).
            objs = scidb.LineageFcnResult.empty(0, 0);
        end
    end
end
