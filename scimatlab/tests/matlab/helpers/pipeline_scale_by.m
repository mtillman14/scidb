function y = pipeline_scale_by(x, factor)
%PIPELINE_SCALE_BY  Test helper: scale x by a constant factor; records the
%   factor received globally (binding-override verification).
    global PIPELINE_TEST_FACTORS
    if isempty(PIPELINE_TEST_FACTORS)
        PIPELINE_TEST_FACTORS = [];
    end
    PIPELINE_TEST_FACTORS(end+1) = double(factor); %#ok<AGROW>
    y = double(x) * double(factor);
end
