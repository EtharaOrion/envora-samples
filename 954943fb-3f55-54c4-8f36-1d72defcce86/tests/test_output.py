"""Deterministic site checks for this task, one pytest test per rubric requirement.

This module IS the site-check table: tests/test.sh runs it with pytest and
turns the junit XML into /logs/verifier/site_channel.json (the if_score
channel). There is no second copy of the table in test.sh any more. Verdict
mapping: pass -> test passes (the reason is printed, and lands in the junit
XML's system-out), fail -> test fails, abstain -> pytest.skip, error ->
failure marked BUNDLE DEFECT (an author defect, not the run's).
Outside the verifier image (no checkout under /workspace) every site test
skips. The graded F2P/P2P sets come from tests/config.json, so this file is
inert for reward grading.
"""
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

PASS, FAIL, ABSTAIN, ERROR = "pass", "fail", "abstain", "error"
PRISTINE_ROOT = "/opt/pristine"
# test.sh writes one diff per repo here when the agent's workspace tarball was
# collected: `diff -ruN /opt/pristine/workspace/<repo> .` run in the agent's
# own tree. It is the only record of the agent's edits to a read-only repo,
# because those edits are never carried into the verifier's checkout.
# test.sh keeps the collected patches in its scratch directory and names it
# through AGENT_PATCH_DIR; the default is where an older test.sh wrote them.
AGENT_PATCH_TEMPLATE = os.environ.get("AGENT_PATCH_DIR", "/logs/verifier").rstrip("/") + "/agent_%s.patch"
HERE = Path(__file__).resolve().parent

REPOS = json.loads(r"""{
    "kvproto": "/workspace/kvproto",
    "pd": "/workspace/pd"
}""")
PRIMARY = 'kvproto'
REQUIREMENTS = json.loads(r"""[
    {
        "id": "S1-text",
        "position": 1,
        "kind": "text_present",
        "category": "process",
        "site": {
            "path": "server/keyspace_service.go",
            "repo": "pd"
        },
        "params": {
            "pattern": "func .*LoadKeyspaceByID\\("
        },
        "load_bearing": false,
        "weight": 5
    },
    {
        "id": "S2-untouched",
        "position": 2,
        "kind": "repo_untouched",
        "category": "topology",
        "site": {
            "path": ".",
            "repo": "kvproto"
        },
        "params": {},
        "load_bearing": false,
        "weight": 5
    }
]""")


def emitted_name(req_id):
    return "test_" + req_id.lower().replace("-", "_")


def rx(pattern):
    return re.compile(pattern, re.MULTILINE)


def root_of(site):
    name = site.get("repo") or PRIMARY
    raw = REPOS.get(name)
    if raw is None:
        return None, (ERROR, "site names repo %r, which task.toml does not declare" % name)
    p = Path(raw)
    if not p.is_dir():
        return None, (ERROR, "repo %r is not checked out at %s" % (name, raw))
    return p, None


def slurp(site):
    root, e = root_of(site)
    if e:
        return None, e
    t = root / site["path"]
    if not t.is_file():
        return None, None
    return t.read_text(encoding="utf-8", errors="replace"), None


def k_text_present(site, p):
    text, e = slurp(site)
    if e:
        return e
    if text is None:
        return FAIL, "%s is absent, so it carries no %s" % (site["path"], p["pattern"])
    hit = rx(p["pattern"]).search(text)
    return (PASS, "%s matches %s" % (site["path"], p["pattern"])) if hit else \
           (FAIL, "%s does not match %s" % (site["path"], p["pattern"]))


def pristine_changes(root):
    snapshot = Path(PRISTINE_ROOT + str(root))
    if not snapshot.is_dir():
        return None, (ABSTAIN, "no .git and no /opt/pristine snapshot, so churn cannot be read")
    changed = set()
    for base, other in ((root, snapshot), (snapshot, root)):
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for fname in filenames:
                here = Path(dirpath) / fname
                rel = here.relative_to(base)
                there = other / rel
                try:
                    if not there.is_file() or here.read_bytes() != there.read_bytes():
                        changed.add(str(rel))
                except OSError:
                    changed.add(str(rel))
    return changed, None


