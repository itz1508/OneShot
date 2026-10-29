# Source and verification status

- Imported from user-provided `OneShot_Full_Latest_Built_2026-10-28(2).zip`.
- SHA-256 of supplied archive: `287e417908beb74cee7d3f0099502736e61c161c928c3af9a0be861955f65729`.
- Only the 28 source files under `OneShot/` were selected from the archive. Their bytes are preserved.
- Two root-level `.env.*.txt` provider credential files and four historical export/report files were excluded.
- `.gitignore` and GitHub Actions Python test workflow are added separately.
- Local re-execution of `python -m pytest -q -p no:cacheprovider` on the extracted application: **137 passed, 1 skipped**.
- The skipped official MCP SDK integration test needs verification on an environment with that SDK installed.
- This is a local OneShot scanner/task/MCP/build candidate, not the original large UI/System product and not a live connected coding Agent.
- External Baseten/Muse Spark integration remains in the separate **private** bridge. Do not copy it into the public source tree.
