function [mvcTable] = loadMVCOneIntervention(delsysConfig, intervention_folder_path, intervention_field_name, regexsConfig, missingFilesPartsToCheck)

%% PURPOSE: LOAD ONE ENTIRE INTERVENTION OF MVC DATA
% Inputs:
% delsysConfig: Config struct for Delsys
% intervention_folder_path: The full path to the intervention folder
% intervention_field_name: The field name of the intervention
% regexsConfig: The config struct for the regexs
%
% Outputs:
% mvcTable: The MVC data table
%
% NOTE: Assumes that subject name, intervention name, pre/post, and speed (ssv/fv) are all present in the file name

file_extension = delsysConfig.FILE_EXTENSION;
subjects_interventions_to_fix = delsysConfig.SUBJECTS_INTERVENTIONS_TO_FIX;

% Get the mat files
generic_mat_path = fullfile(intervention_folder_path, file_extension);
mat_files = dir(generic_mat_path);
mat_file_names = {mat_files.name};

[~, idx] = sort(mat_file_names); % Ensure the trials are in order.
mat_files = mat_files(idx,:);
mat_file_names = {mat_files.name};

% Get the adicht files
generic_adicht_path = fullfile(intervention_folder_path, '*.adicht');
adicht_files = dir(generic_adicht_path);
adicht_file_names = {adicht_files.name};

[~,idx] = sort(adicht_file_names);
adicht_files = adicht_files(idx,:);
adicht_file_names = {adicht_files.name};

%% Rename/number struct fields and preprocess each file
mvcTable = table;
priorNamesNoTrial = cell(length(mat_file_names), 1);
for i = 1:length(priorNamesNoTrial)
    priorNamesNoTrial{i} = ''; % Initialize as chars
end
columnNames = delsysConfig.MVC_CATEGORICAL_COLUMNS;
for i = 1:length(mat_file_names)
    mat_file_name_with_ext = mat_file_names{i};
    % Check if the file is missing
    isMissing = checkMissing(mat_file_name_with_ext, missingFilesPartsToCheck);
    if isMissing
        continue;
    end
    periodIndex = strfind(mat_file_name_with_ext, '.');
    mat_file_name = mat_file_name_with_ext(1:periodIndex-1);
    mat_file_path = fullfile(intervention_folder_path, mat_file_name_with_ext);    
    parsedName = parseFileName(regexsConfig, mat_file_name);
    parsedName = parsedName(1:2);
    if isempty(parsedName{2})
        error(['Intervention missing from file name: ' mat_file_name_with_ext]);
    end
    subject_id = parsedName{1};
    nameNoTrial = [subject_id '_' intervention_field_name];
    priorNamesNoTrial{i} = nameNoTrial;
    trialNum = sum(ismember(priorNamesNoTrial, {nameNoTrial}));
    nameWithTrial = [nameNoTrial '_trial' num2str(trialNum)];    
    loadedData = loadDelsysEMGOneFile(mat_file_path);

    %% Hard-coded fix for EMG muscle mappings for specific subjects & interventions
    if isfield(subjects_interventions_to_fix, subject_id) && ...
        any(strcmp(intervention_field_name, subjects_interventions_to_fix.(subject_id)))
        loadedData = fixMuscleMappings(loadedData);
    end

    %% Get the muscle being tested
    splitName = strsplit(mat_file_name, '_');
    muscleName = strjoin(splitName(4:end), '_');
    parsedName{3} = muscleName;

    tmpTable = table;
    for colNum = 1:length(parsedName)
        try
            tmpTable.(columnNames{colNum}) = string(parsedName{colNum});
            tmpTable.(columnNames{colNum}) = categorical(tmpTable.(columnNames{colNum}));
        catch e
            disp(['Error in file name part: ' columnNames{colNum}]);
            throw(e);
        end
    end

    tmpTable.MVC_Loaded = loadedData;
    mvcTable = [mvcTable; tmpTable];
end