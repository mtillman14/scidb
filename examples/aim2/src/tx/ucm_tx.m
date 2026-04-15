%% Load the data
clearvars;
% Matched
% data_path = "Y:\LabMembers\MTillman\SavedOutcomes\StrokeSpinalStim\Overground_EMG_Kinematics\MergedTablesAffectedUnaffected\matchedCyclesPrePost.csv";
% Unmatched
data_path = "Y:\LabMembers\MTillman\SavedOutcomesAim2\TX\MergedTablesAffectedUnaffected\unmatchedCycles.csv";
df = readtable(data_path);

%% Get the variable names
lastOutcomeMeasureColName = 'Side';
varNames = df.Properties.VariableNames;
outcomeVarsNames = varNames(find(ismember(varNames, lastOutcomeMeasureColName))+1:end);

%% Get the unique subject/intervention combos
levelNames = {'Subject','Intervention'};
levelIdx = ismember(varNames, levelNames); % Column numbers to get the factor names to average within
unique_names_df = unique(df(:,levelIdx), 'rows');
speedColIdx = ismember(df.Properties.VariableNames, 'Speed');
df_for_rows = df(:, levelIdx | speedColIdx); % Variable to use to get the rows from.

%% Set other column names
trialColName = 'Trial';
sideColName = 'Side';
trialColIdx = ismember(varNames, trialColName);
sideColIdx = ismember(varNames, sideColName);

colors.TX4 = [0.0, 0.3, 0.0];      % Dark green
colors.TX7 = [0.13, 0.55, 0.13];   % Forest green
colors.TX10 = [0.2, 0.7, 0.2];     % Medium green
colors.TX13 = [0.3, 0.8, 0.3];     % Green
colors.TX16 = [0.5, 0.9, 0.5];     % Light green
colors.TX19 = [0.7, 0.95, 0.7];    % Pale green
colors.TX22 = [0.85, 1.0, 0.85];   % Very light green

speed = 'FV';
unique_names_df.Speed = repmat(string(speed),height(unique_names_df),1);

subjects = unique(df.Subject,'stable');

rootSavePath = 'Y:\LabMembers\MTillman\GitRepos\Stroke-R01-Aim-2\plots\UCM_TX';

for varNum = 1:length(outcomeVarsNames)
    varName = outcomeVarsNames{varNum};
    varColIdx = ismember(varNames, varName);

    for subjectNum = 1:length(subjects)
        subject = subjects{subjectNum};

        fig = figure;
        hold on;   

        subjectRowsIdx = ismember(df.Subject, subject);
        subjectRows = df(subjectRowsIdx,:);
        interventions = unique(df.Intervention,'stable');
        interventionNames = cell(2*length(interventions),1);
        for i = 1:length(interventions)
            interventionNames{i*2-1} = interventions{i};
            interventionNames{i*2} = ['Mean ' interventions{i}];
        end
        for interventionNum = 1:length(interventions)
            intervention = interventions{interventionNum};
            interventionRowsIdx = ismember(subjectRows.Intervention, intervention);
            speedRowsIdx = ismember(subjectRows.Speed, speed);
            interventionAndSpeedRows = subjectRows(interventionRowsIdx & speedRowsIdx, :);

            % Aggregate the data
            aggVector = interventionAndSpeedRows.(varName);            
            meanVal = abs(mean(aggVector,'omitnan') * 2);
            aggData = NaN(height(interventionAndSpeedRows)-1,2);
            for rowNum = 1:height(interventionAndSpeedRows)-1
                if interventionAndSpeedRows.(trialColName)(rowNum) ~= interventionAndSpeedRows.(trialColName)(rowNum+1)
                    continue; % End of trial
                end
                currSide = interventionAndSpeedRows.(sideColName)(rowNum);
                currData = interventionAndSpeedRows.(varName)(rowNum);
                nextData = interventionAndSpeedRows.(varName)(rowNum+1);
                if strcmp(currSide, 'A')
                    aggData(rowNum,1) = currData;
                    aggData(rowNum,2) = nextData;
                elseif strcmp(currSide, 'U')
                    aggData(rowNum,1) = nextData;
                    aggData(rowNum,2) = currData;
                end
            end

            nanIdx = any(isnan(aggData),2);
            aggData(nanIdx,:) = [];

            % Put it in the first quadrant
            if mean(aggData(:,1)) < 0
                aggData(:,1) = -1*aggData(:,1);
            end
            if mean(aggData(:,2)) < 0
                aggData(:,2) = -1*aggData(:,2);
            end

            % Determine UCM & ORT vectors
            demeanedAggData = aggData - mean(aggData);
            g = ones(1,size(demeanedAggData,2)); % Jacobian
            [~,~,d]=svd(g);
            o = d(:,1); % ORT
            u = d(:,2); % UCM

            % Find length of projections of de-meaned data onto UCM and ORT
            % planes
            m = size(aggData,1);
            distORT = NaN(m,1);
            distUCM = NaN(m,1);
            distTOT = NaN(m,1);
            for i=1:m
                distORT(i) = dot(demeanedAggData(i,:),o);
                distUCM(i) = dot(demeanedAggData(i,:),u);
                distTOT(i) = norm(demeanedAggData(i,:));
            end

            % Find variances of each
            Vucm = sum(diag(distUCM'*distUCM)/length(distUCM));
            Vort = sum(diag(distORT'*distORT)/length(distORT));
            Vtot = sum(diag(distTOT'*distTOT)/length(distTOT));

            % Calculate index of symmetry
            DV = (Vucm-Vort)/(Vtot/2);

            % Compute DVz
            % DVz = 0.5*log(((2+DV)/(2/(1-DV)));
            
            meanData = mean(aggData,1,'omitnan');

            currColor = colors.(intervention);

            % Plot                        
            hold on;
            scatter(aggData(:,1), aggData(:,2), 'MarkerFaceColor', currColor, 'MarkerEdgeColor','none');            
            scatter(meanData(1), meanData(2), 100, 'sq', 'MarkerFaceColor', currColor, 'MarkerEdgeColor','k');
            xlabel('Affected');
            ylabel('Unaffected');
            title({[varName ' Mean: ' num2str(meanVal / 2) ' DV: ' num2str(DV)], ...
                ['Vucm: ' num2str(Vucm) ' Vort: ' num2str(Vort)]},'Interpreter','None');
            xlim([0 meanVal]);
            ylim([0 meanVal]);
            axis equal;            
        end
        ax = gca;        
        axis equal; 
        ylims = ax.YLim;
        line([0 ylims(2)], [0 ylims(2)],'Color','black','LineStyle','--');
        legend([interventionNames; 'Perfect Symmetry']);
        saveName = fullfile(rootSavePath, [subject '_' varName]);
        fig.WindowState = 'maximized';
        saveas(fig, [saveName '.fig']);
        saveas(fig, [saveName '.png']);
        close(fig);
    end    
end