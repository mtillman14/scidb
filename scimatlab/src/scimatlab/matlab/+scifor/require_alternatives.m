function require_alternatives(each_of, kind, param)
%SCIFOR.REQUIRE_ALTERNATIVES  Refuse an EachOf axis with nothing to expand.
%
%   scifor.require_alternatives(E, 'input', PARAM_NAME)
%   scifor.require_alternatives(E, 'where')
%
%   Called by every for_each EachOf-expansion site (+scifor/for_each.m and
%   +scidb/for_each.m, mirroring Python's scifor.require_alternatives in
%   scifor/src/scifor/each_of.py) as each axis is collected, before the
%   cartesian product is built.
%
%   An EachOf may be CONSTRUCTED with no alternatives -- that is what a
%   scidb.Parameter declared with no value yet is, and it has to be legal
%   because a MATLAB superclass constructor call cannot sit in a conditional
%   branch, so +scidb/Parameter.m always calls obj@scifor.EachOf(args{:})
%   and args may be empty. EXPANDING one is the error: the cartesian product
%   over a zero-length axis is empty, so for_each would iterate zero times,
%   write no records, and return as though it had succeeded.
%
%   class(each_of) puts the real type in the message, so a value-less
%   scidb.Parameter reports itself as one without this layer knowing that
%   class exists.

    if nargin < 3
        param = '';
    end

    if ~isempty(each_of.alternatives)
        return;
    end

    if strcmp(kind, 'input')
        target = sprintf('input ''%s''', param);
    else
        target = 'where=';
    end

    error('scifor:EachOf:NoAlternatives', ...
        ['%s bound to %s has no alternatives, so there is nothing to run. ' ...
         'An empty axis would iterate zero times and write no records while ' ...
         'appearing to succeed -- give it at least one value, or unbind it.'], ...
        class(each_of), target);
end
