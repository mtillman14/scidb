classdef PathInput < handle
%SCIFOR.PATHINPUT  Resolve a path template using iteration metadata.
%
%   Works as an input to for_each: on each iteration, .load()
%   substitutes the current metadata values into the template and
%   returns the resolved file path as a string.  The user's function
%   receives the path and handles file reading itself.
%
%   PI = scifor.PathInput(TEMPLATE)
%   PI = scifor.PathInput(TEMPLATE, root_folder=FOLDER)
%   PI = scifor.PathInput(TEMPLATE, root_folder=FOLDER, regex=true)
%
%   The template uses {key} placeholders that are replaced by the
%   metadata values supplied by for_each on each iteration.
%
%   When regex=true, the resolved template is treated as a regular
%   expression and matched against filenames in the directory portion
%   of the path. Exactly one file must match; zero or multiple matches
%   produce an error.
%
%   Example:
%       scifor.for_each(@process_file, ...
%           struct('filepath', scifor.PathInput("{subject}/trial_{trial}.mat", ...
%                                              root_folder="/data"), ...
%                  'raw', data_table), ...
%           subject=[1 2 3], ...
%           trial=[0 1 2]);

    properties (SetAccess = private)
        path_template  string   % Format string with {key} placeholders
        root_folder    string   % Optional root directory
        regex          logical  % Whether to use regex matching
    end

    methods
        function obj = PathInput(path_template, options)
        %PATHINPUT  Construct a PathInput.
        %
        %   PI = scifor.PathInput(TEMPLATE)
        %   PI = scifor.PathInput(TEMPLATE, root_folder=FOLDER)
        %   PI = scifor.PathInput(TEMPLATE, regex=true)

            arguments
                path_template  string
                options.root_folder  string = ""
                options.regex        logical = false
            end

            obj.path_template = path_template;
            obj.root_folder = options.root_folder;
            obj.regex = options.regex;
        end

        function filepath = load(obj, varargin)
        %LOAD  Resolve the template with the given metadata.
        %
        %   PATH = pi.load(Name, Value, ...)
        %
        %   Substitutes {key} placeholders in the template with the
        %   supplied metadata values and returns the resolved absolute
        %   path as a string.  The 'db' key is accepted and ignored
        %   for compatibility with for_each's uniform db= passthrough.

            % Parse name-value pairs
            if mod(numel(varargin), 2) ~= 0
                error('scifor:PathInput', ...
                    'Metadata arguments must be name-value pairs.');
            end

            resolved = obj.path_template;
            for i = 1:2:numel(varargin)
                key = string(varargin{i});
                if strcmpi(key, 'db')
                    continue;  % Skip db parameter
                end
                val = varargin{i+1};
                if isnumeric(val)
                    val_str = num2str(val);
                else
                    val_str = string(val);
                end
                resolved = strrep(resolved, "{" + key + "}", val_str);
            end

            % Resolve to absolute path
            if strlength(obj.root_folder) > 0
                filepath = string(fullfile(obj.root_folder, resolved));
            else
                filepath = string(fullfile(pwd, resolved));
            end

            % Regex matching against directory contents
            if obj.regex
                % Split resolved template on '/' (not fileparts) to avoid
                % treating regex backslashes as Windows path separators.
                slash_idx = find(char(resolved) == '/', 1, 'last');
                if isempty(slash_idx)
                    dir_template = "";
                    pattern = resolved;
                else
                    dir_template = extractBefore(resolved, slash_idx);
                    pattern = extractAfter(resolved, slash_idx);
                end

                if strlength(obj.root_folder) > 0
                    dir_path = string(fullfile(obj.root_folder, dir_template));
                else
                    dir_path = string(fullfile(pwd, dir_template));
                end

                listing = dir(dir_path);
                listing = listing(~[listing.isdir]);
                names = string({listing.name});

                matches = false(size(names));
                for j = 1:numel(names)
                    tok = regexp(names(j), "^" + pattern + "$", 'once');
                    matches(j) = ~isempty(tok);
                end

                matched_names = names(matches);
                if numel(matched_names) == 0
                    error('scifor:PathInput:NoMatch', ...
                        'Regex pattern "%s" matched no files in "%s".', ...
                        pattern, dir_path);
                elseif numel(matched_names) > 1
                    error('scifor:PathInput:MultipleMatches', ...
                        'Regex pattern "%s" matched %d files in "%s": %s', ...
                        pattern, numel(matched_names), dir_path, ...
                        strjoin(matched_names, ', '));
                end

                filepath = string(fullfile(dir_path, matched_names(1)));
            end
        end

        function disp(obj)
        %DISP  Display the PathInput.
            opts = "";
            if strlength(obj.root_folder) > 0
                opts = opts + sprintf(', root_folder="%s"', obj.root_folder);
            end
            if obj.regex
                opts = opts + ", regex=true";
            end
            fprintf('  scifor.PathInput("%s"%s)\n', obj.path_template, opts);
        end
    end
end
