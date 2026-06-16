function y = dummy_return_one(varargin)
%DUMMY_RETURN_ONE  Test helper: returns scalar 1.0 regardless of inputs.
%   Used by TestForEachTimingInstrumentation so the save side stores a
%   tiny DOUBLE (single_column mode), keeping the run dominated by the
%   prepare/load path that we want to profile.
    y = 1.0;
end
