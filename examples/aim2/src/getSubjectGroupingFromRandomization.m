function [subjGroupTable] = getSubjectGroupingFromRandomization(includeWithdrawn)

%% PURPOSE: GET WHICH SUBJECTS ARE IN WHICH GROUPS FROM THE RANDOMIZATION EXCEL
%
% Inputs:
% includeWithdrawn: boolean to indicate whether to include withdrawn
% subjects (default: false)
%
% Outputs:
% subjGroupTable: Columns 'SubjectID' and 'Intervention' map each subject
% to their randomization group.

if nargin==0
    includeWithdrawn = false;
end

randomizationPath = "Y:\Spinal Stim_Stroke R01\AIM 2\Administrative\Randomization.xlsx";
randomizationTable = readtable(randomizationPath);

emptySubjectIDIdx = cellfun(@isempty, randomizationTable.SubjectID);
withdrawnIdx = strcmp(randomizationTable.Notes, 'Withdrawn');

if includeWithdrawn
    withdrawnIdx = true(size(withdrawnIdx));
end

%% Remove unneeded rows (empty subjects, and possibly withdrawn subjects)
subjGroupTable = randomizationTable(~emptySubjectIDIdx & ~withdrawnIdx, :);

%% Remove unneeded variables
subjGroupTable = removevars(subjGroupTable, {'Var4', 'SHAM_0', 'Notes'});

%% Convert intervention to strings
ints = strings(size(subjGroupTable.Intervention));
ints(subjGroupTable.Intervention==0) = "SHAM";
ints(subjGroupTable.Intervention==1) = "STIM";
subjGroupTable.Intervention = categorical(ints);

%% Convert subjects to categorical string array
subjGroupTable.SubjectID = categorical(string(subjGroupTable.SubjectID));

subjGroupTable = sortrows(subjGroupTable, 'SubjectID');