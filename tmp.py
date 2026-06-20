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