1. Move "Runs" to its own area of the GUI so that it's always visible (e.g. bottom left of the canvas). It should be expandable into its own popup window/otherwise expandable to view more info about the previous runs.

2. Move "Hypothesis"/"Research Question" to its own area of the GUI so that it's always visible (e.g. above the canvas). Maybe remove the "Evidence For" and "Evidence Against" text boxes.

3. Move what's currently the "Project" tab on the right sidebar into a popup/other window that appears when a small icon button is clicked. It should probably be renamed to e.g. "Paths", and allow the user to specify paths where Python and/or MATLAB code are stored. OR, use a .env file (not git committed by default) to provide the paths to the codebase.

4. Add default plotting mechanism to plot scalar or 1D numeric data by schema level (e.g. every trial, or average over all trials, or average over all trials and subjects, etc.). Make sure the plots are interactive (i.e. labelling schema ID's, numeric values, etc.)

5. Make all nodes copy-pastable within- and between hypothesis pipelines.

6. Make pipelines translateable to Python/MATLAB/bash, as appropriate.

7. Make pipelines importable/exportable between SciStack users

8. Add a new node type that builds on Constant node types, called "Sweep". It is a parameter sweep node, allowing the user to specify a list of numbers (either directly as a list, or as e.g. a start, end, and step size or number of steps). This would be treated by SciStack as essentially an EachOf() input with each item in the list being one input to EachOf().

9. Clean up sub-pipelines a bit. There should be a mechanism to mark a function input target (i.e. one of the dots on the side of the node that can connect to other nodes) or output variable (the variable itself) to appear as inputs and outputs on the subpipeline node.

10. If two path input (maybe constant and variable nodes too?) nodes are attached to the same function input at the same time, it should be treated as an EachOf() with each input as an EachOf() argument.