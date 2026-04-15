 % add branch files to path
addpath(genpath(fullfile(pwd, 'Aim-1\src\overground')));
% Run from src/overground folder
configPath = 'src\overground\config_Aim2.json';
config = jsondecode(fileread(configPath));

% Path to matlab packages, downloaded from file exchange, do not change.
addpath(genpath('Y:\LabMembers\MTillman\MATLAB_FileExchange_Repository'));
  
runConfig = toml.map_to_struct(toml.read('subjects_to_run.toml'));
allSubjects = runConfig.subjects.run;



%% Iterate over each subject
doPlot = false;
for subNum = 1:length(allSubjects)
    subject = allSubjects{subNum};        
    disp(['Now running subject (' num2str(subNum) '/' num2str(length(allSubjects)) '): ' subject]);
    mainOneSubject_Aim2; % Run the main pipeline.
end

%% Load the 10MWT REDCap report
tenMWTreportPath = "Y:\Spinal Stim_Stroke R01\AIM 2\Subject Data\REDCap Reports\SpinalStimStrokeAim2-10MWTAll_DATA_LABELS_2025-10-08_1045.csv";
tenMWTreportTable = load10MWTREDCapReport(tenMWTreportPath);

% Define relative folder
outDir = fullfile('..','..','SavedOutcomesAim2','Redcap');  % go up 2 levels from src/overground

% Make sure folder exists
if ~exist(outDir, 'dir')
    mkdir(outDir);
end

% Define output file name
outFile = fullfile(outDir, 'tenMWTreportTable.csv');

% Write table
writetable(tenMWTreportTable, outFile);

%% Plot each subject
allSubjectsPlot = runConfig.subjects.plot;
for subNum = 1:length(allSubjectsPlot)
    subject = allSubjectsPlot{subNum};
    loadPath = fullfile(config.PATHS.ROOT_SAVE, subject, [subject '_Overground_EMG_Kinematics.mat']);
    load(loadPath, 'matchedCycleTable');
    % Plot each gait cycle's filtered data, time normalized (for EMG, scaled to max EMG) and each gait cycle of one condition plotted on top of each other.
    baseSavePath = fullfile(config.PATHS.PLOTS.ROOT, config.PATHS.PLOTS.FILTERED_TIME_NORMALIZED);
    baseSavePathEMG = fullfile(baseSavePath, 'EMG');
    baseSavePathXSENS = fullfile(baseSavePath, 'Joint Angles');
    % plotAllTrials(matchedCycleTable, 'Time-Normalized Non-Normalized EMG', baseSavePathEMG, 'Delsys_TimeNormalized'); 
    plotAllTrials(matchedCycleTable, 'Time-Normalized Scaled EMG', baseSavePathEMG, 'Delsys_Normalized_TimeNormalized'); 
    plotAllTrials(matchedCycleTable, 'Time-Normalized Joint Angles', baseSavePathXSENS, 'XSENS_TimeNormalized');
end

%% Load the cycleTable and matchedCycleTable from all subjects
configPath = 'src\overground\config_Aim2.json';
config = jsondecode(fileread(configPath));
categoricalCols = {'Subject','Intervention','Speed','Trial','Cycle','StartFoot'};
cycleTableAll = readtable(config.PATHS.ALL_DATA_CSV.UNMATCHED);
matchedCycleTableAll = readtable(config.PATHS.ALL_DATA_CSV.MATCHED);
for i = 1:length(categoricalCols)
    cycleTableAll.(categoricalCols{i}) = categorical(cycleTableAll.(categoricalCols{i}));
    matchedCycleTableAll.(categoricalCols{i}) = categorical(matchedCycleTableAll.(categoricalCols{i}));
end

%% Load the trialTable from all subjects
trialTableCategoricalCols = {'Subject','Intervention','Speed','Trial'};
trialTableAll = readtable(config.PATHS.ALL_DATA_CSV.TRIAL);
for i = 1:length(trialTableCategoricalCols)
    trialTableAll.(trialTableCategoricalCols{i}) = categorical(trialTableAll.(trialTableCategoricalCols{i}));
end

%% Replace 'StartFoot' with 'Side'
categoricalCols = {'Subject','Intervention','Speed','Trial','Cycle','Side'};
if ismember('StartFoot', cycleTableAll.Properties.VariableNames)
    cycleTableAll.Side = cycleTableAll.StartFoot;
    cycleTableAll = removevars(cycleTableAll, 'StartFoot');
