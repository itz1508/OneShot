"""Optional authenticated Modal GitHub read-only example.

Run independently with ``modal run deployment/modal/github_clone.py --repo-url ...``.
No public HTTP route or host workflow authority is exposed.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import modal

app = modal.App("oneshot-github-readonly")
github_secret = modal.Secret.from_name("github-secret")
pygithub_image = modal.Image.debian_slim(python_version="3.11").pip_install("PyGithub>=2,<3")
git_image = modal.Image.debian_slim(python_version="3.11").apt_install("git")


def _validated_github_url(repo_url: str, branch: str) -> str:
    """Accept only conventional GitHub repository URLs and safe branch refs."""
    parsed = urlsplit(repo_url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("An HTTPS github.com repository URL is required")

    components = parsed.path.strip("/").removesuffix(".git").split("/")
    if len(components) != 2 or any(
        name in (".", "..") or re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None for name in components
    ):
        raise ValueError("Repository must have owner/repo path")

    if (
        re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._/-]{0,127}", branch) is None
        or ".." in branch
        or "//" in branch
        or "@{" in branch
        or branch.endswith(("/", "."))
    ):
        raise ValueError("Invalid branch name")

    return f"https://github.com/{components[0]}/{components[1]}.git"


@app.function(image=pygithub_image, secrets=[github_secret])
def get_username() -> str:
    """Check that the Modal GitHub secret authenticates successfully."""
    import github

    client = github.Github(auth=github.Auth.Token(os.environ["GITHUB_TOKEN"]))
    return client.get_user().login


@app.function(image=git_image, secrets=[github_secret], timeout=180)
def clone_repo(repo_url: str, branch: str = "main") -> list[str]:
    """Clone a GitHub branch temporarily and return top-level file names.

    No credentials are written to the remote URL or persisted in the repository.
    """
    verified_url = _validated_github_url(repo_url, branch)
    token = os.environ["GITHUB_TOKEN"]
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not configured in github-secret")

    with tempfile.TemporaryDirectory() as root:
        askpass = Path(root) / "askpass.sh"
        askpass.write_text(
            '#!/bin/sh\ncase "$1" in\n'
            '  *Username*) printf "%s" "x-access-token" ;;\n'
            '  *Password*) printf "%s" "$GITHUB_TOKEN" ;;\n'
            "  *) exit 1 ;;\n"
            "esac\n"
        )
        askpass.chmod(0o700)
        checkout = Path(root) / "repo"
        env = os.environ.copy()
        env["GIT_ASKPASS"] = str(askpass)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        cmd = [
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
            branch,
            "--",
            verified_url,
            str(checkout),
        ]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=150, check=False)
        if result.returncode:
            # Avoid returning Git's stderr, which may contain sensitive server details.
            raise RuntimeError("GitHub clone failed: check repository access and branch")
        return sorted(item.name for item in checkout.iterdir())


@app.local_entrypoint()
def main(repo_url: str, branch: str = "main") -> None:
    """Execute a read-only smoke test using an authenticated Modal client."""
    print("GitHub username:", get_username.remote())
    print("Repository entries:", clone_repo.remote(repo_url, branch))
