function y = skip_counting_double(x)
%SKIP_COUNTING_DOUBLE  Test function: doubles input and counts invocations.
%   Increments the global SKIP_COUNTING_DOUBLE_CALLS each time it runs so a
%   test can assert whether skip_computed actually prevented execution. The
%   loop runs in MATLAB (same process), so the global persists across calls.
    global SKIP_COUNTING_DOUBLE_CALLS %#ok<GVMIS>
    if isempty(SKIP_COUNTING_DOUBLE_CALLS)
        SKIP_COUNTING_DOUBLE_CALLS = 0;
    end
    SKIP_COUNTING_DOUBLE_CALLS = SKIP_COUNTING_DOUBLE_CALLS + 1;
    y = x * 2;
end