end
if ismember('StartFoot', matchedCycleTableAll.Properties.VariableNames)
    matchedCycleTableAll.Side = matchedCycleTableAll.StartFoot;
    matchedCycleTableAll = removevars(matchedCycleTableAll, 'StartFoot');
end
cycleTableAll = movevars(cycleTableAll,'Side','After','Cycle');
matchedCycleTableAll = movevars(matchedCycleTableAll,'Side','After','Cycle');

%% Calculate symmetries
formulaNum = 6; % computing Sym using the original equation * 100
[colNamesL, colNamesR] = getLRColNames(cycleTableAll);
% Cycle table
cycleTableContraRemoved_NoGR = removeContralateralSideColumns(cycleTableAll, colNamesL, colNamesR);
grVars = cycleTableAll.Properties.VariableNames(contains(cycleTableAll.Properties.VariableNames,'_GR'));
grTable = removevars(cycleTableAll, ~ismember(cycleTableAll.Properties.VariableNames, [grVars, categoricalCols]));
cycleTableContraRemoved = addToTable(cycleTableContraRemoved_NoGR, grTable);
scalarColumnNames = getScalarColumnNames(cycleTableContraRemoved);
allColumnNames = cycleTableContraRemoved.Properties.VariableNames;
nonscalarColumnNames = allColumnNames(~ismember(allColumnNames, [scalarColumnNames; categoricalCols']));
cycleTableContraRemovedScalarColumns = removevars(cycleTableContraRemoved, nonscalarColumnNames);
% Compute the symmetry values
nonSubsetCatVars = {'Cycle','Side'};
lrSidesCycleSymTable = calculateSymmetryAll(cycleTableContraRemovedScalarColumns, '_Sym', formulaNum, nonSubsetCatVars);
categoricalColsTrial = {'Subject','Intervention','Speed','Trial'};
trialTableAllSym = trialTableAll;
cycleTableAllSym = cycleTableContraRemovedScalarColumns;
matchedCycleTableAllSym = addToTable(matchedCycleTableAll, lrSidesCycleSymTable);

%% Adjust intervention name to mapped names
interventions = config.INTERVENTION_FOLDERS;
mapped_interventions = interventions;
intervention_map = containers.Map(interventions, mapped_interventions);
for i = 1:height(trialTableAllSym)
    trialTableAllSym.Intervention(i) = intervention_map(string(trialTableAllSym.Intervention(i)));
end
for i = 1:height(cycleTableAllSym)
    cycleTableAllSym.Intervention(i) = intervention_map(string(cycleTableAllSym.Intervention(i)));
end
for i = 1:height(matchedCycleTableAllSym)
    matchedCycleTableAllSym.Intervention(i) = intervention_map(string(matchedCycleTableAllSym.Intervention(i)));
end

%% Adjust the L & R sides to "U" and "A" for unaffected and affected sides
subjectDemographicsPath = "Y:\Spinal Stim_Stroke R01\AIM 2\Subject Data\Subject Demographics Aim 2.xlsx";
demographics = readExcelFileOneSheet(subjectDemographicsPath, 'Subject', 'Sheet1');
colNames = {'Subject', 'PareticSide'};
inputTableSideCol = 'Side';
demographicsSideCol = 'PareticSide';
allColNames = demographics.Properties.VariableNames;
colNamesIdx = ismember(allColNames, colNames);
reducedDemographics = unique(demographics(:, colNamesIdx), 'rows');
% Omit the subjects from demographics that are not in the data tables
subjectIdx = ismember(string(reducedDemographics.Subject), string(cycleTableAll.Subject));
reducedDemographics(~subjectIdx,:) = [];
trialTableAllUA = trialTableAllSym;
cycleTableAllUA = convertLeftRightSideToAffectedUnaffected(cycleTableAllSym, reducedDemographics, inputTableSideCol, demographicsSideCol);
matchedCycleTableAllUA = convertLeftRightSideToAffectedUnaffected(matchedCycleTableAllSym, reducedDemographics, inputTableSideCol, demographicsSideCol);

%% Save the unaffected and affected side tables
tablesPathPrefixMergedUA = "../../SavedOutcomesAim2/Overground_EMG_Kinematics/1_FromMATLAB_Sym";
writetable(trialTableAllUA, fullfile(tablesPathPrefixMergedUA, 'trialTableAll.csv'));
writetable(matchedCycleTableAllUA, fullfile(tablesPathPrefixMergedUA, 'matchedCycles.csv'));
writetable(cycleTableAllUA, fullfile(tablesPathPrefixMergedUA, 'unmatchedCycles.csv'));