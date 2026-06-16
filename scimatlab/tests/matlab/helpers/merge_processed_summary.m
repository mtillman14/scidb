function y = merge_processed_summary(data)
%MERGE_PROCESSED_SUMMARY  Test fn: summarize a merged table's ProcessedSignal.
%   Returns [height(data); sum(data.ProcessedSignal)] as a column vector.
%   Used to verify, through scidb.Merge, both how many rows survived the
%   where= filter (one variant per schema-key combo, not several) and which
%   ProcessedSignal variant was selected (variants are distinguishable by
%   value: x*2 vs x*3).
    y = [height(data); sum(data.ProcessedSignal)];
end
