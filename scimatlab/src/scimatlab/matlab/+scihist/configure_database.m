function db = configure_database(db_path, schema_keys, varargin)
%SCIHIST.CONFIGURE_DATABASE  Deprecated thin shim over scidb.configure_database.
%
%   DB = scihist.configure_database(DB_PATH, SCHEMA_KEYS, ...)
%
%   DEPRECATED: this used to additionally register a scilineage cache
%   backend, but the rerun cache was removed in the lineage-simplification
%   migration. It now simply delegates to scidb.configure_database, mirroring
%   the deprecated Python ``scihist.configure_database`` shim. Prefer calling
%   scidb.configure_database directly.
%
%   Arguments:
%       db_path     - Path to the DuckDB database file (string or char)
%       schema_keys - String array of metadata keys that form the dataset
%                     schema (e.g. ["subject", "session"])
%       varargin    - Additional name-value pairs forwarded to
%                     scidb.configure_database
%
%   Returns:
%       DB - The configured DatabaseManager Python object.
%
%   Example:
%       db = scidb.configure_database("experiment.duckdb", ...
%           ["subject", "session"]);

    db = scidb.configure_database(db_path, schema_keys, varargin{:});
end
