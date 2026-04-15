function [effectSize] = computeCohensD(v1, v2)

%% PURPOSE: COMPUTE COHEN'S D EFFECT SIZE
% Inputs:
% v1: Numeric vector of group 1 values
% v2: Numeric vector of group 2 values
%
% Outputs:
% effectSize: The Cohen's d effect size

% POSITIVE INDICATES THE FIRST VECTOR HAS LARGER MEAN

d = meanEffectSize(v1, v2, 'Effect', 'cohen');
effectSize = d.Effect;