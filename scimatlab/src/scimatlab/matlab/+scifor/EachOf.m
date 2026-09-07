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
%   An EachOf may be constructed with NO alternatives. That is a
%   placeholder, not a runnable axis -- it is what a scidb.Parameter
%   declared but not yet given a value looks like from here (a Parameter IS
%   an EachOf). It has to be legal at construction: a MATLAB superclass
%   constructor call cannot sit in a conditional branch, so
%   +scidb/Parameter.m has exactly one obj@scifor.EachOf(args{:}) call and
%   args is empty for a value-less Parameter. Refusing it belongs at
%   EXPANSION instead -- see scifor.require_alternatives, which every
%   for_each calls before building the cartesian product.
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
