function validate_csv_filename(filename)
%VALIDATE_CSV_FILENAME  Error unless filename is a single string ending in .csv.
%   Gives a clear MATLAB-native error; Python re-validates as a backstop.
    filename = string(filename);
    if ~isscalar(filename) || ~endsWith(filename, ".csv")
        error('scidb:ToCsvError', ...
            'to_csv() filename must be a single string ending with ''.csv'', got "%s".', ...
            filename);
    end
end
