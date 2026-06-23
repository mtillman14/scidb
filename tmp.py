import scidb
db = scidb.configure_database("/Users/mitchelltillman/Downloads/data.db", ["subject","session","speed","trial","cycle"])
inv = db._duck._fetchall(
    "SELECT invocation_id, output_num FROM _invocation_output WHERE output_record_id = '002bd63afe587e0a'")
print("output edge:", inv)
inv_id = inv[0][0]
print("invocation row:", db._duck._fetchall(
    "SELECT invocation_id, function_name, function_hash, as_table, distribute "
    "FROM _invocation WHERE invocation_id = ?", [inv_id]))
print("input edges for THIS inv:", db._duck._fetchall(
    "SELECT param_name, input_record_id FROM _invocation_input WHERE invocation_id = ?", [inv_id]))
print("total _invocation_input rows in DB:", db._duck._fetchall("SELECT COUNT(*) FROM _invocation_input")[0][0])
print("input edges across ALL distribute invocations:", db._duck._fetchall("""
    SELECT COUNT(*) FROM _invocation_input ii
    JOIN _invocation i ON i.invocation_id = ii.invocation_id
    WHERE i.distribute = TRUE"""))