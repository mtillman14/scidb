function [can_flat, flat, lengths, flat_dtype] = try_flatten_cell_column(col)
%TRY_FLATTEN_CELL_COLUMN  Try to flatten a cell column into a single array.
%
%   For cell columns where every element is a numeric or logical vector
%   (or empty) of the same MATLAB class, concatenate all elements into
%   one flat array and record their lengths.  This enables a single
%   MATLAB->Python bridge crossing instead of one per element.
%
%   Returns:
%     can_flat   - true if flattening succeeded
%     flat       - 1xN flat array of all elements concatenated (row vector)
%     lengths    - 1xM array of element lengths (int64)
%     flat_dtype - numpy dtype string for the flat array

    can_flat = false;
    flat = [];
    lengths = [];
    flat_dtype = '';

    n = numel(col);
    if n == 0
        return;
    end

    % Determine the common class from the first non-empty element
    common_class = '';
    for i = 1:n
        elem = col{i};
        if ~isempty(elem)
            if ~(isnumeric(elem) || islogical(elem))
                return;  % Non-numeric/logical element — can't flatten
            end
            common_class = class(elem);
            break;
        end
    end

    if isempty(common_class)
        % All elements are empty — still flattenable
        can_flat = true;
        flat = double([]);
        lengths = zeros(1, n, 'int64');
        flat_dtype = 'float64';
        return;
    end

    % Verify all elements are numeric/logical vectors of the same class
    lengths = zeros(1, n, 'int64');
    total_len = int64(0);
    for i = 1:n
        elem = col{i};
        if isempty(elem)
            lengths(i) = 0;
        elseif (isnumeric(elem) || islogical(elem)) && isvector(elem) && strcmp(class(elem), common_class)
            lengths(i) = int64(numel(elem));
            total_len = total_len + lengths(i);
        else
            % Mixed type, non-vector, or non-numeric — can't flatten
            return;
        end
    end

    % Preallocate flat array of the common class
    if islogical(col{find(lengths > 0, 1)})
        flat = false(1, total_len);
        flat_dtype = 'bool';
    else
        flat = zeros(1, total_len, common_class);
        flat_dtype = matlab_dtype_to_numpy(zeros(1, 1, common_class));
    end

    % Copy elements into flat array
    pos = int64(1);
    for i = 1:n
        len_i = lengths(i);
        if len_i > 0
            flat(pos:pos + len_i - 1) = col{i}(:)';
            pos = pos + len_i;
        end
    end

    can_flat = true;
end


function dtype = matlab_dtype_to_numpy(data)
    switch class(data)
        case 'double',  dtype = 'float64';
        case 'single',  dtype = 'float32';
        case 'int8',    dtype = 'int8';
        case 'int16',   dtype = 'int16';
        case 'int32',   dtype = 'int32';
        case 'int64',   dtype = 'int64';
        case 'uint8',   dtype = 'uint8';
        case 'uint16',  dtype = 'uint16';
        case 'uint32',  dtype = 'uint32';
        case 'uint64',  dtype = 'uint64';
        otherwise
            dtype = 'float64';
    end
end
