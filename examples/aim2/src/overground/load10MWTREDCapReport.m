function [reportTableOrdered] = load10MWTREDCapReport(reportPath)

%% PURPOSE: LOAD THE 10MWT REPORT FROM REDCAP
% Inputs:
% reportPath: The path to the csv file of the report
%
% Outputs:
% reportTableOrdered: The table with the report's data, ordered by subject
% and session

reportTable = table;

rawReport = readtable(reportPath);

assessmentSessionMappings = {
    'Baseline', 'BL';
    'Midpoint #1', 'MID18';
    'Midpoint #2', 'MID24';
    'Post #1', 'POST18';
    'Post #2', 'POST24'
};

trainingSessionMappings = {
    4,'TX4';
    7,'TX7';
    10,'TX10';
    13,'TX13';
    16,'TX16';
    19,'TX19';
    22,'TX22';
};

for i = 1:height(rawReport)
    row = rawReport(i,:);
    tmpTable = table;
    tmpTable.Subject = row.RecordID;
    
    sessionRaw = row.EventName;
    if contains(sessionRaw, 'Assessment')
        visitName = row.WhichAssessmentVisitIsThis_;
        mapping = assessmentSessionMappings;
        mappingFirstCol = mapping(:,1);
    else
        visitName = row.TrainingSession_;
        mapping = trainingSessionMappings;
        mappingFirstCol = cell2mat(mapping(:,1));
    end
    sessionIdx = ismember(mappingFirstCol, visitName);
   
    session = mapping{sessionIdx, 2};
    tmpTable.Session = {session};
    tmpTable.AverageSSVTime_Seconds = row.AverageSSVTime;
    tmpTable.AverageSSVSpeed_MPS = row.AverageSelfSelectedGaitSpeed;
    tmpTable.AverageFVTime_Seconds = row.AverageFVTime;
    tmpTable.AverageFVSpeed_MPS = row.AverageFastGaitSpeed;
    reportTable = [reportTable; tmpTable];
end

%% Sort the rows of each subject
sortOrder = {'BL','TX4','TX7','MID18','TX10','MID24','TX13','TX16','POST18','TX19','TX22','POST24'};
subjects = unique(reportTable.Subject,'stable');
reportTableOrdered = table;
for i = 1:length(subjects)
    subject = subjects{i};
    subjectRowsIdx = ismember(reportTable.Subject, subject);
    subjectTable = reportTable(subjectRowsIdx,:);
    for j = 1:length(sortOrder)
        rowIdx = ismember(subjectTable.Session, sortOrder(j));
        if ~any(rowIdx)
            continue;
        end
        reportTableOrdered = [reportTableOrdered; subjectTable(rowIdx,:)];
    end
end
