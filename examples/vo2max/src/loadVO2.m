function data = loadVO2(filepath)
% LOADVO2 Read one breath-by-breath CPET file into a table.
%
%   data = loadVO2(filepath) reads the CSV at FILEPATH, which holds one row
%   per breath with the columns "time (sec)" and "vo2 (mL/kg/min)" (see
%   examples/vo2max/data/SS01/SS01_01_CPET.csv).
%
%   The returned table has two double columns, renamed to valid MATLAB
%   identifiers with the units carried in the table's VariableUnits:
%       time - cumulative time of the breath, sec
%       vo2  - oxygen uptake for that breath, mL/kg/min

    arguments
        filepath (1, :) char
    end

    if ~isfile(filepath)
        error('loadVO2:FileNotFound', 'No CPET file at "%s".', filepath);
    end

    % Preserve the header verbatim so the units-bearing names survive the
    % read; they are checked below and then replaced with clean identifiers.
    opts = detectImportOptions(filepath, 'VariableNamingRule', 'preserve');
    opts = setvartype(opts, opts.VariableNames, 'double');
    data = readtable(filepath, opts);

    expectedNames = {'time (sec)', 'vo2 (mL/kg/min)'};
    if ~isequal(data.Properties.VariableNames, expectedNames)
        error('loadVO2:UnexpectedColumns', ...
            'Expected columns {%s} in "%s", found {%s}.', ...
            strjoin(expectedNames, ', '), filepath, ...
            strjoin(data.Properties.VariableNames, ', '));
    end

    data.Properties.VariableNames = {'time', 'vo2'};
    data.Properties.VariableUnits = {'sec', 'mL/kg/min'};
    data.Properties.Description = filepath;
end
