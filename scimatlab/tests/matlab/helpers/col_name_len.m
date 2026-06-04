function out = col_name_len(value, col_name) %#ok<INUSL>
%COL_NAME_LEN  Length of the current column's name (for deferred ColName tests).
%   Proves col_name is the source column being iterated, not a static single
%   value. Returns a struct so for_columns reassembles to "<col>__name_len".
out = struct('name_len', numel(char(col_name)));
end
