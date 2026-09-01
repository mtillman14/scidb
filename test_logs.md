Starting SciStack server...
  Python: /Users/mitchelltillman/Documents/general-sqlite-database/.venv/bin/python
  DB: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
  Schema keys: [pass, cycle] (new DB)
Spawning: /Users/mitchelltillman/Documents/general-sqlite-database/.venv/bin/python -m scistack_gui.server --db /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb --schema-keys pass,cycle
debugpy listener will start on 127.0.0.1:5678 (attach via "Attach to scistack-gui server" launch config)
0.00s - Debugger warning: It seems that frozen modules are being used, which may
0.00s - make the debugger miss breakpoints. Please pass -Xfrozen_modules=off
0.00s - to python to disable frozen modules.
0.00s - Note: Debugging will proceed. Set PYDEVD_DISABLE_FILE_VALIDATION=1 to disable this validation.
20:07:21 [scistack_gui] debugpy listening on 127.0.0.1:5678 (attach from VS Code)
  Auto-discovering pipeline code...
20:07:21 [scistack_gui] [config] Locating config file (project_path=None, db_path=/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb)
20:07:21 [scistack_gui] [config] No explicit project_path, searching upward from db_path: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:21 [scistack_gui] [config] Searching directory 1: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab
20:07:21 [scistack_gui] [config] Searching directory 2: /Users/mitchelltillman/Documents/Work
20:07:21 [scistack_gui] [config] Searching directory 3: /Users/mitchelltillman/Documents
20:07:21 [scistack_gui] [config] Searching directory 4: /Users/mitchelltillman
20:07:21 [scistack_gui] [config] Searching directory 5: /Users
20:07:21 [scistack_gui] [config] Searching directory 6: /
20:07:21 [scistack_gui] [config] Reached filesystem root, search failed
20:07:21 [scistack_gui] [config] No pyproject.toml/scistack.toml with [tool.scistack] found in ancestors of /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:21 [scistack_gui] [config] No pyproject.toml/scistack.toml found; falling back to folder-scan discovery rooted at /Users/mitchelltillman/Documents/Work/aging-well-abilitylab
20:07:21 [scistack_gui] [config] Folder-scan: walking /Users/mitchelltillman/Documents/Work/aging-well-abilitylab for .py/.m files
20:07:21 [scistack_gui] [config] Folder-scan found 13 .py file(s), 31 .m file(s)
20:07:21 [scistack_gui] [config] Folder-scan configuration built for /Users/mitchelltillman/Documents/Work/aging-well-abilitylab: 13 modules, 31 MATLAB sources
20:07:21 [scistack_gui] [registry] Loading from config at /Users/mitchelltillman/Documents/Work/aging-well-abilitylab
20:07:21 [scistack_gui] [registry] Before load: 0 functions, 0 variables
20:07:21 [scistack_gui] [registry] Clearing function registry
20:07:21 [scistack_gui] [registry] Loading 13 file modules
20:07:21 [scistack_gui] [registry] Importing 13 module files
20:07:21 [scistack_gui] [registry] Processing module 1/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Scanning module for functions: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Registered function: brand_axes from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Registered function: brand_figure from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Registered function: format_legend from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Registered function: format_super_title from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Registered function: format_text_labels from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Registered function: format_ticks from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Registered function: format_title from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Registered function: format_xlabel from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Registered function: format_ylabel from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Registered function: get_current_ax from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Registered function: set_default_font_and_text_color from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Discovered 11 functions from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py: ['brand_axes', 'brand_figure', 'format_legend', 'format_super_title', 'format_text_labels', 'format_ticks', 'format_title', 'format_xlabel', 'format_ylabel', 'get_current_ax', 'set_default_font_and_text_color']
20:07:21 [scistack_gui] [registry] Skipped 1 imported/re-exported callables from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py (not defined there): ['Iterable']
20:07:21 [scistack_gui] [registry] Scanning module for parameters: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Scanning module for path inputs: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py
20:07:21 [scistack_gui] [registry] Loaded module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/apply_branding.py (11 functions)
20:07:21 [scistack_gui] [registry] Processing module 2/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_all.py
20:07:21 [scistack_gui] [registry] Failed to load module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_all.py
Traceback (most recent call last):
  File "/Users/mitchelltillman/Documents/general-sqlite-database/scistack-gui/scistack_gui/registry.py", line 306, in _load_file_modules
    spec.loader.exec_module(mod)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_all.py", line 11, in <module>
    from df_parser import parse_df_rom, parse_df_mmt, parse_df_func
