path = "scidb/src/scidb/foreach.py"
src = open(path).read().splitlines(keepends=True)
# 1-indexed line numbers of Log.info( openers to demote to Log.debug(
demote = [1433, 1466, 1477, 1485, 1504, 1621, 1700, 1799, 1886, 1958, 2058, 2063,
        2443, 2446, 2448, 3420, 3437, 3802]
for n in demote:
        line = src[n-1]
        assert "Log.info(" in line, (n, line)
        src[n-1] = line.replace("Log.info(", "Log.debug(")
open(path, "w").write("".join(src))
print("demoted", len(demote), "lines")