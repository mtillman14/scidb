classdef TestIntrospect < matlab.unittest.TestCase
%TESTINTROSPECT  Tests for introspect= flag on load() and for_each().

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

        % -----------------------------------------------------------------
        % branch_params always populated (not just with introspect=true)
        % -----------------------------------------------------------------

        function test_branch_params_always_struct(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            var = RawSignal().load('subject', 1, 'session', 'A');
            testCase.verifyTrue(isstruct(var.branch_params));
        end

        function test_branch_params_empty_for_direct_save(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            var = RawSignal().load('subject', 1, 'session', 'A');
            testCase.verifyEqual(fieldnames(var.branch_params), cell(0, 1));
        end

        % -----------------------------------------------------------------
        % load(introspect=true) — non-table path
        % -----------------------------------------------------------------

        function test_load_introspect_returns_basevariable(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            var = RawSignal().load('subject', 1, 'session', 'A', 'introspect', true);
            testCase.verifyClass(var, 'scidb.BaseVariable');
            testCase.verifyEqual(var.data, 42);
        end

        function test_load_introspect_existing_fields_populated(testCase)
            record_id = RawSignal().save(42, 'subject', 1, 'session', 'A');
            var = RawSignal().load('subject', 1, 'session', 'A', 'introspect', true);
            testCase.verifyEqual(string(var.record_id), string(record_id));
            testCase.verifyFalse(strlength(var.content_hash) == 0);
            testCase.verifyTrue(isstruct(var.branch_params));
        end

        function test_load_introspect_where_is_empty_without_filter(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            var = RawSignal().load('subject', 1, 'session', 'A', 'introspect', true);
            testCase.verifyTrue(isprop(var, 'where'));
            testCase.verifyTrue(isempty(var.where));
        end

        function test_load_introspect_version_mode_default_latest(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            var = RawSignal().load('subject', 1, 'session', 'A', 'introspect', true);
            testCase.verifyTrue(isprop(var, 'version_mode'));
            testCase.verifyEqual(string(var.version_mode), "latest");
        end

        function test_load_introspect_version_mode_all(testCase)
            RawSignal().save(10, 'subject', 1, 'session', 'A');
            RawSignal().save(20, 'subject', 1, 'session', 'A');
            results = RawSignal().load('version', 'all', 'subject', 1, 'session', 'A', 'introspect', true);
            testCase.verifyEqual(numel(results), 2);
            for i = 1:numel(results)
                testCase.verifyEqual(string(results(i).version_mode), "all");
            end
        end

        function test_load_introspect_where_echoes_filter(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            filt = RawSignal("value") > 5;
            var = RawSignal().load('subject', 1, 'session', 'A', ...
                'introspect', true, 'where', filt);
            testCase.verifyTrue(isprop(var, 'where'));
            testCase.verifyClass(var.where, 'scidb.Filter');
            testCase.verifyEqual(var.where, filt);
        end

        function test_load_no_introspect_no_dynamic_props(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            var = RawSignal().load('subject', 1, 'session', 'A');
            testCase.verifyFalse(isprop(var, 'where'));
            testCase.verifyFalse(isprop(var, 'version_mode'));
        end

        function test_load_introspect_multi_result(testCase)
            RawSignal().save(10, 'subject', 1, 'session', 'A');
            RawSignal().save(20, 'subject', 2, 'session', 'A');
            results = RawSignal().load('session', 'A', 'introspect', true);
            testCase.verifyEqual(numel(results), 2);
            for i = 1:numel(results)
                testCase.verifyTrue(isprop(results(i), 'where'));
                testCase.verifyTrue(isprop(results(i), 'version_mode'));
                testCase.verifyEqual(string(results(i).version_mode), "latest");
            end
        end

        % -----------------------------------------------------------------
        % load(as_table=true, introspect=true)
        % -----------------------------------------------------------------

        function test_load_as_table_introspect_returns_table(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            tbl = RawSignal().load('subject', 1, 'session', 'A', ...
                'as_table', true, 'introspect', true);
            testCase.verifyTrue(istable(tbl));
        end

        function test_load_as_table_introspect_extra_columns(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            tbl = RawSignal().load('subject', 1, 'session', 'A', ...
                'as_table', true, 'introspect', true);
            cols = string(tbl.Properties.VariableNames);
            testCase.verifyTrue(ismember("record_id",    cols));
            testCase.verifyTrue(ismember("branch_params", cols));
            testCase.verifyTrue(ismember("content_hash",  cols));
            testCase.verifyTrue(ismember("where",         cols));
            testCase.verifyTrue(ismember("version_mode",  cols));
        end

        function test_load_as_table_introspect_record_id_non_empty(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            tbl = RawSignal().load('subject', 1, 'session', 'A', ...
                'as_table', true, 'introspect', true);
            testCase.verifyFalse(strlength(tbl.record_id(1)) == 0);
        end

        function test_load_as_table_introspect_branch_params_is_struct(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            tbl = RawSignal().load('subject', 1, 'session', 'A', ...
                'as_table', true, 'introspect', true);
            testCase.verifyTrue(isstruct(tbl.branch_params{1}));
        end

        function test_load_as_table_introspect_where_empty_string(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            tbl = RawSignal().load('subject', 1, 'session', 'A', ...
                'as_table', true, 'introspect', true);
            testCase.verifyEqual(string(tbl.where(1)), "");
        end

        function test_load_as_table_introspect_version_mode_repeated(testCase)
            RawSignal().save(10, 'subject', 1, 'session', 'A');
            RawSignal().save(20, 'subject', 2, 'session', 'A');
            tbl = RawSignal().load('session', 'A', 'as_table', true, 'introspect', true);
            testCase.verifyEqual(height(tbl), 2);
            testCase.verifyTrue(all(string(tbl.version_mode) == "latest"));
        end

        function test_load_as_table_introspect_column_order(testCase)
            % Introspect columns must appear to the right of the data column
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            tbl = RawSignal().load('subject', 1, 'session', 'A', ...
                'as_table', true, 'introspect', true);
            cols = string(tbl.Properties.VariableNames);
            % Find the data column (named after the variable type or 'data')
            data_idx = find(cols == "RawSignal" | cols == "data", 1);
            rid_idx  = find(cols == "record_id", 1);
            testCase.verifyLessThan(data_idx, rid_idx);
        end

        function test_load_as_table_no_introspect_no_extra_columns(testCase)
            RawSignal().save(42, 'subject', 1, 'session', 'A');
            tbl = RawSignal().load('subject', 1, 'session', 'A', 'as_table', true);
            cols = string(tbl.Properties.VariableNames);
            testCase.verifyFalse(ismember("record_id",    cols));
            testCase.verifyFalse(ismember("branch_params", cols));
            testCase.verifyFalse(ismember("content_hash",  cols));
        end

        % -----------------------------------------------------------------
        % for_each(introspect=true)
        % -----------------------------------------------------------------

        function test_for_each_introspect_record_id_column_present(testCase)
            RawSignal().save([1 2 3], 'subject', 1, 'session', 'A');

            result = scidb.for_each(@double_values, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A", ...
                'introspect', true);

            testCase.verifyTrue(istable(result));
            cols = string(result.Properties.VariableNames);
            testCase.verifyTrue(ismember("_record_id_x", cols));
        end

        function test_for_each_introspect_record_id_is_string(testCase)
            RawSignal().save([1 2 3], 'subject', 1, 'session', 'A');

            result = scidb.for_each(@double_values, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A", ...
                'introspect', true);

            rid = string(result.("_record_id_x")(1));
            testCase.verifyFalse(strlength(rid) == 0);
        end

        function test_for_each_introspect_branch_params_column_present(testCase)
            RawSignal().save([1 2 3], 'subject', 1, 'session', 'A');

            result = scidb.for_each(@double_values, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A", ...
                'introspect', true);

            cols = string(result.Properties.VariableNames);
            testCase.verifyTrue(ismember("_branch_params_x", cols));
            testCase.verifyTrue(isstruct(result.("_branch_params_x"){1}));
        end

        function test_for_each_introspect_call_id_16char_hex(testCase)
            RawSignal().save([1 2 3], 'subject', 1, 'session', 'A');

            result = scidb.for_each(@double_values, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A", ...
                'introspect', true);

            cols = string(result.Properties.VariableNames);
            testCase.verifyTrue(ismember("_call_id", cols));
            call_id = string(result.("_call_id")(1));
            testCase.verifyEqual(strlength(call_id), 16);
            % Must be valid hex
            testCase.verifyTrue(~isempty(regexp(call_id, '^[0-9a-f]{16}$', 'once')));
        end

        function test_for_each_introspect_call_id_same_every_row(testCase)
            RawSignal().save([1 2 3], 'subject', 1, 'session', 'A');
            RawSignal().save([4 5 6], 'subject', 2, 'session', 'A');

            result = scidb.for_each(@double_values, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', [1 2], 'session', "A", ...
                'introspect', true);

            testCase.verifyEqual(height(result), 2);
            testCase.verifyEqual(string(result.("_call_id")(1)), string(result.("_call_id")(2)));
        end

        function test_for_each_introspect_config_keys_struct(testCase)
            RawSignal().save([1 2 3], 'subject', 1, 'session', 'A');

            result = scidb.for_each(@double_values, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A", ...
                'introspect', true);

            cols = string(result.Properties.VariableNames);
            testCase.verifyTrue(ismember("_config_keys", cols));
            ck = result.("_config_keys"){1};
            testCase.verifyTrue(isstruct(ck));
            testCase.verifyTrue(isfield(ck, 'x__fn'));
            testCase.verifyTrue(isfield(ck, 'x__fn_hash'));
        end

        function test_for_each_introspect_where_empty_without_filter(testCase)
            RawSignal().save([1 2 3], 'subject', 1, 'session', 'A');

            result = scidb.for_each(@double_values, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A", ...
                'introspect', true);

            cols = string(result.Properties.VariableNames);
            testCase.verifyTrue(ismember("_where", cols));
            testCase.verifyTrue(ismissing(result.("_where")(1)) || strlength(string(result.("_where")(1))) == 0);
        end

        function test_for_each_introspect_column_order(testCase)
            % Output column must appear before introspect columns
            RawSignal().save([1 2 3], 'subject', 1, 'session', 'A');

            result = scidb.for_each(@double_values, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A", ...
                'introspect', true);

            cols = string(result.Properties.VariableNames);
            out_idx = find(cols == "ProcessedSignal", 1);
            rid_idx = find(cols == "_record_id_x", 1);
            cid_idx = find(cols == "_call_id", 1);
            testCase.verifyLessThan(out_idx, rid_idx);
            testCase.verifyLessThan(rid_idx, cid_idx);
        end

        function test_for_each_no_introspect_no_extra_columns(testCase)
            RawSignal().save([1 2 3], 'subject', 1, 'session', 'A');

            result = scidb.for_each(@double_values, ...
                struct('x', RawSignal()), ...
                {ProcessedSignal()}, ...
                'subject', 1, 'session', "A");

            cols = string(result.Properties.VariableNames);
            testCase.verifyFalse(any(startsWith(cols, "_record_id_")));
            testCase.verifyFalse(any(startsWith(cols, "_branch_params_")));
            testCase.verifyFalse(ismember("_call_id", cols));
            testCase.verifyFalse(ismember("_config_keys", cols));
            testCase.verifyFalse(ismember("_where", cols));
        end

    end
end
