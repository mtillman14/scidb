/**
 * SciStack GUI — VS Code Extension entry point.
 *
 * activate() is called when the user first triggers a SciStack command.
 * deactivate() is called when the extension is unloaded.
 */

import * as path from 'path';
import * as vscode from 'vscode';
import { PythonProcess } from './pythonProcess';
import { DagPanel } from './dagPanel';
import { checkProjectConfig, promptForMissingConfig } from './projectInit';
import {
  diagnoseStartupFailure,
  probeInterpreter,
  StartupAction,
  StartupDiagnosis,
} from './startupDiagnostics';

let pythonProcess: PythonProcess | null = null;
let dagPanel: DagPanel | null = null;
let outputChannel: vscode.OutputChannel;
let dbWatcher: vscode.FileSystemWatcher | null = null;
let dbWatcherDebounce: ReturnType<typeof setTimeout> | null = null;

// Remember the most recent start args so we can restart the Python process
// (e.g. after editing scistack_gui source code) without re-prompting the user.
interface LastStartArgs {
  dbPath: string;
  modulePath?: string;
  projectPath?: string;
  schemaKeys?: string[];
}
let lastStartArgs: LastStartArgs | null = null;

export function activate(context: vscode.ExtensionContext) {
  outputChannel = vscode.window.createOutputChannel('SciStack');

  const openPipeline = vscode.commands.registerCommand(
    'scistack.openPipeline',
    async () => {
      // Open existing DB or create a new one?
      const dbChoice = await vscode.window.showQuickPick(
        ['Open existing database', 'Create new database'],
        { placeHolder: 'SciStack: Open or create a .duckdb file?' }
      );
      if (!dbChoice) return;

      let dbPath: string;
      let schemaKeys: string[] | undefined;
      if (dbChoice === 'Open existing database') {
        const dbUris = await vscode.window.showOpenDialog({
          canSelectFiles: true,
          canSelectFolders: false,
          canSelectMany: false,
          filters: { 'DuckDB Database': ['duckdb'] },
          title: 'Select SciStack Database',
        });
        if (!dbUris || dbUris.length === 0) return;
        dbPath = dbUris[0].fsPath;
      } else {
        const folderUris = await vscode.window.showOpenDialog({
          canSelectFiles: false,
          canSelectFolders: true,
          canSelectMany: false,
          title: 'Select folder for new SciStack database',
          openLabel: 'Select Folder',
        });
        if (!folderUris || folderUris.length === 0) return;
        const folderPath = folderUris[0].fsPath;

        const nameInput = await vscode.window.showInputBox({
          prompt: 'Database filename',
          placeHolder: 'e.g. my_pipeline.duckdb',
          validateInput: (v) => {
            const trimmed = v.trim();
            if (!trimmed) return 'Provide a filename';
            if (trimmed.includes('/') || trimmed.includes('\\')) {
              return 'Filename must not contain path separators';
            }
            return null;
          },
        });
        if (!nameInput) return;
        const fileName = nameInput.trim().endsWith('.duckdb')
          ? nameInput.trim()
          : `${nameInput.trim()}.duckdb`;
        dbPath = path.join(folderPath, fileName);

        const keysInput = await vscode.window.showInputBox({
          prompt: 'Schema keys (comma-separated, top-down)',
          placeHolder: 'e.g. subject, session',
          validateInput: (v) => {
            const parts = v.split(',').map((s) => s.trim()).filter(Boolean);
            return parts.length === 0 ? 'Provide at least one schema key' : null;
          },
        });
        if (!keysInput) return;
        schemaKeys = keysInput.split(',').map((s) => s.trim()).filter(Boolean);
      }

      // Select pipeline source: project, single file, or none
      const sourceChoice = await vscode.window.showQuickPick(
        [
          'Select a project (pyproject.toml)',
          'Select a single pipeline module (.py)',
          'No module',
        ],
        { placeHolder: 'How should SciStack discover your pipeline code?' }
      );
      if (!sourceChoice) return;

      let modulePath: string | undefined;
      let projectPath: string | undefined;

      if (sourceChoice === 'Select a project (pyproject.toml)') {
        const projectUris = await vscode.window.showOpenDialog({
          canSelectFiles: true,
          canSelectFolders: true,
          canSelectMany: false,
          filters: { 'TOML': ['toml'] },
          title: 'Select pyproject.toml or project directory',
        });
        if (projectUris && projectUris.length > 0) {
          const selectedPath = projectUris[0].fsPath;
          const configStatus = checkProjectConfig(selectedPath);
          if (configStatus === 'no_config_file') {
            const result = await promptForMissingConfig(selectedPath, outputChannel);
            if (result === undefined) return;  // user cancelled
            projectPath = result;
          } else {
            projectPath = selectedPath;
          }
        }
      } else if (sourceChoice === 'Select a single pipeline module (.py)') {
        const moduleUris = await vscode.window.showOpenDialog({
          canSelectFiles: true,
          canSelectFolders: false,
          canSelectMany: false,
          filters: { 'Python': ['py'] },
          title: 'Select Pipeline Module',
        });
        if (moduleUris && moduleUris.length > 0) {
          modulePath = moduleUris[0].fsPath;
        }
      }

      await startPipeline(context, dbPath, modulePath, projectPath, schemaKeys);
    }
  );

  const restartPython = vscode.commands.registerCommand(
    'scistack.restartPython',
    async () => {
      if (!lastStartArgs) {
        vscode.window.showWarningMessage(
          'SciStack: No pipeline has been opened yet — run "SciStack: Open Pipeline" first.'
        );
        return;
      }
      outputChannel.appendLine('Restarting Python process...');
      try {
        await startPipeline(
          context,
          lastStartArgs.dbPath,
          lastStartArgs.modulePath,
          lastStartArgs.projectPath,
          // Don't re-pass schemaKeys: the DB already exists on restart.
          undefined,
        );
        vscode.window.showInformationMessage('SciStack: Python process restarted.');
      } catch (err) {
        vscode.window.showErrorMessage(`SciStack: Restart failed — ${err}`);
      }
    }
  );

  context.subscriptions.push(openPipeline, restartPython, outputChannel);
}

