classdef ColName
%SCIFOR.COLNAME  Resolves to a data column name at for_each time.
%
%   Two forms:
%
%   1. scifor.ColName(tbl) — STATIC. Resolves once, up front, to the single
%      non-schema data column name of TBL. The function body stays
%      framework-agnostic. Errors if TBL has 0 or 2+ non-schema data columns.
%
%   2. scifor.ColName() — DEFERRED. Resolves per-column inside a for_columns
%      iteration to the name of the column currently being fed to the function.
%      Requires at least one iterate input (ColumnSelection(..., iterate=true));
%      using it without one is an error.
%
%   Properties:
%       data - MATLAB table (static form), or [] (deferred form)
%
%   Example (static):
%       result = scifor.for_each(@analyze, ...
%           struct('table', data_table, 'col_name', scifor.ColName(data_table)), ...
%           subject=[1 2 3])
%
%       % The function is pure:
%       function out = analyze(table, col_name)
%           out = mean(table.(col_name));
%       end
%
%   Example (deferred, current for_columns column):
%       result = scifor.for_each(@analyze, ...
%           struct('value', scifor.ColumnSelection(means, [], iterate=true), ...
%                  'col_name', scifor.ColName()), ...
%           subject=[])

    properties (SetAccess = private)
        data  % MATLAB table (static form), or [] (deferred form)
    end

    methods
        function obj = ColName(data)
        %COLNAME  Construct a ColName wrapper.
        %
        %   C = scifor.ColName(tbl)   % static: TBL's single data column
        %   C = scifor.ColName()      % deferred: current for_columns column
        %
        %   Arguments:
        %       data - A MATLAB table with exactly one non-schema data column.
        %              Omit it for the deferred (current-column) form.

            if nargin < 1
                obj.data = [];
            else
                obj.data = data;
            end
        end

        function tf = is_deferred(obj)
        %IS_DEFERRED  True for the no-arg form (current for_columns column).
            tf = isempty(obj.data);
        end

        function disp(obj)
        %DISP  Display the ColName wrapper.
            if istable(obj.data)
                fprintf('  scifor.ColName(<table %dx%d>)\n', ...
                    height(obj.data), width(obj.data));
            elseif isempty(obj.data)
                fprintf('  scifor.ColName()  %% deferred: current for_columns column\n');
            else
                fprintf('  scifor.ColName(%s)\n', class(obj.data));
            end
        end
    end
end
