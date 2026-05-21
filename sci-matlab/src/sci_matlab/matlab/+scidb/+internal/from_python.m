function data = from_python(py_obj)
%FROM_PYTHON  Convert a Python object back to a native MATLAB type.
%
%   Handles numpy ndarrays, Python scalars (float, int, str, bool),
%   lists, and dicts.

    % MATLAB's Python bridge auto-converts certain Python types to native
    % MATLAB types before this function is called (e.g. when reading dict
    % values or extracting elements from cell(py.list(...))).  Detect these
    % early so they never fall through to the expensive py.* isa() checks
    % and the exception-throwing fallback path.
    %
    % IMPORTANT: isnumeric/isstring can return true for Python proxy objects
    % (e.g. py.int, py.str) in some MATLAB versions.  Guard with a class
    % name check to ensure we only short-circuit native MATLAB types.
    cl = class(py_obj);
    is_python = numel(cl) >= 3 && cl(1) == 'p' && cl(2) == 'y' && cl(3) == '.';
    if ~is_python
        if islogical(py_obj) || isnumeric(py_obj) || isstring(py_obj)
            data = py_obj;
            return;
        end
    end

    if isa(py_obj, 'py.NoneType')
        data = [];

    elseif isa(py_obj, 'py.numpy.ndarray')
        % Bypass MATLAB-numpy bridge (libmwbuffer issues) by converting
        % to Python list first, then to MATLAB
        py_c = py.numpy.ascontiguousarray(py_obj);
        dtype_kind = string(py_c.dtype.kind);
        arr_shape = int64(py_c.shape);
        arr_ndim = int64(py_c.ndim);
        scidb.Log.debug('from_python: numpy array dtype=%s, shape=[%s], ndim=%d', ...
            string(char(py.str(py_c.dtype))), strjoin(string(arr_shape), ' '), arr_ndim);

        % Convert to Python list to avoid libmwbuffer errors
        try
            py_list = py_c.tolist();
            scidb.Log.debug('from_python: tolist() succeeded, converting to MATLAB...');
        catch list_err
            scidb.Log.err('from_python: tolist() failed: %s', list_err.message);
            rethrow(list_err);
        end

        if dtype_kind == "b"
            % bool array -> logical
            c = cell(py_list);
            if isempty(c)
                data = logical([]);
            else
                % Convert list of bools to MATLAB logical array
                % Explicitly handle py.bool objects
                if ~isempty(c) && isa(c{1}, 'py.bool')
                    data = cellfun(@logical, c);
                else
                    data = cellfun(@logical, c);
                end
            end
        elseif dtype_kind == "O"
            % Object array -> cell array, convert each element
            c = cell(py_list);
            data = cell(1, numel(c));
            for i = 1:numel(c)
                data{i} = scidb.internal.from_python(c{i});
            end
        else
            % Numeric array -> MATLAB numeric array
            c = cell(py_list);
            if isempty(c)
                data = [];
            else
                % Convert list of numbers to MATLAB array
                % Handle case where c contains py.int/py.float objects
                if ~isempty(c) && (isa(c{1}, 'py.int') || isa(c{1}, 'py.float'))
                    % Explicitly convert Python numeric types to MATLAB doubles
                    data = cellfun(@double, c);
                else
                    data = cell2mat(c);
                end
            end
        end

        % 1-D numpy arrays: force to Nx1 column vectors to match the
        % columnar convention of DuckDB storage.  2-D arrays keep their shape.
        if dtype_kind ~= "O" && int64(py_c.ndim) == 1 && ~isempty(data)
            data = data(:);
        end

        scidb.Log.debug('from_python: numpy conversion complete, result class=%s size=[%s]', ...
            class(data), num2str(size(data)))

    elseif isa(py_obj, 'py.bool')
        % Must check py.bool BEFORE py.int: Python bool is a subclass of int,
        % so isa(py_obj, 'py.int') returns true for True/False values.
        data = logical(py_obj);

    elseif isa(py_obj, 'py.float')
        data = double(py_obj);

    elseif isa(py_obj, 'py.int')
        data = double(py_obj);

    elseif isa(py_obj, 'py.str')
        data = string(py_obj);

    elseif isa(py_obj, 'py.datetime.datetime')
        data = datetime(string(py_obj.isoformat()), 'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss');

    elseif isa(py_obj, 'py.list')
        % Fast path: try converting the entire list to a numpy array in one
        % Python call.  This avoids N individual boundary crossings when the
        % list contains homogeneous numeric values (the common case for
        % DOUBLE[] columns loaded from DuckDB).
        try
            py_arr = py.numpy.asarray(py_obj);
            dtype_kind = string(py_arr.dtype.kind);
            if dtype_kind ~= "O"
                % Successfully converted to a typed numpy array — use the
                % ndarray path which handles bool/numeric in bulk.
                data = scidb.internal.from_python(py_arr);
                return;
            end
        catch
            % Fall through to element-by-element conversion below
        end

        c = cell(py_obj);
        n = numel(c);
        data = cell(1, n);
        all_str = n > 0;
        all_numeric_scalar = n > 0;
        all_logical_scalar = n > 0;
        for i = 1:n
            data{i} = scidb.internal.from_python(c{i});
            if all_str && ~isstring(data{i})
                all_str = false;
            end
            if all_numeric_scalar && ~(isnumeric(data{i}) && isscalar(data{i}))
                all_numeric_scalar = false;
            end
            if all_logical_scalar && ~(islogical(data{i}) && isscalar(data{i}))
                all_logical_scalar = false;
            end
        end
        if all_str
            % All-string list -> string array (round-trips string arrays)
            data = [data{:}];
        elseif all_numeric_scalar
            % All-scalar-numeric list -> numeric vector
            data = [data{:}];
        elseif all_logical_scalar
            % All-scalar-logical list -> logical vector
            data = [data{:}];
        end

    elseif isa(py_obj, 'py.pandas.core.frame.DataFrame') || isa(py_obj, 'py.pandas.DataFrame')
        data = convert_dataframe(py_obj);

    elseif isa(py_obj, 'py.dict')
        data = scidb.internal.pydict_to_struct(py_obj);

    else
        % Fallback: isa() can miss pandas DataFrames depending on MATLAB
        % version / class proxy resolution.  Use Python isinstance as a
        % robust secondary check before giving up.
        is_df = false;
        try
            is_df = logical(py.builtins.isinstance(py_obj, py.pandas.DataFrame));
        catch
        end

        if is_df
            data = convert_dataframe(py_obj);
        else
            % Last resort: try MATLAB's automatic conversion
            try
                data = double(py_obj);
            catch
                data = py_obj;  % Return raw Python object
            end
        end
    end
