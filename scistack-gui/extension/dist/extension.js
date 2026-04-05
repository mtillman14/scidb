"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/extension.ts
var extension_exports = {};
__export(extension_exports, {
  activate: () => activate,
  deactivate: () => deactivate
});
module.exports = __toCommonJS(extension_exports);
var vscode2 = __toESM(require("vscode"));

// src/pythonProcess.ts
var import_child_process = require("child_process");
var readline = __toESM(require("readline"));
var PythonProcess = class {
  constructor(pythonPath, dbPath, modulePath, outputChannel2, schemaKeys) {
    this.outputChannel = outputChannel2;
    this.nextId = 1;
    this.pending = /* @__PURE__ */ new Map();
    this.notificationHandlers = [];
    this.readyResolve = null;
    this.readyReject = null;
    const args = ["-m", "scistack_gui.server", "--db", dbPath];
    if (modulePath) {
      args.push("--module", modulePath);
    }
    if (schemaKeys && schemaKeys.length > 0) {
      args.push("--schema-keys", schemaKeys.join(","));
    }
    this.outputChannel.appendLine(`Spawning: ${pythonPath} ${args.join(" ")}`);
    this.proc = (0, import_child_process.spawn)(pythonPath, args, {
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env }
    });
    const rl = readline.createInterface({ input: this.proc.stdout });
    rl.on("line", (line) => this.handleLine(line));
    this.proc.stderr?.on("data", (data) => {
      this.outputChannel.appendLine(data.toString().trimEnd());
    });
    this.proc.on("exit", (code, signal) => {
      const msg = `Python process exited (code=${code}, signal=${signal})`;
      this.outputChannel.appendLine(msg);
      for (const [, pending] of this.pending) {
        pending.reject(new Error(msg));
      }
      this.pending.clear();
      if (this.readyReject) {
        this.readyReject(new Error(msg));
        this.readyResolve = null;
        this.readyReject = null;
      }
    });
    this.proc.on("error", (err) => {
      this.outputChannel.appendLine(`Python process error: ${err.message}`);
      if (this.readyReject) {
        this.readyReject(err);
        this.readyResolve = null;
        this.readyReject = null;
      }
    });
  }
  /**
   * Wait for the Python server to signal readiness.
   * Returns the ready notification params (db_name, schema_keys).
   */
  waitForReady(timeoutMs) {
    return new Promise((resolve, reject) => {
      this.readyResolve = resolve;
      this.readyReject = reject;
      setTimeout(() => {
        if (this.readyReject) {
          this.readyReject(new Error(`Python server did not become ready within ${timeoutMs}ms`));
          this.readyResolve = null;
          this.readyReject = null;
        }
      }, timeoutMs);
    });
  }
  /**
   * Send a JSON-RPC request and return a promise for the result.
   */
  request(method, params) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      const msg = JSON.stringify({ jsonrpc: "2.0", method, params, id });
      this.proc.stdin?.write(msg + "\n", (err) => {
        if (err) {
          this.pending.delete(id);
          reject(err);
        }
      });
    });
  }
  /**
   * Register a handler for push notifications from Python.
   */
  onNotification(handler) {
    this.notificationHandlers.push(handler);
  }
  /**
   * Kill the Python process.
   */
  kill() {
    this.proc.kill();
  }
  handleLine(line) {
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      this.outputChannel.appendLine(`[stdout non-JSON] ${line}`);
      return;
    }
    if ("id" in msg && msg.id !== null && msg.id !== void 0) {
      const id = msg.id;
      const pending = this.pending.get(id);
      if (pending) {
        this.pending.delete(id);
        if ("error" in msg) {
          const err = msg.error;
          pending.reject(new Error(err.message));
        } else {
          pending.resolve(msg.result);
        }
      }
      return;
    }
    const method = msg.method;
    const params = msg.params ?? {};
    if (method === "ready" && this.readyResolve) {
      this.readyResolve(params);
      this.readyResolve = null;
      this.readyReject = null;
      return;
    }
    if (method === "error") {
      this.outputChannel.appendLine(`Server error: ${params.message}`);
      if (this.readyReject) {
        this.readyReject(new Error(params.message));
        this.readyResolve = null;
        this.readyReject = null;
      }
      return;
    }
    for (const handler of this.notificationHandlers) {
      handler(method, params);
    }
  }
};

