function result_tbl = for_each(varargin)
%SCIDB.FOR_EACH  Passthrough to scifor.for_each.
%
%   scidb.for_each(@FN, INPUTS, OUTPUTS, Name, Value, ...)
%
%   This function delegates to scifor.for_each, which holds the full
%   implementation. See scifor.for_each for complete documentation.

    result_tbl = scifor.for_each(varargin{:});

end
