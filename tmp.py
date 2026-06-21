p="scidb/tests/test_exclusions.py"
s=open(p).read().split("\n")
# delete from the line "    def test_override_hash_in_version_keys" to EOF
start=next(i for i,l in enumerate(s) if "def test_override_hash_in_version_keys" in l)
new=s[:start]
# strip trailing blank lines, keep one newline
while new and new[-1].strip()=="":
    new.pop()
open(p,"w").write("\n".join(new)+"\n")
print("deleted from line", start+1, "-> new len", len(new))

However, for the sake of the GUI, there needs to be a way to query whether a function with only PathInput and constant inputs (i.e. no variable input) is outdated from the last run.
    I think the best way to do this is to check whether the union of 1. all the schema_ids found by the PathInput and 2. the specified iteration schema_ids is a subset of the schema_ids in the database for this invocation_id.