// src/dagPanel.ts
var vscode = __toESM(require("vscode"));
var path = __toESM(require("path"));
var DagPanel = class {
  constructor(context, pythonProcess2, outputChannel2) {
    this.context = context;
    this.pythonProcess = pythonProcess2;
    this.outputChannel = outputChannel2;
    this.disposables = [];
    this.disposeCallbacks = [];
    this.panel = vscode.window.createWebviewPanel(
      "scistack.dag",
      "SciStack Pipeline",
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [
          vscode.Uri.file(path.join(context.extensionPath, "dist", "webview"))
        ]
      }
    );
    this.panel.webview.html = this.getHtml();
    this.panel.webview.onDidReceiveMessage(
      async (msg) => {
        try {
          const result = await this.pythonProcess.request(
            msg.method,
            msg.params ?? {}
          );
          this.panel.webview.postMessage({
            id: msg.id,
            result
          });
        } catch (err) {
          this.panel.webview.postMessage({
            id: msg.id,
            error: { message: String(err) }
          });
        }
      },
      void 0,
      this.disposables
    );
    this.panel.onDidDispose(() => {
      this.disposables.forEach((d) => d.dispose());
      for (const cb of this.disposeCallbacks)
        cb();
    }, null, this.disposables);
  }
  /**
   * Post a notification message to the Webview (from Python push notifications).
   */
  postMessage(msg) {
    this.panel.webview.postMessage(msg);
  }
  /**
   * Reveal the panel if it's hidden.
   */
  reveal() {
    this.panel.reveal(vscode.ViewColumn.One);
  }
  /**
   * Register a callback for when the panel is disposed.
   */
  onDidDispose(callback) {
    this.disposeCallbacks.push(callback);
  }
  getHtml() {
    const webviewDir = path.join(this.context.extensionPath, "dist", "webview");
    const webview = this.panel.webview;
    const scriptUri = webview.asWebviewUri(
      vscode.Uri.file(path.join(webviewDir, "index.js"))
    );
    const styleUri = webview.asWebviewUri(
      vscode.Uri.file(path.join(webviewDir, "index.css"))
    );
    const nonce = getNonce();
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'none';
                 style-src ${webview.cspSource} 'unsafe-inline';
                 script-src 'nonce-${nonce}';
                 img-src ${webview.cspSource} data:;
                 font-src ${webview.cspSource};" />
  <link rel="stylesheet" href="${styleUri}" />
  <title>SciStack Pipeline</title>
  <style>
    html, body, #root {
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
    }
  </style>
</head>
<body>
  <div id="root"></div>
  <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
  }
};
function getNonce() {
  let text = "";
  const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}

