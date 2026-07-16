function y = pipeline_counting_double(x)
%PIPELINE_COUNTING_DOUBLE  Test helper: doubles x, counts calls globally.
%   Reset/read the counter via `global PIPELINE_TEST_CALLS_DOUBLE`.
    global PIPELINE_TEST_CALLS_DOUBLE
    if isempty(PIPELINE_TEST_CALLS_DOUBLE)
        PIPELINE_TEST_CALLS_DOUBLE = 0;
    end
    PIPELINE_TEST_CALLS_DOUBLE = PIPELINE_TEST_CALLS_DOUBLE + 1;
    y = double(x) * 2;
end
