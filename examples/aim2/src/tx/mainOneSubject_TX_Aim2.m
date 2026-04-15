%% Created by MT 10/02/25
% The main pipeline for TX sessions in R01 Stroke Spinal Stim Aim 2 (using tables)
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%% 
% Comment this part out when running all subjects at once.
% clc;
% clearvars;
% subject = 'SS10';
% configFilePath = 'Y:\LabMembers\MTillman\GitRepos\Stroke-R01-Aim-2\src\overground\config_Aim2.json';
% config = jsondecode(fileread(configFilePath));
% disp(['Loaded configuration from: ' configFilePath]);
% doPlot = false;
% addpath(genpath('Y:\LabMembers\MTillman\GitRepos\Stroke-R01-Aim-2'));
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Get configuration
txConfig = config.TX;
intervention_folders = txConfig.INTERVENTION_FOLDERS;
intervention_field_names = txConfig.MAPPED_INTERVENTIONS;
mapped_interventions = containers.Map(intervention_folders, intervention_field_names);
gaitriteConfig = config.GAITRITE;
missingFilesPartsToCheck = config.MISSING_FILES;
regexsConfig = config.REGEXS;
regexsConfig.INTERVENTIONS = txConfig.REGEXS.INTERVENTIONS;

% Folder to load the data from.
pathsConfig = config.PATHS;
txPathsConfig = txConfig.PATHS;
subjectLoadPath = fullfile(pathsConfig.ROOT_LOAD, subject);
% Path to save the data to.
subjectSaveFolder = fullfile(pathsConfig.ROOT_SAVE, subject);
saveFileName = txPathsConfig.SAVE_FILE_NAME;
codeFolderPath = pathsConfig.CODE_FOLDER_PATH; % Folder where the code lives
addpath(genpath(pathsConfig.CODE_FOLDER_PATH));

%% Initialize outcome measure tables
trialTable = table; % Each row is one trial, all data
cycleTable = table; % Each row is one UNMATCHED gait cycle, all data
visitTable = table; % Each row is one whole session
speedInterventionTable = table; % Each row is one combination of SSV/FV & Pre/Post
cycleTableContraRemoved = table; % Each row is one UNMATCHED gait cycle, with the contralateral data removed and column names merged

%% GaitRite Load
subject_gaitrite_folder = fullfile(subjectLoadPath, gaitriteConfig.FOLDER_NAME);
gaitRiteTable = loadGaitRiteAllInterventions(gaitriteConfig, subject_gaitrite_folder, intervention_folders, mapped_interventions, regexsConfig, missingFilesPartsToCheck);

%% Distribute GaitRite vectors from the trial table to the gait cycle table.
% e.g. step/stride lengths/widths/durations/etc.
% Also include the start and end of each gait cycle and swing/stance phase
grDistributedTable = distributeGaitRiteDataToSeparateTable(gaitRiteTable);

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Add this participant's data to the CSV file of all participants' data.
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%% Merge the GaitRite and unmatched cycle tables
leadingZeroRegex = '^0+'; % Regex to remove leading zeros
T = copyCategorical(grDistributedTable);
if ismember({'GaitRiteRow'}, T.Properties.VariableNames)
    grDistributedTable.Cycle = grDistributedTable.GaitRiteRow;
    grDistributedTable = removevars(grDistributedTable, 'GaitRiteRow');
end
T = copyCategorical(grDistributedTable);
mergeVarNames = T.Properties.VariableNames(~ismember(T.Properties.VariableNames, {'StartFoot','Cycle'}));

grDistributedTable.Cycle = categorical(regexprep(string(grDistributedTable.Cycle),leadingZeroRegex,''));
grDistributedTable = movevars(grDistributedTable, 'Cycle', 'After', 'Trial');

%% Make sure the cycles maintain the proper order.
grDistributedTable.Cycle = categorical(regexprep(string(grDistributedTable.Cycle),leadingZeroRegex,''));
cycleOrder = string(1:max(str2double(string(grDistributedTable.Cycle))));
grDistributedTable.Cycle = reordercats(grDistributedTable.Cycle, cycleOrder);

%% Save the cycle table and the matched cycle table to the all data CSV file
addOneParticipantDataToAllDataCSV(grDistributedTable, txConfig.PATHS.ALL_DATA_CSV);

%% Save the structs to the participant's save folder.
subjectSavePath = fullfile(subjectSaveFolder, [subject '_' saveFileName]);
if ~isfolder(subjectSaveFolder)
    mkdir(subjectSaveFolder);
end
cycleTable = grDistributedTable;
trialTable = gaitRiteTable;
save(subjectSavePath, 'trialTable', 'cycleTable');
disp(['Saved ' subject ' tables to: ' subjectSavePath]);