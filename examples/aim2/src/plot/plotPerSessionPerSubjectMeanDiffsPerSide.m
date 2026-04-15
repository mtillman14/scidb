function [] = plotPerSessionPerSubjectMeanDiffsPerSide(dataTable, colName)

%% PURPOSE: PLOT DIFFERENCE VALUES PER SESSION, PER SUBJECT, U & A SIDES
% Inputs:
% dataTable: Table with all the data across all subjects
% colName: The table column name
% savePath: Where to save the figure to

subjects = dataTable.subject;

%% Define unique sessions and subjects
uniqueSubjects = unique(subjects,'stable');
nSubjects  = numel(uniqueSubjects);

% Assign a color per subject
cmap = lines(nSubjects);  % or use 'parula', 'hsv', etc.

%% Plot
figure('Color', 'w', 'Position', [100 100, 900, 550]);
hold on;

% Small x-jitter so overlapping subjects are visible
jitterWidth = 0.15;
offsets = linspace(-jitterWidth * (nSubjects-1)/2, ...
                    jitterWidth * (nSubjects-1)/2, nSubjects);

sides = unique(dataTable.Side);
lineW = 1.5;
lineWMarker = 2.5; % 1.5?
sz = 120;
for sideNum = 1:length(sides)
    side = sides(sideNum);

    % if ~ismember(side, ["U", "A"])
    %     continue;
    % end

    for si = 1:nSubjects
        subject = uniqueSubjects{si};

        sessions = dataTable.session(dataTable.subject == subject);

        sessionOrder = {'BL', 'TX4', 'TX7', 'TX10', 'MID24', 'TX13', 'TX16', 'TX19', 'TX22', 'POST24', 'MO1FU', 'MO3FU'};
        uniqueSessions = sessionOrder(ismember(sessionOrder, unique(sessions)));
        
        nSessions  = numel(uniqueSessions);

        color = cmap(si, :);

        scatter(offsets(si), 0, sz, color,'LineWidth', lineWMarker);

        for se = 1:nSessions
            session = uniqueSessions{se};
            rowIdx = ismember(dataTable.subject, subject) & ismember(dataTable.session, session) & ismember(dataTable.Side, side);            
            row = dataTable(rowIdx,:);
            p = row.PValue;
            val = row.(colName);
            xPos = se+offsets(si);

            if side == "A"
                mrk = "o";
            elseif side == "U"
                mrk = "o";
            else
                mrk = "o";
            end

            if p < 0.05
                scatter(xPos, val, sz, color, 'filled', 'Marker',mrk, 'LineWidth', lineWMarker);
            else
                scatter(xPos, val, sz, color, 'Marker',mrk, 'LineWidth', lineWMarker);
            end

            if side == "A"
                lineStyle = "-";
            elseif side == "U"
                lineStyle = "--";
            else
                lineStyle = "-";
            end

            if se < length(uniqueSessions)                
                nextRowIdx = ismember(dataTable.subject, subject) & ismember(dataTable.session, uniqueSessions{se+1}) & ismember(dataTable.Side, side);
                nextRow = dataTable(nextRowIdx,:);
                nextVal = nextRow.(colName);
                plot([xPos se+1+offsets(si)], [val, nextVal], 'LineStyle', lineStyle, 'Color', color, 'LineWidth', lineW);
            end
            if se == 1
                plot([offsets(si) xPos], [0 val], 'LineStyle', lineStyle, 'Color', color, 'LineWidth', lineW);
            end
        end
    end
end

set(gca, ...
    'XTick', 0:11, ...
    'XTickLabel', sessionOrder, ...
    'XTickLabelRotation', 0, ...
    'FontSize', 11, ...
    'XLim', [-0.5, 12.5] ...
);

xlabel('Session', 'FontSize', 13);
ylabel(colName,'FontSize',13,'Interpreter','None');
title([colName ' by Session and Subject (Mean Difference)'], 'FontSize',14,'Interpreter','none');

