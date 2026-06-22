function result_tbl = for_each(fn, inputs, outputs, varargin)
%SCIHIST.FOR_EACH  Deprecated thin shim over scidb.for_each.
%
%   scihist.for_each(@FN, INPUTS, OUTPUTS, Name, Value, ...)
%
%   DEPRECATED: lineage is now tracked automatically by scidb.for_each
%   (the bipartite provenance graph is recorded on save). The former
%   per-call scidb.LineageFcn auto-wrap was removed; this function now
%   simply delegates to scidb.for_each, mirroring the deprecated Python
%   ``scihist.for_each`` shim. Prefer calling scidb.for_each directly.
%
%   Arguments and Name-Value options are identical to scidb.for_each.
%
%   Returns:
%       result_tbl - MATLAB table with metadata columns and output columns.
%
%   Example:
%       scidb.for_each(@filter_data, ...
%           struct('step_length', StepLength(), 'smoothing', 0.2), ...
%           {FilteredStepLength()}, ...
%           subject=[1 2 3], session=["A" "B"]);

    result_tbl = scidb.for_each(fn, inputs, outputs, varargin{:});
end
