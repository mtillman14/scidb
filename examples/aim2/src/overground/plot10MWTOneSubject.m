function [] = plot10MWTOneSubject(reportTable, subject, speed, column)

%% PURPOSE: PLOT THE 10MWT TIMES FOR ONE SUBJECT
% Inputs:
% reportTable: Table containing all 10MWT times
% subject: The subject to plot the times for

if ~exist('speed','var')
    speed = 'FV';
end

if ~exist('column','var')
    column = 'Seconds';
end

if strcmpi(column, 's')
    column = 'Time_Seconds';
elseif strcmpi(column, 'mps')
    column = 'Speed_MPS';
else
    error('Wrong column type');
end

subjectRowsIdx = ismember(reportTable.Subject, subject);
subjectRows = reportTable(subjectRowsIdx,:);
colName = ['Average' speed column];

x = 1:height(subjectRows);
xLabels = subjectRows.Session;

scatter(x, subjectRows.(colName), 'filled');
xticks(x);
xticklabels(xLabels);
title([subject ' 10MWT ' speed]);
ylabel(['Average ' column],'Interpreter','none');

blIdx = ismember(subjectRows.Session, {'BL'});
blValue = subjectRows.(colName)(blIdx);
% https://www.sralab.org/rehabilitation-measures/10-meter-walk-test
smallMCID = 0.06;
substantialMCID = 0.13;
yline(blValue + smallMCID,'b');
yline(blValue + substantialMCID,'g');