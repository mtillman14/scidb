# MATLAB Output Names vs Variable Types

## The Distinction

MATLAB functions have **output parameter names** declared in their function signature (e.g., `extracted_data`). These are the names of the variables in MATLAB workspace that receive the function's return values. They are NOT the same as **variable types** (e.g., `XSENSLoaded`), which are the scidb `BaseVariable` subclass names that data is saved as in the database.

The mapping between the two is established by edges in the GUI: the user connects a function node's output handle (labeled with the MATLAB output name) to a variable node (labeled with the variable type).

## Where Each Is Used

| Context | Uses Output Parameter Name | Uses Variable Type |
|---------|---------------------------|-------------------|
| Function node output handles (UI ports) | `extracted_data` | |
| MATLAB command generation (`generate_matlab_command`) | | `XSENSLoaded` (inferred from edges) |
| Database saves (`save(XSENSLoaded)`) | | `XSENSLoaded` |
| `_record_metadata` table | | `XSENSLoaded` (as `variable_name`) |
| `_lineage` table | | `XSENSLoaded` (as output type) |
| `BaseVariable._all_subclasses` lookup | | `XSENSLoaded` |
| State computation (`_own_state_for_function`) | | `XSENSLoaded` |

## The Bug (Fixed)

In `scistack-gui/scistack_gui/api/pipeline.py`, there was code that overrode `resolved_output_types` for MATLAB functions to use the declared output parameter names (for handle rendering). This same variable was then passed to `_own_state_for_function()`, which tried to look up the output parameter name (e.g., `extracted_data`) in `BaseVariable._all_subclasses`. Since output parameter names are not variable class names, the lookup always failed, `output_classes` was empty, and the function returned `"red"` unconditionally.

### Before (broken)
```python
resolved_output_types = resolved.output_types  # ['XSENSLoaded']
if _mr.is_matlab_function(fn_label):
    resolved_output_types = list(info.output_names)  # ['extracted_data'] -- OVERWRITES
# State computation uses 'extracted_data' -- WRONG
manual_fn_state = _own_state_for_function(db, fn_label, set(resolved_output_types))
```

### After (fixed)
```python
resolved_output_types = resolved.output_types  # ['XSENSLoaded']
state_output_types = resolved_output_types      # preserve for state computation
if _mr.is_matlab_function(fn_label):
    resolved_output_types = list(info.output_names)  # ['extracted_data'] -- only for handles
# State computation uses 'XSENSLoaded' -- CORRECT
manual_fn_state = _own_state_for_function(db, fn_label, set(state_output_types))
```

## Multi-Output Functions

A MATLAB function can have multiple outputs (e.g., `[peak, trough] = analyzeCurve(...)`). Each output parameter name maps to a different variable type via separate edges:
- `peak` handle -> edge -> `PeakData` variable node
- `trough` handle -> edge -> `TroughData` variable node

The handle names (`peak`, `trough`) must match the MATLAB signature so the GUI can wire them correctly. The state computation must use the variable types (`PeakData`, `TroughData`) so it can find the actual records in the database.

## Key Invariant

**Handle rendering** uses MATLAB output parameter names (must match the function signature).
**State computation** uses edge-resolved variable types (must match `BaseVariable` subclass names in the database).

These two name spaces must never be conflated.
