function out_path = plot_self_saving(signal, filename)
%PLOT_SELF_SAVING  Endpoint test helper: saves its own figure, returns the path.
    fig = figure('Visible', 'off');
    plot(signal(:));
    exportgraphics(fig, char(string(filename)));
    close(fig);
    out_path = char(string(filename));
end
