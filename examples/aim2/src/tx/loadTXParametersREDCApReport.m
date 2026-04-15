function [reportTable] = loadTXParametersREDCApReport(reportPath)

%% PURPOSE: LOAD THE REDCap REPORT FOR THE TX SESSION PARAMETERS

rawTable = readtable(reportPath);

subjects = unique(rawTable.record_id, 'stable');

txArray = mapEventsTX();

reportTable = table;

allColumnNames = rawTable.Properties.VariableNames;
stimColumnsIdx = find(contains(allColumnNames, 'stim_min'));
speedColumnsIdx = find(contains(allColumnNames, 'speed_min'));

for i = 1:length(subjects)
    subject = subjects{i};
    subjectRowsIdx = ismember(rawTable.record_id, subject);
    subjectRows = rawTable(subjectRowsIdx, :);
    for subjectRowNum = 1:height(subjectRows)
        subjectRow = subjectRows(subjectRowNum,:);
        tmpTable = table;
        tmpTable.Subject = string(subject);
        curr_redcap_event_name = subjectRow.redcap_event_name{1}(18:end);
        tmpTable.TXNumber = find(ismember(txArray, curr_redcap_event_name));
        tmpTable.Date = subjectRow.training_date;
        % Build the stim intensities vector
        stimIntensities = [];
        for stimColumnNum = 1:length(stimColumnsIdx)
            stimColumnName = stimColumnsIdx(stimColumnNum);
            stimIntensities(stimColumnNum,1) = subjectRow.(stimColumnName);
        end
        tmpTable.StimIntensities = {stimIntensities};
        % Build the treadmill speeds vector
        treadmillSpeeds = [];
        for speedColumnNum = 1:length(speedColumnsIdx)
            speedColumnName = speedColumnsIdx(speedColumnNum);
            treadmillSpeeds(speedColumnNum,1) = subjectRow.(speedColumnName);
        end
        tmpTable.TreadmillSpeeds = {treadmillSpeeds};

        reportTable = [reportTable; tmpTable];
    end
end

reportTable = sortrows(reportTable, {'Subject', 'TXNumber'});