def patch_paths(text):
    """Paths a `diff -ruN` patch touches: the post-image side of every `+++`
    header (so an added file is named too), plus binary files, which diff
    reports on a single "Binary files A and B differ" line with no header."""
    paths = []
    for line in text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].split("\t")[0].strip()
        elif line.startswith("Binary files ") and line.endswith(" differ"):
            path = line[len("Binary files "):-len(" differ")].rpartition(" and ")[2].strip()
        else:
            continue
        if path.startswith("./"):
            path = path[2:]
        if path and path not in paths:
            paths.append(path)
    return paths


def k_repo_untouched(site, p):
    root, e = root_of(site)
    if e:
        return e
    label = site.get("repo") or "the repo"
    # Preferred source: the diff of the agent's OWN workspace. The verifier's
    # checkout of a read-only repo is built from the image and never receives
    # the agent's edits, so comparing it with /opt/pristine compares a tree to
    # itself and passes whatever the agent did.
    collected = Path(AGENT_PATCH_TEMPLATE % (site.get("repo") or PRIMARY))
    if collected.is_file():
        text = collected.read_text(encoding="utf-8", errors="replace")
        if not text:
            return PASS, ("%s is byte-identical (verified from the collected "
                          "workspace diff %s)" % (label, collected))
        changed = patch_paths(text)
        return FAIL, "%s was modified in the agent workspace: %s%s" % (
            label, changed[:5] or ["<unparsed diff, %d bytes>" % len(text)],
            " (+%d more)" % (len(changed) - 5) if len(changed) > 5 else "")
    if (root / ".git").is_dir():
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                           capture_output=True, text=True, timeout=120)
        if r.returncode:
            return ERROR, "git status failed: %s" % r.stderr.strip()[:200]
        paths = {ln[3:].strip().split(" -> ")[-1] for ln in r.stdout.splitlines() if ln.strip()}
    else:
        paths, e = pristine_changes(root)
        if e:
            return e
    # Fallback only: no workspace diff was collected, so this is the
    # verifier's own tree -- say so, rather than claim a verification it
    # could not make.
    return (FAIL, "%s was modified: %s" % (label, sorted(paths)[:5])) if paths else \
           (PASS, "%s is byte-identical to its checkout (fell back to the "
                  "verifier's own tree: no %s was collected, so the agent's "
                  "workspace was not inspected)" % (label, collected))


KINDS = {
    "text_present": k_text_present,
    "repo_untouched": k_repo_untouched,
}


def run_requirement(req_id):
    if not any(Path(p).is_dir() for p in REPOS.values()):
        pytest.skip("no checkout under the workspace; run inside the verifier image")
    req = next(r for r in REQUIREMENTS if r["id"] == req_id)
    fn = KINDS.get(req["kind"])
    if fn is None:
        pytest.fail("BUNDLE DEFECT: unsupported kind %r" % req["kind"], pytrace=False)
    try:
        verdict, why = fn(req["site"], req.get("params") or {})
    except re.error as exc:
        pytest.fail("BUNDLE DEFECT: malformed pattern: %s" % exc, pytrace=False)
    except Exception as exc:
        pytest.fail("BUNDLE DEFECT: %s: %s" % (type(exc).__name__, exc), pytrace=False)
    if verdict == PASS:
        # Printed so the junit XML (junit_logging=system-out) carries the
        # reason a check held, not only the reason one failed.
        print(why)
        return
    if verdict == ABSTAIN:
        pytest.skip(why)
    if verdict == ERROR:
        pytest.fail("BUNDLE DEFECT: %s" % why, pytrace=False)
    pytest.fail(why, pytrace=False)


def test_s1_text():
    run_requirement('S1-text')

def test_s2_untouched():
    run_requirement('S2-untouched')


def test_the_site_table_matches_the_rubric():
    rubric = json.loads((HERE / "rubrics.json").read_text(encoding="utf-8"))
    rubric_ids = [req["id"] for site in rubric["sites"] for req in site["requirements"]]
    assert rubric_ids == [req["id"] for req in REQUIREMENTS]
    for site, req in ((s, r) for s in rubric["sites"] for r in s["requirements"]):
        table = next(t for t in REQUIREMENTS if t["id"] == req["id"])
        assert table["kind"] == req["check"]["kind"]
        assert table["params"] == req["check"]["params"]
        assert table["site"] == {"path": site["path"], "repo": site["repo"]}


def test_every_site_check_is_priced_in_test_weights():
    weights = json.loads((HERE / "test_weights.json").read_text(encoding="utf-8"))
    assert sorted(weights) == sorted(emitted_name(req["id"]) for req in REQUIREMENTS)
