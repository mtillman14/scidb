function val = read_file_value(filepath)
%READ_FILE_VALUE  Read a scalar double from a text file (test helper).
%   Reading (not just naming) the file makes unresolved literal paths fail
%   the combo, mirroring the Python schema-key-type tests.
    val = str2double(strtrim(fileread(char(filepath))));
    if isnan(val)
        error('helpers:read_file_value', ...
            'File %s did not contain a scalar number.', char(filepath));
    end
end
