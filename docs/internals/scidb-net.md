# scidb-net — networking layer

!!! info "Internal package (optional)"
    Most pipelines never need this. It lets `scidb` storage live on another
    machine while your `save()`/`load()` calls stay unchanged.

`scidb-net` is an optional client-server layer that wraps SciStack's database
manager behind a FastAPI server and provides a drop-in HTTP client. With it,
existing `BaseVariable.save()` / `.load()` calls — and lineage caching — work
transparently over the network.

## How it works

```
CLIENT MACHINE                       SERVER MACHINE
==============                       ==============
Your analysis code                   scidb-server process
       |                                    |
  configure_remote_database()        create_app() / scidb-server CLI
       |                                    |
  RemoteDatabaseManager  --- HTTP -->  FastAPI app
       |                                    |
  RawSignal.save(...) / .load(...)     the local DuckDB database
```

Because the client implements the same interface as the local database manager,
analysis code is identical whether the database is local or remote.
