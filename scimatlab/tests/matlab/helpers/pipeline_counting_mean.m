function y = pipeline_counting_mean(x)
%PIPELINE_COUNTING_MEAN  Test helper: mean of x, counts calls globally.
%   Reset/read the counter via `global PIPELINE_TEST_CALLS_MEAN`.
    global PIPELINE_TEST_CALLS_MEAN
    if isempty(PIPELINE_TEST_CALLS_MEAN)
        PIPELINE_TEST_CALLS_MEAN = 0;
    end
    PIPELINE_TEST_CALLS_MEAN = PIPELINE_TEST_CALLS_MEAN + 1;
    y = mean(double(x(:)), 'omitnan');
end