async function startPipeline(
  context: vscode.ExtensionContext,
  dbPath: string,
  modulePath?: string,
  projectPath?: string,
  schemaKeys?: string[],
) {
  // Remember args so "Restart Python" can respawn without re-prompting.
  // Preserve the prior schemaKeys if this call didn't supply them (e.g. restart).
  lastStartArgs = {
    dbPath,
    modulePath,
    projectPath,
    schemaKeys: schemaKeys ?? lastStartArgs?.schemaKeys,
  };

  // Kill existing process if any
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }

  // Resolve Python interpreter
  const interpreter = await resolvePythonPath();
  if (!interpreter) {
    vscode.window.showErrorMessage(
      'SciStack: Could not find a Python interpreter. ' +
      'Install the Python extension or set scistack.pythonPath in settings.'
    );
    return;
  }
  const { path: pythonPath, source: interpreterSource } = interpreter;

  // Start the Python JSON-RPC server
  outputChannel.appendLine(`Starting SciStack server...`);
  outputChannel.appendLine(`  Python: ${pythonPath} (from ${interpreterSource})`);
  outputChannel.appendLine(`  DB: ${dbPath}`);
  if (projectPath) outputChannel.appendLine(`  Project: ${projectPath}`);
  if (modulePath) outputChannel.appendLine(`  Module: ${modulePath}`);
  if (schemaKeys) outputChannel.appendLine(`  Schema keys: [${schemaKeys.join(', ')}] (new DB)`);

  pythonProcess = new PythonProcess(pythonPath, dbPath, modulePath, outputChannel, schemaKeys, projectPath);

  try {
    const cfg = vscode.workspace.getConfiguration('scistack');
    const startupTimeoutMs = cfg.get<number>('startupTimeoutMs', 60000);
    const readyParams = await pythonProcess.waitForReady(startupTimeoutMs);
    outputChannel.appendLine(
      `Server ready — DB: ${readyParams.db_name}, schema: [${readyParams.schema_keys.join(', ')}]`
    );
  } catch (err) {
    const failed = pythonProcess;
    pythonProcess = null;
    failed.kill();
    await reportStartupFailure(failed, interpreterSource, err);
    return;
  }

  // Create or reveal the DAG Webview panel
  if (dagPanel) {
    dagPanel.updatePythonProcess(pythonProcess);
    dagPanel.reveal();
    // Trigger the webview to re-fetch the registry (and DAG) so any new
    // functions/variables added since the last start are reflected.
    dagPanel.postMessage({ method: 'dag_updated', params: {} });
  } else {
    dagPanel = new DagPanel(context, pythonProcess, outputChannel);
    dagPanel.onDidDispose(() => {
      dagPanel = null;
      if (pythonProcess) {
        pythonProcess.kill();
        pythonProcess = null;
      }
    });
    // MATLAB has released the database — replay whatever the file-watcher
    // withheld while it was running. Registered here (once per panel)
    // rather than in the run_done branch below, because the terminal and
    // clipboard tiers finish inside DagPanel and never emit a Python
    // notification at all.
    dagPanel.matlabRuns.onAllFinished(flushDeferredDagRefresh);
  }

  // Forward push notifications from Python → Webview
  pythonProcess.onNotification((method, params) => {
    if (dagPanel) {
      dagPanel.postMessage({ method, params });
      // When a run finishes, auto-detach the debugger if we auto-attached it.
      if (method === 'run_done') {
        dagPanel.stopDebugSession();
        // Sidecar-driven MATLAB runs end here; the tracker fires the
        // callback registered above once the last one clears.
        dagPanel.matlabRuns.end(params.run_id as string | undefined);
      }
    }
  });

  // Watch the DuckDB file for external changes (e.g. MATLAB writes).
  // Debounce with a 2-second window so rapid writes don't flood the UI.
  setupDbWatcher(dbPath);

  // Status bar
  const statusItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left, 100
  );
  statusItem.text = `$(database) SciStack: ${dbPath.split('/').pop()}`;
  statusItem.tooltip = dbPath;
  statusItem.show();
}

