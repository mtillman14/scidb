function py_kwargs = build_csv_kwargs(metadata_args, version, where, db_val)
%BUILD_CSV_KWARGS  Assemble the pyargs cell for a to_csv() Python call.
%   Combines metadata name-value pairs with version, where (scidb.Filter),
%   and db, converting each to its Python-compatible form. Shared by
%   BaseVariable.to_csv and Merge.to_csv.

    py_kwargs = scidb.internal.metadata_to_pykwargs(metadata_args{:});
    py_kwargs{end+1} = 'version';      %#ok<AGROW>
    py_kwargs{end+1} = char(version);  %#ok<AGROW>
    if ~isempty(where)
        py_kwargs{end+1} = 'where';          %#ok<AGROW>
        py_kwargs{end+1} = where.py_filter;  %#ok<AGROW>
    end
    if ~isempty(db_val)
        py_kwargs{end+1} = 'db';    %#ok<AGROW>
        py_kwargs{end+1} = db_val;  %#ok<AGROW>
    end
end
