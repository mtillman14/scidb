%% Test script for table concatenation optimization in to_python
% This verifies that cell columns containing homogeneous tables are
% converted efficiently (1 log message instead of N).

% Setup
this_dir = fileparts(mfilename('fullpath'));
run(fullfile(this_dir, 'sci-matlab/tests/matlab/scidb/setup_paths.m'));

% Create temporary test database
test_dir = tempname;
mkdir(test_dir);
try
    scidb.configure_database( ...
        fullfile(test_dir, 'test.duckdb'), ...
        ["subject", "session"]);

    fprintf('=== Test 1: Homogeneous 1xN tables (optimization should trigger) ===\n');

    % Create a result table similar to GAITRite data structure
    % Each row has a cell containing a 1x54 table
    n_rows = 3;
    result_tbl = table();
    result_tbl.subject = [1; 1; 1];
    result_tbl.session = [1; 2; 3];
    result_tbl.GAITRiteLoaded = cell(n_rows, 1);

    % Populate each cell with a 1x54 table
    for i = 1:n_rows
        tbl_1x54 = table();
        for j = 1:54
            tbl_1x54.(sprintf('col_%d', j)) = j * i;  % Different values per row
        end
        result_tbl.GAITRiteLoaded{i} = tbl_1x54;
    end

    fprintf('Created table with %d rows, each containing 1x54 table\n', n_rows);
    fprintf('Converting to Python (watch for log messages)...\n\n');

    % Convert - should see ONE log message for 54 columns, not THREE
    py_df = scidb.internal.to_python(result_tbl);

    fprintf('\nConversion complete. Check above - should see:\n');
    fprintf('  - "trying table concat" (optimization triggered)\n');
    fprintf('  - "table concat succeeded"\n');
    fprintf('  - Only ONE set of "processing table column 1/54..." messages\n\n');

    % Verify the result
    assert(isa(py_df, 'py.pandas.core.frame.DataFrame'), 'Result should be a DataFrame');
    assert(int64(py_df.shape{1}) == n_rows, 'Should have 3 rows');

    fprintf('=== Test 2: Mixed types (fallback to element-by-element) ===\n');

    mixed_tbl = table();
    mixed_tbl.subject = [1; 2];
    mixed_tbl.data = cell(2, 1);
    mixed_tbl.data{1} = table(1, 2, 'VariableNames', {'A', 'B'});
    mixed_tbl.data{2} = [1 2 3];  % Not a table - should trigger fallback

    fprintf('Converting mixed-type cell column...\n\n');
    py_df2 = scidb.internal.to_python(mixed_tbl);

    fprintf('\nShould see "element-by-element" in logs (fallback used)\n\n');

    fprintf('=== Test 3: Schema mismatch (fallback to element-by-element) ===\n');

    mismatch_tbl = table();
    mismatch_tbl.subject = [1; 2];
    mismatch_tbl.data = cell(2, 1);
    mismatch_tbl.data{1} = table(1, 2, 'VariableNames', {'A', 'B'});
    mismatch_tbl.data{2} = table(1, 2, 3, 'VariableNames', {'A', 'B', 'C'});  % Different schema

    fprintf('Converting tables with mismatched schemas...\n\n');
    py_df3 = scidb.internal.to_python(mismatch_tbl);

    fprintf('\nShould see "element-by-element" in logs (fallback used)\n\n');

    fprintf('=== Test 4: from_python optimization (loading DataFrames) ===\n');

    % Create a Python list of DataFrames with identical schemas
    py_df_list = py.list();
    for i = 1:3
        df_data = py.dict();
        for j = 1:54
            col_name = sprintf('col_%d', j);
            df_data{col_name} = py.list({j * i});
        end
        single_df = py.pandas.DataFrame(df_data);
        py_df_list.append(single_df);
    end

    fprintf('Created Python list of 3 DataFrames (each 1x54)\n');
    fprintf('Converting from Python (watch for log messages)...\n\n');

    % Convert - should see ONE log message for 54 columns, not THREE
    matlab_cell = scidb.internal.from_python(py_df_list);

    fprintf('\nConversion complete. Check above - should see:\n');
    fprintf('  - "trying DataFrame concat" (optimization triggered)\n');
    fprintf('  - "DataFrame concat succeeded"\n');
    fprintf('  - Only ONE set of "convert_dataframe: column X/54" messages\n\n');

    % Verify the result
    assert(iscell(matlab_cell), 'Result should be a cell array');
    assert(numel(matlab_cell) == 3, 'Should have 3 tables');
    assert(istable(matlab_cell{1}), 'Each element should be a table');
    assert(width(matlab_cell{1}) == 54, 'Each table should have 54 columns');

    fprintf('✓ All tests passed!\n');

catch ME
    fprintf('✗ Test failed: %s\n', ME.message);
    rethrow(ME);
end

% Cleanup
try
    scidb.get_database().close();
catch
end
rmdir(test_dir, 's');
