# tmp.py                                                                                                                                                                                               
import duckdb                                                                                                                                                                                          
conn = duckdb.connect(                                                                                                                                                                                 
    '/Users/mitchelltillman/Documents/Stroke-R01-Aim-2/aim2.duckdb',                                                                                                                                   
    read_only=True,                                                                                                                                                                                    
)                                                                                                                                                                                                      
rows = conn.execute("""                                                                                                                                                                                
    SELECT DISTINCT function_hash, COUNT(*) as n_rows                                                                                                                                                  
    FROM _lineage
    WHERE function_name = 'load_csv'                                                                                                                                                                   
    GROUP BY function_hash                                
""").fetchall()                                                                                                                                                                                        
print(f"{'function_hash':<68} n_rows")                    
for h, n in rows:                                                                                                                                                                                      
    marker = " <-- matches GUI proxy hash" if h and h.startswith("ce634fb42246") else ""
    print(f"{h!s:<68} {n}{marker}")