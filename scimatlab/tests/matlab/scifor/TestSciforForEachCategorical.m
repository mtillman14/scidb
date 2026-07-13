classdef TestSciforForEachCategorical < matlab.unittest.TestCase
%TESTSCIFORFOREACHCATEGORICAL  Tests for the categorical option of scifor.for_each.

    methods (TestMethodSetup)
        function resetSchema(~)
            scifor.set_schema(string.empty(1, 0));
        end
    end

    % =====================================================================
    % A. Default behavior (categorical=false)
    % =====================================================================

    methods (Test)

        function test_default_numeric_metadata_is_double(tc)
        %   By default, numeric metadata columns stay as double.
            scifor.set_schema(["subject"]);

            tbl = table([1;2], [10;20], 'VariableNames', {'subject','value'});
            result = scifor.for_each(@(x) x, ...
                struct('x', tbl), subject=[1 2]);

            tc.verifyFalse(iscategorical(result.subject));
            tc.verifyTrue(isnumeric(result.subject));
        end

        function test_default_string_metadata_is_string(tc)
        %   By default, string metadata columns stay as string.
            scifor.set_schema(["group"]);

            result = scifor.for_each(@() 1, struct(), group=["A" "B"]);

            tc.verifyFalse(iscategorical(result.group));
            tc.verifyTrue(isstring(result.group));
        end

        function test_categorical_false_same_as_default(tc)
        %   Explicit categorical=false behaves same as default.
            scifor.set_schema(["subject"]);

            tbl = table([1;2], [10;20], 'VariableNames', {'subject','value'});
            result = scifor.for_each(@(x) x, ...
                struct('x', tbl), subject=[1 2], categorical=false);

            tc.verifyFalse(iscategorical(result.subject));
        end

    end

    % =====================================================================
    % B. categorical=true with scalar outputs
    % =====================================================================

    methods (Test)

        function test_categorical_numeric_metadata(tc)
        %   Numeric metadata becomes categorical.
            scifor.set_schema(["subject"]);

            tbl = table([1;2], [10;20], 'VariableNames', {'subject','value'});
            result = scifor.for_each(@(x) x * 2, ...
                struct('x', tbl), subject=[1 2], categorical=true);

            tc.verifyTrue(iscategorical(result.subject));
            tc.verifyEqual(result.output, [20; 40]);
        end

        function test_categorical_string_metadata(tc)
        %   String metadata becomes categorical.
            scifor.set_schema(["group"]);

            result = scifor.for_each(@() 42, struct(), ...
                group=["ctrl" "exp"], categorical=true);

            tc.verifyTrue(iscategorical(result.group));
            tc.verifyEqual(categories(result.group), {'ctrl'; 'exp'});
        end

        function test_categorical_two_metadata_keys(tc)
        %   Both metadata columns become categorical.
            scifor.set_schema(["subject", "session"]);

            tbl = table([1;1;2;2], ["A";"B";"A";"B"], [10;20;30;40], ...
                'VariableNames', ["subject","session","value"]);
            result = scifor.for_each(@(x) x, ...
                struct('x', tbl), ...
                subject=[1 2], session=["A" "B"], categorical=true);

            tc.verifyTrue(iscategorical(result.subject));
            tc.verifyTrue(iscategorical(result.session));
            tc.verifyEqual(height(result), 4);
        end

        function test_categorical_does_not_affect_output_column(tc)
        %   The 'output' data column should NOT become categorical.
            scifor.set_schema(["subject"]);

            tbl = table([1;2], [10;20], 'VariableNames', {'subject','value'});
            result = scifor.for_each(@(x) x, ...
                struct('x', tbl), subject=[1 2], categorical=true);

            tc.verifyFalse(iscategorical(result.output));
        end

    end

    % =====================================================================
    % C. categorical=true with table outputs
    % =====================================================================

    methods (Test)

        function test_categorical_table_output(tc)
        %   Table output with categorical metadata: metadata is categorical,
        %   data columns are not.
            scifor.set_schema(["subject"]);

            result = scifor.for_each( ...
                @() table([1.0; 2.0], ["a"; "b"], 'VariableNames', {'num','str'}), ...
                struct(), subject=[1 2], categorical=true);

            tc.verifyTrue(iscategorical(result.subject));
            tc.verifyFalse(iscategorical(result.num));
            tc.verifyFalse(iscategorical(result.str));
            tc.verifyEqual(height(result), 4);
        end

        function test_categorical_table_output_metadata_replicated(tc)
        %   Replicated metadata in table output is categorical.
            scifor.set_schema(["subject"]);

            result = scifor.for_each( ...
                @() table([10; 20; 30], 'VariableNames', {'val'}), ...
                struct(), subject=[1 2], categorical=true);

            tc.verifyTrue(iscategorical(result.subject));
            tc.verifyEqual(height(result), 6);
        end

    end

    % =====================================================================
    % D. categorical=true with multiple outputs
    % =====================================================================

    methods (Test)

        function test_categorical_multiple_outputs(tc)
        %   Both output tables get categorical metadata.
            scifor.set_schema(["subject"]);

            tbl = table([1;2], [10;20], 'VariableNames', {'subject','value'});
            [r1, r2] = scifor.for_each(@(x) deal(x*2, x+1), ...
                struct('x', tbl), subject=[1 2], categorical=true);

            tc.verifyTrue(iscategorical(r1.subject));
            tc.verifyTrue(iscategorical(r2.subject));
            tc.verifyFalse(iscategorical(r1.output));
            tc.verifyFalse(iscategorical(r2.output));
        end

    end

    % =====================================================================
    % E. Interactions with other features
    % =====================================================================

    methods (Test)

        function test_categorical_with_distribute(tc)
        %   categorical + distribute: metadata columns are categorical.
            scifor.set_schema(["subject", "trial"]);

            result = scifor.for_each( ...
                @() [100; 200; 300], struct(), ...
                subject=[1 2], distribute=true, categorical=true);

            tc.verifyTrue(iscategorical(result.subject));
            tc.verifyTrue(iscategorical(result.trial));
        end

        function test_categorical_with_output_names(tc)
        %   categorical + output_names: metadata is categorical, named
        %   output column is not.
            scifor.set_schema(["subject"]);

            tbl = table([1;2], [10;20], 'VariableNames', {'subject','value'});
            result = scifor.for_each(@(x) x, ...
                struct('x', tbl), subject=[1 2], ...
                categorical=true, output_names={"result"});

            tc.verifyTrue(iscategorical(result.subject));
            tc.verifyTrue(ismember('result', result.Properties.VariableNames));
            tc.verifyFalse(iscategorical(result.result));
        end

    end

    % =====================================================================
    % F. Categorical schema-key columns as INPUT (regression 2026-07-13)
    %
    %   categorical erases whether a column's source values were numeric or
    %   string. Resolving key=[] from a categorical column must recover
    %   numeric identity when every label is a canonical numeric spelling
    %   ("1" -> 1), and must keep labels verbatim as strings otherwise
    %   (zero-padded "01" stays "01"). Regression: numeric keys came back as
    %   lexically-sorted strings ("10" < "2"), changing schema-key identity.
    % =====================================================================

    methods (Test)

        function test_categorical_numeric_key_input_recovers_numeric(tc)
        %   key=[] on a numeric-backed categorical column: values come back
        %   numeric, in numeric (not lexical) order.
            scifor.set_schema(["subject"]);

            tbl = table(categorical([1;2;10]), [10;20;30], ...
                'VariableNames', {'subject','value'});
            result = scifor.for_each(@(x) x, ...
                struct('x', tbl), subject=[]);

            tc.verifyTrue(isnumeric(result.subject));
            tc.verifyEqual(result.subject, [1;2;10]);  % lexical would be 1,10,2
            tc.verifyEqual(result.output, [10;20;30]);
        end

        function test_categorical_zero_padded_key_input_stays_string(tc)
        %   Zero-padded labels are not canonical numeric spellings: they stay
        %   strings verbatim — spelling is identity for undeclared keys.
            scifor.set_schema(["trial"]);

            tbl = table(categorical(["01";"02";"10"]), [1;2;3], ...
                'VariableNames', {'trial','value'});
            result = scifor.for_each(@(x) x, ...
                struct('x', tbl), trial=[]);

            tc.verifyTrue(isstring(result.trial));
            tc.verifyEqual(result.trial, ["01";"02";"10"]);
            tc.verifyEqual(result.output, [1;2;3]);
        end

        function test_categorical_mixed_padding_key_input_stays_string(tc)
        %   "1" and "01" are distinct identities; one non-canonical label
        %   keeps the whole key as strings (no partial conversion).
            scifor.set_schema(["trial"]);

            tbl = table(categorical(["1";"01"]), [1;2], ...
                'VariableNames', {'trial','value'});
            result = scifor.for_each(@(x) x, ...
                struct('x', tbl), trial=[]);

            tc.verifyTrue(isstring(result.trial));
            tc.verifyEqual(height(result), 2);
            tc.verifyEqual(sort(result.trial), ["01";"1"]);
        end

        function test_categorical_nonnumeric_key_input_stays_string(tc)
        %   Plain text labels stay strings.
            scifor.set_schema(["group"]);

            tbl = table(categorical(["ctrl";"exp"]), [1;2], ...
                'VariableNames', {'group','value'});
            result = scifor.for_each(@(x) x, ...
                struct('x', tbl), group=[]);

            tc.verifyTrue(isstring(result.group));
            tc.verifyEqual(result.group, ["ctrl";"exp"]);
        end

        function test_categorical_noninteger_key_input_recovers_numeric(tc)
        %   Non-integer canonical spellings ("1.5") also round-trip.
            scifor.set_schema(["level"]);

            tbl = table(categorical([0.5;1.5]), [1;2], ...
                'VariableNames', {'level','value'});
            result = scifor.for_each(@(x) x, ...
                struct('x', tbl), level=[]);

            tc.verifyTrue(isnumeric(result.level));
            tc.verifyEqual(result.level, [0.5;1.5]);
        end

        function test_categorical_output_roundtrips_to_numeric_keys(tc)
        %   categorical=true output fed back into for_each: numeric key
        %   identity survives the round trip.
            scifor.set_schema(["subject"]);

            tbl = table([1;2], [10;20], 'VariableNames', {'subject','value'});
            r1 = scifor.for_each(@(x) x, ...
                struct('x', tbl), subject=[1 2], categorical=true);
            tc.verifyTrue(iscategorical(r1.subject));

            r2 = scifor.for_each(@(x) x + 1, ...
                struct('x', r1), subject=[]);

            tc.verifyTrue(isnumeric(r2.subject));
            tc.verifyEqual(r2.subject, [1;2]);
            tc.verifyEqual(r2.output, [11;21]);
        end

        function test_categorical_two_keys_nested_struct_output(tc)
        %   Mirrors the field regression: two categorical schema keys,
        %   ColumnSelection input, struct outputs (nested mode). Keys must
        %   come back numeric and in numeric order.
            scifor.set_schema(["FileNum", "CycleNum"]);

            tbl = table( ...
                categorical([1;1;2]), categorical([2;10;3]), ...
                {struct('a', 1); struct('a', 2); struct('a', 3)}, ...
                'VariableNames', {'FileNum', 'CycleNum', 'Seg'});
            result = scifor.for_each(@(s) s, ...
                struct('tableIn', scifor.ColumnSelection(tbl, 'Seg')), ...
                output_names={'Seg_Out'}, FileNum=[], CycleNum=[]);

            tc.verifyTrue(isnumeric(result.FileNum));
            tc.verifyTrue(isnumeric(result.CycleNum));
            % Combos iterate CycleNum in numeric order [2 3 10]; only the
            % three (FileNum, CycleNum) pairs with data produce rows.
            tc.verifyEqual(result.FileNum, [1;1;2]);
            tc.verifyEqual(result.CycleNum, [2;10;3]);
            tc.verifyEqual([result.Seg_Out.a]', [1;2;3]);
        end

    end
end
