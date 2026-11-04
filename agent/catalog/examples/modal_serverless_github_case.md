# Modal serverless + GitHub — audited implementation example

**Lesson:** Normalize credentials, repository inputs, environment selection, and verification evidence before promoting a Modal/GitHub integration from a working code sample to a deployable service.

## Classification and provenance

- **Catalog reference:** `SAMPLE-MODAL-GITHUB-001` in `agent/catalog/research_samples.yaml`.
- **Type:** Synthetic reusable requirements and a historical *CI-passing implementation example*.
- **Authority:** No deployment, feature request, or production architecture is authorized by this sample.
- **Source:** [OneShot PR #16](https://github.com/itz1508/OneShot/pull/16), source branch `feat/modal-serverless-starter`, verified head `4be39313a1e86ed44e36e37c7657400c82655886`.
- **Evidence:** GitHub Actions CI run `41780834836`: Python 3.11 and 3.12 jobs passed lint, Ruff formatting, mypy, and pytest.
- **Not verified:** Modal account/environment access, provisioned secrets, deployed endpoint, actual private repository clone, live MCP, Builder integration, or end-to-end execution.

Historical source is retained in PR #16; this entry records the *normalized patterns and acceptance evidence*, not an additional executable implementation.

## Original example and performed normalization

| Input / issue | Implemented normalization | Why it mattered |
| --- | --- | --- |
| User-supplied Modal `get_username()` and `clone_repo()` using PyGithub and GitPython | Separated a health-only Modal App from an optional read-only GitHub inspection App | A sample must not silently become a public execution API |
| `assert repo_url.startswith("https://")` | Parsed URL and enforced scheme, exact `github.com` host, `owner/repo` path, no embedded credentials, query, or fragment | Avoid unintentionally cloning a third-party endpoint with a GitHub token |
| `repo_url.replace("https://", "https://" + token + "@")` | Token supplied to Git via temporary `GIT_ASKPASS` instead of a credential-bearing URL | Avoid token exposure in clone arguments or remote origin configuration |
| Branch supplied directly to Git | Branch syntax validation and `subprocess.run(..., shell=False)` argument vector | Block unsafe ref shapes and shell interpolation |
| Unbounded clone invocation | Shallow, single-branch clone, bounded timeout, isolated temporary checkout | Reduce resource use; limit persisted content |
| Git state or hooks potentially inheriting host settings | Disabled terminal credential prompts, inherited system/global Git config, credential helper, and hooks | Reduce untrusted repository and credential interactions |
| Reused one credential name for all purposes | Separate Modal deployment tokens (`MODAL_TOKEN_ID` + `MODAL_TOKEN_SECRET`), Modal proxy tokens, and GitHub read-only `GITHUB_TOKEN` | Deployment authorization, endpoint access, and GitHub access are distinct |
| Implicit Modal environment | Required an explicit deployment environment input and `modal deploy --env ...` | Prevent deployment into an unintended Modal environment |
| Initial failed CI | Applied exact Ruff formatting repairs and added clone-security regression tests | Corrected an observed failure without changing the host workflow |

The `github.com` hostname is an **intentional allowlist** for this GitHub-specific example. A future generic Git provider integration must define a new host/credential trust contract; it must not remove this check merely for configurability.

## Implementation patterns (illustrative excerpts)

Original unsafe token-in-URL approach — **rejected**:

```python
# Do not adopt this pattern.
repo_url_with_creds = repo_url.replace("https://", "https://" + os.environ["GITHUB_TOKEN"] + "@")
```

Normalized Git clone boundary — **applied in PR #16**:

```python
# Validate the user-controlled URL/branch *before* using credentials.
parsed = urlsplit(repo_url)
if parsed.scheme != "https" or parsed.netloc != "github.com":
    raise ValueError("An HTTPS github.com repository URL is required")
# Additional owner/repo and branch checks are required; see PR #16 source.

# Keep the token out of the remote URL and process arguments.
env = os.environ.copy()
env["GIT_ASKPASS"] = str(temporary_askpass_script)
env["GIT_TERMINAL_PROMPT"] = "0"
env["GIT_CONFIG_NOSYSTEM"] = "1"
env["GIT_CONFIG_GLOBAL"] = os.devnull
subprocess.run(
    [
        "git",
        "-c",
        "credential.helper=",
        "-c",
        "core.hooksPath=/dev/null",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--no-tags",
        "--branch",
        validated_branch,
        "--",
        verified_url,
        checkout_dir,
    ],
    env=env,
    capture_output=True,
    text=True,
    timeout=150,
    check=False,
)
```

Deployment boundary — **prepared, not executed**:

```yaml
# Example: manual GitHub Actions deployment; requires environment + secrets.
env:
  MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}
  MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}
  MODAL_ENVIRONMENT: ${{ inputs.modal_environment }}
# Command:
# modal deploy --env "$MODAL_ENVIRONMENT" deployment/modal/app.py
```

Only the distinct Modal `github-secret` supplies `GITHUB_TOKEN` to the optional read-only App. The HTTP health endpoint does not clone repositories or expose agent execution.

## Verification ladder: what success looks like

| Gate | Required evidence | PR #16 historical result |
| --- | --- | --- |
| G1. Source & contracts | Reviewed scoped diff; no authority moved away from OneShot Host | Source inspected; separate apps |
| G2. Input & credential boundaries | Host/path/branch rejection tests; token absent from command arguments and thrown errors; temporary checkout deleted | Mock-backed regression tests passed in CI |
| G3. Static quality | Ruff check + format; mypy; pytest on supported Python versions | **Passed** on Python 3.11 and 3.12, run `41780834836` |
| G4. Environment admission | Named Modal environment exists; scoped deployment API token pair present; named GitHub secret present | **Not verified** |
| G5. Live deploy | Actual `modal deploy --env <environment>` reports deployed URL; health endpoint returns expected JSON | **Not verified** |
| G6. Authenticated integration | Actual Modal invocation reads a permitted private GitHub repo; denied/invalid access fails safely; no token leakage | **Not verified** |
| G7. OneShot product integration | Frozen Plan/Build Admission, trusted receipts, effect boundaries, interruption recovery, and independently observed E2E | **Out of scope / not verified** |

**Observed result is G3 PASS, not full implementation success.** Do not claim `READY` for production before G4–G6; do not claim OneShot Builder acceptance before G7. An example may describe the target success state without asserting it occurred.

## Reuse rule

Research may match this example to requests involving Modal serverless deployment, GitHub cloning, isolated execution, and credential handling. It should inspect current SDK documentation, code, and exact user requirements; surface the checklist and gaps to Audit Discovery and Planner. Planner chooses architecture and authorized file actions; Builder executes only an admitted revision; verification records observed results. Synthetic catalog text must never be treated as a verified source, authorization receipt, or instruction to deploy.

## Known limitations

- Mocked Git and Modal objects in CI cannot prove an actual Modal worker or GitHub network call.
- The source sample currently returns top-level repository names; it does not implement project search, MCP tools, mutation, or artifact storage.
- The account workspace URL and `OneShot` environment were not independently inspected.
- Access to a GitHub repository is bounded by token scopes and the Modal Secret; it does not confer OneShot Build Admission.
- Protect the original exposed proxy credentials independently and rotate if they were shared beyond the intended secure boundary.