/**
 * Explain a failed server start.
 *
 * The bare rejection reason ("Python process exited (code=1)") never says
 * which interpreter was used or what it was missing, which is the whole
 * question when scistack_gui simply is not installed in the environment
 * VS Code picked. So: probe the interpreter, classify, and offer the fix.
 */
async function reportStartupFailure(
  failed: PythonProcess,
  interpreterSource: string,
  err: unknown,
): Promise<void> {
  const errorMessage = err instanceof Error ? err.message : String(err);
  outputChannel.appendLine(`Server failed to start: ${errorMessage}`);
  outputChannel.appendLine(`Probing interpreter ${failed.pythonPath}...`);

  // Let the dying child flush its stderr before we quote it.
  await failed.whenClosed();
  const probe = await probeInterpreter(failed.pythonPath);
  const diagnosis = diagnoseStartupFailure({
    pythonPath: failed.pythonPath,
    interpreterSource,
    args: failed.args,
    errorMessage,
    stderr: failed.getStderr(),
    exitCode: failed.getExitCode(),
    probe,
  });

  outputChannel.appendLine('');
  outputChannel.appendLine(`=== SciStack startup failure (${diagnosis.kind}) ===`);
  outputChannel.appendLine(diagnosis.detail);
  if (diagnosis.installCommand) {
    outputChannel.appendLine(`Install with: ${diagnosis.installCommand}`);
  }
  outputChannel.appendLine('=== end of startup failure report ===');

  await showDiagnosisMessage(diagnosis);
}

const ACTION_LABELS: Record<StartupAction, string> = {
  showOutput: 'Show Details',
  selectInterpreter: 'Select Interpreter',
  openSettings: 'Open Settings',
  copyInstallCommand: 'Copy Install Command',
};

