import duckdb
con = duckdb.connect('test_gui.duckdb', read_only=True)
print('=== Manual edges ===')
for row in con.execute('SELECT * FROM _pipeline_edges').fetchall():
    print(row)
print()
print('=== Manual nodes ===')
for row in con.execute('SELECT * FROM _pipeline_nodes').fetchall():
    print(row)