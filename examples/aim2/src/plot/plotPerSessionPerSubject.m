function [a] = plotPerSessionPerSubject(dataTable, colName, savePath)

%% PURPOSE: PLOT VALUES PER SESSION, PER SUBJECT
% Inputs:
% dataTable: Table with all the data across all subjects
% colName: The table column name
% savePath: Where to save the figure to

%% Extract string values from nested cells
subjects = dataTable.subject;
sessions = dataTable.session;

a = NaN;

% Unwrap StepLengths
data = dataTable.(colName);

%% Define unique sessions and subjects
uniqueSubjects = unique(subjects,'stable');
sessionOrder = {'BL', 'TX4', 'TX7', 'TX10', 'MID24', 'TX13', 'TX16', 'TX19', 'TX22', 'POST24', 'MO1FU', 'MO3FU'};
uniqueSessions = sessionOrder(ismember(sessionOrder, unique(sessions)));

nSessions  = numel(uniqueSessions);
nSubjects  = numel(uniqueSubjects);

% Assign a color per subject
cmap = lines(nSubjects);  % or use 'parula', 'hsv', etc.

%% Compute mean & std per subject x session
meanMat = NaN(nSubjects, nSessions);
stdMat  = NaN(nSubjects, nSessions);

isBL = dataTable.session == "BL";

data(data==0 & ~isBL) = NaN;

for si = 1:nSubjects
    for se = 1:nSessions
        idx = strcmp(subjects, uniqueSubjects{si}) & ...
              strcmp(sessions, uniqueSessions{se});
        vals = data(idx);
        if ~isempty(vals)
            meanMat(si, se) = mean(vals, 'omitnan');
            stdMat(si, se)  = std(vals,  'omitnan');
        end
    end
end

%% Plot
figure('Color', 'w', 'Position', [100 100, 900, 550]);
hold on;

% Small x-jitter so overlapping subjects are visible
jitterWidth = 0.15;
offsets = linspace(-jitterWidth * (nSubjects-1)/2, ...
                    jitterWidth * (nSubjects-1)/2, nSubjects);

hHandles = gobjects(nSubjects, 1);

for si = 1:nSubjects
    xPos = (1:nSessions) + offsets(si);
    color = cmap(si, :);

    % Individual data points (faint)
    for se = 1:nSessions
        idx = strcmp(subjects, uniqueSubjects{si}) & ...
              strcmp(sessions, uniqueSessions{se});
        vals = data(idx);
        if ~isempty(vals)
            scatter(repmat(xPos(se), size(vals)), vals, 25, ...
                color, 'filled', 'MarkerFaceAlpha', 0.25, 'HandleVisibility', 'off');
        end
    end

    % Mean ± SD
    hHandles(si) = errorbar(xPos, meanMat(si,:), stdMat(si,:), ...
        'o', ...
        'Color',           color, ...
        'MarkerFaceColor', color, ...
        'MarkerSize',      7, ...
        'LineWidth',       1.5, ...
        'CapSize',         6);
    hHandles(si).DisplayName = uniqueSubjects{si};

    plot(xPos, meanMat(si,:), 'Color', color, 'LineWidth', 1.5);

end

%% Formatting
set(gca, ...
    'XTick',          1:nSessions, ...
    'XTickLabel',     uniqueSessions, ...
    'XTickLabelRotation', 0, ...
    'FontSize',       11, ...
    'XLim',           [0.5, nSessions + 0.5]);

xlabel('Session',         'FontSize', 13);
ylabel(colName, 'FontSize', 13,'Interpreter','None');
title([colName ' by Session and Subject (Mean ± SD)'], 'FontSize', 14,'Interpreter','none');
legend(hHandles, 'Location', 'best', 'FontSize', 10);
box off;
hold off;