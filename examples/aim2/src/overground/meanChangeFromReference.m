function [meanChangeMag] = meanChangeFromReference(reference, values)

%% PURPOSE: COMPUTE THE MEAN CHANGE FROM BASELINE
% Inputs:
% reference: Numeric vector of values to use as a reference
% values: Numeric vector of the other values to get the change from
%
% Outputs:
% meanChangeMag: Magnitude of the mean change

if iscell(reference)
    reference = cell2mat(reference);
end

if size(reference,2) > size(reference,1)
    reference = reference';
end

if size(values,2) > size(values,1)
    values = values';
end

if iscell(values)
    values = cell2mat(values);
end

reference(reference==0) = NaN;
values(values==0) = NaN;

refMean = mean(reference, 1, 'omitnan');

valsMean = mean(values, 1, 'omitnan');

meanChangeMag = valsMean - refMean;