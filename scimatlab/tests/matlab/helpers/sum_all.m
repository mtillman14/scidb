function s = sum_all(vals)
%SUM_ALL  Test helper: sum whatever numeric payload arrives (array or table).
    if istable(vals)
        s = 0;
        vn = vals.Properties.VariableNames;
        for i = 1:numel(vn)
            col = vals.(vn{i});
            if isnumeric(col)
                s = s + sum(col(:), 'omitnan');
            elseif iscell(col)
                for r = 1:numel(col)
                    if isnumeric(col{r})
                        s = s + sum(col{r}(:), 'omitnan');
                    end
                end
            end
        end
    else
        s = sum(double(vals(:)), 'omitnan');
    end
end
