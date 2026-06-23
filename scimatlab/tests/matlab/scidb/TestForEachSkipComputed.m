classdef TestForEachSkipComputed < matlab.unittest.TestCase
%TESTFOREACHSKIPCOMPUTED  End-to-end tests for skip_computed on the MATLAB path.
%
%   Verifies that scidb.for_each(..., 'skip_computed', true) actually
%   prevents re-execution of the user function for combos whose output
%   already exists with unchanged upstream provenance — the behavior that
%   was silently broken because the flag was swallowed as a metadata axis
%   and the bridge never built the skip hook.

    properties
        test_dir
    end

    methods (TestClassSetup)
        function addPaths(~)
            this_dir = fileparts(mfilename('fullpath'));
            run(fullfile(this_dir, 'setup_paths.m'));
        end
    end

    methods (TestMethodSetup)
        function setupDatabase(testCase)
            testCase.test_dir = tempname;
            mkdir(testCase.test_dir);
            scidb.configure_database( ...
                fullfile(testCase.test_dir, 'test.duckdb'), ...
                ["subject", "session"]);
            % Reset the invocation counter before each test.
            global SKIP_COUNTING_DOUBLE_CALLS %#ok<GVMIS>
            SKIP_COUNTING_DOUBLE_CALLS = 0;
        end
    end

    methods (TestMethodTeardown)
        function cleanup(testCase)
            try
                scidb.get_database().close();
            catch
            end
            if isfolder(testCase.test_dir)
                rmdir(testCase.test_dir, 's');
            end
        end
    end

    methods (Test)

        function test_second_run_skips_function(testCase)
            % First run computes; second run with skip_computed=true must NOT
            % re-execute the function.
            global SKIP_COUNTING_DOUBLE_CALLS %#ok<GVMIS>
            RawSignal().save([1 2 3], 'subject', 1, 'session', 'A');

            scidb.for_each(@skip_counting_double, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A", ...
                'skip_computed', true);
            testCase.verifyEqual(SKIP_COUNTING_DOUBLE_CALLS, 1, ...
                'First run should execute the function exactly once.');

            scidb.for_each(@skip_counting_double, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A", ...
                'skip_computed', true);
            testCase.verifyEqual(SKIP_COUNTING_DOUBLE_CALLS, 1, ...
                'Second run should be skipped (counter unchanged).');

            % Output still present and correct.
            result = ProcessedSignal().load('subject', 1, 'session', 'A');
            testCase.verifyEqual(result.data, [2 4 6]', 'AbsTol', 1e-10);
        end

        function test_skips_only_unchanged_combos(testCase)
            % subject 1 already computed; subject 2 is new. A combined run with
            % skip_computed=true must run only the new combo.
            global SKIP_COUNTING_DOUBLE_CALLS %#ok<GVMIS>
            RawSignal().save([1 2 3], 'subject', 1, 'session', 'A');
            RawSignal().save([4 5 6], 'subject', 2, 'session', 'A');

            % Compute subject 1 only.
            scidb.for_each(@skip_counting_double, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A", ...
                'skip_computed', true);
            testCase.verifyEqual(SKIP_COUNTING_DOUBLE_CALLS, 1);

            % Now run both: subject 1 skipped, subject 2 computed → +1.
            scidb.for_each(@skip_counting_double, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', [1 2], 'session', "A", ...
                'skip_computed', true);
            testCase.verifyEqual(SKIP_COUNTING_DOUBLE_CALLS, 2, ...
                'Only the new combo (subject 2) should execute.');

            r2 = ProcessedSignal().load('subject', 2, 'session', 'A');
            testCase.verifyEqual(r2.data, [8 10 12]', 'AbsTol', 1e-10);
        end

        function test_flag_off_reruns(testCase)
            % Without skip_computed the function re-executes (default behavior).
            global SKIP_COUNTING_DOUBLE_CALLS %#ok<GVMIS>
            RawSignal().save([1 2 3], 'subject', 1, 'session', 'A');

            scidb.for_each(@skip_counting_double, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A");
            scidb.for_each(@skip_counting_double, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A");
            testCase.verifyEqual(SKIP_COUNTING_DOUBLE_CALLS, 2, ...
                'Default (no skip_computed) should re-run the function.');
        end

    end
end
