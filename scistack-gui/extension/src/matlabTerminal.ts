/**
 * MathWorks MATLAB terminal integration.
 *
 * Detects whether the MathWorks VS Code extension is installed, opens the
 * MATLAB command window, and sends commands to it.
 */

import * as vscode from 'vscode';

/**
 * Check whether the MathWorks MATLAB extension is installed.
 */
export function isMatlabExtensionAvailable(): boolean {
  return vscode.extensions.getExtension('MathWorks.language-matlab') !== undefined;
}

/**
 * Send a command string to the MathWorks MATLAB terminal.
 *
 * Opens the MATLAB command window (if not already open), finds the terminal,
 * and sends the text.
 *
 * @returns true if the command was sent, false if the terminal is unavailable.
 */
export async function runInMatlabTerminal(
  command: string,
  outputChannel?: vscode.OutputChannel,
): Promise<boolean> {
  if (!isMatlabExtensionAvailable()) {
    return false;
  }

  try {
    // The MathWorks extension provides this command to open the MATLAB
    // command window as an integrated terminal.
    await vscode.commands.executeCommand('matlab.openCommandWindow');

    // Find the MATLAB terminal (created by the MathWorks extension).
    const terminal = vscode.window.terminals.find(t => t.name === 'MATLAB');
    if (!terminal) {
      outputChannel?.appendLine(
        'MathWorks extension found but MATLAB terminal not available.'
      );
      return false;
    }

    terminal.sendText(command);
    terminal.show();
    return true;
  } catch (err) {
    outputChannel?.appendLine(`Failed to send to MATLAB terminal: ${err}`);
    return false;
  }
}
