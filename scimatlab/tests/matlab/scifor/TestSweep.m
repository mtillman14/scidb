classdef TestSweep < matlab.unittest.TestCase
%TESTSWEEP  scifor.Sweep is named sugar for scifor.EachOf (see
%   docs/claude/code-discovery-categories.md) — these tests cover only
%   what's NEW (construction, isa(_, 'scifor.EachOf'), disp), not
%   EachOf's expansion mechanics, which TestEachOf.m already covers and
%   Sweep inherits unchanged.

    methods (TestClassSetup)
        function addPaths(~)
            this_dir = fileparts(mfilename('fullpath'));
            run(fullfile(this_dir, 'setup_paths.m'));
        end
    end

    methods (Test)
        function test_is_a_eachof(testCase)
            s = scifor.Sweep(10, 20, 30);
            testCase.verifyTrue(isa(s, 'scifor.EachOf'));
        end

        function test_alternatives_match_constructor_args(testCase)
            s = scifor.Sweep(10, 20, 30);
            testCase.verifyEqual(s.alternatives, {10, 20, 30});
        end

        function test_single_value_still_a_sweep(testCase)
            s = scifor.Sweep(42);
            testCase.verifyTrue(isa(s, 'scifor.EachOf'));
            testCase.verifyEqual(s.alternatives, {42});
        end

        function test_requires_at_least_one_value(testCase)
            testCase.verifyError(@() scifor.Sweep(), 'scifor:EachOf');
        end

        function test_expands_in_for_each_same_as_eachof(testCase)
            % A Sweep-wrapped constant fans out into independent calls,
            % exactly as a bare scifor.EachOf would (inherited, unchanged
            % expansion logic — spot-checked here, not re-derived).
            fn = @(window_seconds) window_seconds * 2;
            result = scifor.for_each(fn, ...
                struct('window_seconds', scifor.Sweep(10, 20, 30)));

            testCase.verifyEqual(height(result), 3);
            testCase.verifyEqual(sort(result.output), sort([20; 40; 60]));
        end
    end
end
