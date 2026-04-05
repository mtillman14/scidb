/**
 * SciStack GUI — VS Code Extension entry point.
 *
 * activate() is called when the user first triggers a SciStack command.
 * deactivate() is called when the extension is unloaded.
 */

import * as vscode from 'vscode';
import { PythonProcess } from './pythonProcess';
import { DagPanel } from './dagPanel';

let pythonProcess: PythonProcess | null = null;
let dagPanel: DagPanel | null = null;
let outputChannel: vscode.OutputChannel;

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
        const dbUri = await vscode.window.showSaveDialog({
          filters: { 'DuckDB Database': ['duckdb'] },
          title: 'Create SciStack Database',
          saveLabel: 'Create',
        });
        if (!dbUri) return;
        dbPath = dbUri.fsPath;

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

      // Optionally select a pipeline .py module
      const moduleChoice = await vscode.window.showQuickPick(
        ['Select a pipeline module (.py)', 'No module'],
        { placeHolder: 'Do you have a pipeline .py file to load?' }
      );
      let modulePath: string | undefined;
      if (moduleChoice === 'Select a pipeline module (.py)') {
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

      await startPipeline(context, dbPath, modulePath, schemaKeys);
    }
  );

  const refreshModule = vscode.commands.registerCommand(
    'scistack.refreshModule',
    async () => {
      if (!pythonProcess) {
        vscode.window.showWarningMessage('SciStack: No pipeline is open.');
        return;
      }
      try {
        await pythonProcess.request('refresh_module', {});
        vscode.window.showInformationMessage('SciStack: Module refreshed.');
      } catch (err) {
        vscode.window.showErrorMessage(`SciStack: Refresh failed — ${err}`);
      }
    }
  );

  context.subscriptions.push(openPipeline, refreshModule, outputChannel);
}

async function startPipeline(
  context: vscode.ExtensionContext,
  dbPath: string,
  modulePath?: string,
  schemaKeys?: string[],
) {
  // Kill existing process if any
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }

  // Resolve Python interpreter
  const pythonPath = await resolvePythonPath();
  if (!pythonPath) {
    vscode.window.showErrorMessage(
      'SciStack: Could not find a Python interpreter. ' +
      'Install the Python extension or set scistack.pythonPath in settings.'
    );
    return;
  }

  // Start the Python JSON-RPC server
  outputChannel.appendLine(`Starting SciStack server...`);
  outputChannel.appendLine(`  Python: ${pythonPath}`);
  outputChannel.appendLine(`  DB: ${dbPath}`);
  if (modulePath) outputChannel.appendLine(`  Module: ${modulePath}`);
  if (schemaKeys) outputChannel.appendLine(`  Schema keys: [${schemaKeys.join(', ')}] (new DB)`);

  pythonProcess = new PythonProcess(pythonPath, dbPath, modulePath, outputChannel, schemaKeys);

  try {
    const readyParams = await pythonProcess.waitForReady(10000);
    outputChannel.appendLine(
      `Server ready — DB: ${readyParams.db_name}, schema: [${readyParams.schema_keys.join(', ')}]`
    );
  } catch (err) {
    vscode.window.showErrorMessage(`SciStack: Server failed to start — ${err}`);
    pythonProcess.kill();
    pythonProcess = null;
    return;
  }

  // Create or reveal the DAG Webview panel
  if (dagPanel) {
    dagPanel.reveal();
  } else {
    dagPanel = new DagPanel(context, pythonProcess, outputChannel);
    dagPanel.onDidDispose(() => {
      dagPanel = null;
    });
  }

  // Forward push notifications from Python → Webview
  pythonProcess.onNotification((method, params) => {
    if (dagPanel) {
      dagPanel.postMessage({ method, params });
    }
  });

  // Status bar
  const statusItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left, 100
  );
  statusItem.text = `$(database) SciStack: ${dbPath.split('/').pop()}`;
  statusItem.tooltip = dbPath;
  statusItem.show();
}

async function resolvePythonPath(): Promise<string | undefined> {
  // 1. Check extension setting
  const config = vscode.workspace.getConfiguration('scistack');
  const configured = config.get<string>('pythonPath');
  if (configured) return configured;

  // 2. Try the VS Code Python extension
  const pythonExt = vscode.extensions.getExtension('ms-python.python');
  if (pythonExt) {
    if (!pythonExt.isActive) await pythonExt.activate();
    // The Python extension exports an API to get the active interpreter
    const api = pythonExt.exports;
    if (api?.environments?.getActiveEnvironmentPath) {
      const envPath = api.environments.getActiveEnvironmentPath();
      if (envPath?.path) return envPath.path;
    }
  }

  // 3. Fallback to "python3" on PATH
  return 'python3';
}

export function deactivate() {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
}
