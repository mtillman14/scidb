function [] = plotTrainingVariablesOverTimeOneSubject(reportTable, subject, overlap, trainingVariable)

%% PURPOSE: PLOT THE CONTINUOUS TRAINING VARIABLE ('StimIntensities' OR 'TreadmillSpeeds' FOR EACH MINUTE FOR EACH TX SESSION
% Inputs:
% reportTable: The table containing all stim intensities and treadmill speeds for all subjects
% subject: The subject of interest to plot
% overlap: boolean to indicate whether each tx's line should overlap
% trainingVariable: Variable of interest to plot ('stim' or 'tread')
%
%       'stim'  : plot stimulation intensities of a session across all sessions
%       'tread' : plot treadmill speeds of a session across all sessions
%
% Outputs:
% fig: The generated figure

if ~exist('overlap','var')
    overlap = true;
end

fig = figure('Name', subject);
ax = axes(fig);
hold(ax, 'on');

subjectRowsIdx = ismember(reportTable.Subject, subject);
subjectTable = reportTable(subjectRowsIdx,:);
numRowsOneSubject = height(subjectTable);
p = gobjects(numRowsOneSubject,1);
sessionLabels = cell(size(p));
txTicks = NaN(numRowsOneSubject,1);

% Choose variable & labels
if strcmp(trainingVariable,'stim')
    variable = subjectTable.StimIntensities;
    yLabelStr = 'Stimulation Intensity (mA)';
    titleStr = [subject ' TX Stimulation Intensities'];
elseif strcmp(trainingVariable,'tread')
    variable = subjectTable.TreadmillSpeeds;
    yLabelStr = 'Treadmill Speed (m/s)';
    titleStr = [subject ' TX Treadmill Speeds'];
else
    disp('You must specify which variable to plot: stim or tread');
    return;
end


% Plot variable over sessions
for i = 1:numRowsOneSubject
    data = variable{i};
    xOverlap = 0:length(data)-1;
    x = xOverlap;
    if ~overlap
        x = x + 45*(i-1);
    end
    txTicks(i) = mean(x);
    if mod(i,2) == 1
        color = 'k';
    else
        color = 'b';
    end
    p(i) = plot(ax, x, data, 'Color', color);
    sessionLabels{i} = ['TX' num2str(i)];
    p(i).DataTipTemplate.DataTipRows(end+1) = dataTipTextRow('Session', repmat(sessionLabels(i), size(x)));    
end

xlim([0 max(x) + 45]);
xticks(txTicks);
xticklabels(sessionLabels);

xlabel('TX sessions');
ylabel(yLabelStr);
title(titleStr);

% legend(p, sessionLabels, 'AutoUpdate', 'off');

end
 