// src/extension.ts
var pythonProcess = null;
var dagPanel = null;
var outputChannel;
function activate(context) {
  outputChannel = vscode2.window.createOutputChannel("SciStack");
  const openPipeline = vscode2.commands.registerCommand(
    "scistack.openPipeline",
    async () => {
      const dbChoice = await vscode2.window.showQuickPick(
        ["Open existing database", "Create new database"],
        { placeHolder: "SciStack: Open or create a .duckdb file?" }
      );
      if (!dbChoice)
        return;
      let dbPath;
      let schemaKeys;
      if (dbChoice === "Open existing database") {
        const dbUris = await vscode2.window.showOpenDialog({
          canSelectFiles: true,
          canSelectFolders: false,
          canSelectMany: false,
          filters: { "DuckDB Database": ["duckdb"] },
          title: "Select SciStack Database"
        });
        if (!dbUris || dbUris.length === 0)
          return;
        dbPath = dbUris[0].fsPath;
      } else {
        const dbUri = await vscode2.window.showSaveDialog({
          filters: { "DuckDB Database": ["duckdb"] },
          title: "Create SciStack Database",
          saveLabel: "Create"
        });
        if (!dbUri)
          return;
        dbPath = dbUri.fsPath;
        const keysInput = await vscode2.window.showInputBox({
          prompt: "Schema keys (comma-separated, top-down)",
          placeHolder: "e.g. subject, session",
          validateInput: (v) => {
            const parts = v.split(",").map((s) => s.trim()).filter(Boolean);
            return parts.length === 0 ? "Provide at least one schema key" : null;
          }
        });
        if (!keysInput)
          return;
        schemaKeys = keysInput.split(",").map((s) => s.trim()).filter(Boolean);
      }
      const moduleChoice = await vscode2.window.showQuickPick(
        ["Select a pipeline module (.py)", "No module"],
        { placeHolder: "Do you have a pipeline .py file to load?" }
      );
      let modulePath;
      if (moduleChoice === "Select a pipeline module (.py)") {
        const moduleUris = await vscode2.window.showOpenDialog({
          canSelectFiles: true,
          canSelectFolders: false,
          canSelectMany: false,
          filters: { "Python": ["py"] },
          title: "Select Pipeline Module"
        });
        if (moduleUris && moduleUris.length > 0) {
          modulePath = moduleUris[0].fsPath;
        }
      }
      await startPipeline(context, dbPath, modulePath, schemaKeys);
    }
  );
  const refreshModule = vscode2.commands.registerCommand(
    "scistack.refreshModule",
    async () => {
      if (!pythonProcess) {
        vscode2.window.showWarningMessage("SciStack: No pipeline is open.");
        return;
      }
      try {
        await pythonProcess.request("refresh_module", {});
        vscode2.window.showInformationMessage("SciStack: Module refreshed.");
      } catch (err) {
        vscode2.window.showErrorMessage(`SciStack: Refresh failed \u2014 ${err}`);
      }
    }
  );
  context.subscriptions.push(openPipeline, refreshModule, outputChannel);
}
async function startPipeline(context, dbPath, modulePath, schemaKeys) {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
  const pythonPath = await resolvePythonPath();
  if (!pythonPath) {
    vscode2.window.showErrorMessage(
      "SciStack: Could not find a Python interpreter. Install the Python extension or set scistack.pythonPath in settings."
    );
    return;
  }
  outputChannel.appendLine(`Starting SciStack server...`);
  outputChannel.appendLine(`  Python: ${pythonPath}`);
  outputChannel.appendLine(`  DB: ${dbPath}`);
  if (modulePath)
    outputChannel.appendLine(`  Module: ${modulePath}`);
  if (schemaKeys)
    outputChannel.appendLine(`  Schema keys: [${schemaKeys.join(", ")}] (new DB)`);
  pythonProcess = new PythonProcess(pythonPath, dbPath, modulePath, outputChannel, schemaKeys);
  try {
    const readyParams = await pythonProcess.waitForReady(1e4);
    outputChannel.appendLine(
      `Server ready \u2014 DB: ${readyParams.db_name}, schema: [${readyParams.schema_keys.join(", ")}]`
    );
  } catch (err) {
    vscode2.window.showErrorMessage(`SciStack: Server failed to start \u2014 ${err}`);
    pythonProcess.kill();
    pythonProcess = null;
    return;
  }
  if (dagPanel) {
    dagPanel.reveal();
  } else {
    dagPanel = new DagPanel(context, pythonProcess, outputChannel);
    dagPanel.onDidDispose(() => {
      dagPanel = null;
    });
  }
  pythonProcess.onNotification((method, params) => {
    if (dagPanel) {
      dagPanel.postMessage({ method, params });
    }
  });
  const statusItem = vscode2.window.createStatusBarItem(
    vscode2.StatusBarAlignment.Left,
    100
  );
  statusItem.text = `$(database) SciStack: ${dbPath.split("/").pop()}`;
  statusItem.tooltip = dbPath;
  statusItem.show();
}
async function resolvePythonPath() {
  const config = vscode2.workspace.getConfiguration("scistack");
  const configured = config.get("pythonPath");
  if (configured)
    return configured;
  const pythonExt = vscode2.extensions.getExtension("ms-python.python");
  if (pythonExt) {
    if (!pythonExt.isActive)
      await pythonExt.activate();
    const api = pythonExt.exports;
    if (api?.environments?.getActiveEnvironmentPath) {
      const envPath = api.environments.getActiveEnvironmentPath();
      if (envPath?.path)
        return envPath.path;
    }
  }
  return "python3";
}
function deactivate() {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
}
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  activate,
  deactivate
});
//# sourceMappingURL=extension.js.map
