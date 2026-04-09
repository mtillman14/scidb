import numpy as np                                                                                                             
import scifor as _scifor                                                                                                                                                            
from scidb import BaseVariable, configure_database, for_each  
import tempfile, pathlib                                                                                                                                                            
                                                                                
db = configure_database(pathlib.Path(tempfile.mkdtemp()) / 'test.duckdb', ['subject', 'session'])
_scifor.set_schema([])                                                                                                                                                              

class RawSignal(BaseVariable): pass                                                                                                                                                 
class Aggregated(BaseVariable): pass                                             
                                                                                                                                                                                    
RawSignal.save(1.0, subject='S01', session='1')                                                                                                                                     
RawSignal.save(1.0, subject='S01', session='2')
RawSignal.save(1.0, subject='S02', session='1')                                                                                                                                     
RawSignal.save(1.0, subject='S02', session='2')                                  
                                    
def agg(signal):                       
    print(f"  signal type={type(signal).__name__}, val={signal}")                                                                                                                   
    return np.float64(4.0)
                                                                                                                                                                                    
result = for_each(agg, {'signal': RawSignal}, [Aggregated], save=False)          
print(f"result: {result}")                                                                                                                                                          
print(f"columns: {list(result.columns) if result is not None else None}")                                                                                                           
print(f"len: {len(result) if result is not None else None}")