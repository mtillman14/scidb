function db = configure_database(dataset_db_path, dataset_schema_keys, options)
%SCIDB.CONFIGURE_DATABASE  Set up the SciStack database connection.
%
%   db = scidb.configure_database(DB_PATH, SCHEMA_KEYS)
%   db = scidb.configure_database(DB_PATH, SCHEMA_KEYS, schema_key_types=TYPES)
%   configures the global database connection with DuckDB for data and
%   lineage storage.
%
%   Arguments:
%       dataset_db_path     - Path to the DuckDB database file (string)
%       dataset_schema_keys - Metadata keys defining the dataset schema
%                             (string array, e.g. ["subject", "session"])
%       schema_key_types    - Optional struct declaring per-key types, e.g.
%                             struct('trial', 'numeric').  'numeric' keys
%                             canonicalize every spelling of the same number
%                             ("001", 1, 1.0 all store as "1"; zero-padded
%                             filenames still resolve via PathInput's
%                             numeric fallback).  'string' keys are verbatim
%                             — spelling IS identity, PathInput matches them
%                             exactly only.  Undeclared keys raise
%                             scidb:SchemaKeyTypeError the first time a
%                             PathInput resolution has to bridge spellings.
%
%   Example:
%       scidb.configure_database( ...
%           "experiment.duckdb", ...
%           ["subject", "trial"], ...
%           schema_key_types=struct('trial', 'numeric'));

    arguments
        dataset_db_path     string
        dataset_schema_keys string
        options.schema_key_types struct = struct()
    end

    % Convert keys to row vector
    if size(dataset_schema_keys,1) > 1
        dataset_schema_keys = dataset_schema_keys';
    end

    % Convert MATLAB string array to Python list of strings
    py_schema_keys = py.list(cellstr(dataset_schema_keys));

    dataset_db_path = char(dataset_db_path);
    if ~scidb.isabsolute(dataset_db_path)
        dataset_db_path = fullfile(pwd, dataset_db_path);
    end

    % Convert schema_key_types struct -> py.dict (validated Python-side)
    kt_fields = fieldnames(options.schema_key_types);
    py_key_types = py.dict();
    for i = 1:numel(kt_fields)
        py_key_types.update(pyargs(kt_fields{i}, ...
            char(string(options.schema_key_types.(kt_fields{i})))));
    end

    % Call Python's configure_database
    if isempty(kt_fields)
        db = py.scidb.configure_database( ...
            char(dataset_db_path), ...
            py_schema_keys);
    else
        db = py.scidb.configure_database( ...
            char(dataset_db_path), ...
            py_schema_keys, ...
            pyargs('schema_key_types', py_key_types));
    end

    % Verify the Python environment is working
    py_db = py.scidb.database.get_database();
    if isempty(py_db)
        error('scidb:ConfigFailed', ...
            'configure_database() did not produce a valid DatabaseManager.');
    end

    % Propagate schema keys to scifor so that table-input detection and
    % distribute=true work identically in DB-backed and standalone modes.
    scifor.set_schema(dataset_schema_keys);

    % Set log file path next to the database file
    [db_dir, ~, ~] = fileparts(dataset_db_path);
    scidb.Log.set_path(fullfile(db_dir, 'scidb.log'));

    scidb.Log.info('configure_database (MATLAB host): %s', dataset_db_path);

end
