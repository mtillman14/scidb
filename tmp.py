from scidb import configure_database

db = configure_database("test_gui.duckdb", ["subject"])
for v in db.list_pipeline_variants():
    if v["function_name"] == "compute_rolling_vo2":
        print(v.get("call_id"), v["constants"], v["record_count"])
