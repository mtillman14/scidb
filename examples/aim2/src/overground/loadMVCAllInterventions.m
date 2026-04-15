function [mvcTable] = loadMVCAllInterventions(delsysConfig, subject_mvc_folder, intervention_folders, mapped_interventions, regexsConfig, missingFilesPartsToCheck)

%% PURPOSE: LOAD ALL OF THE MVC FILES FROM ALL INTERVENTIONS
% Inputs:
% delsysConfig: Config struct for Delsys specifically (contains MVC config)
% subject_mvc_folder: The folder containing the subject's MVC data
% intervention_folders: Cell array of folder names, one per intervention
% mapped_interventions: The intervention folder names mapped to field names
% regexsConfig: Config struct for regexs
%
% Outputs:
% mvcTable: Table with MVC data

disp('Loading MVC');

mvcTable = table;
for i = 1:length(intervention_folders)
    intervention_folder = intervention_folders{i};        
    intervention_folder_path = fullfile(subject_mvc_folder, intervention_folder);
    intervention_field_name = mapped_interventions(intervention_folder);
    % if ~isfolder(intervention_folder_path)
    %     continue;
    % end
    tmpTable = loadMVCOneIntervention(delsysConfig, intervention_folder_path, intervention_field_name, regexsConfig, missingFilesPartsToCheck);
    if isempty(tmpTable)
        continue;
    end
    mvcTable = addToTable(mvcTable, tmpTable);
end

