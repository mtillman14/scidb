classdef TestPathInput < matlab.unittest.TestCase
%TESTPATHINPUT  Integration tests for scifor.PathInput.

    properties
        tmp_dir  string  % Temp directory for regex tests
    end

    methods (TestClassSetup)
        function addPaths(~)
            this_dir = fileparts(mfilename('fullpath'));
            run(fullfile(this_dir, 'setup_paths.m'));
        end
    end

    methods (TestMethodSetup)
        function createTempDir(testCase)
            testCase.tmp_dir = string(tempname);
            mkdir(testCase.tmp_dir);
            % Create subdirectory with test files for regex tests
            sub_dir = fullfile(testCase.tmp_dir, '1');
            mkdir(sub_dir);
            % Zero-padded files
            fclose(fopen(fullfile(sub_dir, '6mwt-001.xlsx'), 'w'));
            fclose(fopen(fullfile(sub_dir, '6mwt-010.xlsx'), 'w'));
            fclose(fopen(fullfile(sub_dir, '6mwt-100.xlsx'), 'w'));
            % Duplicate-match files
            dup_dir = fullfile(testCase.tmp_dir, 'dup');
            mkdir(dup_dir);
            fclose(fopen(fullfile(dup_dir, 'data_v1.csv'), 'w'));
            fclose(fopen(fullfile(dup_dir, 'data_v2.csv'), 'w'));
            % Single exact file
            exact_dir = fullfile(testCase.tmp_dir, 'exact');
            mkdir(exact_dir);
            fclose(fopen(fullfile(exact_dir, 'report.txt'), 'w'));
        end
    end

    methods (TestMethodTeardown)
        function removeTempDir(testCase)
            if isfolder(testCase.tmp_dir)
                rmdir(testCase.tmp_dir, 's');
            end
        end
    end

    methods (Test)
        function test_basic_resolution(testCase)
            pi = scifor.PathInput("{subject}/data.mat", ...
                'root_folder', '/data');
            path = pi.load('subject', 1);
            expected = string(fullfile('/data', '1', 'data.mat'));
            testCase.verifyEqual(path, expected);
        end

        function test_multiple_placeholders(testCase)
            pi = scifor.PathInput("{subject}/session_{session}/trial.mat", ...
                'root_folder', '/experiment');
            path = pi.load('subject', 1, 'session', 'A');
            expected = string(fullfile('/experiment', '1', 'session_A', 'trial.mat'));
            testCase.verifyEqual(path, expected);
        end

        function test_numeric_value_in_template(testCase)
            pi = scifor.PathInput("sub{subject}_trial{trial}.mat", ...
                'root_folder', '/data');
            path = pi.load('subject', 3, 'trial', 7);
            testCase.verifyTrue(contains(path, "sub3"));
            testCase.verifyTrue(contains(path, "trial7"));
        end

        function test_string_value_in_template(testCase)
            pi = scifor.PathInput("{group}/results.csv", ...
                'root_folder', '/output');
            path = pi.load('group', 'control');
            expected = string(fullfile('/output', 'control', 'results.csv'));
            testCase.verifyEqual(path, expected);
        end

        function test_no_root_folder_uses_pwd(testCase)
            pi = scifor.PathInput("{x}/data.mat");
            path = pi.load('x', 1);
            expected = string(fullfile(pwd, '1', 'data.mat'));
            testCase.verifyEqual(path, expected);
        end

        function test_returns_string(testCase)
            pi = scifor.PathInput("{x}.mat", 'root_folder', '/data');
            path = pi.load('x', 1);
            testCase.verifyClass(path, 'string');
        end

        function test_unused_metadata_ignored(testCase)
            % Extra metadata keys not in template should not cause errors
            pi = scifor.PathInput("{subject}/data.mat", ...
                'root_folder', '/data');
            path = pi.load('subject', 1, 'session', 'A');
            expected = string(fullfile('/data', '1', 'data.mat'));
            testCase.verifyEqual(path, expected);
        end

        function test_absolute_path_in_template(testCase)
            pi = scifor.PathInput("{subject}/data.mat", ...
                'root_folder', '/absolute/root');
            path = pi.load('subject', 5);
            % Verify the path contains the root folder and resolved template
            testCase.verifyTrue(contains(path, "absolute"));
            testCase.verifyTrue(contains(path, "root"));
            testCase.verifyTrue(contains(path, "5"));
            testCase.verifyTrue(contains(path, "data.mat"));
        end

        %% Regex tests

        function test_regex_basic(testCase)
            % An exact filename used as the regex pattern should match
            pi = scifor.PathInput("exact/report\.txt", ...
                'root_folder', testCase.tmp_dir, 'regex', true);
            path = pi.load();
            expected = string(fullfile(testCase.tmp_dir, 'exact', 'report.txt'));
            testCase.verifyEqual(path, expected);
        end

        function test_regex_zero_padding(testCase)
            % Pattern with regex quantifier matches zero-padded filename
            pi = scifor.PathInput("{subject}/6mwt-0{0,2}1\.xlsx", ...
                'root_folder', testCase.tmp_dir, 'regex', true);
            path = pi.load('subject', 1);
            expected = string(fullfile(testCase.tmp_dir, '1', '6mwt-001.xlsx'));
            testCase.verifyEqual(path, expected);
        end

        function test_regex_no_match_errors(testCase)
            % Pattern that matches nothing should error
            pi = scifor.PathInput("{subject}/nonexistent.*\.xyz", ...
                'root_folder', testCase.tmp_dir, 'regex', true);
            testCase.verifyError(@() pi.load('subject', 1), ...
                'scifor:PathInput:NoMatch');
        end

        function test_regex_multiple_match_errors(testCase)
            % Pattern that matches multiple files should error
            pi = scifor.PathInput("dup/data_v\d\.csv", ...
                'root_folder', testCase.tmp_dir, 'regex', true);
            testCase.verifyError(@() pi.load(), ...
                'scifor:PathInput:MultipleMatches');
        end
    end
end
