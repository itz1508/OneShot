# Playwright fixture ZIPs

Build these on a dev host before running the specs:

```bash
cd tests/frontend/e2e/chat/fixtures

# pack.zip (happy path): two inner files
python3 - << 'PY'
import zipfile
with zipfile.ZipFile("pack.zip", "w") as z:
    z.writestr("docs/readme.md", "# hello")
    z.writestr("notes.txt", "note")
PY

# slip.zip (zip-slip): one entry outside the archive root
python3 - << 'PY'
import zipfile
with zipfile.ZipFile("slip.zip", "w") as z:
    z.writestr("../etc/passwd", "evil")
PY
```

The sandbox cannot run `pnpm playwright test`. Commit the fixtures alongside
`intake.spec.ts` so the dev host test run is reproducible.
