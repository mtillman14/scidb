/**
 * Project configuration detection and auto-creation helpers.
 *
 * Before spawning the Python server, we check whether the selected project
 * directory contains a pyproject.toml or scistack.toml.  If neither exists
 * we prompt the user to create a minimal scistack.toml so the server can
 * start with sensible defaults.
 */

import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

export type ConfigStatus = "ready" | "no_config_file";

/**
 * Check whether `dirPath` (or its parent, if it points at a file) contains
 * a pyproject.toml or scistack.toml.
 */
export function checkProjectConfig(dirPath: string): ConfigStatus {
  const resolved = fs.statSync(dirPath, { throwIfNoEntry: false });
  if (!resolved) {
    // Path doesn't exist yet — caller will handle the error later.
    return "ready";
  }

  const dir = resolved.isFile() ? path.dirname(dirPath) : dirPath;

  if (
    fs.existsSync(path.join(dir, "pyproject.toml")) ||
    fs.existsSync(path.join(dir, "scistack.toml"))
  ) {
    return "ready";
  }

  return "no_config_file";
}

/**
 * Create a minimal scistack.toml in `dirPath` with commented-out examples.
 */
export function createScistackToml(dirPath: string): string {
  const filePath = path.join(dirPath, "scistack.toml");
  const content = `# SciStack project configuration
# See documentation for all available options.

# Python pipeline modules (relative paths)
# modules = ["pipelines/my_pipeline.py"]

# Pip-installed packages to scan for pipeline functions
# packages = ["my_scistack_plugin"]

# Auto-discover scistack.plugins entry points (default: true)
# auto_discover = true

# File where 'create_variable' writes new variable classes
# variable_file = "src/vars.py"

# [matlab]
# functions = ["src/"]
# variables = ["src/vars/"]
# variable_dir = "src/vars/"
`;
  fs.writeFileSync(filePath, content, "utf-8");
  return filePath;
}

/**
 * Show a modal warning when no config file is found in `dirPath`.
 *
 * Returns:
 *  - The (possibly unchanged) `dirPath` if the user chose to continue
 *  - `undefined` if the user cancelled
 */
export async function promptForMissingConfig(
  dirPath: string,
  outputChannel: vscode.OutputChannel
): Promise<string | undefined> {
  const createOption = "Create scistack.toml";
  const continueOption = "Continue anyway";

  const choice = await vscode.window.showWarningMessage(
    `No pyproject.toml or scistack.toml found in "${path.basename(
      dirPath
    )}". ` + "The server needs a config file to discover pipeline code.",
    { modal: true },
    createOption,
    continueOption
  );

  if (choice === createOption) {
    const filePath = createScistackToml(dirPath);
    outputChannel.appendLine(`Created ${filePath}`);
    // Open the new file in the editor so the user can customise it.
    const doc = await vscode.workspace.openTextDocument(filePath);
    await vscode.window.showTextDocument(doc);
    return dirPath;
  }

  if (choice === continueOption) {
    outputChannel.appendLine(
      "Continuing without config file — server will use defaults if possible."
    );
    return dirPath;
  }

  // User dismissed the dialog.
  return undefined;
}
