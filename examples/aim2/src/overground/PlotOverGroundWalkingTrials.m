%% Plot Overground EMG & Kinematics for All Subjects
% This script visualizes time-normalized EMG and kinematic data for all subjects.
% Requires subjects to be pre-processed using mainAllSubjects_Aim2.
% For each intervention and speed, it generates tiled plots with left and right
% Outputs are saved for each subject as both .fig and .png  files.

clear; clc; close all;

dataDir = 'Y:\Spinal Stim_Stroke R01\AIM 2\Subject Data\MATLAB Processed Overground_EMG_Kinematics';
saveDir = fullfile(dataDir, 'Plots');
if ~exist(saveDir, 'dir'), mkdir(saveDir); end

lineWidth = 1.2;
alphaVal  = 0.6;
files = dir(fullfile(dataDir, 'SS*_Overground_EMG_Kinematics.mat'));

for f = 1:numel(files)
    filePath = fullfile(files(f).folder, files(f).name);
    [~, baseName] = fileparts(filePath);
    fprintf('Processing %s...\n', baseName);

    try
        S = load(filePath, 'matchedCycleTable');
        if ~isfield(S, 'matchedCycleTable'), continue; end
        T = S.matchedCycleTable;

        subjID = regexp(baseName, 'SS\d+', 'match', 'once');
        if isempty(subjID), subjID = baseName; end
        subjSaveDir = fullfile(saveDir, subjID);
        if ~exist(subjSaveDir, 'dir'), mkdir(subjSaveDir); end

        % Convert categorical to string
        intCol = string(T.Intervention);
        spdCol = string(T.Speed);
        interventions = unique(intCol);
        speeds = unique(spdCol);

        for iInt = 1:numel(interventions)
            for iSpd = 1:numel(speeds)
                mask = intCol == interventions(iInt) & spdCol == speeds(iSpd);
                G = T(mask, :);
                if isempty(G), continue; end

                trials = unique(G.Trial);
                nTrials = numel(trials);
                colors = lines(nTrials);

                %% EMG (DELSYS)
                fn = fieldnames(G.Delsys_Normalized_TimeNormalized(1));
                L = fn(startsWith(fn,'L','IgnoreCase',true));
                R = fn(startsWith(fn,'R','IgnoreCase',true));
                nRows = max(numel(L), numel(R));

                fig = figure('Color','w','Position',[100 100 1200 800]);
                tiledlayout(nRows,2,'TileSpacing','compact','Padding','compact');

                for i = 1:numel(L)
                    nexttile((i-1)*2+1); hold on;
                    for t = 1:nTrials
                        rows = G.Trial == trials(t);
                        for r = find(rows)'
                            d = G.Delsys_Normalized_TimeNormalized(r);
                            plot(d.(L{i}), 'Color', [colors(t,:) alphaVal], 'LineWidth', lineWidth);
                        end
                    end
                    title(L{i}); xlabel('% Gait Cycle'); ylabel('EMG (a.u.)'); grid on;
                end

                for i = 1:numel(R)
                    nexttile((i-1)*2+2); hold on;
                    for t = 1:nTrials
                        rows = G.Trial == trials(t);
                        for r = find(rows)'
                            d = G.Delsys_Normalized_TimeNormalized(r);
                            plot(d.(R{i}), 'Color', [colors(t,:) alphaVal], 'LineWidth', lineWidth);
                        end
                    end
                    title(R{i}); xlabel('% Gait Cycle'); ylabel('EMG (a.u.)'); grid on;
                end

                % Add legend once (per figure)
                ax = gca; hold(ax,'on');
                hTrial = gobjects(nTrials,1);
                for t = 1:nTrials
                    hTrial(t) = plot(ax, nan, nan, '-', 'LineWidth', lineWidth, 'Color', colors(t,:));
                end
                legend(hTrial, cellstr("Trial " + string(trials)), 'Location','bestoutside', 'Interpreter','none');

                sgtitle(sprintf('%s | %s | %s | EMG', subjID, interventions(iInt), speeds(iSpd)));
                saveName = sprintf('%s_%s_%s_EMG', subjID, interventions(iInt), speeds(iSpd));
                exportgraphics(fig, fullfile(subjSaveDir,[saveName '.png']), 'Resolution',300);
                close(fig);

                %% KINEMATICS (XSENS)
                fn = fieldnames(G.XSENS_TimeNormalized(1));
                L = fn(startsWith(fn,'L','IgnoreCase',true));
                R = fn(startsWith(fn,'R','IgnoreCase',true));
                nRows = max(numel(L), numel(R));

                fig = figure('Color','w','Position',[100 100 1000 700]);
                tiledlayout(nRows,2,'TileSpacing','compact','Padding','compact');

                for i = 1:numel(L)
                    nexttile((i-1)*2+1); hold on;
                    for t = 1:nTrials
                        rows = G.Trial == trials(t);
                        for r = find(rows)'
                            d = G.XSENS_TimeNormalized(r);
                            plot(d.(L{i}), 'Color', [colors(t,:) alphaVal], 'LineWidth', lineWidth);
                        end
                    end
                    title(L{i}); xlabel('% Gait Cycle'); ylabel('Angle (°)'); grid on;
                end

                for i = 1:numel(R)
                    nexttile((i-1)*2+2); hold on;
                    for t = 1:nTrials
                        rows = G.Trial == trials(t);
                        for r = find(rows)'
                            d = G.XSENS_TimeNormalized(r);
                            plot(d.(R{i}), 'Color', [colors(t,:) alphaVal], 'LineWidth', lineWidth);
                        end
                    end
                    title(R{i}); xlabel('% Gait Cycle'); ylabel('Angle (°)'); grid on;
                end

                ax = gca; hold(ax,'on');
                hTrial = gobjects(nTrials,1);
                for t = 1:nTrials
                    hTrial(t) = plot(ax, nan, nan, '-', 'LineWidth', lineWidth, 'Color', colors(t,:));
                end
                legend(hTrial, cellstr("Trial " + string(trials)), 'Location','bestoutside', 'Interpreter','none');

                sgtitle(sprintf('%s | %s | %s | Kinematics', subjID, interventions(iInt), speeds(iSpd)));
                saveName = sprintf('%s_%s_%s_Kinematics', subjID, interventions(iInt), speeds(iSpd));
                exportgraphics(fig, fullfile(subjSaveDir,[saveName '.png']), 'Resolution',300);
                close(fig);
            end
        end
    catch ME
        warning('Error in %s: %s', baseName, ME.message);
    end
end

fprintf('All subjects processed. Plots saved in %s\n', saveDir);
