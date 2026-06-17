# Plotting leaf nodes (`plot_` functions)

Plots and statistics are the **leaf nodes** of a processing pipeline: they
consume saved variables and emit an artifact (an image file) rather than new
data to process further. scidb gives plotting functions first-class support so
they participate in the same `for_each` iteration, lineage, and `skip_computed`
machinery as any other step — while storing the plot's **path**, not its bytes.

## Authoring a plot function

A function is treated as a plotting leaf when its name starts with `plot_`.
It must be given a `PathOutput` input naming where the figure goes, and it
returns a matplotlib `Figure`:

```python
from scidb import for_each, PathOutput, BaseVariable

class PlotFigure(BaseVariable):
    schema_version = 1

def plot_timeseries(signal, filename, subject=None, signal_limits=None):
    fig, ax = plt.subplots()
    ax.plot(signal)
    if subject is not None:
        ax.set_title(f"subject {subject}")
    if signal_limits is not None:
        ax.set_ylim(*signal_limits)
    return fig            # framework saves + closes it, stores the path

for_each(
    plot_timeseries,
    inputs={"signal": RawSignal,
            "filename": PathOutput("plots/{subject}_{trial}.png")},
    outputs=[PlotFigure],
    share_limits={"signal": ["subject"]},
    subject=["1", "2"], trial=["1", "2", "3"],
)

PlotFigure.load(subject="1", trial="2")   # -> "plots/1_2.png"
```

## What the framework does

Detection and wrapping live in `scidb/foreach.py`:

- **Detection** (`Step 1.55`): `fn.__name__.startswith("plot_")`. The single
  `PathOutput` input is located; if absent, `for_each` raises.
- **Figure wrapper** (`_make_plot_wrapper`): wraps the user fn so that, per
  combo, it calls the fn, saves the returned Figure to the resolved
  `PathOutput` path (`fig.savefig`), **closes** the figure (`plt.close`, to
  bound memory across many combos), and returns the path **string**. If the fn
  already returns a `str`/`Path` (it saved the figure itself), that passes
  through. The wrapper uses `functools.wraps`, so the original name, signature,
  and `__wrapped__` are preserved for combo-metadata injection and function
  hashing.
- **Combo-metadata injection** is enabled for plot functions, so they may
  accept schema keys (`subject`, `trial`, …) as kwargs (guarded — only injected
  if the signature accepts them).
- **Storage**: the returned path string flows through the *normal* lineage +
  save path (not the lineage-only `generated:` mode), so each plot is a
  queryable `VARCHAR` record with full call-site provenance and a
  `lineage_hash`. `skip_computed=True` therefore skips re-rendering a plot whose
  inputs/function are unchanged.

## Shared axis limits (`share_limits`)

`share_limits={"input": [schema_keys_to_hold_fixed]}` makes every combo in a
group share an axis range. The prepass lives in **scifor** (`scifor/foreach.py`,
`_compute_shared_limits`), which holds the loaded DataFrames and combos:

- Group the named input's data by the held-fixed keys (e.g. `subject`).
- Compute each group's global numeric `(min, max)` across all *other* iterated
  keys (e.g. across every `trial`), flattening array-valued cells.
- Inject `{input}_limits=(min, max)` into each call — **only if** the function
  accepts that keyword (or has `**kwargs`).

So `share_limits={"signal": ["subject"]}` gives every per-trial plot within a
subject the same `signal_limits`, and a different one per subject. It is general
(not plot-specific): any function accepting `{input}_limits` receives it.

## Deliberately out of scope (v1)

- **Auto-creating output directories** — the `PathOutput` parent dir must
  exist; `fig.savefig` errors otherwise.
- **`stat_` functions** — a parallel convention for statistics leaves is a
  natural follow-on but not implemented.

## Tests

`scidb/tests/test_plotting.py`: files written + path records queryable;
`share_limits` produces identical per-subject limits that differ across
subjects; a second identical run skips re-rendering via `skip_computed`.
