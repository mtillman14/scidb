classdef Sweep < scifor.EachOf
%SCIFOR.SWEEP  Named sugar for EachOf: a fixed list of alternatives for
%one constant parameter, meant to be bound to a persistent variable (a
%zero-arg "getter" function file, since MATLAB has no module-level
%globals — see docs/claude/code-discovery-categories.md) so it's
%discoverable the same way a PathInput getter is, rather than written
%inline at a call site.
%
%   S = scifor.Sweep(V1, V2, ...)
%
%   Behaves identically to scifor.EachOf in every other respect
%   (isa(S, 'scifor.EachOf') is true for a Sweep); mirrors Python's
%   scifor.Sweep (scifor/src/scifor/each_of.py).
%
%   Example:
%       function s = window_seconds()
%           s = scifor.Sweep(10, 20, 30);
%       end

    methods
        function obj = Sweep(varargin)
        %SWEEP  Construct a Sweep wrapper.
        %
        %   S = scifor.Sweep(V1, V2, ...)
            obj@scifor.EachOf(varargin{:});
        end

        function disp(obj)
        %DISP  Display the Sweep wrapper.
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
            fprintf('  scifor.Sweep(%s)\n', strjoin(parts, ', '));
        end
    end
end
