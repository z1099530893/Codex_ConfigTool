"""Publish a GitHub release for this project: draft, upload, verify, then publish.

Run ``build.bat`` first - this script uploads what that produces, it does not build.

    python scripts/publish_release.py status     # what would be published, and from where
    python scripts/publish_release.py create     # create the release as a DRAFT
    python scripts/publish_release.py upload     # attach the two release assets
    python scripts/publish_release.py verify     # compare the release against the local files
    python scripts/publish_release.py publish    # flip the draft to published
    python scripts/publish_release.py body       # re-push the release notes as the body

Why draft -> upload -> verify -> publish, instead of one call that publishes immediately:
a published release whose assets are still uploading is visible to users and looks
broken. The draft state makes the whole thing invisible until it is complete, and the
verify step is what turns "the API returned 200" into "the page really matches the
files on disk".

Why verify compares hashes instead of trusting the upload response: the API reports a
``digest`` (sha256) per asset, so the check costs nothing and catches a truncated or
substituted upload without downloading a hundred megabytes back.

Version, tag and asset names are all derived from APP_VERSION in codex_config_tool.py,
so there is exactly one place to bump. The repository is read from the git remote
rather than hardcoded. The token comes from GH_TOKEN / GITHUB_TOKEN if set, otherwise
from the credential helper - see resolve_token() for why that is not a one-liner on
this machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"
ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
STATE = ROOT / "build" / "publish-release-state.json"
APP_MODULE = ROOT / "codex_config_tool.py"


def read_version() -> str:
    match = re.search(
        r'^APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"$',
        APP_MODULE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise SystemExit(f"APP_VERSION could not be read from {APP_MODULE}")
    return match.group(1)


def git_candidates() -> list[str]:
    """Every plausible git, best first.

    Not a formality: on this machine the git first on PATH is a portable build whose
    credential helper returns nothing, so it falls through to an interactive prompt and
    hangs. The system installation's helper is the one that actually has the token, so
    it is tried explicitly instead of trusting PATH.
    """
    found: list[str] = []
    on_path = shutil.which("git")
    if on_path:
        found.append(on_path)
    for extra in (
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
    ):
        if pathlib.Path(extra).is_file():
            found.append(extra)
    return found


def credential_helper(git: str) -> str:
    """Which credential helper a given git would use, or "" if it cannot be asked.

    This exists to skip Git for Windows' ``helper-selector``. That helper is not a
    credential store at all - it is a GUI that asks the user to *pick* a store, so
    calling it non-interactively opens a dialog and blocks forever.
    ``GIT_TERMINAL_PROMPT=0`` does not prevent that: the variable only suppresses
    git's own terminal prompts, and by the time the helper runs git is not prompting,
    the helper is. Reading the configured name is instant and touches no network.
    """
    try:
        result = subprocess.run(
            [git, "config", "--get-all", "credential.helper"],
            capture_output=True,
            timeout=15,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except Exception:  # noqa: BLE001 - an unusable git is just a candidate to skip
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", "replace").strip()


def run_git(args: list[str], git: str | None = None) -> str:
    last_error = ""
    for candidate in ([git] if git else git_candidates()):
        try:
            result = subprocess.run(
                [candidate, "-C", str(ROOT), *args],
                capture_output=True,
                timeout=60,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except Exception as exc:  # noqa: BLE001 - any failure just means "try the next git"
            last_error = f"{candidate}: {exc}"
            continue
        if result.returncode == 0:
            return result.stdout.decode("utf-8", "replace").strip()
        last_error = f"{candidate}: {result.stderr.decode('utf-8', 'replace').strip()}"
    raise SystemExit(f"git failed for {args}:\n{last_error}")


def resolve_repo() -> str:
    url = run_git(["remote", "get-url", "origin"])
    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$", url)
    if not match:
        raise SystemExit(f"origin is not a GitHub remote: {url}")
    return f"{match.group('owner')}/{match.group('repo')}"


def resolve_token() -> str:
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    # Fall back to the credential helper. `git credential fill` prints the secret on
    # stdout as `password=...`; it must be fed the protocol/host on stdin.
    #
    # Candidates whose helper is `helper-selector` are skipped before they are invoked.
    # On this machine the git first on PATH is exactly that one, and asking it opens a
    # picker dialog that never returns - which is why the loop is not allowed to just
    # "try everything in order". The system git at C:\Program Files\Git is the one whose
    # `manager` helper actually holds the token.
    payload = b"protocol=https\nhost=github.com\n\n"
    skipped: list[str] = []
    for candidate in git_candidates():
        if "helper-selector" in credential_helper(candidate):
            skipped.append(candidate)
            continue
        try:
            result = subprocess.run(
                [candidate, "credential", "fill"],
                input=payload,
                capture_output=True,
                timeout=30,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except Exception:  # noqa: BLE001 - a slow git is just a candidate to skip
            continue
        for line in result.stdout.decode("utf-8", "replace").splitlines():
            if line.startswith("password="):
                token = line[len("password="):].strip()
                if token:
                    return token
    detail = ""
    if skipped:
        detail = (
            "\n  skipped (their helper is helper-selector, which waits for a click "
            "instead of answering):\n    " + "\n    ".join(skipped)
        )
    raise SystemExit(
        "No GitHub token. Set GH_TOKEN, or make sure the credential helper that has it "
        "is reachable (on this machine that is C:\\Program Files\\Git)." + detail
    )


def request(method, url, token, data=None, raw=None, extra_headers=None, timeout=600):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "codex-config-tool-publish",
    }
    if extra_headers:
        headers.update(extra_headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if raw is not None:
        body = raw
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(text) if text.strip() else {})
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Context:
    def __init__(self) -> None:
        self.version = read_version()
        self.tag = f"v{self.version}"
        self.repo = resolve_repo()
        self.notes = ROOT / "docs" / f"RELEASE_NOTES_{self.version}.md"
        self.assets = [
            DIST / f"CodexConfigTool-Setup-v{self.version}.exe",
            DIST / f"CodexConfigTool-Portable-v{self.version}.exe",
        ]
        self.state_path = STATE
        self._token = ""

    @property
    def token(self) -> str:
        if not self._token:
            self._token = resolve_token()
        return self._token

    def load_state(self) -> dict:
        if self.state_path.is_file():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return {}

    def save_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def call(self, method, url, **kwargs):
        return request(method, url, self.token, **kwargs)

    def release_by_tag(self):
        status, payload = self.call("GET", f"{API}/repos/{self.repo}/releases/tags/{self.tag}")
        if status == 404:
            return None
        if status != 200:
            raise SystemExit(f"GET release {self.tag} -> {status}: {payload}")
        return payload

    def release_by_id(self, rid: int):
        status, payload = self.call("GET", f"{API}/repos/{self.repo}/releases/{rid}")
        if status != 200:
            raise SystemExit(f"GET release {rid} -> {status}: {payload}")
        return payload


def preflight(ctx: Context) -> None:
    problems = []
    if not ctx.notes.is_file():
        problems.append(f"release notes missing: {ctx.notes}")
    for asset in ctx.assets:
        if not asset.is_file():
            problems.append(f"release asset missing: {asset}")
    if problems:
        joined = "\n  ".join(problems)
        raise SystemExit(f"preflight failed:\n  {joined}\nRun scripts\\build.bat first.")


def cmd_status(ctx: Context) -> int:
    print(f"repository : {ctx.repo}")
    print(f"version    : {ctx.version}   (from {APP_MODULE.name})")
    print(f"tag        : {ctx.tag}")
    local_commit = None
    try:
        local_commit = run_git(["rev-parse", f"{ctx.tag}^{{commit}}"])
        print(f"tag commit : {local_commit}")
    except SystemExit as exc:
        print(f"tag commit : NOT FOUND locally - {exc}")
    try:
        remote_commit = run_git(["rev-parse", f"refs/remotes/origin/{ctx.tag}^{{commit}}"])
        print(f"remote tag : {remote_commit}")
    except SystemExit:
        print("remote tag : not fetched locally (git fetch --tags to check)")
    print(f"notes      : {ctx.notes.name} ({ctx.notes.stat().st_size if ctx.notes.is_file() else 0} bytes)")
    for asset in ctx.assets:
        if asset.is_file():
            print(f"asset      : {asset.name}  {asset.stat().st_size} bytes  {sha256(asset)}")
        else:
            print(f"asset      : {asset.name}  MISSING")
    release = ctx.release_by_tag()
    if release is None:
        print("release    : does not exist yet")
    else:
        print(f"release    : id {release['id']} draft={release['draft']} assets={len(release['assets'])}")
        print(f"             {release['html_url']}")
    return 0


def cmd_create(ctx: Context) -> int:
    preflight(ctx)
    existing = ctx.release_by_tag()
    if existing is not None:
        raise SystemExit(
            f"{ctx.tag} already has a release (id {existing['id']}). "
            "Delete it on GitHub first if you really mean to recreate it."
        )
    # The tag has to exist and be pushed before the release is created, so the commit is
    # read back from the tag rather than passed in. This also means a mistyped or
    # unpushed tag fails here instead of producing a release pointing at the wrong tree.
    commit = run_git(["rev-parse", f"{ctx.tag}^{{commit}}"])
    body = ctx.notes.read_text(encoding="utf-8")
    status, payload = ctx.call(
        "POST",
        f"{API}/repos/{ctx.repo}/releases",
        data={
            "tag_name": ctx.tag,
            "target_commitish": commit,
            "name": f"Codex 配置助手 {ctx.tag}",
            "body": body,
            "draft": True,
            "prerelease": False,
        },
    )
    print("create ->", status)
    if status != 201:
        print(payload)
        return 1
    state = ctx.load_state()
    state.update(
        {
            "version": ctx.version,
            "tag": ctx.tag,
            "repo": ctx.repo,
            "release_id": payload["id"],
            "html_url": payload["html_url"],
            "tag_commit": commit,
            "notes_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "assets": {},
        }
    )
    ctx.save_state(state)
    print("release_id =", payload["id"], "(draft)")
    return 0


def cmd_upload(ctx: Context) -> int:
    preflight(ctx)
    release = ctx.release_by_tag()
    if release is None:
        raise SystemExit("no release yet - run create first")
    rid = release["id"]
    already = {a["name"] for a in release["assets"]}
    state = ctx.load_state()
    state.setdefault("assets", {})
    for asset in ctx.assets:
        if asset.name in already:
            print(f"skip {asset.name} (already attached)")
            continue
        status, payload = ctx.call(
            "POST",
            f"{UPLOADS}/repos/{ctx.repo}/releases/{rid}/assets?name={asset.name}",
            raw=asset.read_bytes(),
            extra_headers={"Content-Type": "application/octet-stream"},
        )
        print(f"upload {asset.name} -> {status}")
        if status != 201:
            print(payload)
            return 1
        state["assets"][asset.name] = {
            "id": payload["id"],
            "local_size": asset.stat().st_size,
            "local_sha256": sha256(asset),
        }
        ctx.save_state(state)
    return 0


def cmd_verify(ctx: Context) -> int:
    release = ctx.release_by_tag()
    if release is None:
        raise SystemExit("no release to verify")
    problems = []
    if release["tag_name"] != ctx.tag:
        problems.append(f"tag_name is {release['tag_name']}, expected {ctx.tag}")
    if release["draft"]:
        problems.append("release is still a draft")
    if ctx.notes.is_file():
        local = ctx.notes.read_text(encoding="utf-8")
        if release["body"].strip() != local.strip():
            problems.append("release body differs from the local release notes")
    remote = {a["name"]: a for a in release["assets"]}
    expected = {a.name for a in ctx.assets}
    for asset in ctx.assets:
        entry = remote.get(asset.name)
        if entry is None:
            problems.append(f"{asset.name}: not attached")
            continue
        if not asset.is_file():
            continue
        local_size = asset.stat().st_size
        local_hash = sha256(asset)
        digest = entry.get("digest") or ""
        if entry["size"] != local_size:
            problems.append(f"{asset.name}: size {entry['size']} != {local_size}")
        if digest and digest != f"sha256:{local_hash}":
            problems.append(f"{asset.name}: sha256 {digest} != sha256:{local_hash}")
        if entry["state"] != "uploaded":
            problems.append(f"{asset.name}: state is {entry['state']}")
        print(
            f"  {asset.name}: {entry['size']} bytes state={entry['state']} "
            f"downloads={entry['download_count']} sha_match={digest == 'sha256:' + local_hash}"
        )
    extra = sorted(set(remote) - expected)
    if extra:
        problems.append(f"unexpected extra assets: {extra}")
    print("release:", release["html_url"], "draft =", release["draft"])
    if problems:
        print("PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        return 1
    print("VERIFY OK")
    return 0


def cmd_body(ctx: Context) -> int:
    release = ctx.release_by_tag()
    if release is None:
        raise SystemExit("no release to update")
    body = ctx.notes.read_text(encoding="utf-8")
    status, payload = ctx.call(
        "PATCH", f"{API}/repos/{ctx.repo}/releases/{release['id']}", data={"body": body}
    )
    print("update body ->", status)
    if status != 200:
        print(payload)
        return 1
    state = ctx.load_state()
    state["notes_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    ctx.save_state(state)
    print("body chars:", len(body))
    return 0


def cmd_publish(ctx: Context) -> int:
    release = ctx.release_by_tag()
    if release is None:
        raise SystemExit("no release to publish")
    if cmd_verify(ctx) != 0:
        raise SystemExit("verify failed - not publishing")
    status, payload = ctx.call(
        "PATCH",
        f"{API}/repos/{ctx.repo}/releases/{release['id']}",
        data={"draft": False, "prerelease": False},
    )
    print("publish ->", status)
    if status != 200:
        print(payload)
        return 1
    print("published:", payload["html_url"], "draft =", payload["draft"])
    return 0


def cmd_latest(ctx: Context) -> int:
    status, payload = ctx.call("GET", f"{API}/repos/{ctx.repo}/releases/latest")
    print("releases/latest ->", status)
    if status == 200:
        print("  tag:", payload["tag_name"], "assets:", len(payload["assets"]))
    return 0 if status == 200 else 1


def cmd_list(ctx: Context) -> int:
    status, payload = ctx.call("GET", f"{API}/repos/{ctx.repo}/releases?per_page=50")
    if status != 200:
        print("list ->", status, payload)
        return 1
    for release in payload:
        print(
            f"  {release['tag_name']:10s} draft={str(release['draft']):5s} "
            f"assets={len(release['assets'])} published={release['published_at']}"
        )
    return 0


COMMANDS = {
    "status": cmd_status,
    "create": cmd_create,
    "upload": cmd_upload,
    "verify": cmd_verify,
    "body": cmd_body,
    "publish": cmd_publish,
    "latest": cmd_latest,
    "list": cmd_list,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=sorted(COMMANDS))
    args = parser.parse_args()
    return COMMANDS[args.command](Context())


if __name__ == "__main__":
    sys.exit(main())
