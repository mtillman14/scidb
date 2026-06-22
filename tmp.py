import numpy as np, pandas as pd
from scidb import BaseVariable, configure_database, for_each
from scidb import provenance_query

db = configure_database("/tmp/xlvl.duckdb", ["subject", "trial"])

class Side(BaseVariable): schema_version = 1
class RawSig(BaseVariable): schema_version = 1
class Summed(BaseVariable): schema_version = 1

def agg_sum(x):
    if isinstance(x, pd.DataFrame):
        return float(x.select_dtypes(include="number").values.sum())
    return float(np.sum(x))

Side.save("L", subject="S01", trial="1")
Side.save("R", subject="S01", trial="2")
RawSig.save(10.0, subject="S01", trial="1")
RawSig.save(20.0, subject="S01", trial="2")

for_each(agg_sum, {"x": RawSig}, [Summed], subject=["S01"], where=(Side == "L"))
for_each(agg_sum, {"x": RawSig}, [Summed], subject=["S01"], where=(Side == "R"))

rows = db._duck._fetchall(
    "SELECT rm.record_id, r.schema_id FROM _record_save rm "
    "JOIN _record r ON r.record_id = rm.record_id WHERE r.type = 'Summed'", [])
print("Summed records:", rows)
print("consumed:", provenance_query.consumed_input_schema_ids(db._duck, [r[0] for r in rows]))
db.close()