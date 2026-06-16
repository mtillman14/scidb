function data = try_stack_numeric(data)
%TRY_STACK_NUMERIC  Stack a cell of same-size numeric vectors into a matrix.
%   If every element is numeric with identical size, vertcat them into a
%   matrix (round-trips multi-column table variables and 2D arrays stored as
%   list-of-rows).  Otherwise return the cell array unchanged.
    if ~iscell(data) || isempty(data) || ~isnumeric(data{1}), return; end
    ref_sz = size(data{1});
    for k = 2:numel(data)
        if ~isnumeric(data{k}) || ~isequal(size(data{k}), ref_sz)
            return;
        end
    end
    % from_python converts 1-D numpy arrays to Nx1 column vectors.
    % When they represent rows of a matrix, transpose to row vectors so
    % vertcat produces an N×M matrix matching MATLAB table convention.
    % For a single cell, unwrap without stacking to preserve original shape.
    if numel(data) == 1
        data = data{1};
        % DuckDB 1D-array convention: 1D arrays always load as column vectors.
        % This corrects cases where from_python returned a row vector (e.g.
        % when a 2D numpy (1,N) came back through cellfun(@double,...)).
        if isnumeric(data) && isvector(data)
            data = data(:);
        end
    elseif iscolumn(data{1}) && ~isscalar(data{1})
        transposed = cellfun(@(v) v', data, 'UniformOutput', false);
        data = vertcat(transposed{:});
    else
        data = vertcat(data{:});
    end
end
