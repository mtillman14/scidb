classdef TestSciforForEachSchemaKeys < matlab.unittest.TestCase
%TESTSCIFORFOREACHSCHEMAKEYS  Tests for scifor.for_each's schema_keys= option.
%
%   schema_keys= is structural sugar for "iterate over these schema key
%   names" — equivalent to passing key=[] for each one by hand, then
%   letting the existing empty-array resolution (distinct_values_from_inputs)
%   fill in the values. scidb.for_each's schema_keys= (DB-backed) reuses the
%   same expansion logic on the MATLAB side too (+scidb/for_each.m forwards
%   to the Python bridge, which calls scifor.expand_schema_keys()).

    methods (TestMethodSetup)
        function resetSchema(~)
            scifor.set_schema(string.empty(1, 0));
        end
    end

    methods (Test)

        function test_schema_keys_resolves_from_table(tc)
        %   schema_keys=[...] auto-resolves each key's values by scanning
        %   inputs, identical to passing key=[] explicitly.
            tbl = table([1;1;2;2], ["A";"B";"A";"B"], [10;20;30;40], ...
                'VariableNames', {'pass','Cycle','value'});

            result = scifor.for_each(@(x) x, ...
                struct('x', tbl), ...
                schema_keys=["pass","Cycle"]);

            tc.verifyEqual(height(result), 4);
            row_1A = result(result.pass == 1 & result.Cycle == "A", :);
            tc.verifyEqual(row_1A.output, 10);
            row_2B = result(result.pass == 2 & result.Cycle == "B", :);
            tc.verifyEqual(row_2B.output, 40);
        end

        function test_schema_keys_matches_explicit_empty_lists(tc)
        %   schema_keys=["pass","Cycle"] must behave the same as
        %   pass=[], Cycle=[] (the pre-existing spelled-out form).
            tbl = table([1;1;2;2], ["A";"B";"A";"B"], [10;20;30;40], ...
                'VariableNames', {'pass','Cycle','value'});

            via_schema_keys = scifor.for_each(@(x) x, ...
                struct('x', tbl), schema_keys=["pass","Cycle"]);
            via_explicit = scifor.for_each(@(x) x, ...
                struct('x', tbl), pass=[], Cycle=[]);

            tc.verifyEqual(height(via_schema_keys), height(via_explicit));
            tc.verifyEqual(sortrows(via_schema_keys, {'pass','Cycle'}), ...
                sortrows(via_explicit, {'pass','Cycle'}));
        end

        function test_schema_keys_subset_is_aggregation(tc)
        %   Requesting fewer keys than the full schema aggregates over the
        %   rest, same as the pre-existing "extra key not in schema"
        %   behavior — a property of the underlying filtering, not
        %   something schema_keys adds.
            scifor.set_schema(["pass", "Cycle"]);
            tbl = table([1;1;2;2], ["A";"B";"A";"B"], [10;20;30;40], ...
                'VariableNames', {'pass','Cycle','value'});

            result = scifor.for_each(@(x) height(x), ...
                struct('x', tbl), ...
                as_table=true, schema_keys=["pass"]);

            % One call per "pass" value; each sees both Cycle rows (2), not 1.
            tc.verifyEqual(result.output, [2; 2]);
        end

        function test_schema_keys_conflicts_with_metadata(tc)
        %   Error when combining schema_keys with explicit metadata name-
        %   value pairs (mutual exclusivity, mirroring the Python side).
            tbl = table([1;2], [10;30], 'VariableNames', {'pass','value'});

            tc.verifyError(@() scifor.for_each(@(x) x, ...
                struct('x', tbl), schema_keys=["pass"], pass=[1 2]), ...
                'scifor:for_each');
        end

    end

end