ModuleNotFoundError: No module named 'df_parser'
20:07:21 [scistack_gui] [registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_all.py', 'error': "No module named 'df_parser'"}
20:07:21 [scistack_gui] [registry] Processing module 3/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_10MWT_gait_speeds_confidence_limits.py
20:07:21 [scistack_gui] [registry] Failed to load module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_10MWT_gait_speeds_confidence_limits.py
Traceback (most recent call last):
  File "/Users/mitchelltillman/Documents/general-sqlite-database/scistack-gui/scistack_gui/registry.py", line 306, in _load_file_modules
    spec.loader.exec_module(mod)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_10MWT_gait_speeds_confidence_limits.py", line 8, in <module>
    from apply_branding import *
ModuleNotFoundError: No module named 'apply_branding'
20:07:21 [scistack_gui] [registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_10MWT_gait_speeds_confidence_limits.py', 'error': "No module named 'apply_branding'"}
20:07:21 [scistack_gui] [registry] Processing module 4/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_6MWT_distance_confidence_limits.py
20:07:21 [scistack_gui] [registry] Failed to load module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_6MWT_distance_confidence_limits.py
Traceback (most recent call last):
  File "/Users/mitchelltillman/Documents/general-sqlite-database/scistack-gui/scistack_gui/registry.py", line 306, in _load_file_modules
    spec.loader.exec_module(mod)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_6MWT_distance_confidence_limits.py", line 9, in <module>
    from apply_branding import *
ModuleNotFoundError: No module named 'apply_branding'
20:07:21 [scistack_gui] [registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_6MWT_distance_confidence_limits.py', 'error': "No module named 'apply_branding'"}
20:07:21 [scistack_gui] [registry] Processing module 5/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/df_parser.py
20:07:21 [scistack_gui] [registry] Scanning module for functions: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/df_parser.py
20:07:21 [scistack_gui] [registry] Registered function: clean_value from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/df_parser.py
20:07:21 [scistack_gui] [registry] Registered function: parse_df_func from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/df_parser.py
20:07:21 [scistack_gui] [registry] Registered function: parse_df_mmt from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/df_parser.py
20:07:21 [scistack_gui] [registry] Registered function: parse_df_rom from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/df_parser.py
20:07:21 [scistack_gui] [registry] Registered function: parse_range from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/df_parser.py
20:07:21 [scistack_gui] [registry] Discovered 5 functions from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/df_parser.py: ['clean_value', 'parse_df_func', 'parse_df_mmt', 'parse_df_rom', 'parse_range']
20:07:21 [scistack_gui] [registry] Scanning module for parameters: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/df_parser.py
20:07:21 [scistack_gui] [registry] Scanning module for path inputs: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/df_parser.py
20:07:21 [scistack_gui] [registry] Loaded module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/df_parser.py (5 functions)
20:07:21 [scistack_gui] [registry] Processing module 6/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/font_sizes.py
20:07:21 [scistack_gui] [registry] Scanning module for functions: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/font_sizes.py
20:07:21 [scistack_gui] [registry] Scanning module for parameters: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/font_sizes.py
20:07:21 [scistack_gui] [registry] Scanning module for path inputs: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/font_sizes.py
20:07:21 [scistack_gui] [registry] Loaded module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/font_sizes.py (0 functions)
20:07:21 [scistack_gui] [registry] Processing module 7/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_agonist_antagonist.py
20:07:21 [scistack_gui] [registry] Failed to load module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_agonist_antagonist.py
Traceback (most recent call last):
  File "/Users/mitchelltillman/Documents/general-sqlite-database/scistack-gui/scistack_gui/registry.py", line 306, in _load_file_modules
    spec.loader.exec_module(mod)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_agonist_antagonist.py", line 7, in <module>
    from df_parser import parse_df_mmt
ModuleNotFoundError: No module named 'df_parser'
20:07:21 [scistack_gui] [registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_agonist_antagonist.py', 'error': "No module named 'df_parser'"}
20:07:21 [scistack_gui] [registry] Processing module 8/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_gait_speeds.py
20:07:30 [scistack_gui] [registry] captured stderr during import:
/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_gait_speeds.py:81: UserWarning: Tight layout not applied. The bottom and top margins cannot be made large enough to accommodate all Axes decorations.
  plt.tight_layout()
20:07:30 [scistack_gui] [registry] Failed to load module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_gait_speeds.py
Traceback (most recent call last):
  File "/Users/mitchelltillman/Documents/general-sqlite-database/scistack-gui/scistack_gui/registry.py", line 306, in _load_file_modules
    spec.loader.exec_module(mod)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_gait_speeds.py", line 90, in <module>
    plot_gait(sex, age, speed)
  File "/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_gait_speeds.py", line 85, in plot_gait
    plt.savefig(SAVE_PATH)
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/pyplot.py", line 1346, in savefig
    res = fig.savefig(fname, **kwargs)  # type: ignore[func-returns-value]
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/figure.py", line 3515, in savefig
    self.canvas.print_figure(fname, **kwargs)
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/backend_bases.py", line 2281, in print_figure
    result = print_method(
             ^^^^^^^^^^^^^
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/backend_bases.py", line 2138, in <lambda>
    print_method = functools.wraps(meth)(lambda *args, **kwargs: meth(
                                                                 ^^^^^
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/backends/backend_svg.py", line 1355, in print_svg
    with cbook.open_file_cm(filename, "w", encoding="utf-8") as fh:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/cbook.py", line 589, in open_file_cm
    fh, opened = to_filehandle(path_or_file, mode, True, encoding)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/cbook.py", line 575, in to_filehandle
    fh = open(fname, flag, encoding=encoding)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '/home/mtillman/mnt/rto/Spinal Stim_Stroke R01/Aging Well AbilityLab/Participants/aw_pilot002/plots/gait_speed.svg'
20:07:30 [scistack_gui] [registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_gait_speeds.py', 'error': "[Errno 2] No such file or directory: '/home/mtillman/mnt/rto/Spinal Stim_Stroke R01/Aging Well AbilityLab/Participants/aw_pilot002/plots/gait_speed.svg'"}
20:07:30 [scistack_gui] [registry] Processing module 9/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_tug_times.py
20:07:34 [scistack_gui] [registry] captured stderr during import:
/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_tug_times.py:82: UserWarning: Tight layout not applied. The bottom and top margins cannot be made large enough to accommodate all Axes decorations.
  plt.tight_layout()
20:07:34 [scistack_gui] [registry] Failed to load module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_tug_times.py
Traceback (most recent call last):
  File "/Users/mitchelltillman/Documents/general-sqlite-database/scistack-gui/scistack_gui/registry.py", line 306, in _load_file_modules
    spec.loader.exec_module(mod)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_tug_times.py", line 91, in <module>
    plot_tug(sex, age, speed)
  File "/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_tug_times.py", line 86, in plot_tug
    plt.savefig(SAVE_PATH)
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/pyplot.py", line 1346, in savefig
    res = fig.savefig(fname, **kwargs)  # type: ignore[func-returns-value]
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/figure.py", line 3515, in savefig
    self.canvas.print_figure(fname, **kwargs)
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/backend_bases.py", line 2281, in print_figure
    result = print_method(
             ^^^^^^^^^^^^^
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/backend_bases.py", line 2138, in <lambda>
    print_method = functools.wraps(meth)(lambda *args, **kwargs: meth(
                                                                 ^^^^^
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/backends/backend_agg.py", line 537, in print_png
    self._print_pil(filename_or_obj, "png", pil_kwargs, metadata)
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/backends/backend_agg.py", line 486, in _print_pil
    mpl.image.imsave(
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/matplotlib/image.py", line 1722, in imsave
    image.save(fname, **pil_kwargs)
  File "/Users/mitchelltillman/Documents/general-sqlite-database/.venv/lib/python3.11/site-packages/PIL/Image.py", line 2708, in save
    fp = builtins.open(filename, "w+b")
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '/home/mtillman/mnt/rto/Spinal Stim_Stroke R01/Aging Well AbilityLab/Participants/aw_pilot002/plots/tug_times.png'
20:07:34 [scistack_gui] [registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_tug_times.py', 'error': "[Errno 2] No such file or directory: '/home/mtillman/mnt/rto/Spinal Stim_Stroke R01/Aging Well AbilityLab/Participants/aw_pilot002/plots/tug_times.png'"}
20:07:34 [scistack_gui] [registry] Processing module 10/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_vo2peak_treadmill_running.py
20:07:34 [scistack_gui] [registry] Scanning module for functions: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_vo2peak_treadmill_running.py
20:07:34 [scistack_gui] [registry] Registered function: get_age_group from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_vo2peak_treadmill_running.py
20:07:34 [scistack_gui] [registry] Registered function: plot_vo2peak_with_participant from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_vo2peak_treadmill_running.py
20:07:34 [scistack_gui] [registry] Discovered 2 functions from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_vo2peak_treadmill_running.py: ['get_age_group', 'plot_vo2peak_with_participant']
20:07:34 [scistack_gui] [registry] Scanning module for parameters: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_vo2peak_treadmill_running.py
20:07:34 [scistack_gui] [registry] Scanning module for path inputs: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_vo2peak_treadmill_running.py
20:07:34 [scistack_gui] [registry] Loaded module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_vo2peak_treadmill_running.py (2 functions)
20:07:34 [scistack_gui] [registry] Processing module 11/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plotter.py
20:07:34 [scistack_gui] [registry] Failed to load module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plotter.py
Traceback (most recent call last):
  File "/Users/mitchelltillman/Documents/general-sqlite-database/scistack-gui/scistack_gui/registry.py", line 306, in _load_file_modules
    spec.loader.exec_module(mod)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plotter.py", line 5, in <module>
    from apply_branding import *
ModuleNotFoundError: No module named 'apply_branding'
20:07:34 [scistack_gui] [registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plotter.py', 'error': "No module named 'apply_branding'"}
20:07:34 [scistack_gui] [registry] Processing module 12/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_spm.py
20:07:34 [scistack_gui] [registry] Failed to load module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_spm.py
Traceback (most recent call last):
  File "/Users/mitchelltillman/Documents/general-sqlite-database/scistack-gui/scistack_gui/registry.py", line 306, in _load_file_modules
    spec.loader.exec_module(mod)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_spm.py", line 5, in <module>
    from apply_branding import *
ModuleNotFoundError: No module named 'apply_branding'
20:07:34 [scistack_gui] [registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_spm.py', 'error': "No module named 'apply_branding'"}
20:07:34 [scistack_gui] [registry] Processing module 13/13: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_vo2max.py
20:07:34 [scistack_gui] [registry] Failed to load module file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_vo2max.py
Traceback (most recent call last):
  File "/Users/mitchelltillman/Documents/general-sqlite-database/scistack-gui/scistack_gui/registry.py", line 306, in _load_file_modules
    spec.loader.exec_module(mod)
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_vo2max.py", line 17, in <module>
    from apply_branding import *
ModuleNotFoundError: No module named 'apply_branding'
20:07:34 [scistack_gui] [registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_vo2max.py', 'error': "No module named 'apply_branding'"}
20:07:34 [scistack_gui] [registry] Loading 0 packages
20:07:34 [scistack_gui] [registry] Importing 0 packages
20:07:34 [scistack_gui] [registry] Auto-discovering entry points
20:07:34 [scistack_gui] [registry] Discovering entry points in group: scistack.plugins
20:07:34 [scistack_gui] [registry] Found 0 entry points
20:07:34 [scistack_gui] [registry] After load: 18 functions, 0 variables
20:07:34 [scistack_gui] [registry] Config loading complete
20:07:34 [scistack_gui] [registry] Registry summary: 18 functions, 0 variables
20:07:34 [scistack_gui] [registry] Added functions: ['brand_axes', 'brand_figure', 'clean_value', 'format_legend', 'format_super_title', 'format_text_labels', 'format_ticks', 'format_title', 'format_xlabel', 'format_ylabel', 'get_age_group', 'get_current_ax', 'parse_df_func', 'parse_df_mmt', 'parse_df_rom', 'parse_range', 'plot_vo2peak_with_participant', 'set_default_font_and_text_color']
20:07:34 [scistack_gui] Auto-discovered: 18 functions, 0 variables
  Auto-discovered 18 Python functions, 0 variables
20:07:34 [scistack_gui] [matlab_registry] Loading MATLAB config
20:07:34 [scistack_gui] [matlab_registry] Clearing registries
20:07:34 [scistack_gui] [matlab_registry] Parsing 0 MATLAB function files
20:07:34 [scistack_gui] [matlab_registry] Parsing 0 MATLAB variable files
20:07:34 [scistack_gui] [matlab_registry] Classifying 31 unified MATLAB source file(s)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 1/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/plots/aw_pilot003/data_validation/data_validation.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/plots/aw_pilot003/data_validation/data_validation.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/plots/aw_pilot003/data_validation/data_validation.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/plots/aw_pilot003/data_validation/data_validation.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] No function declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/plots/aw_pilot003/data_validation/data_validation.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 0 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/plots/aw_pilot003/data_validation/data_validation.m
20:07:34 [scistack_gui] [matlab_registry] Skipping non-function/non-variable MATLAB file (folder-scan): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/plots/aw_pilot003/data_validation/data_validation.m
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 2/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/Cosmed_DataCompilation.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/Cosmed_DataCompilation.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/Cosmed_DataCompilation.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/Cosmed_DataCompilation.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] No function declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/Cosmed_DataCompilation.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 0 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/Cosmed_DataCompilation.m
20:07:34 [scistack_gui] [matlab_registry] Skipping non-function/non-variable MATLAB file (folder-scan): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/Cosmed_DataCompilation.m
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 3/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/PCI_f.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/PCI_f.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/PCI_f.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/PCI_f.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: PCI_f
20:07:34 [scistack_gui] [matlab_parser] Function has 2 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function PCI_f has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: PCI_f
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: PCI_f (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/PCI_f.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 4/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/average_cosmed.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/average_cosmed.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/average_cosmed.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/average_cosmed.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: average_cosmed
20:07:34 [scistack_gui] [matlab_parser] Function has 1 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function average_cosmed has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: average_cosmed
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: average_cosmed (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/average_cosmed.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 5/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v10_NewDEVICE.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v10_NewDEVICE.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v10_NewDEVICE.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v10_NewDEVICE.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] No function declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v10_NewDEVICE.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 0 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v10_NewDEVICE.m
20:07:34 [scistack_gui] [matlab_registry] Skipping non-function/non-variable MATLAB file (folder-scan): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v10_NewDEVICE.m
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 6/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] No function declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 0 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9.m
20:07:34 [scistack_gui] [matlab_registry] Skipping non-function/non-variable MATLAB file (folder-scan): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9.m
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 7/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9_Demo_subjects.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9_Demo_subjects.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9_Demo_subjects.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9_Demo_subjects.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] No function declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9_Demo_subjects.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 0 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9_Demo_subjects.m
20:07:34 [scistack_gui] [matlab_registry] Skipping non-function/non-variable MATLAB file (folder-scan): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/cosmed_v9_Demo_subjects.m
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 8/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netDist_f.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netDist_f.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netDist_f.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netDist_f.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: netDist_f
20:07:34 [scistack_gui] [matlab_parser] Function has 1 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function netDist_f has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: netDist_f
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: netDist_f (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netDist_f.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 9/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netEE_f.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netEE_f.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netEE_f.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netEE_f.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: netEE_f
20:07:34 [scistack_gui] [matlab_parser] Function has 1 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function netEE_f has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: netEE_f
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: netEE_f (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netEE_f.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 10/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netVO2_f.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netVO2_f.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netVO2_f.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netVO2_f.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: netVO2_f
20:07:34 [scistack_gui] [matlab_parser] Function has 1 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function netVO2_f has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: netVO2_f
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: netVO2_f (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/Cosmed code/netVO2_f.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 11/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/computeCocontraction.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/computeCocontraction.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/computeCocontraction.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/computeCocontraction.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: computeCocontraction
20:07:34 [scistack_gui] [matlab_parser] Function has 3 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function computeCocontraction has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: computeCocontraction
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: computeCocontraction (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/computeCocontraction.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 12/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/convertXSENStoDelsysCycleIndices.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/convertXSENStoDelsysCycleIndices.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/convertXSENStoDelsysCycleIndices.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/convertXSENStoDelsysCycleIndices.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: convertXSENStoDelsysCycleIndices
20:07:34 [scistack_gui] [matlab_parser] Function has 3 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function convertXSENStoDelsysCycleIndices has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: convertXSENStoDelsysCycleIndices
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: convertXSENStoDelsysCycleIndices (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/convertXSENStoDelsysCycleIndices.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 13/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/ensureAlternatingLRForPilotData.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/ensureAlternatingLRForPilotData.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/ensureAlternatingLRForPilotData.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/ensureAlternatingLRForPilotData.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: ensureAlternatingLRForPilotData
20:07:34 [scistack_gui] [matlab_parser] Function has 1 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function ensureAlternatingLRForPilotData has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: ensureAlternatingLRForPilotData
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: ensureAlternatingLRForPilotData (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/ensureAlternatingLRForPilotData.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 14/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/estimateHeelStrikeIndicesFromEMG.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/estimateHeelStrikeIndicesFromEMG.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/estimateHeelStrikeIndicesFromEMG.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/estimateHeelStrikeIndicesFromEMG.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: estimateHeelStrikeIndicesFromEMG
20:07:34 [scistack_gui] [matlab_parser] Function has 4 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function estimateHeelStrikeIndicesFromEMG has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: estimateHeelStrikeIndicesFromEMG
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: estimateHeelStrikeIndicesFromEMG (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/estimateHeelStrikeIndicesFromEMG.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 15/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/estimateHeelStrikeIndicesFromRF.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/estimateHeelStrikeIndicesFromRF.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/estimateHeelStrikeIndicesFromRF.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/estimateHeelStrikeIndicesFromRF.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: estimateHeelStrikeIndicesFromRF
20:07:34 [scistack_gui] [matlab_parser] Function has 1 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function estimateHeelStrikeIndicesFromRF has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: estimateHeelStrikeIndicesFromRF
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: estimateHeelStrikeIndicesFromRF (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/estimateHeelStrikeIndicesFromRF.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 16/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/exportDataToExcel.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/exportDataToExcel.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/exportDataToExcel.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/exportDataToExcel.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: exportDataToExcel
20:07:34 [scistack_gui] [matlab_parser] Function has 0 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 0 outputs
20:07:34 [scistack_gui] [matlab_parser] Function exportDataToExcel has docstring: True
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: exportDataToExcel
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: exportDataToExcel (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/exportDataToExcel.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 17/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/filterDelsysTable.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/filterDelsysTable.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/filterDelsysTable.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/filterDelsysTable.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: filterDelsysTable
20:07:34 [scistack_gui] [matlab_parser] Function has 5 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function filterDelsysTable has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: filterDelsysTable
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: filterDelsysTable (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/filterDelsysTable.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 18/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/generateDummyHR.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/generateDummyHR.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/generateDummyHR.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/generateDummyHR.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: generateDummyHR
20:07:34 [scistack_gui] [matlab_parser] Function has 3 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function generateDummyHR has docstring: True
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: generateDummyHR
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: generateDummyHR (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/generateDummyHR.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 19/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/mainOneSubject_251117.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/mainOneSubject_251117.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/mainOneSubject_251117.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/mainOneSubject_251117.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] No function declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/mainOneSubject_251117.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 0 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/mainOneSubject_251117.m
20:07:34 [scistack_gui] [matlab_registry] Skipping non-function/non-variable MATLAB file (folder-scan): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/mainOneSubject_251117.m
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 20/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] No function declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 6 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 6 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m
20:07:34 [scistack_gui] WARN: [matlab_registry] PathInput 'emgPathTemplate6MWT' in entities file /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m is not a simple literal construction (references a MATLAB variable/expression) -- cannot statically extract its value, so it won't appear as a canvas node or resolve in generated MATLAB commands.
20:07:34 [scistack_gui] [matlab_registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m', 'error': "PathInput 'emgPathTemplate6MWT' is not a literal construction"}
20:07:34 [scistack_gui] [registry] Registered path input: xsensPathTemplate6MWT from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB PathInput: xsensPathTemplate6MWT (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m) template='6MWT-{pass}.xlsx' root_folder=None
20:07:34 [scistack_gui] WARN: [matlab_registry] PathInput 'grPathTemplate6MWT' in entities file /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m is not a simple literal construction (references a MATLAB variable/expression) -- cannot statically extract its value, so it won't appear as a canvas node or resolve in generated MATLAB commands.
20:07:34 [scistack_gui] [matlab_registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m', 'error': "PathInput 'grPathTemplate6MWT' is not a literal construction"}
20:07:34 [scistack_gui] WARN: [matlab_registry] PathInput 'emgPathTemplate10MWT' in entities file /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m is not a simple literal construction (references a MATLAB variable/expression) -- cannot statically extract its value, so it won't appear as a canvas node or resolve in generated MATLAB commands.
20:07:34 [scistack_gui] [matlab_registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m', 'error': "PathInput 'emgPathTemplate10MWT' is not a literal construction"}
20:07:34 [scistack_gui] WARN: [matlab_registry] PathInput 'xsensPathTemplate10MWT' in entities file /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m is not a simple literal construction (references a MATLAB variable/expression) -- cannot statically extract its value, so it won't appear as a canvas node or resolve in generated MATLAB commands.
20:07:34 [scistack_gui] [matlab_registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m', 'error': "PathInput 'xsensPathTemplate10MWT' is not a literal construction"}
20:07:34 [scistack_gui] [registry] Registered path input: grPathTemplate10MWT from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB PathInput: grPathTemplate10MWT (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m) template='Y:\\Spinal Stim_Stroke R01\\Aging Well AbilityLab\\Participants\\AFL_001\\data\\GAITRite\\10MWT_GR.xlsx' root_folder=None
20:07:34 [scistack_gui] [matlab_registry] Loaded 2 entities from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 21/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_EMG_timeseries.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_EMG_timeseries.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_EMG_timeseries.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_EMG_timeseries.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] No function declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_EMG_timeseries.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 0 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_EMG_timeseries.m
20:07:34 [scistack_gui] [matlab_registry] Skipping non-function/non-variable MATLAB file (folder-scan): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_EMG_timeseries.m
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 22/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] No function declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 0 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike.m
20:07:34 [scistack_gui] [matlab_registry] Skipping non-function/non-variable MATLAB file (folder-scan): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike.m
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 23/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike_cosmed.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike_cosmed.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike_cosmed.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike_cosmed.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] No function declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike_cosmed.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 0 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike_cosmed.m
20:07:34 [scistack_gui] [matlab_registry] Skipping non-function/non-variable MATLAB file (folder-scan): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_vo2max_bike_cosmed.m
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 24/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/mergeFileRows.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/mergeFileRows.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/mergeFileRows.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/mergeFileRows.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: mergeFileRows
20:07:34 [scistack_gui] [matlab_parser] Function has 4 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function mergeFileRows has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: mergeFileRows
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: mergeFileRows (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/mergeFileRows.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 25/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plotAllCyclesTimeseries.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plotAllCyclesTimeseries.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plotAllCyclesTimeseries.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plotAllCyclesTimeseries.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: plotAllCyclesTimeseries
20:07:34 [scistack_gui] [matlab_parser] Function has 3 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function plotAllCyclesTimeseries has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: plotAllCyclesTimeseries
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: plotAllCyclesTimeseries (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plotAllCyclesTimeseries.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 26/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_EMG_timeseries.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_EMG_timeseries.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_EMG_timeseries.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_EMG_timeseries.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: plot_EMG_timeseries
20:07:34 [scistack_gui] [matlab_parser] Function has 2 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 0 outputs
20:07:34 [scistack_gui] [matlab_parser] Function plot_EMG_timeseries has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: plot_EMG_timeseries
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: plot_EMG_timeseries (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_EMG_timeseries.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 27/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_EMG_timeseries_SPM.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_EMG_timeseries_SPM.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_EMG_timeseries_SPM.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_EMG_timeseries_SPM.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: plot_EMG_timeseries_SPM
20:07:34 [scistack_gui] [matlab_parser] Function has 2 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function plot_EMG_timeseries_SPM has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: plot_EMG_timeseries_SPM
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: plot_EMG_timeseries_SPM (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_EMG_timeseries_SPM.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 28/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/saveTables.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/saveTables.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/saveTables.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/saveTables.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: saveTables
20:07:34 [scistack_gui] [matlab_parser] Function has 3 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 0 outputs
20:07:34 [scistack_gui] [matlab_parser] Function saveTables has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: saveTables
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: saveTables (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/saveTables.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 29/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/segmentCycles.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/segmentCycles.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/segmentCycles.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/segmentCycles.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: segmentCycles
20:07:34 [scistack_gui] [matlab_parser] Function has 5 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function segmentCycles has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: segmentCycles
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: segmentCycles (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/segmentCycles.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 30/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/splitMovementIntoReps.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/splitMovementIntoReps.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/splitMovementIntoReps.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/splitMovementIntoReps.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] Found function: splitMovementIntoReps
20:07:34 [scistack_gui] [matlab_parser] Function has 2 parameters
20:07:34 [scistack_gui] [matlab_parser] Function has 1 outputs
20:07:34 [scistack_gui] [matlab_parser] Function splitMovementIntoReps has docstring: False
20:07:34 [scistack_gui] [matlab_parser] Successfully parsed function: splitMovementIntoReps
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB function: splitMovementIntoReps (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/splitMovementIntoReps.m)
20:07:34 [scistack_gui] [matlab_registry] Classifying source file 31/31: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m
20:07:34 [scistack_gui] [matlab_parser] Parsing variable classdef file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m
20:07:34 [scistack_gui] [matlab_parser] Searching for classdef declaration
20:07:34 [scistack_gui] [matlab_parser] No classdef declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m
20:07:34 [scistack_gui] [matlab_parser] Parsing function file: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m
20:07:34 [scistack_gui] [matlab_parser] Computing source hash
20:07:34 [scistack_gui] [matlab_parser] Searching for function declaration
20:07:34 [scistack_gui] [matlab_parser] No function declaration found in /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 2 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m
20:07:34 [scistack_gui] [matlab_parser] Parsed 2 entity declaration(s) from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m
20:07:34 [scistack_gui] WARN: [matlab_registry] PathInput 'emgPathTemplate' in entities file /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m is not a simple literal construction (references a MATLAB variable/expression) -- cannot statically extract its value, so it won't appear as a canvas node or resolve in generated MATLAB commands.
20:07:34 [scistack_gui] [matlab_registry] Recorded load error: {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m', 'error': "PathInput 'emgPathTemplate' is not a literal construction"}
20:07:34 [scistack_gui] [registry] Registered path input: xsensPathTemplate from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m
20:07:34 [scistack_gui] [matlab_registry] Registered MATLAB PathInput: xsensPathTemplate (/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m) template='6MWT-{pass}.xlsx' root_folder=None
20:07:34 [scistack_gui] [matlab_registry] Loaded 1 entity from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m
20:07:34 [scistack_gui] [matlab_registry] MATLAB registry loading complete - 20 functions, 0 variables, 3 path inputs, 0 sweeps
20:07:34 [scistack_gui] MATLAB: 20 functions, 0 variables
  MATLAB: 20 functions, 0 variables
  Opening database...
20:07:34 [scistack_gui] [db] create_db: creating new database at /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb with schema keys: ['pass', 'cycle']
20:07:34 [scistack_gui] [db] validating database does not exist
20:07:34 [scistack_gui] [db] validating schema keys
20:07:34 [scistack_gui] [db] configuring new database with 2 schema key(s)
20:07:34 [sciduck] DuckDB lock ACQUIRED (read_only=False): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _schema ( schema_id INTEGER PRIMARY KEY, schema_level VARCHAR NOT NULL, "pass" VARCHAR, "cycle" VARCHAR )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE SEQUENCE IF NOT EXISTS _schema_id_seq START 1
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _variables ( variable_name VARCHAR PRIMARY KEY, schema_level VARCHAR NOT NULL, dtype VARCHAR, created_at TIMESTAMP DEFAULT current_timestamp, description VARCHAR DEFAULT '' ...(truncated)
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _variable_groups ( group_name VARCHAR NOT NULL, variable_name VARCHAR NOT NULL, PRIMARY KEY (group_name, variable_name) )
20:07:34 [sciduck] _fetchall thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT COUNT(*) FROM _schema
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _registered_types ( type_name VARCHAR PRIMARY KEY, table_name VARCHAR NOT NULL, schema_version INTEGER NOT NULL, registered_at TIMESTAMP DEFAULT current_timestamp )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _record_save ( record_id VARCHAR NOT NULL, timestamp VARCHAR NOT NULL, user_id VARCHAR, PRIMARY KEY (record_id, timestamp) )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS __scidb_schema_overrides ( "pass" VARCHAR, "cycle" VARCHAR, status BOOLEAN NOT NULL, reason TEXT NOT NULL, changed_at TIMESTAMP NOT NULL, changed_by TEXT )
20:07:34 [scidb] ensure_provenance_tables: creating bipartite provenance schema
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _record ( record_id VARCHAR PRIMARY KEY, created_at VARCHAR NOT NULL, type VARCHAR NOT NULL, schema_id INTEGER, content_hash VARCHAR, schema_version INTEGER, excluded BOOLEA...(truncated)
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _constant ( record_id VARCHAR PRIMARY KEY, value_repr VARCHAR, value_type VARCHAR, content_hash VARCHAR )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _invocation ( invocation_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, function_hash VARCHAR NOT NULL, as_table VARCHAR[], distribute BOOLEAN DEFAULT FALSE )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _invocation_input ( invocation_id VARCHAR NOT NULL, param_name VARCHAR NOT NULL, input_record_id VARCHAR NOT NULL, selector VARCHAR, PRIMARY KEY (invocation_id, param_name, ...(truncated)
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _invocation_output ( invocation_id VARCHAR NOT NULL, output_num INTEGER NOT NULL, output_record_id VARCHAR NOT NULL, PRIMARY KEY (invocation_id, output_num) )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _run ( run_id VARCHAR PRIMARY KEY, timestamp VARCHAR NOT NULL, user_id VARCHAR, function_name VARCHAR NOT NULL, where_clause VARCHAR )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _run_invocation ( run_id VARCHAR NOT NULL, invocation_id VARCHAR NOT NULL, PRIMARY KEY (run_id, invocation_id) )
20:07:34 [sciduck] _fetchall thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT column_name FROM information_schema.columns WHERE table_name = '_invocation_input'
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE INDEX IF NOT EXISTS idx_inv_output_rid ON _invocation_output (output_record_id)
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE INDEX IF NOT EXISTS idx_inv_input_inv ON _invocation_input (invocation_id)
20:07:34 [scidb] ensure_provenance_tables: done
20:07:34 [scidb] configure_database: path=/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb, schema_keys=['pass', 'cycle'], schema_key_types={} | python=3.11.11, pid=19558, scidb=0.1.0, scifor=0.1.0, sciduckdb=0.1.0, scilineage=0.1.0, scistacklog=0.1.1.dev28+gbd65589ac.d20260707
20:07:34 [scistack_gui] [db] create_db complete: new database created at /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:34 [scistack_gui] Created database: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb (schema_keys=['pass', 'cycle'])
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:34 [sciduck] _execute thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:34 [sciduck] _fetchall thread=8360009920 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT name, language FROM _pipeline_builtin_functions
20:07:34 [scistack_gui] [builtin_function_service] Replayed persisted builtins: {'python': 0, 'matlab': 0}
20:07:34 [scistack_gui] [startup] checking lockfile staleness for project: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab
20:07:34 [scistack_gui] [startup] no pyproject.toml at /Users/mitchelltillman/Documents/Work/aging-well-abilitylab — skipping lockfile staleness check
20:07:34 [scistack_gui] Startup complete in 13.07s
Server ready — DB: test_afl.duckdb, schema: [pass, cycle]
20:07:34 [scistack_gui] close_initial_connection: releasing startup lock
20:07:34 [sciduck] DuckDB lock RELEASED: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:34 [scistack_gui] DB connection released after startup — MATLAB can now access the file
20:07:34 [scistack_gui] Server ready, waiting for requests on stdin...
20:07:35 [scidb] RPC >> get_info()
20:07:35 [scistack_gui] [db] acquire_db_connection: current state - open=False, refcount=0
20:07:35 [scistack_gui] [db] acquire_db_connection: connection closed, reopening
20:07:35 [sciduck] DuckDB lock ACQUIRED (reopen, read_only=False): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:35 [scistack_gui] [db] acquire_db_connection: successfully reopened connection
20:07:35 [scistack_gui] [db] acquire_db_connection complete: refcount=1, reopened=True
20:07:35 [scidb] RPC << get_info OK (8.6ms)
20:07:35 [scistack_gui] [db] release_db_connection: current refcount=1, open=True
20:07:35 [scistack_gui] [db] release_db_connection: refcount reached 0, closing connection
20:07:35 [sciduck] DuckDB lock RELEASED: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:35 [scistack_gui] [db] release_db_connection complete: refcount=0, closed=True
20:07:35 [scidb] RPC >> list_hypotheses()
20:07:35 [scistack_gui] [db] acquire_db_connection: current state - open=False, refcount=0
20:07:35 [scistack_gui] [db] acquire_db_connection: connection closed, reopening
20:07:35 [sciduck] DuckDB lock ACQUIRED (reopen, read_only=False): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:35 [scidb] RPC >> get_hidden_pipelines()
20:07:35 [scidb] RPC >> get_pipeline(pipeline_id=main)
20:07:35 [scidb] RPC >> get_registry()
20:07:35 [scidb] RPC >> get_path_inputs()
20:07:35 [scistack_gui] [db] acquire_db_connection: successfully reopened connection
20:07:35 [scidb] RPC >> get_notes()
20:07:35 [scistack_gui] [db] acquire_db_connection complete: refcount=1, reopened=True
20:07:35 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=1
20:07:35 [scidb] RPC >> list_pipelines()
20:07:35 [scistack_gui] [db] acquire_db_connection complete: refcount=2, reopened=False
20:07:35 [scidb] RPC >> list_hypotheses()
20:07:35 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=2
20:07:35 [scidb] RPC >> get_hidden_pipelines()
20:07:35 [scistack_gui] [db] acquire_db_connection complete: refcount=3, reopened=False
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:35 [scidb] RPC >> get_schema()
20:07:35 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=3
20:07:35 [scistack_gui] [db] acquire_db_connection complete: refcount=4, reopened=False
20:07:35 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=4
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0012s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:35 [scistack_gui] [db] acquire_db_connection complete: refcount=5, reopened=False
20:07:35 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=5
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0006s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:35 [scistack_gui] [db] acquire_db_connection complete: refcount=6, reopened=False
20:07:35 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=6
20:07:35 [scistack_gui] [db] acquire_db_connection complete: refcount=7, reopened=False
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0033s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:35 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=7
20:07:35 [scistack_gui] [db] acquire_db_connection complete: refcount=8, reopened=False
20:07:35 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=8
20:07:35 [scistack_gui] [db] acquire_db_connection complete: refcount=9, reopened=False
20:07:35 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=9
20:07:35 [scistack_gui] [db] acquire_db_connection complete: refcount=10, reopened=False
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0130s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0126s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0129s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0015s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0017s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0016s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:35 [sciduck] _fetchall thread=6385446912 waited=0.0019s tx_owner=None foreign_tx=False sql=SELECT DISTINCT "pass" FROM _schema WHERE "pass" IS NOT NULL ORDER BY "pass"
20:07:35 [scistack_gui] [layout] Loading layout file from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.layout.json
20:07:35 [scistack_gui] [layout] Layout file does not exist, using empty defaults
20:07:35 [scistack_gui] [layout] Loaded layout file with 0 top-level keys
20:07:35 [scistack_gui] [layout] scoping migration: moving 0 flat position(s) under root scope 'main'
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0024s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0033s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:35 [scidb] RPC << get_path_inputs OK (31.1ms)
20:07:35 [scistack_gui] [layout] Layout has 0 scope(s), 0 constants
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0034s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:35 [scidb] RPC << get_notes OK (23.6ms)
20:07:35 [scistack_gui] [db] release_db_connection: current refcount=10, open=True
20:07:35 [scistack_gui] [db] release_db_connection complete: refcount=9, closed=False
20:07:35 [scistack_gui] [db] release_db_connection: current refcount=9, open=True
20:07:35 [scistack_gui] [db] release_db_connection complete: refcount=8, closed=False
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0037s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:35 [sciduck] _fetchall thread=6385446912 waited=0.0030s tx_owner=None foreign_tx=False sql=SELECT DISTINCT "cycle" FROM _schema WHERE "cycle" IS NOT NULL ORDER BY "cycle"
20:07:35 [scidb] RPC << get_schema OK (19.8ms)
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0022s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:35 [scistack_gui] [db] release_db_connection: current refcount=8, open=True
20:07:35 [scistack_gui] [db] release_db_connection complete: refcount=7, closed=False
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0026s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0060s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0022s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0022s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0014s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0071s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0014s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0014s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0014s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0014s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0012s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0012s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0012s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0025s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0011s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0010s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0010s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0010s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0013s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0013s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0012s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0013s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0013s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0010s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0010s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0010s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0010s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0009s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0012s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0012s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0013s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0013s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0014s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0013s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0011s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0011s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0012s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0012s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0012s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0025s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0033s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0034s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0020s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0045s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0044s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0046s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0047s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:35 [sciduck] _execute thread=6267662336 waited=0.0046s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:35 [sciduck] _fetchall thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT name, language FROM _pipeline_builtin_functions
20:07:35 [scistack_gui] get_registry: 18 python fns (+0 library refs), 20 matlab fns, 0 vars, 14 load errors
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0080s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:35 [scistack_gui] matlab_functions: ['PCI_f', 'average_cosmed', 'computeCocontraction', 'convertXSENStoDelsysCycleIndices', 'ensureAlternatingLRForPilotData', 'estimateHeelStrikeIndicesFromEMG', 'estimateHeelStrikeIndicesFromRF', 'exportDataToExcel', 'filterDelsysTable', 'generateDummyHR', 'mergeFileRows', 'netDist_f', 'netEE_f', 'netVO2_f', 'plotAllCyclesTimeseries', 'plot_EMG_timeseries', 'plot_EMG_timeseries_SPM', 'saveTables', 'segmentCycles', 'splitMovementIntoReps']
20:07:35 [scistack_gui] WARN: get_registry: 14 discovery load error(s): [{'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_all.py', 'error': "No module named 'df_parser'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_10MWT_gait_speeds_confidence_limits.py', 'error': "No module named 'apply_branding'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_6MWT_distance_confidence_limits.py', 'error': "No module named 'apply_branding'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_agonist_antagonist.py', 'error': "No module named 'df_parser'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_gait_speeds.py', 'error': "[Errno 2] No such file or directory: '/home/mtillman/mnt/rto/Spinal Stim_Stroke R01/Aging Well AbilityLab/Participants/aw_pilot002/plots/gait_speed.svg'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_tug_times.py', 'error': "[Errno 2] No such file or directory: '/home/mtillman/mnt/rto/Spinal Stim_Stroke R01/Aging Well AbilityLab/Participants/aw_pilot002/plots/tug_times.png'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plotter.py', 'error': "No module named 'apply_branding'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_spm.py', 'error': "No module named 'apply_branding'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_vo2max.py', 'error': "No module named 'apply_branding'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m', 'error': "PathInput 'emgPathTemplate6MWT' is not a literal construction"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m', 'error': "PathInput 'grPathTemplate6MWT' is not a literal construction"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m', 'error': "PathInput 'emgPathTemplate10MWT' is not a literal construction"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m', 'error': "PathInput 'xsensPathTemplate10MWT' is not a literal construction"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m', 'error': "PathInput 'emgPathTemplate' is not a literal construction"}]
20:07:35 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:35 [scidb] RPC << get_registry OK (57.3ms)
20:07:35 [scistack_gui] [db] release_db_connection: current refcount=7, open=True
20:07:35 [scistack_gui] [db] release_db_connection complete: refcount=6, closed=False
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0065s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0078s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0134s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0097s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:35 [sciduck] _fetchall thread=6234009600 waited=0.0045s tx_owner=None foreign_tx=False sql=SELECT p.pipeline_id, p.name, h.pipeline_id IS NOT NULL FROM _pipelines p LEFT JOIN _hypotheses h ON h.pipeline_id = p.pipeline_id WHERE p.hidden ORDER BY p.name
20:07:35 [scidb] RPC << get_hidden_pipelines OK (68.8ms)
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0042s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:35 [scistack_gui] [db] release_db_connection: current refcount=6, open=True
20:07:35 [scistack_gui] [db] release_db_connection complete: refcount=5, closed=False
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0034s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:35 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0031s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0017s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0058s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:35 [sciduck] _fetchall thread=6217183232 waited=0.0015s tx_owner=None foreign_tx=False sql=SELECT p.pipeline_id, p.name, h.research_question, h.hypothesis_statement, h.evidence_for, h.evidence_against FROM _hypotheses h JOIN _pipelines p ON p.pipeline_id = h.pipeline_id WHERE NOT p.hidden O...(truncated)
20:07:35 [scidb] RPC << list_hypotheses OK (87.6ms)
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0146s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:35 [scistack_gui] [db] release_db_connection: current refcount=5, open=True
20:07:35 [scistack_gui] [db] release_db_connection complete: refcount=4, closed=False
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0155s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0156s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:35 [sciduck] _fetchall thread=6287929344 waited=0.0007s tx_owner=None foreign_tx=False sql=SELECT pipeline_id, name FROM _pipelines WHERE NOT hidden ORDER BY (pipeline_id != ?), name
20:07:35 [sciduck] _execute thread=6368620544 waited=0.0008s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0016s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0016s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:35 [sciduck] _fetchall thread=6368620544 waited=0.0008s tx_owner=None foreign_tx=False sql=SELECT p.pipeline_id, p.name, h.pipeline_id IS NOT NULL FROM _pipelines p LEFT JOIN _hypotheses h ON h.pipeline_id = p.pipeline_id WHERE p.hidden ORDER BY p.name
20:07:35 [scidb] RPC << get_hidden_pipelines OK (73.7ms)
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0011s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:35 [scistack_gui] [db] release_db_connection: current refcount=4, open=True
20:07:35 [scistack_gui] [db] release_db_connection complete: refcount=3, closed=False
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0018s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0003s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0002s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:35 [sciduck] _execute thread=6334967808 waited=0.0003s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:35 [sciduck] _fetchall thread=6334967808 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT p.pipeline_id, p.name, h.research_question, h.hypothesis_statement, h.evidence_for, h.evidence_against FROM _hypotheses h JOIN _pipelines p ON p.pipeline_id = h.pipeline_id WHERE NOT p.hidden O...(truncated)
20:07:35 [scidb] RPC << list_hypotheses OK (79.0ms)
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0025s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:35 [scistack_gui] [db] release_db_connection: current refcount=3, open=True
20:07:35 [scistack_gui] [db] release_db_connection complete: refcount=2, closed=False
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:35 [sciduck] _execute thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:35 [sciduck] _fetchall thread=6287929344 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT use_id, parent_pipeline_id, child_pipeline_id, binding_json FROM _pipeline_uses
20:07:35 [scidb] RPC << list_pipelines OK (89.9ms)
20:07:35 [scistack_gui] [db] release_db_connection: current refcount=2, open=True
20:07:35 [scistack_gui] [db] release_db_connection complete: refcount=1, closed=False
20:07:36 [scistack_gui] [pipeline] Starting graph build orchestration (scope=main)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT node_id FROM _pipeline_hidden_nodes WHERE pipeline_id = ?
20:07:36 [sciduck] _fetchall thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT node_id FROM _pipeline_hidden_combos
20:07:36 [scistack_gui] [pipeline] loaded 0 hidden node ID(s) for scope=main
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT edge_id FROM _pipeline_hidden_edges WHERE pipeline_id = ?
20:07:36 [scistack_gui] [pipeline] loaded 0 hidden edge ID(s) for scope=main
20:07:36 [scistack_gui] [pipeline] Fetching aggregated variants from scidb
20:07:36 [sciduck] _fetchall thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT invocation_id, function_name, as_table, distribute FROM _invocation WHERE function_name != ?
20:07:36 [scistack_gui] [pipeline] fetched data for 0 functions, 0 variables, 0 constants, 0 path inputs
20:07:36 [scistack_gui] [pipeline] Converting to AggregatedData format
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT name, template, root_folder FROM _pipeline_path_input_history ORDER BY name, template
20:07:36 [scistack_gui] [pipeline] Filtering hidden nodes
20:07:36 [scistack_gui] [graph_builder] filter_hidden: filtering 0 hidden node(s) (strip_var_type_values=False)
20:07:36 [scistack_gui] [pipeline] Using record counts from scidb
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT constant_name, value FROM _pipeline_pending_constants
20:07:36 [scistack_gui] [pipeline] loaded 0 pending constant(s)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT edge_id, source, target, source_handle, target_handle FROM _pipeline_edges
20:07:36 [scistack_gui] [pipeline] Computing run states (delegating to run_state)
20:07:36 [scidb] check_multiple_nodes_state: checked 0 nodes, 0 results
20:07:36 [scistack_gui] [run_state] propagate_run_states: processing 0 function call site(s)
20:07:36 [scistack_gui] [run_state] Building variable producer map and propagating states through DAG
20:07:36 [scistack_gui] [run_state] identified 0 variable type(s) with producer(s)
20:07:36 [scistack_gui] [run_state] starting DAG propagation for 0 call site(s)
20:07:36 [scistack_gui] [run_state] DAG propagation complete after 0 iteration(s)
20:07:36 [scistack_gui] [run_state] Building final result mapping
20:07:36 [scistack_gui] [run_state] propagate_run_states complete: 0 total nodes (0 green, 0 pending, 0 red)
20:07:36 [scistack_gui] run_states complete: 0 call sites in 0.4ms (0 green, 0 pending, 0 red)
20:07:36 [scistack_gui] [pipeline] computed run states for 0 nodes
20:07:36 [scistack_gui] [pipeline] Grouping call sites by wiring
20:07:36 [scistack_gui] [run_state] propagate_run_states: processing 0 function call site(s)
20:07:36 [scistack_gui] [run_state] Building variable producer map and propagating states through DAG
20:07:36 [scistack_gui] [run_state] identified 0 variable type(s) with producer(s)
20:07:36 [scistack_gui] [run_state] starting DAG propagation for 0 call site(s)
20:07:36 [scistack_gui] [run_state] DAG propagation complete after 0 iteration(s)
20:07:36 [scistack_gui] [run_state] Building final result mapping
20:07:36 [scistack_gui] [run_state] propagate_run_states complete: 0 total nodes (0 green, 0 pending, 0 red)
20:07:36 [scistack_gui] [graph_builder] filter_hidden: filtering 0 hidden node(s) (strip_var_type_values=True)
20:07:36 [scistack_gui] [pipeline] Building function parameter maps and saved configs
20:07:36 [scistack_gui] [pipeline] building parameter maps for 0 unique function(s)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT node_id, node_type, label, config, pipeline_id FROM _pipeline_nodes
20:07:36 [scistack_gui] [pipeline] loaded 0 manual node(s)
20:07:36 [scistack_gui] [pipeline] matlab_param_to_class={}
20:07:36 [scistack_gui] [pipeline] loaded 0 parameter(s) from registry
20:07:36 [scistack_gui] [pipeline] Building nodes (delegating to graph_builder)
20:07:36 [scistack_gui] [graph_builder] build_variable_nodes: building 0 variable node(s)
20:07:36 [scistack_gui] [graph_builder] built 0 variable node(s)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT const_name, value FROM _pipeline_hidden_constant_values WHERE pipeline_id = ?
20:07:36 [scistack_gui] [graph_builder] build_parameter_nodes: building 0 parameter node(s)
20:07:36 [scistack_gui] [graph_builder] built 0 parameter node(s)
20:07:36 [scistack_gui] [graph_builder] build_path_input_nodes: building 3 path input node(s)
20:07:36 [scistack_gui] [graph_builder] built 3 path input node(s)
20:07:36 [scistack_gui] [graph_builder] build_function_nodes: building 0 function node(s)
20:07:36 [scistack_gui] [graph_builder] built 0 function node(s)
20:07:36 [scistack_gui] [pipeline] built 3 nodes: 0 variable, 0 constant, 3 path input, 0 sweep, 0 function
20:07:36 [scistack_gui] [pipeline] Building edges (delegating to graph_builder)
20:07:36 [scistack_gui] [graph_builder] build_edges: building edges from DB-derived data and manual edges
20:07:36 [scistack_gui] [graph_builder] building variable → function edges
20:07:36 [scistack_gui] [graph_builder] built 0 variable → function edge(s) (0 hidden)
20:07:36 [scistack_gui] [graph_builder] building function → variable edges
20:07:36 [scistack_gui] [graph_builder] built 0 function → variable edge(s) (0 hidden)
20:07:36 [scistack_gui] [graph_builder] building constant → function edges
20:07:36 [scistack_gui] [graph_builder] built 0 constant → function edge(s) (0 hidden)
20:07:36 [scistack_gui] [graph_builder] building pathInput → function edges
20:07:36 [scistack_gui] [graph_builder] built 0 pathInput → function edge(s) (0 hidden)
20:07:36 [scistack_gui] [graph_builder] merging 0 manual edge(s)
20:07:36 [scistack_gui] [graph_builder] added 0 manual edge(s)
20:07:36 [scistack_gui] [graph_builder] build_edges complete: 0 total edges (0 DB-derived, 0 manual, 0 hidden, 0 manual superseded by DB-derived)
20:07:36 [scistack_gui] [pipeline] built 0 edges
20:07:36 [scistack_gui] [pipeline] Merging manual nodes (delegating to graph_builder)
20:07:36 [scistack_gui] [layout] Loading layout file from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.layout.json
20:07:36 [scistack_gui] [layout] Layout file does not exist, using empty defaults
20:07:36 [scistack_gui] [layout] Loaded layout file with 0 top-level keys
20:07:36 [scistack_gui] [layout] scoping migration: moving 0 flat position(s) under root scope 'main'
20:07:36 [scistack_gui] [layout] Layout has 0 scope(s), 0 constants
20:07:36 [scistack_gui] [pipeline] loaded 0 saved position(s) across 0 scope(s)
20:07:36 [scistack_gui] [graph_builder] merge_manual_nodes: processing 0 manual node(s) against 3 existing node(s)
20:07:36 [scistack_gui] [graph_builder] merge_manual_nodes complete: 0 to add, 0 to graduate
20:07:36 [scistack_gui] [pipeline] Executing 0 graduation action(s)
20:07:36 [scistack_gui] [pipeline] Building 0 manual node(s) to add
20:07:36 [scistack_gui] [pipeline] Filtering graph to scope main
20:07:36 [scistack_gui] [scope_filter] scope main: kept 3/3 node(s), 0/0 edge(s)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT use_id, parent_pipeline_id, child_pipeline_id, binding_json FROM _pipeline_uses
20:07:36 [scistack_gui] [pipeline] Graph build complete - assembling final result
20:07:36 [scistack_gui] [pipeline] graph built successfully (scope=main): 3 total nodes (3 pathInputNode), 0 edges
20:07:36 [scidb] RPC << get_pipeline OK (533.9ms)
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=1, open=True
20:07:36 [scistack_gui] [db] release_db_connection: refcount reached 0, closing connection
20:07:36 [sciduck] DuckDB lock RELEASED: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=0, closed=True
20:07:36 [scidb] RPC >> get_layout(pipeline_id=main)
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=False, refcount=0
20:07:36 [scistack_gui] [db] acquire_db_connection: connection closed, reopening
20:07:36 [sciduck] DuckDB lock ACQUIRED (reopen, read_only=False): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:36 [scistack_gui] [db] acquire_db_connection: successfully reopened connection
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=1, reopened=True
20:07:36 [scistack_gui] [layout] Loading layout file from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.layout.json
20:07:36 [scistack_gui] [layout] Layout file does not exist, using empty defaults
20:07:36 [scistack_gui] [layout] Loaded layout file with 0 top-level keys
20:07:36 [scistack_gui] [layout] scoping migration: moving 0 flat position(s) under root scope 'main'
20:07:36 [scistack_gui] [layout] Layout has 0 scope(s), 0 constants
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT node_id, node_type, label, config, pipeline_id FROM _pipeline_nodes WHERE pipeline_id = ?
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT edge_id, source, target, source_handle, target_handle FROM _pipeline_edges
20:07:36 [scidb] RPC << get_layout OK (16.8ms)
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=1, open=True
20:07:36 [scistack_gui] [db] release_db_connection: refcount reached 0, closing connection
20:07:36 [sciduck] DuckDB lock RELEASED: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=0, closed=True
20:07:36 [scidb] RPC >> get_hidden_edges(pipeline_id=main)
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=False, refcount=0
20:07:36 [scistack_gui] [db] acquire_db_connection: connection closed, reopening
20:07:36 [sciduck] DuckDB lock ACQUIRED (reopen, read_only=False): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:36 [scidb] RPC >> get_hidden_ports(pipeline_id=main)
20:07:36 [scistack_gui] [db] acquire_db_connection: successfully reopened connection
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=1, reopened=True
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=1
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=2, reopened=False
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0001s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0013s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT edge_id, source, target, source_handle, target_handle FROM _pipeline_hidden_edges WHERE pipeline_id = ?
20:07:36 [scidb] RPC << get_hidden_edges OK (15.5ms)
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=2, open=True
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=1, closed=False
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0046s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT direction, var_type FROM _pipeline_hidden_ports WHERE pipeline_id = ?
20:07:36 [scidb] RPC << get_hidden_ports OK (17.6ms)
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=1, open=True
20:07:36 [scistack_gui] [db] release_db_connection: refcount reached 0, closing connection
20:07:36 [sciduck] DuckDB lock RELEASED: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=0, closed=True
DuckDB file changed externally — refreshing DAG
20:07:36 [scidb] RPC >> list_hypotheses()
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=False, refcount=0
20:07:36 [scistack_gui] [db] acquire_db_connection: connection closed, reopening
20:07:36 [sciduck] DuckDB lock ACQUIRED (reopen, read_only=False): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:36 [scidb] RPC >> get_hidden_pipelines()
20:07:36 [scidb] RPC >> get_registry()
20:07:36 [scidb] RPC >> get_pipeline(pipeline_id=main)
20:07:36 [scidb] RPC >> get_path_inputs()
20:07:36 [scistack_gui] [db] acquire_db_connection: successfully reopened connection
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=1, reopened=True
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=1
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=2, reopened=False
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=2
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=3, reopened=False
20:07:36 [scidb] RPC >> list_pipelines()
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=3
20:07:36 [scidb] RPC >> list_hypotheses()
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=4, reopened=False
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0025s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [scidb] RPC >> get_hidden_pipelines()
20:07:36 [scistack_gui] [pipeline] Starting graph build orchestration (scope=main)
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=4
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=5, reopened=False
20:07:36 [scidb] RPC << get_path_inputs OK (5.2ms)
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=5
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=6, reopened=False
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=6
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=7, reopened=False
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=7
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=8, reopened=False
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=8, open=True
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=7, closed=False
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0018s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=13035925504 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT p.pipeline_id, p.name, h.research_question, h.hypothesis_statement, h.evidence_for, h.evidence_against FROM _hypotheses h JOIN _pipelines p ON p.pipeline_id = h.pipeline_id WHERE NOT p.hidden O...(truncated)
20:07:36 [scidb] RPC << list_hypotheses OK (9.0ms)
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=7, open=True
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=6, closed=False
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0102s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0086s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT pipeline_id, name FROM _pipelines WHERE NOT hidden ORDER BY (pipeline_id != ?), name
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0052s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0140s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=13052751872 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT p.pipeline_id, p.name, h.pipeline_id IS NOT NULL FROM _pipelines p LEFT JOIN _hypotheses h ON h.pipeline_id = p.pipeline_id WHERE p.hidden ORDER BY p.name
20:07:36 [scidb] RPC << get_hidden_pipelines OK (19.5ms)
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0225s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=6, open=True
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=5, closed=False
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0057s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6234009600 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT use_id, parent_pipeline_id, child_pipeline_id, binding_json FROM _pipeline_uses
20:07:36 [scidb] RPC << list_pipelines OK (24.6ms)
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=5, open=True
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=4, closed=False
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0038s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6284488704 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT name, language FROM _pipeline_builtin_functions
20:07:36 [scistack_gui] get_registry: 18 python fns (+0 library refs), 20 matlab fns, 0 vars, 14 load errors
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0130s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [scistack_gui] matlab_functions: ['PCI_f', 'average_cosmed', 'computeCocontraction', 'convertXSENStoDelsysCycleIndices', 'ensureAlternatingLRForPilotData', 'estimateHeelStrikeIndicesFromEMG', 'estimateHeelStrikeIndicesFromRF', 'exportDataToExcel', 'filterDelsysTable', 'generateDummyHR', 'mergeFileRows', 'netDist_f', 'netEE_f', 'netVO2_f', 'plotAllCyclesTimeseries', 'plot_EMG_timeseries', 'plot_EMG_timeseries_SPM', 'saveTables', 'segmentCycles', 'splitMovementIntoReps']
20:07:36 [scistack_gui] WARN: get_registry: 14 discovery load error(s): [{'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_plot_all.py', 'error': "No module named 'df_parser'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_10MWT_gait_speeds_confidence_limits.py', 'error': "No module named 'apply_branding'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_6MWT_distance_confidence_limits.py', 'error': "No module named 'apply_branding'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_agonist_antagonist.py', 'error': "No module named 'df_parser'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_gait_speeds.py', 'error': "[Errno 2] No such file or directory: '/home/mtillman/mnt/rto/Spinal Stim_Stroke R01/Aging Well AbilityLab/Participants/aw_pilot002/plots/gait_speed.svg'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plot_tug_times.py', 'error': "[Errno 2] No such file or directory: '/home/mtillman/mnt/rto/Spinal Stim_Stroke R01/Aging Well AbilityLab/Participants/aw_pilot002/plots/tug_times.png'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_pt_measures/plotter.py', 'error': "No module named 'apply_branding'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_spm.py', 'error': "No module named 'apply_branding'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/plot_vo2max.py', 'error': "No module named 'apply_branding'"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m', 'error': "PathInput 'emgPathTemplate6MWT' is not a literal construction"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m', 'error': "PathInput 'grPathTemplate6MWT' is not a literal construction"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m', 'error': "PathInput 'emgPathTemplate10MWT' is not a literal construction"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/main_all_analyses.m', 'error': "PathInput 'xsensPathTemplate10MWT' is not a literal construction"}, {'source': '/Users/mitchelltillman/Documents/Work/aging-well-abilitylab/src/tmp_args_for_loadAndProcessAllGait.m', 'error': "PathInput 'emgPathTemplate' is not a literal construction"}]
20:07:36 [scidb] RPC << get_registry OK (33.1ms)
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=4, open=True
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=3, closed=False
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0259s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6250835968 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT p.pipeline_id, p.name, h.pipeline_id IS NOT NULL FROM _pipelines p LEFT JOIN _hypotheses h ON h.pipeline_id = p.pipeline_id WHERE p.hidden ORDER BY p.name
20:07:36 [scidb] RPC << get_hidden_pipelines OK (46.5ms)
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=3, open=True
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=2, closed=False
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0035s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0315s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0021s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT p.pipeline_id, p.name, h.research_question, h.hypothesis_statement, h.evidence_for, h.evidence_against FROM _hypotheses h JOIN _pipelines p ON p.pipeline_id = h.pipeline_id WHERE NOT p.hidden O...(truncated)
20:07:36 [scidb] RPC << list_hypotheses OK (62.6ms)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0036s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=2, open=True
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=1, closed=False
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT node_id FROM _pipeline_hidden_nodes WHERE pipeline_id = ?
20:07:36 [sciduck] _fetchall thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT node_id FROM _pipeline_hidden_combos
20:07:36 [scistack_gui] [pipeline] loaded 0 hidden node ID(s) for scope=main
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT edge_id FROM _pipeline_hidden_edges WHERE pipeline_id = ?
20:07:36 [scistack_gui] [pipeline] loaded 0 hidden edge ID(s) for scope=main
20:07:36 [scistack_gui] [pipeline] Fetching aggregated variants from scidb
20:07:36 [sciduck] _fetchall thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT invocation_id, function_name, as_table, distribute FROM _invocation WHERE function_name != ?
20:07:36 [scistack_gui] [pipeline] fetched data for 0 functions, 0 variables, 0 constants, 0 path inputs
20:07:36 [scistack_gui] [pipeline] Converting to AggregatedData format
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT name, template, root_folder FROM _pipeline_path_input_history ORDER BY name, template
20:07:36 [scistack_gui] [pipeline] Filtering hidden nodes
20:07:36 [scistack_gui] [graph_builder] filter_hidden: filtering 0 hidden node(s) (strip_var_type_values=False)
20:07:36 [scistack_gui] [pipeline] Using record counts from scidb
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT constant_name, value FROM _pipeline_pending_constants
20:07:36 [scistack_gui] [pipeline] loaded 0 pending constant(s)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT edge_id, source, target, source_handle, target_handle FROM _pipeline_edges
20:07:36 [scistack_gui] [pipeline] Computing run states (delegating to run_state)
20:07:36 [scidb] check_multiple_nodes_state: checked 0 nodes, 0 results
20:07:36 [scistack_gui] [run_state] propagate_run_states: processing 0 function call site(s)
20:07:36 [scistack_gui] [run_state] Building variable producer map and propagating states through DAG
20:07:36 [scistack_gui] [run_state] identified 0 variable type(s) with producer(s)
20:07:36 [scistack_gui] [run_state] starting DAG propagation for 0 call site(s)
20:07:36 [scistack_gui] [run_state] DAG propagation complete after 0 iteration(s)
20:07:36 [scistack_gui] [run_state] Building final result mapping
20:07:36 [scistack_gui] [run_state] propagate_run_states complete: 0 total nodes (0 green, 0 pending, 0 red)
20:07:36 [scistack_gui] run_states complete: 0 call sites in 0.3ms (0 green, 0 pending, 0 red)
20:07:36 [scistack_gui] [pipeline] computed run states for 0 nodes
20:07:36 [scistack_gui] [pipeline] Grouping call sites by wiring
20:07:36 [scistack_gui] [run_state] propagate_run_states: processing 0 function call site(s)
20:07:36 [scistack_gui] [run_state] Building variable producer map and propagating states through DAG
20:07:36 [scistack_gui] [run_state] identified 0 variable type(s) with producer(s)
20:07:36 [scistack_gui] [run_state] starting DAG propagation for 0 call site(s)
20:07:36 [scistack_gui] [run_state] DAG propagation complete after 0 iteration(s)
20:07:36 [scistack_gui] [run_state] Building final result mapping
20:07:36 [scistack_gui] [run_state] propagate_run_states complete: 0 total nodes (0 green, 0 pending, 0 red)
20:07:36 [scistack_gui] [graph_builder] filter_hidden: filtering 0 hidden node(s) (strip_var_type_values=True)
20:07:36 [scistack_gui] [pipeline] Building function parameter maps and saved configs
20:07:36 [scistack_gui] [pipeline] building parameter maps for 0 unique function(s)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT node_id, node_type, label, config, pipeline_id FROM _pipeline_nodes
20:07:36 [scistack_gui] [pipeline] loaded 0 manual node(s)
20:07:36 [scistack_gui] [pipeline] matlab_param_to_class={}
20:07:36 [scistack_gui] [pipeline] loaded 0 parameter(s) from registry
20:07:36 [scistack_gui] [pipeline] Building nodes (delegating to graph_builder)
20:07:36 [scistack_gui] [graph_builder] build_variable_nodes: building 0 variable node(s)
20:07:36 [scistack_gui] [graph_builder] built 0 variable node(s)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT const_name, value FROM _pipeline_hidden_constant_values WHERE pipeline_id = ?
20:07:36 [scistack_gui] [graph_builder] build_parameter_nodes: building 0 parameter node(s)
20:07:36 [scistack_gui] [graph_builder] built 0 parameter node(s)
20:07:36 [scistack_gui] [graph_builder] build_path_input_nodes: building 3 path input node(s)
20:07:36 [scistack_gui] [graph_builder] built 3 path input node(s)
20:07:36 [scistack_gui] [graph_builder] build_function_nodes: building 0 function node(s)
20:07:36 [scistack_gui] [graph_builder] built 0 function node(s)
20:07:36 [scistack_gui] [pipeline] built 3 nodes: 0 variable, 0 constant, 3 path input, 0 sweep, 0 function
20:07:36 [scistack_gui] [pipeline] Building edges (delegating to graph_builder)
20:07:36 [scistack_gui] [graph_builder] build_edges: building edges from DB-derived data and manual edges
20:07:36 [scistack_gui] [graph_builder] building variable → function edges
20:07:36 [scistack_gui] [graph_builder] built 0 variable → function edge(s) (0 hidden)
20:07:36 [scistack_gui] [graph_builder] building function → variable edges
20:07:36 [scistack_gui] [graph_builder] built 0 function → variable edge(s) (0 hidden)
20:07:36 [scistack_gui] [graph_builder] building constant → function edges
20:07:36 [scistack_gui] [graph_builder] built 0 constant → function edge(s) (0 hidden)
20:07:36 [scistack_gui] [graph_builder] building pathInput → function edges
20:07:36 [scistack_gui] [graph_builder] built 0 pathInput → function edge(s) (0 hidden)
20:07:36 [scistack_gui] [graph_builder] merging 0 manual edge(s)
20:07:36 [scistack_gui] [graph_builder] added 0 manual edge(s)
20:07:36 [scistack_gui] [graph_builder] build_edges complete: 0 total edges (0 DB-derived, 0 manual, 0 hidden, 0 manual superseded by DB-derived)
20:07:36 [scistack_gui] [pipeline] built 0 edges
20:07:36 [scistack_gui] [pipeline] Merging manual nodes (delegating to graph_builder)
20:07:36 [scistack_gui] [layout] Loading layout file from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.layout.json
20:07:36 [scistack_gui] [layout] Layout file does not exist, using empty defaults
20:07:36 [scistack_gui] [layout] Loaded layout file with 0 top-level keys
20:07:36 [scistack_gui] [layout] scoping migration: moving 0 flat position(s) under root scope 'main'
20:07:36 [scistack_gui] [layout] Layout has 0 scope(s), 0 constants
20:07:36 [scistack_gui] [pipeline] loaded 0 saved position(s) across 0 scope(s)
20:07:36 [scistack_gui] [graph_builder] merge_manual_nodes: processing 0 manual node(s) against 3 existing node(s)
20:07:36 [scistack_gui] [graph_builder] merge_manual_nodes complete: 0 to add, 0 to graduate
20:07:36 [scistack_gui] [pipeline] Executing 0 graduation action(s)
20:07:36 [scistack_gui] [pipeline] Building 0 manual node(s) to add
20:07:36 [scistack_gui] [pipeline] Filtering graph to scope main
20:07:36 [scistack_gui] [scope_filter] scope main: kept 3/3 node(s), 0/0 edge(s)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6267662336 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT use_id, parent_pipeline_id, child_pipeline_id, binding_json FROM _pipeline_uses
20:07:36 [scistack_gui] [pipeline] Graph build complete - assembling final result
20:07:36 [scistack_gui] [pipeline] graph built successfully (scope=main): 3 total nodes (3 pathInputNode), 0 edges
20:07:36 [scidb] RPC << get_pipeline OK (76.3ms)
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=1, open=True
20:07:36 [scistack_gui] [db] release_db_connection: refcount reached 0, closing connection
20:07:36 [sciduck] DuckDB lock RELEASED: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=0, closed=True
20:07:36 [scidb] RPC >> get_layout(pipeline_id=main)
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=False, refcount=0
20:07:36 [scistack_gui] [db] acquire_db_connection: connection closed, reopening
20:07:36 [sciduck] DuckDB lock ACQUIRED (reopen, read_only=False): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:36 [scistack_gui] [db] acquire_db_connection: successfully reopened connection
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=1, reopened=True
20:07:36 [scistack_gui] [layout] Loading layout file from /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.layout.json
20:07:36 [scistack_gui] [layout] Layout file does not exist, using empty defaults
20:07:36 [scistack_gui] [layout] Loaded layout file with 0 top-level keys
20:07:36 [scistack_gui] [layout] scoping migration: moving 0 flat position(s) under root scope 'main'
20:07:36 [scistack_gui] [layout] Layout has 0 scope(s), 0 constants
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT node_id, node_type, label, config, pipeline_id FROM _pipeline_nodes WHERE pipeline_id = ?
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6217183232 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT edge_id, source, target, source_handle, target_handle FROM _pipeline_edges
20:07:36 [scidb] RPC << get_layout OK (16.3ms)
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=1, open=True
20:07:36 [scistack_gui] [db] release_db_connection: refcount reached 0, closing connection
20:07:36 [sciduck] DuckDB lock RELEASED: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:36 [scidb] RPC >> get_hidden_edges(pipeline_id=main)
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=0, closed=True
20:07:36 [scidb] RPC >> get_hidden_ports(pipeline_id=main)
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=False, refcount=0
20:07:36 [scistack_gui] [db] acquire_db_connection: connection closed, reopening
20:07:36 [sciduck] DuckDB lock ACQUIRED (reopen, read_only=False): /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:36 [scistack_gui] [db] acquire_db_connection: successfully reopened connection
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=1, reopened=True
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [scistack_gui] [db] acquire_db_connection: current state - open=True, refcount=1
20:07:36 [scistack_gui] [db] acquire_db_connection complete: refcount=2, reopened=False
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0008s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_nodes ( node_id VARCHAR PRIMARY KEY, node_type VARCHAR NOT NULL, label VARCHAR NOT NULL, config VARCHAR DEFAULT '{}', pipeline_id VARCHAR NOT NULL DEFAULT 'main' )
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_edges ( edge_id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, target_handle VARCHAR )
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_pending_constants ( constant_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (constant_name, value) )
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions ( name VARCHAR PRIMARY KEY, language VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', node_id VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, node_id) )
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6271102976 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT direction, var_type FROM _pipeline_hidden_ports WHERE pipeline_id = ?
20:07:36 [scidb] RPC << get_hidden_ports OK (13.1ms)
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=2, open=True
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=1, closed=False
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0046s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos ( node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL )
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_constant_values ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', const_name VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, const_name, va...(truncated)
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_path_input_history ( name VARCHAR NOT NULL, template VARCHAR NOT NULL, root_folder VARCHAR NOT NULL DEFAULT '', PRIMARY KEY (name, template, root_folder) )
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', edge_id VARCHAR NOT NULL, source VARCHAR NOT NULL, target VARCHAR NOT NULL, source_handle VARCHAR, targ...(truncated)
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports ( pipeline_id VARCHAR NOT NULL DEFAULT 'main', direction VARCHAR NOT NULL, var_type VARCHAR NOT NULL, PRIMARY KEY (pipeline_id, direction, var_type) )
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipelines ( pipeline_id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, hidden BOOLEAN DEFAULT FALSE )
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _pipeline_uses ( use_id VARCHAR PRIMARY KEY, parent_pipeline_id VARCHAR NOT NULL, child_pipeline_id VARCHAR NOT NULL, binding_json VARCHAR DEFAULT '{}' )
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=CREATE TABLE IF NOT EXISTS _hypotheses ( pipeline_id VARCHAR PRIMARY KEY, research_question VARCHAR DEFAULT '', hypothesis_statement VARCHAR DEFAULT '', evidence_for VARCHAR DEFAULT '[]', evidence_aga...(truncated)
20:07:36 [sciduck] _execute thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING
20:07:36 [sciduck] _fetchall thread=6237450240 waited=0.0000s tx_owner=None foreign_tx=False sql=SELECT edge_id, source, target, source_handle, target_handle FROM _pipeline_hidden_edges WHERE pipeline_id = ?
20:07:36 [scidb] RPC << get_hidden_edges OK (17.1ms)
20:07:36 [scistack_gui] [db] release_db_connection: current refcount=1, open=True
20:07:36 [scistack_gui] [db] release_db_connection: refcount reached 0, closing connection
20:07:36 [sciduck] DuckDB lock RELEASED: /Users/mitchelltillman/Documents/Work/aging-well-abilitylab/test_afl.duckdb
20:07:36 [scistack_gui] [db] release_db_connection complete: refcount=0, closed=True