async function showDiagnosisMessage(diagnosis: StartupDiagnosis): Promise<void> {
  const labels = diagnosis.actions.map((a) => ACTION_LABELS[a]);
  const picked = await vscode.window.showErrorMessage(diagnosis.message, ...labels);
  if (!picked) return;

  const action = diagnosis.actions.find((a) => ACTION_LABELS[a] === picked);
  switch (action) {
    case 'showOutput':
      outputChannel.show(true);
      break;
    case 'selectInterpreter':
      await vscode.commands.executeCommand('python.setInterpreter');
      break;
    case 'openSettings':
      await vscode.commands.executeCommand(
        'workbench.action.openSettings', 'scistack.pythonPath'
      );
      break;
    case 'copyInstallCommand':
      if (diagnosis.installCommand) {
        await vscode.env.clipboard.writeText(diagnosis.installCommand);
        vscode.window.showInformationMessage(
          `SciStack: copied to clipboard — ${diagnosis.installCommand}`
        );
      }
      break;
  }
}

interface ResolvedInterpreter {
  path: string;
  /** Human-readable origin, so an error message can say where to change it. */
  source: string;
}

async function resolvePythonPath(): Promise<ResolvedInterpreter | undefined> {
  // 1. Check extension setting
  const config = vscode.workspace.getConfiguration('scistack');
  const configured = config.get<string>('pythonPath');
  if (configured) return { path: configured, source: 'scistack.pythonPath setting' };

  // 2. Try the VS Code Python extension
  const pythonExt = vscode.extensions.getExtension('ms-python.python');
  if (pythonExt) {
    if (!pythonExt.isActive) await pythonExt.activate();
    // The Python extension exports an API to get the active interpreter
    const api = pythonExt.exports;
    if (api?.environments?.getActiveEnvironmentPath) {
      const envPath = api.environments.getActiveEnvironmentPath();
      if (envPath?.path) {
        return { path: envPath.path, source: 'active interpreter from the Python extension' };
      }
    }
  }

  // 3. Fallback to "python3" on PATH
  return { path: 'python3', source: 'PATH fallback (no Python extension interpreter)' };
}

/**
 * Emit the DAG refresh that was withheld while MATLAB owned the database.
 *
 * No-op when nothing was withheld: a MATLAB run that wrote nothing (or that
 * failed before writing) shouldn't cost a full graph re-fetch.
 */
function flushDeferredDagRefresh(): void {
  if (!dagPanel) return;
  if (!dagPanel.matlabRuns.takeDeferredRefresh()) return;
  outputChannel.appendLine(
    'MATLAB run finished — applying the deferred DAG refresh',
  );
  dagPanel.postMessage({ method: 'dag_updated', params: {} });
}

function setupDbWatcher(dbPath: string): void {
  // Dispose any previous watcher.
  if (dbWatcher) {
    dbWatcher.dispose();
    dbWatcher = null;
  }
  if (dbWatcherDebounce) {
    clearTimeout(dbWatcherDebounce);
    dbWatcherDebounce = null;
  }

  const dbDir = path.dirname(dbPath);
  const dbBase = path.basename(dbPath);
  // Watch for .duckdb and .duckdb.wal files.
  const pattern = new vscode.RelativePattern(dbDir, dbBase + '*');
  dbWatcher = vscode.workspace.createFileSystemWatcher(pattern);

  const onDbChange = () => {
    if (dbWatcherDebounce) {
      clearTimeout(dbWatcherDebounce);
    }
    dbWatcherDebounce = setTimeout(() => {
      dbWatcherDebounce = null;
      if (!dagPanel) return;
      // MATLAB writes to the WAL throughout a run, not just at the end. A
      // refresh now would fire graph RPCs at a database MATLAB currently
      // holds the file lock on, and every one of them can only fail — so
      // the tracker remembers the change and we refresh once it lets go.
      if (!dagPanel.matlabRuns.noteDbChange()) {
        outputChannel.appendLine(
          'DuckDB file changed while MATLAB owns the database — ' +
          'deferring DAG refresh until the run finishes',
        );
        return;
      }
      outputChannel.appendLine('DuckDB file changed externally — refreshing DAG');
      dagPanel.postMessage({ method: 'dag_updated', params: {} });
    }, 2000);
  };

  dbWatcher.onDidChange(onDbChange);
  dbWatcher.onDidCreate(onDbChange);
}

export function deactivate() {
  if (dbWatcher) {
    dbWatcher.dispose();
    dbWatcher = null;
  }
  if (dbWatcherDebounce) {
    clearTimeout(dbWatcherDebounce);
    dbWatcherDebounce = null;
  }
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
}
