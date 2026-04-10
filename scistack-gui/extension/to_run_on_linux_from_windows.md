# Open GUI
1. SSH into the Linux machine.
2. Set scistack-gui/extension as the workspace root
3. Click "Launch Extension" in the "Run and Debug" tab, with the below "launch.json"
4. It should open a new VS Code window which will also ask you to SSH in.
5. Open the Command Palette and open the SciStack: Open Pipeline option.

# Update extension
1. Navigate to the scistack-gui/extension folder
2. Run `powershell -ExecutionPolicy Bypass -File .\build-on-windows.ps1`
3. Reload the window to reload the extension.

launch.json:
```json
{
  "version": "0.2.0",
  "configurations": [  
    {
      "name": "Run Extension",
      "type": "extensionHost",
      "request": "launch",
      "args": ["--extensionDevelopmentPath=${workspaceFolder}"],
      "outFiles": ["${workspaceFolder}/dist/**/*.js"]
    }
  ]
}
```