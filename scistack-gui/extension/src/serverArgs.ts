/**
 * serverArgs — build the `python -m scistack_gui.server` argv.
 *
 * Split out of `pythonProcess.ts` so the argv can be unit-tested under
 * `node --test` (nothing here imports `vscode`).
 *
 * The extension deliberately never passes `--module` or `--project`. Both
 * used to be filled in by a "How should SciStack discover your pipeline
 * code?" QuickPick shown before every open; that step is gone, so the
 * server always takes `bootstrap.open_or_create_project`'s auto-discovery
 * branch. Which directory that scans is decided by
 * `config.resolve_project_root`, and with no `--project` the answer is
 * `--project-root` (the VS Code workspace folder) — see the rule list in
 * that docstring. Callers must therefore pass `projectRoot` whenever a
 * workspace folder exists, or discovery silently falls back to the
 * extension host's cwd.
 */

export interface ServerArgsOptions {
  /** Path to the .duckdb file to open or create. */
  dbPath: string;
  /** Top-down schema keys. Only meaningful when creating a new database. */
  schemaKeys?: string[];
  /** The VS Code workspace folder, i.e. "the project the user opened". */
  projectRoot?: string;
}

export function buildServerArgs({
  dbPath,
  schemaKeys,
  projectRoot,
}: ServerArgsOptions): string[] {
  const args = ['-m', 'scistack_gui.server', '--db', dbPath];
  if (schemaKeys && schemaKeys.length > 0) {
    args.push('--schema-keys', schemaKeys.join(','));
  }
  // The workspace folder is what the user thinks of as "the project", and
  // it is the server's only way to know: a .duckdb usually lives in a
  // datasets folder, so without this a new scistack.toml + entities file
  // would be written next to the data instead of in the project.
  if (projectRoot) {
    args.push('--project-root', projectRoot);
  }
  return args;
}