end


function data = convert_dataframe(py_obj)
%CONVERT_DATAFRAME  Convert a pandas DataFrame to a MATLAB table.
    try
        py_cols = py_obj.columns.tolist();
        scidb.Log.debug('convert_dataframe: got columns, converting to cell...');
        col_names = cell(py_cols);
        scidb.Log.debug('convert_dataframe: %d columns: %s', numel(col_names), strjoin(string(col_names(1:min(5,end))), ', '));
        args = cell(1, numel(col_names));

        scidb.Log.debug('convert_dataframe: getting row count...');
        py_len = py.builtins.len(py_obj);
        n_rows = int64(py_len);
        scidb.Log.debug('convert_dataframe: py_len type = %s, n_rows = %d', class(py_len), n_rows);
        scidb.Log.debug('convert_dataframe: converting DataFrame with %d rows, %d columns', ...
            n_rows, numel(col_names));
    catch init_err
        scidb.Log.err('convert_dataframe: initialization failed: %s', init_err.message);
        rethrow(init_err);
    end
    for i = 1:numel(col_names)
        try
            col_key = col_names{i};
            scidb.Log.debug('convert_dataframe: column %d - getting column "%s"', i, string(col_key));
            col = py.operator.getitem(py_obj, col_key);
            scidb.Log.debug('convert_dataframe: column %d - got column, getting dtype...', i);

            % Break down dtype conversion into steps to find where it fails
            try
                py_dtype = col.dtype;
                scidb.Log.debug('convert_dataframe: got dtype object');
                py_dtype_str = py.str(py_dtype);
                scidb.Log.debug('convert_dataframe: converted dtype to py.str');
                char_dtype = char(py_dtype_str);
                scidb.Log.debug('convert_dataframe: converted py.str to char');
                dtype_str = string(char_dtype);
                scidb.Log.debug('convert_dataframe: converted char to string: %s', dtype_str);
            catch dtype_err
                scidb.Log.err('convert_dataframe: dtype conversion failed: %s', dtype_err.message);
                rethrow(dtype_err);
            end
            scidb.Log.debug('convert_dataframe: column %d/%d "%s" dtype=%s', ...
                i, numel(col_names), string(col_key), dtype_str);
        catch col_err
            scidb.Log.err('convert_dataframe: column %d "%s" failed: %s', i, string(col_key), col_err.message);
            rethrow(col_err);
        end
        if startsWith(dtype_str, "datetime")
            scidb.Log.debug('convert_dataframe: column %d - datetime branch', i);
            % datetime64 column -> MATLAB datetime via ISO strings
            iso_strs = cell(col.dt.strftime('%Y-%m-%dT%H:%M:%S.%f').tolist());
            args{i} = datetime(iso_strs, 'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS');
        elseif dtype_str == "object"
            scidb.Log.debug('convert_dataframe: column %d "%s" - object branch', i, string(col_key));
            % Object column (e.g. dicts/structs, array columns) -> cell array via from_python
            py_list = col.tolist();
            c = cell(py_list);
            col_data = cell(numel(c), 1);
            for k = 1:numel(c)
                col_data{k} = scidb.internal.from_python(c{k});
                % Parse stringified arrays (e.g. "[[false], [true], ...]")
                % that result from nested-list storage in DuckDB.
                % Only attempts to parse SCALAR strings — a multi-element
                % string array (from pandas object columns holding string
                % arrays) would break strlength's scalar contract.
                cd = col_data{k};
                if isstring(cd) && isscalar(cd) ...
                        && strlength(cd) > 1 && startsWith(cd, "[")
                    try
                        col_data{k} = jsondecode(char(cd));
                    catch
                    end
                end
            end

            % Optimized path: convert the entire Python list in one call to
            % from_python(), which uses the optimized py.list branch. This is
            % much faster than converting to a MATLAB cell first and iterating.
            try
                scidb.Log.debug('convert_dataframe: column %d - attempting optimized py.list conversion...', i);
                col_data = scidb.internal.from_python(py_list);
                scidb.Log.debug('convert_dataframe: column %d - SUCCESS: used optimized py.list conversion', i);

                % Ensure we have a cell array (from_python might return a matrix
                % for homogeneous data)
                if ~iscell(col_data)
                    col_data = num2cell(col_data);
                end

                % Try to stack into matrix if all same size
                col_data = try_stack_numeric(col_data);
                % Coalesce strings
                col_data = try_stack_strings(col_data);
                % Stack structs
                col_data = try_stack_structs(col_data);
                args{i} = col_data;
            catch opt_err
                % Fallback: element-by-element conversion (for complex types)
                scidb.Log.warn('convert_dataframe: column %d - FAILED optimized conversion, using slow fallback', i);
                scidb.Log.debug('convert_dataframe: column %d - error was: %s', i, opt_err.message);
                c = cell(py_list);
                col_data = cell(numel(c), 1);
                scidb.Log.debug('convert_dataframe: column %d - converting %d elements individually (SLOW)...', i, numel(c));
                for k = 1:numel(c)
                    col_data{k} = scidb.internal.from_python(c{k});
                    % Parse stringified arrays (e.g. "[[false], [true], ...]")
                    if isstring(col_data{k}) && strlength(col_data{k}) > 1 ...
                            && startsWith(col_data{k}, "[")
                        try
                            col_data{k} = jsondecode(char(col_data{k}));
                        catch
                        end
                    end
                end
                col_data = try_stack_numeric(col_data);
                col_data = try_stack_strings(col_data);
                args{i} = try_stack_structs(col_data);
            end
        else
            scidb.Log.debug('convert_dataframe: column %d - default branch, calling to_numpy()', i);
            try
                py_arr = col.to_numpy();
                scidb.Log.debug('convert_dataframe: column %d - to_numpy() succeeded, calling from_python', i);
                args{i} = scidb.internal.from_python(py_arr);
                scidb.Log.debug('convert_dataframe: column %d - from_python succeeded', i);
                % pandas 3.0+ returns StringDtype for text columns; from_python
                % converts these to cell arrays.  Stack into string arrays.
                if iscell(args{i})
                    args{i} = try_stack_strings(args{i});
                end
            catch convert_err
                scidb.Log.err('convert_dataframe: column %d conversion failed: %s', i, convert_err.message);
                rethrow(convert_err);
            end
        end
        % Ensure column vector — but only when the number of elements
        % matches the DataFrame row count.  Otherwise a 1-row DataFrame
        % with a 14-element array value would be reshaped from 1x14 to
        % 14x1, making the table think there are 14 rows.
        if isvector(args{i}) && numel(args{i}) == n_rows
            args{i} = args{i}(:);
        end
    end
    col_name_strs = cellfun(@string, col_names, 'UniformOutput', false);
    data = table;
    for i = 1:numel(args)
        % Special case: a 1-row DataFrame whose column carries a non-scalar
        % vector/matrix should stay cell-wrapped — scifor's
        % _nest_table_outputs=true convention treats each cell as one
        % per-row payload, and downstream MATLAB code expects to brace-
        % index back into it.  Without this guard, ``size(args{i},1) ==
        % n_rows`` would be true (1==1) and the data would land in the
        % table as a raw 1×N numeric column.
        if n_rows == 1 && ~iscell(args{i}) && ~isscalar(args{i})
            data.(col_name_strs{i}) = args(i);
        elseif size(args{i}, 1) == n_rows
            % Per-row values: assign directly.
            % size(·,1) handles both column vectors (Nx1) and matrix columns
            % (NxM) so that e.g. a 3×3 matrix is assigned as a 3-row column
            % rather than cell-wrapped.
            data.(col_name_strs{i}) = args{i};
        else
            % Per-row array values (e.g. time series stored in one cell per row):
            % cell-wrap so the table sees one cell per row, not one row per element.
            data.(col_name_strs{i}) = args(i);
        end
    end
