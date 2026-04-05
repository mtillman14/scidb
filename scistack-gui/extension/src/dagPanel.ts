/**
 * DagPanel — manages the Webview panel that hosts the React DAG UI.
 *
 * Responsibilities:
 *   - Creates a WebviewPanel with the React bundle loaded
 *   - Generates HTML with a Content Security Policy (CSP)
 *   - Forwards messages between the Webview ↔ Python process
 *   - Handles panel lifecycle (dispose, reveal)
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { PythonProcess } from './pythonProcess';

export class DagPanel {
  private panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];
  private disposeCallbacks: (() => void)[] = [];

  constructor(
    private context: vscode.ExtensionContext,
    private pythonProcess: PythonProcess,
    private outputChannel: vscode.OutputChannel,
  ) {
    this.panel = vscode.window.createWebviewPanel(
      'scistack.dag',
      'SciStack Pipeline',
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [
          vscode.Uri.file(path.join(context.extensionPath, 'dist', 'webview')),
        ],
      }
    );

    this.panel.webview.html = this.getHtml();

    // Forward messages from Webview → Python
    this.panel.webview.onDidReceiveMessage(
      async (msg: Record<string, unknown>) => {
        try {
          const result = await this.pythonProcess.request(
            msg.method as string,
            (msg.params ?? {}) as Record<string, unknown>,
          );
          // Send response back to Webview with the matching id
          this.panel.webview.postMessage({
            id: msg.id,
            result,
          });
        } catch (err) {
          this.panel.webview.postMessage({
            id: msg.id,
            error: { message: String(err) },
          });
        }
      },
      undefined,
      this.disposables,
    );

    this.panel.onDidDispose(() => {
      this.disposables.forEach(d => d.dispose());
      for (const cb of this.disposeCallbacks) cb();
    }, null, this.disposables);
  }

  /**
   * Post a notification message to the Webview (from Python push notifications).
   */
  postMessage(msg: Record<string, unknown>): void {
    this.panel.webview.postMessage(msg);
  }

  /**
   * Reveal the panel if it's hidden.
   */
  reveal(): void {
    this.panel.reveal(vscode.ViewColumn.One);
  }

  /**
   * Register a callback for when the panel is disposed.
   */
  onDidDispose(callback: () => void): void {
    this.disposeCallbacks.push(callback);
  }

  private getHtml(): string {
    const webviewDir = path.join(this.context.extensionPath, 'dist', 'webview');
    const webview = this.panel.webview;

    // Resolve the built JS and CSS assets
    const scriptUri = webview.asWebviewUri(
      vscode.Uri.file(path.join(webviewDir, 'index.js'))
    );
    const styleUri = webview.asWebviewUri(
      vscode.Uri.file(path.join(webviewDir, 'index.css'))
    );

    // CSP nonce for inline scripts
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
}

function getNonce(): string {
  let text = '';
  const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}
