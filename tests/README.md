# Tests

Placeholder for the project's test suite.

There are currently no automated tests. The old `test/` folder held one-off
scratch experiments rather than real tests — those have been moved to the
`dev` folder for reference, and the dead ones removed.

## Guidance for future tests

The addon is split across two very different execution contexts, which shapes how
each part can be tested:

- **`src/`** — runs inside Blender and imports `bpy`. Logic that does *not* need
  `bpy` (path building in `src/paths.py`, the downloaded-asset JSON store in
  `src/assets.py`) can be unit-tested with plain `pytest` by importing those
  modules in isolation. UI/operator code needs Blender itself (headless
  `blender -b --python <test>.py`).
- **`scripts/fab_api.py`** — a standalone script run inside a venv. It can be
  tested directly with a normal Python interpreter that has `requests`,
  `cloudscraper`, `zstandard` and `pillow` installed.

When adding tests, prefer the `bpy`-free units first — they give the most coverage
for the least harness effort.
