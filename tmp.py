import json
ck = {'__fn': 'double_values', '__fn_hash': 'abc123', '__inputs': {}, '__constants': {}}
print(json.dumps(ck))
import jsondecode_sim
" 2>/dev/null || python3 -c "
import json
# jsondecode in MATLAB replaces leading __ with x__ prefix
# Let's verify what the actual config_keys dict keys are
ck = {'__fn': 'double_values', '__fn_hash': 'abc123', '__inputs': {}, '__constants': {}}
# MATLAB jsondecode makes '__fn' -> 'x__fn'
for k in ck:
    matlab_k = k.replace('__', 'x__', 1) if k.startswith('__') else k
    print(f'{k!r} -> {matlab_k!r}')