function sk = schema_key(key)
%SCIDB.SCHEMA_KEY  Create a schema-key filter builder.
%
%   SK = scidb.schema_key(KEY)
%
%   KEY is the name of a schema key defined at configure_database (string).
%
%   Returns a scidb.SchemaKey object supporting:
%       ismember(SK, values)  — set membership
%       SK == value           — equality
%       SK ~= value           — inequality
%       SK < value            — less than (numeric keys)
%       SK <= value           — less than or equal
%       SK > value            — greater than (numeric keys)
%       SK >= value           — greater than or equal
%
%   Returned filters can be combined with & / | / ~.
%
%   Example:
%       MyData().load(where=ismember(scidb.schema_key("session"), ["BL","POST"]))
%       MyData().load(where=scidb.schema_key("subject") > 2)
%       MyData().load(where=(scidb.schema_key("subject") >= 1) & ...
%                           (scidb.schema_key("subject") <= 3))

    sk = scidb.SchemaKey(key);
end
