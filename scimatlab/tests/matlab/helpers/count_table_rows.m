function n = count_table_rows(x)
%COUNT_TABLE_ROWS  Test function: return the row count of a table input as a double.
%   Used with as_table=true to observe how many rows an aggregated
%   (multi-row) combo received.
    n = double(height(x));
end
