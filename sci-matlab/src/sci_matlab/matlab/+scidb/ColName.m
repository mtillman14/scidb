classdef ColName
%SCIDB.COLNAME  Resolves to a data column name at for_each time.
%
%   Two forms:
%
%   1. scidb.ColName(MyVar()) — STATIC. Resolves to the single data column
%      name of a DB-backed variable. The function body stays
%      framework-agnostic. Errors if the variable has 0 or 2+ data columns.
%
%   2. scidb.ColName() — DEFERRED. Resolves per-column inside a for_columns
%      iteration to the name of the column currently being fed to the function.
%      Requires at least one iterate input (MyVar().for_columns()); using it
%      without one is an error.
%
%   Properties:
%       var_type - BaseVariable instance (static form), or [] (deferred form)
%
%   Example (static):
%       scidb.for_each(@analyze, ...
%           struct('table', MyVar(), 'col_name', scidb.ColName(MyVar())), ...
%           {Result()}, ...
%           subject=[1 2 3])
%
%       % The function is pure:
%       function out = analyze(table, col_name)
%           out = mean(table.(col_name));
%       end
%
%   Example (deferred, current for_columns column):
%       scidb.for_each(@analyze, ...
%           struct('df', MyVar().for_columns(), 'col_name', scidb.ColName()), ...
%           {Result()}, ...
%           subject=[])

    properties (SetAccess = private)
        var_type  % BaseVariable instance (static form), or [] (deferred form)
    end

    methods
        function obj = ColName(var_type)
        %COLNAME  Construct a ColName wrapper for DB-backed variables.
        %
        %   C = scidb.ColName(VarInstance())   % static: var's single data column
        %   C = scidb.ColName()                % deferred: current for_columns column
        %
        %   Arguments:
        %       var_type - A BaseVariable instance. Omit it for the deferred
        %                  (current-column) form.

            if nargin < 1
                obj.var_type = [];
            else
                obj.var_type = var_type;
            end
        end

        function tf = is_deferred(obj)
        %IS_DEFERRED  True for the no-arg form (current for_columns column).
            tf = isempty(obj.var_type);
        end

        function disp(obj)
        %DISP  Display the ColName wrapper.
            if isempty(obj.var_type)
                fprintf('  scidb.ColName()  %% deferred: current for_columns column\n');
            else
                fprintf('  scidb.ColName(%s)\n', class(obj.var_type));
            end
        end
    end
end
