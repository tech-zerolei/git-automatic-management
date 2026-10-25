"""Linux process cleanup shared by the isolated preflight experiments."""

import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import uuid


REGISTRY_ENV = "GIT_PLANNER_PROBE_GROUP_REGISTRY"
SCOPE_ENV = "GIT_PLANNER_PROBE_GROUP_SCOPE"


def process_start(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


def update_registry(path, update):
    with open(path, "r+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        document = json.load(handle)
        value = update(document)
        handle.seek(0)
        json.dump(document, handle)
        handle.truncate()
        return value


def registered_exec(path, scope, argv):
    # Registration precedes exec. The closing flag closes the late-spawn race.
    def register(document):
        owner = document["owner"]
        closed = any(scope == item or scope.startswith(item + "/") for item in document["closed"])
        if not document["open"] or closed or process_start(owner["pid"]) != owner["start"]:
            return False
        document["groups"].append({"pid": os.getpid(), "start": process_start(os.getpid()), "scope": scope})
        return True

    try:
        allowed = update_registry(path, register)
    except FileNotFoundError:
        allowed = False
    if not allowed:
        raise SystemExit(125)
    os.execvpe(argv[0], argv, os.environ)


def kill_group(pid, expected_start=None):
    actual = process_start(pid)
    if expected_start is not None and actual is not None and actual != expected_start:
        return
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def close_registry(path, scope, root=False):
    def close(document):
        if root:
            document["open"] = False
        if scope not in document["closed"]:
            document["closed"].append(scope)
        return [group for group in document["groups"] if root or group["scope"] == scope or group["scope"].startswith(scope + "/")]

    for group in reversed(update_registry(path, close)):
        kill_group(group["pid"], group["start"])


def run_bounded(argv, *, cwd, env=None, timeout=30, check=False, own_group=True):
    """Register and clean all nested supervised groups, including on timeout.

    The outer call owns a private registry. Every nested own-group call joins
    it before executing its command, even when the supplied environment is
    isolated. This is controlled-fixture supervision, not an arbitrary-code
    sandbox: an uncooperative program can deliberately escape supervision.
    """
    if sys.platform != "linux":
        raise OSError("preflight process supervision requires Linux /proc and flock")
    registry = os.environ.get(REGISTRY_ENV)
    temporary = None
    if own_group and not registry:
        temporary = tempfile.TemporaryDirectory(prefix="git-planner-process-groups-")
        registry = str(Path(temporary.name) / "groups.json")
        Path(registry).write_text(json.dumps({"open": True, "groups": [], "closed": [],
                                              "owner": {"pid": os.getpid(), "start": process_start(os.getpid())}}))
    parent_scope = os.environ.get(SCOPE_ENV, "") if not temporary else ""
    scope = (parent_scope + "/" + uuid.uuid4().hex).lstrip("/") if own_group else parent_scope
    child_env = dict(os.environ if env is None else env)
    if registry:
        child_env[REGISTRY_ENV] = registry
        child_env[SCOPE_ENV] = scope
    launch = [sys.executable, "-B", str(Path(__file__).resolve()), "--registered-exec", registry, scope, *argv] if own_group else argv
    try:
        process = subprocess.Popen(launch, cwd=cwd, env=child_env, start_new_session=own_group,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except BaseException:
        if temporary:
            temporary.cleanup()
        raise
    start = process_start(process.pid)

    def terminate():
        if registry and own_group:
            close_registry(registry, scope, root=bool(temporary))
        try:
            if own_group:
                kill_group(process.pid, start)
            else:
                process.kill()
        except ProcessLookupError:
            pass

    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(argv, timeout, output=stdout, stderr=stderr)
        completed = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
        if check:
            completed.check_returncode()
        return completed
    finally:
        terminate()
        process.wait()
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    if len(sys.argv) < 5 or sys.argv[1] != "--registered-exec":
        raise SystemExit(2)
    registered_exec(sys.argv[2], sys.argv[3], sys.argv[4:])