end


function data = try_stack_numeric(data)
%TRY_STACK_NUMERIC  Stack a cell of same-size numeric vectors into a matrix.
%   If every element is numeric with identical size, vertcat them into a
%   matrix (round-trips multi-column table variables).  Otherwise return
%   the cell array unchanged.
    if ~iscell(data) || isempty(data) || ~isnumeric(data{1}), return; end
    ref_sz = size(data{1});
    for k = 2:numel(data)
        if ~isnumeric(data{k}) || ~isequal(size(data{k}), ref_sz)
            return;
        end
    end
    % from_python converts 1-D numpy arrays to Nx1 column vectors.
    % When they represent rows of a matrix column (N cells, each Mx1),
    % transpose to row vectors so vertcat produces an N×M matrix matching
    % the MATLAB table convention (each row is a 1×M row vector).
    % For a single cell, there's nothing to stack — preserve the value's
    % original shape so a per-row vector payload round-trips faithfully.
    if numel(data) == 1
        data = data{1};
    elseif iscolumn(data{1}) && ~isscalar(data{1})
        transposed = cellfun(@(v) v', data, 'UniformOutput', false);
        data = vertcat(transposed{:});
    else
        data = vertcat(data{:});
    end
end


function data = try_stack_strings(data)
%TRY_STACK_STRINGS  Convert a cell array of scalar strings to a string array.
%   If every element is a scalar MATLAB string, concatenate into a column
%   string vector (round-trips string columns stored as pandas object dtype).
%   Otherwise return the cell array unchanged.
    if ~iscell(data) || isempty(data) || ~isstring(data{1}) || ~isscalar(data{1}), return; end
    for k = 2:numel(data)
        if ~isstring(data{k}) || ~isscalar(data{k})
            return;
        end
    end
    data = vertcat(data{:});
end


function data = try_stack_structs(data)
%TRY_STACK_STRUCTS  Convert a cell array of structs to a struct array.
%   If every element is a struct with identical fields, vertcat them into
%   a struct array.  This allows table access as t.field.subfield instead
%   of t.field{1}.subfield.  Otherwise return the data unchanged.
    if ~iscell(data) || isempty(data) || ~isstruct(data{1}), return; end
    ref_fields = sort(fieldnames(data{1}));
    for k = 2:numel(data)
        if ~isstruct(data{k})
            return;
        end
        cur_fields = sort(fieldnames(data{k}));
        if ~isequal(cur_fields, ref_fields)
            return;
        end
    end
    % Check if vertcat will work (fields must have compatible sizes)
    try
        data = vertcat(data{:});
    catch
    end
end
