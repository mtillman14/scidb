classdef EachOf
%SCIFOR.EACHOF  Express multiple alternatives for a for_each() parameter.
%
%   E = scifor.EachOf(ALT1, ALT2, ...)
%
%   Wraps alternatives for one for_each() input parameter (or the where=
%   filter). Each alternative expands into a separate, independent
%   for_each() call; results are concatenated. The total number of calls
%   is the cartesian product of all EachOf axes in a single for_each()
%   call.
%
%   With a single alternative, behaves identically to passing that value
%   directly.
%
%   Mirrors Python's scifor.EachOf (scifor/src/scifor/each_of.py) — see
%   docs/claude/each-of-variant-expansion.md.
%
%   Example:
%       scidb.for_each(@my_analysis, struct('filepath', ...
%           scifor.EachOf( ...
%               scifor.PathInput(template, root_folder="root/assessment"), ...
%               scifor.PathInput(template, root_folder="root/training") ...
%           )), {Output()}, subject=[], session=[]);

    properties (SetAccess = private)
        alternatives  cell  % Cell array of alternative values
    end

    methods
        function obj = EachOf(varargin)
        %EACHOF  Construct an EachOf wrapper.
        %
        %   E = scifor.EachOf(ALT1, ALT2, ...)

            if isempty(varargin)
                error('scifor:EachOf', ...
                    'EachOf requires at least one alternative.');
            end
            obj.alternatives = varargin;
        end

        function disp(obj)
        %DISP  Display the EachOf wrapper.
            parts = cell(1, numel(obj.alternatives));
            for i = 1:numel(obj.alternatives)
                alt = obj.alternatives{i};
                if isobject(alt)
                    parts{i} = class(alt);
                elseif isnumeric(alt) || islogical(alt)
                    parts{i} = sprintf('%g', alt);
                else
                    parts{i} = sprintf('%s', string(alt));
                end
            end
            fprintf('  scifor.EachOf(%s)\n', strjoin(parts, ', '));
        end
    end
end
