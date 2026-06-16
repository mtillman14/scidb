# Building These Docs

<!-- Ground truth (source win over prose). Verified against:
     mkdocs.yml (material theme; nav tree; navigation.tabs/indexes; pymdownx extensions;
     exclude_docs for claude/); docs/requirements.txt
     (mkdocs>=1.5, mkdocs-material>=9.0); .readthedocs.yaml (ubuntu-22.04, python 3.11,
     mkdocs configuration: mkdocs.yml, install docs/requirements.txt).
     Local venv at .venv has mkdocs + mkdocs-material installed. -->

This documentation is a [MkDocs](https://www.mkdocs.org/) site using the
[Material](https://squidfunk.github.io/mkdocs-material/) theme, published on
[Read the Docs](https://readthedocs.org/).

## Prerequisites

```bash
pip install -r docs/requirements.txt   # mkdocs + mkdocs-material
```

## Preview and build locally

```bash
mkdocs serve            # live preview at http://127.0.0.1:8000 (reloads on save)
mkdocs build --strict   # one-shot build; FAILS on broken nav or links
```

Always run `--strict` before pushing: it turns broken internal links and pages
missing from the navigation into errors, which is exactly the CI gate Read the
Docs applies.

## How the site is configured

Everything lives in `mkdocs.yml`:

- **`nav`** — the section/page tree. Adding a page means adding both the file under
  `docs/` and an entry here; a file not in `nav` is excluded from the build.
- **`theme.features`** — the reading experience: top-level areas render as header
  tabs (`navigation.tabs`), each area can have its own landing page
  (`navigation.indexes`), and dual-language examples use linked Python/MATLAB
  content tabs (`content.tabs.link`).
- **`markdown_extensions`** — the authoring features pages rely on: admonitions,
  collapsible blocks (`pymdownx.details`), tabbed code, tables, task lists, and
  emoji/status icons.
- **`exclude_docs`** — internal engineering notes under `docs/claude/` are kept
  in the repo but excluded from the published site.

## Authoring conventions

- **Dual-language examples** use tabbed blocks so Python and MATLAB switch
  together site-wide:

    ```markdown
    === "Python"
        ```python
        ...
        ```
    === "MATLAB"
        ```matlab
        ...
        ```
    ```

- **Tests are the source of truth.** Page prose is reconciled against each
  package's `tests/` directory; when older prose disagrees with the tests, the
  tests win. New or rewritten pages carry a short HTML comment near the top citing
  the test/source files they were verified against.

## Read the Docs

`.readthedocs.yaml` pins the build (Ubuntu 22.04, Python 3.11), points RTD at
`mkdocs.yml`, and installs `docs/requirements.txt`. Pushes to the connected
branch trigger a rebuild automatically.

**Next:** [Contributing & Dev Setup](contributing.md) ·
[FAQ & Troubleshooting](faq.md)
