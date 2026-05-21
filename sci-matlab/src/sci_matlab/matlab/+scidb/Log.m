classdef Log
%SCIDB.LOG  Unified logger that delegates to Python scidb.log.Log.
%
%   scidb.Log.set_level('DEBUG')   — show all messages
%   scidb.Log.set_level('INFO')    — show INFO, WARN, ERROR (default)
%   scidb.Log.set_level('WARN')    — show WARN, ERROR only
%   scidb.Log.set_level('ERROR')   — show ERROR only
%
%   scidb.Log.debug('Processing %d items', n)
%   scidb.Log.info('Loaded %s', type_name)
%   scidb.Log.warn('No data for %s', key)
%   scidb.Log.err('Failed: %s', msg)
%
%   Output format: [HH:MM:SS.FFF] [LEVEL] message
%
%   All logging calls delegate to the Python scidb.log.Log class to ensure
%   unified log level settings and output. Writes to scidb.log next to the
%   database file (set automatically by scidb.configure_database()).
%
%   The log level is cached in MATLAB's appdata for performance, but the
%   Python logger is the source of truth.

    properties (Constant)
        DEBUG = 0
        INFO  = 1
        WARN  = 2
        ERROR = 3
    end

    methods (Static)

        function set_level(level)
        %SET_LEVEL  Set the global log level.
        %   Accepts a string ('DEBUG','INFO','WARN','ERROR') or numeric (0-3).
        %   Delegates to Python logging to unify log level settings.
            if isnumeric(level)
                % Convert numeric to string for Python
                level_names = {'DEBUG', 'INFO', 'WARN', 'ERROR'};
                if level >= 0 && level <= 3
                    level = level_names{level + 1};
                else
                    level = 'INFO';
                end
            end
            % Set Python log level (source of truth)
            py.scidb.log.Log.set_level(char(level));
            % Cache in MATLAB for fast get_level() calls
            level_num = scidb.Log.parse_level(char(upper(string(level))));
            setappdata(0, 'scidb_log_level', level_num);
        end

        function level = get_level()
        %GET_LEVEL  Get the current log level (default: INFO).
        %   Returns cached value for performance (avoids Python bridge crossing).
            if isappdata(0, 'scidb_log_level')
                level = getappdata(0, 'scidb_log_level');
            else
                level = scidb.Log.INFO;
            end
        end

        function set_path(log_path)
        %SET_PATH  Set the log file path for file output.
        %   Called automatically by scidb.configure_database().
        %   Delegates to Python logging to unify log file location.
            py.scidb.log.Log.set_path(char(log_path));
            % Cache in MATLAB for legacy compatibility
            setappdata(0, 'scidb_log_path', char(log_path));
        end

        function p = get_path()
        %GET_PATH  Get the current log file path (empty if not set).
            if isappdata(0, 'scidb_log_path')
                p = getappdata(0, 'scidb_log_path');
            else
                p = '';
            end
        end

        function debug(fmt, varargin)
        %DEBUG  Log a message at DEBUG level.
        %   Delegates to Python logging for unified output.
            if scidb.Log.get_level() <= scidb.Log.DEBUG
                msg = sprintf(fmt, varargin{:});
                py.scidb.log.Log.debug(msg);
            end
        end

        function info(fmt, varargin)
        %INFO  Log a message at INFO level.
        %   Delegates to Python logging for unified output.
            if scidb.Log.get_level() <= scidb.Log.INFO
                msg = sprintf(fmt, varargin{:});
                py.scidb.log.Log.info(msg);
            end
        end

        function warn(fmt, varargin)
        %WARN  Log a message at WARN level.
        %   Delegates to Python logging for unified output.
            if scidb.Log.get_level() <= scidb.Log.WARN
                msg = sprintf(fmt, varargin{:});
                py.scidb.log.Log.warn(msg);
            end
        end

        function err(fmt, varargin)
        %ERR  Log a message at ERROR level.
        %   Named 'err' to avoid conflict with MATLAB's built-in 'error'.
        %   Delegates to Python logging for unified output.
            if scidb.Log.get_level() <= scidb.Log.ERROR
                msg = sprintf(fmt, varargin{:});
                py.scidb.log.Log.error(msg);
            end
        end

    end

    methods (Static, Access = private)

        function level = parse_level(name)
        %PARSE_LEVEL  Convert a level name string to numeric value.
            switch name
                case 'DEBUG'
                    level = scidb.Log.DEBUG;
                case 'INFO'
                    level = scidb.Log.INFO;
                case 'WARN'
                    level = scidb.Log.WARN;
                case 'ERROR'
                    level = scidb.Log.ERROR;
                otherwise
                    warning('scidb:Log', 'Unknown log level ''%s'', defaulting to INFO.', name);
                    level = scidb.Log.INFO;
            end
        end

    end

end
