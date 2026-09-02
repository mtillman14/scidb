classdef TestSciforForEachMappingInputs < matlab.unittest.TestCase
%TESTSCIFORFOREACHMAPPINGINPUTS  Tests for the '_mapping_inputs' option.
%
%   A variable whose records are STRUCTS is stored one database column per
%   field and loaded spread, so by the time the columns arrive here a single
%   record is indistinguishable from a one-row table. '_mapping_inputs' is
%   how scidb states which inputs are struct records; without it the user
%   function received a 1xN table and every field access returned a 1x1 cell
%   ("Undefined function 'isnan' for input arguments of type 'cell'").
%
%   The mark cannot be inferred from shape: "one row, N data columns" is
%   also exactly what a genuine table-valued variable looks like. That is
%   what test_unmarked_table_input_is_unchanged pins.
%
%   See .claude/plan-matlab-struct-and-iteration-26-09-02.md defect 3.

    methods (TestMethodSetup)
        function resetSchema(~)
            scifor.set_schema(string.empty(1, 0));
        end
    end

    methods (Static)
        function tbl = emgTable()
        %EMGTABLE  Three pass-level records, two struct fields each.
            tbl = table([1; 2; 3], ...
                {[1; 2]; [3; 4]; [5; 6]}, ...
                {7; 8; 9}, ...
                'VariableNames', {'pass', 'RHAM', 'RVL'});
        end
    end

    methods (Test)

        function test_marked_single_row_is_a_struct(testCase)
        %   One record per combo arrives as the struct that was saved.
            scifor.set_schema("pass");
            received = {};

            function result = consumer(emg)
                received{end+1} = emg; %#ok<AGROW>
                result = 0;
            end

            scifor.for_each(@consumer, ...
                struct('emg', TestSciforForEachMappingInputs.emgTable()), ...
                '_mapping_inputs', struct('emg', ["RHAM", "RVL"]), ...
                'pass', [1 2 3]);

            testCase.verifyEqual(numel(received), 3);
            for k = 1:3
                testCase.verifyTrue(isstruct(received{k}));
                testCase.verifyTrue(isscalar(received{k}));
                testCase.verifyEqual(sort(fieldnames(received{k})), ...
                    {'RHAM'; 'RVL'});
            end
            testCase.verifyEqual(received{1}.RHAM, [1; 2]);
            testCase.verifyEqual(received{3}.RVL, 9);
        end

        function test_marked_field_keeps_its_saved_column_shape(testCase)
        %   When several records load together, from_python stacks their
        %   vectors as ROWS of a matrix; filtering to one row gives 1xN
        %   where the saved value was Nx1. The field must come back Nx1.
            scifor.set_schema("pass");
            tbl = table([1; 2], [10 20; 30 40], [1; 2], ...
                'VariableNames', {'pass', 'RHAM', 'RVL'});
            received = {};

            function result = consumer(emg)
                received{end+1} = emg; %#ok<AGROW>
                result = 0;
            end

            scifor.for_each(@consumer, struct('emg', tbl), ...
                '_mapping_inputs', struct('emg', ["RHAM", "RVL"]), ...
                'pass', [1 2]);

            testCase.verifyEqual(received{1}.RHAM, [10; 20]);
            testCase.verifyEqual(received{2}.RHAM, [30; 40]);
        end

        function test_marked_multi_row_slice_stays_a_table(testCase)
        %   A coarser iteration level has no single struct to give.
            scifor.set_schema(["pass", "cycle"]);
            tbl = table([1; 1; 2], [1; 2; 1], [10; 20; 30], [40; 50; 60], ...
                'VariableNames', {'pass', 'cycle', 'RHAM', 'RVL'});
            received = {};

            function result = consumer(emg)
                received{end+1} = emg; %#ok<AGROW>
                result = 0;
            end

            scifor.for_each(@consumer, struct('emg', tbl), ...
                '_mapping_inputs', struct('emg', ["RHAM", "RVL"]), ...
                'pass', 1);

            testCase.verifyEqual(numel(received), 1);
            testCase.verifyTrue(istable(received{1}));
            testCase.verifyEqual(height(received{1}), 2);
        end

        function test_as_table_still_wins(testCase)
        %   as_table is an explicit request for the table.
            scifor.set_schema("pass");
            received = {};

            function result = consumer(emg)
                received{end+1} = emg; %#ok<AGROW>
                result = 0;
            end

            scifor.for_each(@consumer, ...
                struct('emg', TestSciforForEachMappingInputs.emgTable()), ...
                '_mapping_inputs', struct('emg', ["RHAM", "RVL"]), ...
                'as_table', true, 'pass', 1);

            testCase.verifyTrue(istable(received{1}));
        end

        function test_unmarked_table_input_is_unchanged(testCase)
        %   Without the mark a multi-column single row stays a table --
        %   the reason this cannot be inferred from shape alone.
            scifor.set_schema("pass");
            received = {};

            function result = consumer(emg)
                received{end+1} = emg; %#ok<AGROW>
                result = 0;
            end

            scifor.for_each(@consumer, ...
                struct('emg', TestSciforForEachMappingInputs.emgTable()), ...
                'pass', 1);

            testCase.verifyFalse(isstruct(received{1}));
        end

        function test_stale_column_names_fall_back_to_a_table(testCase)
        %   A renamed/dropped column must degrade to the previous behavior
        %   rather than handing the function an empty struct.
            scifor.set_schema("pass");
            received = {};

            function result = consumer(emg)
                received{end+1} = emg; %#ok<AGROW>
                result = 0;
            end

            scifor.for_each(@consumer, ...
                struct('emg', TestSciforForEachMappingInputs.emgTable()), ...
                '_mapping_inputs', struct('emg', ["gone", "also_gone"]), ...
                'pass', 1);

            testCase.verifyFalse(isstruct(received{1}));
        end

    end
end
