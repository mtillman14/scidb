classdef TestParameter < matlab.unittest.TestCase
%TESTPARAMETER  scidb.Parameter is a named EachOf carrying a description
%   (see docs/claude/entity-editability-model.md) — these tests cover only
%   what is NEW (construction, description, .values/.value, isa), not
%   EachOf expansion mechanics, which TestEachOf.m already covers and
%   Parameter inherits unchanged.

    methods (TestClassSetup)
        function addPaths(~)
            this_dir = fileparts(mfilename('fullpath'));
            run(fullfile(this_dir, 'setup_paths.m'));
        end
    end

    methods (Test)
        function test_is_a_eachof(testCase)
            s = scidb.Parameter(10, 20, 30);
            testCase.verifyTrue(isa(s, 'scifor.EachOf'));
        end

        function test_alternatives_match_constructor_args(testCase)
            s = scidb.Parameter(10, 20, 30);
            testCase.verifyEqual(s.alternatives, {10, 20, 30});
        end

        function test_single_value_still_a_parameter(testCase)
            s = scidb.Parameter(42);
            testCase.verifyTrue(isa(s, 'scifor.EachOf'));
            testCase.verifyEqual(s.alternatives, {42});
        end

        function test_constructs_with_no_values(testCase)
            % Declared but not yet valued -- what the GUI's "New parameter"
            % form produces. It used to be papered over with a placeholder 0
            % written into source, indistinguishable from a real value.
            p = scidb.Parameter();
            testCase.verifyEqual(p.values, {});
            testCase.verifyTrue(isa(p, 'scifor.EachOf'));
        end

        function test_no_values_keeps_its_description(testCase)
            p = scidb.Parameter('description', 'filled in later');
            testCase.verifyEqual(p.description, 'filled in later');
            testCase.verifyEqual(p.values, {});
        end

        function test_value_says_there_is_none_yet(testCase)
            testCase.verifyError(@() scidb.Parameter().value, ...
                'scidb:Parameter:NoValue');
        end

        function test_expanding_a_value_less_parameter_errors(testCase)
            % The failure this replaces was SILENT: a zero-length axis makes
            % the cartesian product empty, so for_each iterated zero times,
            % wrote no records and returned as though it had worked.
            fn = @(window_seconds) window_seconds * 2;
            testCase.verifyError( ...
                @() scifor.for_each(fn, ...
                    struct('window_seconds', scidb.Parameter())), ...
                'scifor:EachOf:NoAlternatives');
        end

        function test_description_defaults_and_is_captured(testCase)
            testCase.verifyEqual(scidb.Parameter(1).description, '');
            p = scidb.Parameter(10, 20, 'description', 'Analysis window');
            testCase.verifyEqual(p.description, 'Analysis window');
            % The description must NOT become an alternative.
            testCase.verifyEqual(p.alternatives, {10, 20});
        end

        function test_values_and_value_accessors(testCase)
            testCase.verifyEqual(scidb.Parameter(10, 20).values, {10, 20});
            testCase.verifyEqual(scidb.Parameter(42).value, 42);
            % .value on a fan-out would silently pick one of several.
            testCase.verifyError(@() scidb.Parameter(1, 2).value, ...
                'scidb:Parameter:NotSingleValued');
        end

        function test_expands_in_for_each_same_as_eachof(testCase)
            % A Parameter fans out into independent calls, exactly as a
            % bare scifor.EachOf would (inherited, unchanged expansion
            % logic — spot-checked here, not re-derived).
            fn = @(window_seconds) window_seconds * 2;
            result = scifor.for_each(fn, ...
                struct('window_seconds', scidb.Parameter(10, 20, 30)));

            testCase.verifyEqual(height(result), 3);
            testCase.verifyEqual(sort(result.output), sort([20; 40; 60]));
        end
    end
end
