import duckdb                                                                                                                                                 
import pandas as pd                                                                                                                                         
import numpy as np

# Create a test with array columns
conn = duckdb.connect(':memory:')
conn.execute("""
    CREATE TABLE test (
        id INTEGER,
        scalar_col DOUBLE,
        array_col DOUBLE[]
    )
""")
conn.execute("""
    INSERT INTO test VALUES
    (1, 1.5, [1.0, 2.0, 3.0]),
    (2, 2.5, [4.0, 5.0]),
    (3, 3.5, [6.0, 7.0, 8.0, 9.0])
""")

df = conn.execute("SELECT * FROM test").df()

print("DataFrame dtypes:")
print(df.dtypes)
print("\nDataFrame contents:")
print(df)
print("\narray_col[0] type:", type(df['array_col'].iloc[0]))
print("array_col[0] value:", df['array_col'].iloc[0])
print("array_col[0] dtype:", df['array_col'].iloc[0].dtype if isinstance(df['array_col'].iloc[0], np.ndarray) else 'N/A')

# Test if we can stack them
arrays = df['array_col'].tolist()
print("\nAll are numpy arrays?", all(isinstance(x, np.ndarray) for x in arrays))
print("All same length?", len(set(len(x) for x in arrays)) == 1)