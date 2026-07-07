function n = count_specs(df)
%COUNT_SPECS  Test helper for AcrossVariants pooling: the pooled table
%   carries each namespaced branch_param as an ordinary column (MATLAB
%   sanitizes 'add_offset.offset' to a valid variable name on conversion);
%   return how many distinct specification values were pooled.
    vn = string(df.Properties.VariableNames);
    bp_col = vn(contains(vn, "offset") & vn ~= "offset");
    if isempty(bp_col)
        bp_col = vn(vn == "offset");
    end
    assert(~isempty(bp_col), ...
        'branch_param column missing from pooled AcrossVariants table');
    n = numel(unique(df.(char(bp_col(1)))));
end
