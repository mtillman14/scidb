function [redcapTable] = loadFunctionalOutcomesREDCapReport(reportPath)

%% PURPOSE: LOAD THE FUNCTIONAL OUTCOMES REPORT DATA (FROM ASSESSMENT DAYS ONLY)
% Inputs:
% reportPath: The path to the report
%
% Outputs:
% redcapTable: The table with the loaded functional outcomes

%% Load table
rawTable = readtable(reportPath);

%% Remove invalid record_ids
record_id_pattern = '^SS\d{2}';
record_ids = rawTable.record_id;
valid_record_ids_idx = cellfun(@(x) ~isempty(regexp(x, record_id_pattern, 'once')), record_ids);
validTable = rawTable(valid_record_ids_idx,:);

colsToDrop = {'redcap_event_name', 'redcap_repeat_instrument', 'redcap_repeat_instance'};
validTable = removevars(validTable, colsToDrop);

%% Rename variables
validTable.ssv_speed_mps = validTable.ssv;
validTable.ssv = [];
validTable.fv_speed_mps = validTable.fv;
validTable.fv = [];
validTable.trial1_dual_task_tug = validTable.trial1_dt;
validTable.trial1_dt = [];
validTable.trial2_dual_task_tug = validTable.trial2_dt;
validTable.trial2_dt = [];
validTable.average_time_dual_task_tug = validTable.avgtime_dt;
validTable.avgtime_dt = [];
validTable.num_s_words = validTable.dual_task1;
validTable.dual_task1 = [];
validTable.num_p_words = validTable.dual_task2;
validTable.dual_task2 = [];

%% Make categorical columns
redcapTable = validTable;
redcapTable.subject = categorical(redcapTable.record_id);
redcapTable.record_id = [];
redcapTable.visit = categorical(redcapTable.visit);
redcapTable = movevars(redcapTable, 'subject','Before','visit');

%% Remove missing visits
isMissingIdx = ismissing(redcapTable.visit);
redcapTable(isMissingIdx,:) = [];

%% Change how the average 10MWT (SSV & FV) is computed to handle NaN
for i = 1:height(redcapTable)
    ssv1 = redcapTable.ssv1_time(i);
    ssv2 = redcapTable.ssv2_time(i);
    ssv3 = redcapTable.ssv3_time(i);
    avg_ssv = mean([ssv1, ssv2, ssv3], 2, 'omitnan');
    redcapTable.ssv_avgtime(i) = avg_ssv;

    fv1 = redcapTable.fv1_time(i);
    fv2 = redcapTable.fv2_time(i);
    fv3 = redcapTable.fv3_time(i);
    avg_fv = mean([fv1, fv2, fv3], 2, 'omitnan');
    redcapTable.fv_avgtime(i) = avg_fv;
end

%% Change the speed to use the new average time.
redcapTable.ssv_speed_mps = 10 ./ redcapTable.ssv_avgtime;
redcapTable.fv_speed_mps = 10 ./ redcapTable.fv_avgtime;