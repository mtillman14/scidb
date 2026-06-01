classdef ColumnSelection
%SCIFOR.COLUMNSELECTION  Extract specific columns from a table input.
%
%   After filtering the table for the current combo, extracts only the
%   specified columns. Single column -> returns the column values (array).
%   Multiple columns -> returns a sub-table.
%
%   Properties:
%       data    - MATLAB table
%       columns - String array of column names to extract
%       iterate - logical; when true the selection means "run fn once per
%                 column and reassemble the per-column results into one wide
%                 row" rather than "pass these columns as one argument".
%                 (default false)
%
%   Example:
%       scifor.for_each(@fn, ...
%           struct('speed', scifor.ColumnSelection(data_table, "speed")), ...
%           subject=[1 2 3])
%
%       scifor.for_each(@fn, ...
%           struct('data', scifor.ColumnSelection(data_table, ["speed", "force"])), ...
%           subject=[1 2 3])
%
%       % Column-wise iteration (for_columns): fn runs once per column and
%       % the per-column scalars are reassembled into a 1xN row.
%       scifor.for_each(@col_mean, ...
%           struct('value', scifor.ColumnSelection(data_table, ["speed", "force"], true)), ...
%           subject=[1 2 3])

    properties (SetAccess = private)
        data     % MATLAB table
        columns  string  % String array of column names to extract
        iterate  logical % Iterate per-column and reassemble (for_columns)
    end

    methods
        function obj = ColumnSelection(data, columns, iterate)
        %COLUMNSELECTION  Construct a ColumnSelection wrapper.
        %
        %   CS = scifor.ColumnSelection(tbl, columns)
        %   CS = scifor.ColumnSelection(tbl, columns, iterate)
        %
        %   Arguments:
        %       data    - A MATLAB table
        %       columns - String or string array of column names
        %       iterate - (optional) logical; iterate per-column and
        %                 reassemble into one wide row. Default false.

            obj.data = data;
            obj.columns = string(columns);
            if nargin >= 3 && ~isempty(iterate)
                obj.iterate = logical(iterate);
            else
                obj.iterate = false;
            end
        end

        function disp(obj)
        %DISP  Display the ColumnSelection wrapper.
            if obj.iterate
                suffix = ', iterate';
            else
                suffix = '';
            end
            fprintf('  scifor.ColumnSelection(<table>, [%s]%s)\n', ...
                strjoin('"' + obj.columns + '"', ', '), suffix);
        end
    end
end
