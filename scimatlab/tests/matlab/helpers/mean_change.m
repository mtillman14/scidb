function d = mean_change(baseline, value)
%MEAN_CHANGE  Change in a column's mean from a baseline (for for_columns zip tests).
d = mean(double(value)) - mean(double(baseline));
end
