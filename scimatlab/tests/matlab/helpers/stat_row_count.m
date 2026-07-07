function r = stat_row_count(df, filename)
%STAT_ROW_COUNT  Endpoint test helper: stat_ prefixed, returns a result struct.
%   In draft mode the framework passes filename=[] (report writers should
%   skip their artifact); in record mode it is the resolved report path.
    r = struct();
    r.n = height(df);
    r.date = '2026-07-07 00:00:00';   % must be STRIPPED by normalization
    if ~isempty(filename)
        fig = figure('Visible', 'off');
        exportgraphics(fig, char(string(filename)));
        close(fig);
    end
end
