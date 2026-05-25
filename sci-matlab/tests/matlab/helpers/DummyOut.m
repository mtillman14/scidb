classdef DummyOut < scidb.BaseVariable
%DUMMYOUT  Test variable: scalar output for TestForEachTimingInstrumentation.
%   Each record's data is a single double, keeping the save side fast so
%   the prepare/load timing dominates the run.
end
