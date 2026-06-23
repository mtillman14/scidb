import scidb
db = scidb.configure_database("/Users/mitchelltillman/Downloads/data.db", ["subject","session","speed","trial","cycle"])

class GAITRiteLoaded(scidb.BaseVariable):
    pass

# (a) the GAITRiteLoaded DOUBLE[] for one trial (adjust kwargs to a real trial)
gl = GAITRiteLoaded.load(subject="SS02", session="BL", speed="FV", trial="3")
print("GAITRiteLoaded.data:\n", gl.data)

# (b) the GAITRiteLoadedCycle DOUBLE values for that trial, per run (save time), by cycle
print(db._duck._fetchall("""
    SELECT rs.timestamp, CAST(s.cycle AS INTEGER) AS cycle, t.*
    FROM _record r
    JOIN _schema s        ON s.schema_id = r.schema_id
    JOIN _record_save rs  ON rs.record_id = r.record_id
    JOIN "GAITRiteLoadedCycle_data" t ON t.record_id = r.record_id
    WHERE r.type = 'GAITRiteLoadedCycle'
    AND s.subject='SS02' AND s.session='BL' AND s.speed='FV' AND s.trial='3'
    ORDER BY rs.timestamp, CAST(s.cycle AS INTEGER)
"""))