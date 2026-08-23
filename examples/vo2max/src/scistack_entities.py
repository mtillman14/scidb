"""Auto-created by the SciStack GUI -- new Sweep/PathInput/Variable/
Constant declarations created from the GUI are appended here."""
import scidb

class test(scidb.BaseVariable):
    pass

test_const = scidb.constant(2, description='')

test_path_input = scidb.PathInput('{subject}/{subject}_{session}.csv')

test_sweep = scidb.Sweep(0, 1, 2)
