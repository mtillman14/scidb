import duckdb

DB_PATH = "/Users/mitchelltillman/Documents/general-sqlite-database/test_gui.duckdb"
REC_ID = "514561b77c629c4b"

con = duckdb.connect(DB_PATH)

row = con.execute("SELECT type FROM _record WHERE record_id = ?", [REC_ID]).fetchone()
print("record row:", row)

if row:
    con.execute(f'DELETE FROM "{row[0]}_data" WHERE record_id = ?', [REC_ID])
    con.execute("DELETE FROM _record WHERE record_id = ?", [REC_ID])
    print(f"removed record {REC_ID} (type={row[0]})")
else:
    print("already gone — nothing to do")

con.close()