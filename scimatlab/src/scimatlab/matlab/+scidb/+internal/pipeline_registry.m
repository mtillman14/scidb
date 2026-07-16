function out = pipeline_registry(action, name, obj)
%PIPELINE_REGISTRY  Session map: pipeline name -> scidb.Pipeline wrapper.
%
%   MATLAB-side lookup used by scidb.for_each's registration seam and by
%   composed runs (an execution-order descriptor names its owner pipeline;
%   the fn handles + raw call args that cannot cross the bridge live on the
%   owner's wrapper, found here).
%
%   pipeline_registry('put',   name, obj)  — register a wrapper
%   pipeline_registry('get',   name)       — fetch ([] if unknown)
%   pipeline_registry('clear')             — reset (test isolation)

    persistent reg
    if isempty(reg)
        reg = containers.Map('KeyType', 'char', 'ValueType', 'any');
    end

    switch action
        case 'put'
            reg(char(name)) = obj;
            out = obj;
        case 'get'
            if isKey(reg, char(name))
                out = reg(char(name));
            else
                out = [];
            end
        case 'clear'
            reg = containers.Map('KeyType', 'char', 'ValueType', 'any');
            out = [];
        otherwise
            error('scidb:pipeline_registry', 'Unknown action "%s"', action);
    end
end
