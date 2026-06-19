import re
p = "scidb/src/scidb/database.py"
s = open(p).read()
s = s.replace(
    "records = _filter_records_by_branch_params(records, branch_params_filter)",
    "records = _filter_records_by_branch_params(records, branch_params_filter, self._duck)",
)
open(p,"w").write(s)
print("done", s.count("_filter_records_by_branch_params(records, branch_params_filter, self._duck)"))