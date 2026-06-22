function py_val = to_python_input(arg)
%TO_PYTHON_INPUT  Marshal a MATLAB argument to a Python object.
%
%   For scidb.BaseVariable, returns the Python shadow (.py_obj) so the
%   Python side sees the real Python type and provenance is preserved.
%
%   For raw MATLAB data (scalars, arrays), converts to the Python
%   equivalent via to_python().

    if isa(arg, 'scidb.BaseVariable')
        % Pass the real Python BaseVariable (carries record_id / content_hash)
        py_val = arg.py_obj;

    else
        % Convert raw MATLAB data
        py_val = scidb.internal.to_python(arg);
    end
end
