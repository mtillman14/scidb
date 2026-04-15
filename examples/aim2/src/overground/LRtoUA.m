function [uaSides] = LRtoUA(startFootTable, uaConfig)

%% PURPOSE: CONVERT THE L/R START FOOT TO U/A (UNAFFECTED/AFFECTED)

startFootStr = string(startFootTable.StartFoot);
subject = startFootTable.subject{1};

affectedSide = uaConfig.(subject);

uaSides = repmat("", length(startFootStr), 1);
for i = 1:length(startFootStr)
    if affectedSide == startFootStr(i)
        ua = "A";
    else
        ua = "U";
    end
    uaSides(i) = ua;
end