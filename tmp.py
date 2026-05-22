# Let's check what _for_each_prepare actually does                                                                                                            
import ast                                                                                                                                                  
import inspect
with open('sci-matlab/src/sci_matlab/bridge.py', 'r') as f:
    content = f.read()
    # Find the import and see where _for_each_prepare comes from
    print('_for_each_prepare is imported from: scidb.foreach')