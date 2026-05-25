classdef DummyMixed < scidb.BaseVariable
%DUMMYMIXED  Test variable: dataframe-mode storage with mixed cell types.
%   Each record's data is a 1-row MATLAB table with 54 columns: 27 scalar
%   double (DOUBLE), 25 cell-of-vector double (DOUBLE[]), 2 struct (JSON).
%   Used by TestForEachTimingInstrumentation to exercise the bulk load
%   path that the [timing] instrumentation reports against.
end
