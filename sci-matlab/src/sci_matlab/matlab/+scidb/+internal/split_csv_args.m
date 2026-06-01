function [metadata_args, version, where, db] = split_csv_args(varargin)
%SPLIT_CSV_ARGS  Separate 'version', 'where', and 'db' from metadata args.
%
%   Used by to_csv() on BaseVariable and Merge so both share one parser.
%   Returns:
%       metadata_args - remaining name-value pairs (schema / branch-param metadata)
%       version       - "latest" (default), "all", or a record_id string
%       where         - scidb.Filter ([] if not given)
%       db            - DatabaseManager ([] if not given)

    version = "latest";
    where = [];
    db = [];
    metadata_args = {};

    i = 1;
    while i <= numel(varargin)
        key = varargin{i};
        if isstring(key), key = char(key); end

        if strcmpi(key, 'version') && i < numel(varargin)
            version = string(varargin{i+1});
            i = i + 2;
        elseif strcmpi(key, 'where') && i < numel(varargin)
            where = varargin{i+1};
            i = i + 2;
        elseif strcmpi(key, 'db') && i < numel(varargin)
            db = varargin{i+1};
            i = i + 2;
        else
            metadata_args{end+1} = varargin{i};    %#ok<AGROW>
            metadata_args{end+1} = varargin{i+1};  %#ok<AGROW>
            i = i + 2;
        end
    end
end
