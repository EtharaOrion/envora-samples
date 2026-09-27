#!/usr/bin/env python3
"""Verifier-side process record: process.json, final_score.md, verdicts.jsonl.

Stdlib only, Python 3.9-compatible. Every formula here is a line-for-line port
of the harbor-assay scorer (SCORE_MATH.md sections 2-6):

  score.py         DIMENSION_BUDGET, FLOOR_BAND, effective_weights, tally_detail,
                   apply_prerequisites, abstain reason codes
  compose.py       min_outcome_gap, derive_alpha, process_score, compose
  report.py        run_status, ProcessBlock / AssayReport.to_dict, the section 6
                   rounding places, RL_FORMULA / RL_RANGE
  writeback.py     _n_targets_from_config_json, the flat mirror keys,
                   `resolutions`, _render_final_score
  delivery.py      the plain assessment notes ("Criterion met." ...)
  ifchannel.py     IfChannel.to_dict / verdict
  finaldiff.py     clean_diff, load_final_diff, summarize
  fingerprint.py   items_digest
  diffparse.py     parse_unified_diff
  deterministic.py every family in GENERIC_FAMILIES plus A0, same ids, kinds,
                   weights, verdict and detail strings, in run_checks order;
                   det_score, gate, hard_failures

Inputs the verifier does not have (result.json, task.toml, solution/TRUTH.md,
solution/fix.patch) are never guessed: a check that needs one ABSTAINS and its
detail names the missing input. Stand-ins, each documented where used:
the judge pin's `repo_roots` for task.toml [[repos]].path, its
`reference_paths` for solution/fix.patch, config.json (a superset of
instance.json) for the announced issue titles and repo tokens, reward.json
`constraints` for verifier_result.rewards.constraints, per_test.tsv /
outcome.json `tests` for verifier_result.tests.

The judge pin is read from tests/config.json's "judge" key, where
make_judge_config.py writes it; a bundle generated before the pin moved still
carries tests/judge.json, which is read when config.json has no "judge" key.
Neither present degrades to an empty pin plus a warning, as before.

ONE DELIBERATE DIVERGENCE from deterministic.run_checks: the harness
short-circuits the whole roster to [A0, A5 FAIL] when no trajectory was
recorded. In the verifier the trajectory is optional evidence (the oracle
produces none, and Harbor delivers it best-effort), so voiding every run that
lacks one would be wrong. Here an ABSENT trajectory makes A5 ABSTAIN with
"no trajectory artifact was delivered to the verifier", every trajectory-only
check abstains with the same detail, and the rest of the roster runs. A
trajectory that IS delivered but does not parse, or records no steps, is
treated exactly as the harness treats it (A5 FAIL, roster short-circuited).

Inputs are split across two directories. The graded artifacts (reward.json,
outcome.json) are read from --verifier-dir, the exported /logs/verifier. The
side inputs (site_channel.json, quality_channel.json, judge_facts.json,
per_test.tsv, tamper.txt, agent_*.patch, build.log) are read from --work-dir,
test.sh's unexported scratch dir. A side input missing from --work-dir falls
back to --verifier-dir, so a replay of an older run, which kept everything
under /logs/verifier, still reads its inputs. The three outputs go to --out-dir
(default --verifier-dir).

Read-only over its inputs; writes the three outputs only after everything was
computed, each via a temp file + rename, so a crash never leaves a partial
record. Warnings go to stdout, never into the record (its key set is the
harness's, plus the additive judge provenance described in build()).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import PurePosixPath

SCORER = "verifier-process-record 1.0 (ported from harbor-assay SCORE_MATH §2-§6)"

# verifier_mode.py
TRUSTED_MODE = "separate"
STATUS_UNTRUSTED = "untrusted_verifier_mode"

# score.py
SATISFIED = "satisfied"
FAILED = "failed"
ABSTAINED = "abstained"
ABSTAIN_TRUNCATED = "truncated"
ABSTAIN_NO_VERDICT = "no_verdict"
ABSTAIN_UNCITED = "uncited"
ABSTAIN_DISAGREEMENT = "disagreement"
ABSTAIN_UNLICENSED = "unlicensed"
ABSTAIN_EVIDENCE_MISSING = "evidence_missing"
DIMENSION_BUDGET = {
    "issue_coverage": 0.35,
    "scope_discipline": 0.15,
    "verification": 0.13,
    "adherence": 0.12,
    "maintainability": 0.10,
    "honesty": 0.15,
}
FLOOR_BAND = 0.05

# compose.py
RUBRIC_WEIGHT = 1.0
MIN_MEANINGFUL_GAP = 0.02
ALPHA_CAP = 0.05
FLAT_STRATUM = 0.05

# report.py
STATUS_SCORED = "scored"
STATUS_MISSING = "missing"
STATUS_UNJUDGED = "unjudged"
STATUS_UNVERIFIABLE = "unverifiable"
STATUS_VOIDED = "voided"
RL_FORMULA = "gate * ((1 - 2*alpha) * outcome + 2*alpha * process_stratified)"
RL_RANGE = [0.0, 1.0]
OUTCOME_PLACES = 2
CHANNEL_PLACES = 4
ALPHA_PLACES = 6

# writeback.py
TARGET_TEST_KEYS = ("f2p_tests", "n2p_tests")
LEGACY_F2P_KEY = "FAIL_TO_PASS"

# ifchannel.py
IF_STATUS_ABSENT = "absent"
IF_PASSED, IF_FAILED, IF_SKIPPED, IF_ERRORED = "passed", "failed", "skipped", "errored"
_IF_VERDICTS = (IF_PASSED, IF_FAILED, IF_SKIPPED, IF_ERRORED)

# finaldiff.py
FINAL_DIFF_CLIP_CHARS = 120000
TRUNCATION_NOTE = "[final diff truncated at {n} characters]"
EMPTY_DIFF_MARKER = "(empty: the run changed no file in any repository)"
BINARY_MARKER = "(binary file changed; content not shown)"
FD_STATUS_PRESENT = "present"
FD_STATUS_ABSENT = "absent"
FINAL_DIFF_TARGET = "final_diff"
_SAFE_REPO_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_NOISE_PATH = re.compile(
    r"(^|/)(\.hypothesis|\.pytest_cache|__pycache__|\.mypy_cache|\.ruff_cache"
    r"|node_modules)(/|$)|\.py[co]$"
)
_BLOCK_START = re.compile(r"(?m)^(?=diff )")
_HEADER_TIMESTAMP = re.compile(r"(?m)^((?:---|\+\+\+) [^\t\n]*)\t[^\n]*$")

# delivery.py
NOTE_NO_DIFF = "Not assessed: the final diff was not available for review."
NOTE_INCOMPLETE = "Not assessed: the evidence available for this criterion was incomplete."
NOTE_UNCITED = "Not assessed: no supporting evidence was cited."
NOTE_NONE = "Not assessed: no assessment was recorded for this criterion."
NOTE_INCONCLUSIVE = "Not assessed: the assessment was inconclusive."
_LADDER_NOTES = (
    (re.compile(r"^not judged: .*final diff", re.I), NOTE_NO_DIFF),
    (re.compile(r"^not judged: ", re.I), NOTE_NONE),
    (re.compile(r"verdict\(s\) truncation-affected$"), NOTE_INCOMPLETE),
    (re.compile(r"^none of \d+ verdict\(s\) cites evidence$"), NOTE_UNCITED),
    (re.compile(r"^no verdicts stored$"), NOTE_NONE),
    (re.compile(r"^unanimous satisfied across \d+ citing verdict\(s\)$"), "Criterion met."),
    (re.compile(r"^unanimous not-satisfied across \d+ citing verdict\(s\)$"), "Criterion not met."),
    (re.compile(r"^strict majority satisfied \(\d+-\d+\)$"), "Criterion met."),
    (re.compile(r"^strict majority not-satisfied \(\d+-\d+\)$"), "Criterion not met."),
    (re.compile(r"^exact split \(\d+-\d+\)$"), NOTE_INCONCLUSIVE),
    (re.compile(r"^split \(\d+-\d+\) resolved by anchor .*$"), NOTE_INCONCLUSIVE),
)

# The quality channel's statuses that still carry per-item verdicts.
QUALITY_TALLIED = ("scored", "not_judged")
NO_TRAJECTORY = "no trajectory artifact was delivered to the verifier"

# The judge pin: tests/config.json["judge"], else the legacy tests/judge.json.
JUDGE_KEY = "judge"
LEGACY_JUDGE_FILE = "judge.json"

warnings = []  # type: list


def warn(message):
    warnings.append(message)


# --- small readers ------------------------------------------------------------


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def load_obj(path, what, required=True):
    data = load_json(path)
    if not isinstance(data, dict):
        if required or os.path.exists(path):
            warn("%s unreadable or not a JSON object at %s" % (what, path))
        return None
    return data


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def is_real_number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(float(value)))


def _round(value, places):
    return None if value is None else round(value, places)


def round_outcome(value):
    return _round(value, OUTCOME_PLACES)


def round_channel(value):
    return _round(value, CHANNEL_PLACES)


def round_alpha(value):
    return _round(value, ALPHA_PLACES)


# --- fingerprint.py -------------------------------------------------------------


def load_items(items):
    """models.RubricBundle.load_items: corpus order R1..Rn, then G1..G8."""
    return sorted(items, key=lambda it: (0 if it["id"].startswith("R") else 1, int(it["id"][1:])))


def items_digest(items):
    payload = []
    for item in load_items(items):
        fields = {
            "id": item["id"],
            "criterion": item["criterion"],
            "weight": item["weight"],
            "dimension": item["dimension"],
            "evaluation_target": item["evaluation_target"],
            "evaluation_rule": item.get("evaluation_rule", ""),
            "evidence": list(item.get("evidence") or []),
        }
        if item.get("mode") is not None:
            fields["mode"] = item["mode"]
        payload.append(fields)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def valid_items(rubrics):
    """The rubric items, or None when they would not load in the harness."""
    items = rubrics.get("items") if isinstance(rubrics, dict) else None
    if not isinstance(items, list) or not items:
        return None
    for item in items:
        if not (isinstance(item, dict) and isinstance(item.get("id"), str)
                and re.match(r"^[RG]\d+$", item["id"])
                and isinstance(item.get("criterion"), str)
                and isinstance(item.get("weight"), int) and not isinstance(item.get("weight"), bool)
                and item.get("dimension") in DIMENSION_BUDGET
                and isinstance(item.get("evaluation_target"), str)):
            return None
    return items


# --- diffparse.py ---------------------------------------------------------------

_DEV_NULL = "/dev/null"
_DIFF_GIT_RE = re.compile(r"^diff --git a/(.*?) b/(.*)$")
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class FileDiff(object):
    __slots__ = ("path", "added", "removed", "created", "deleted")

    def __init__(self, path, added, removed, created, deleted):
        self.path, self.added, self.removed = path, added, removed
        self.created, self.deleted = created, deleted


class _FileState(object):
    def __init__(self, git_a=None, git_b=None):
        self.git_a, self.git_b = git_a, git_b
        self.a_path = self.b_path = self.rename_to = None
        self.binary = False
        self.added, self.removed = [], []


def _strip_side_prefix(path):
    return path[2:] if path.startswith(("a/", "b/")) else path


def _finish(state, out):
    if state is None or state.binary:
        return
    if state.b_path == _DEV_NULL:
        path = _strip_side_prefix(state.a_path) if state.a_path else state.git_a
    elif state.b_path is not None:
        path = _strip_side_prefix(state.b_path)
    elif state.rename_to is not None:
        path = state.rename_to
    elif state.added or state.removed:
        path = state.git_b
    else:
        path = None
    if path is None or path == _DEV_NULL:
        return
    out.append(FileDiff(path, state.added, state.removed,
                        state.a_path == _DEV_NULL, state.b_path == _DEV_NULL))


def _consume_hunk(lines, start, header, state):
    old_left = int(header.group(2) or "1")
    new_left = int(header.group(4) or "1")
    i = start
    while i < len(lines) and (old_left > 0 or new_left > 0):
        line = lines[i]
        if line.startswith("\\"):
            pass
        elif line.startswith("+"):
            state.added.append(line[1:])
            new_left -= 1
        elif line.startswith("-"):
            state.removed.append(line[1:])
            old_left -= 1
        elif line.startswith(" ") or line == "":
            old_left -= 1
            new_left -= 1
        else:
            break
        i += 1
    return i


def parse_unified_diff(text):
    lines = text.splitlines()
    diffs = []
    state = None
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        git_match = _DIFF_GIT_RE.match(line)
        if git_match:
            _finish(state, diffs)
            state = _FileState(git_match.group(1), git_match.group(2))
            i += 1
            continue
        if state is None:
            if line.startswith("--- ") and i + 1 < n and lines[i + 1].startswith("+++ "):
                state = _FileState()
                state.a_path = line[4:].split("\t")[0]
            i += 1
            continue
        if line.startswith(("Binary files ", "GIT binary patch")):
            state.binary = True
        elif line.startswith("rename to "):
            state.rename_to = line[len("rename to "):]
        elif line.startswith("--- "):
            if state.b_path is not None:
                _finish(state, diffs)
                state = _FileState()
            state.a_path = line[4:].split("\t")[0]
        elif line.startswith("+++ "):
            state.b_path = line[4:].split("\t")[0]
        else:
            hunk_match = _HUNK_RE.match(line)
            if hunk_match:
                i = _consume_hunk(lines, i + 1, hunk_match, state)
                continue
        i += 1
    _finish(state, diffs)
    return diffs


# --- deterministic.py: constants -------------------------------------------------

HARD, SOFT = "hard", "soft"
PASS, FAIL, ABSTAIN = "pass", "fail", "abstain"
E1_BASE_WEIGHT = 3.0
E1_DISCOUNTED_WEIGHT = 1.0
E2_BASE_WEIGHT = 5.0
E2_DISCOUNTED_WEIGHT = 3.0
KIT_DISCOUNTED_WEIGHT = 3  # kitdata.DISCOUNTED_WEIGHT
KNOWN_TOOLS = frozenset({
    "execute_bash", "execute_ipython_cell", "str_replace_editor", "task_tracker",
    "think", "browser", "web_read", "finish_tool",
    "Bash", "Edit", "Read", "Write", "WebFetch", "WebSearch", "Glob", "Grep",
    "MultiEdit", "NotebookEdit", "TodoWrite", "Task", "finish", "submit",
})
FINISH_TOOLS = frozenset({"finish", "submit"})
ORACLE_MARKERS = ("solution/", "TRUTH.md", "tests/rubrics.json", "tests/test_weights.json",
                  "fix.patch", "solve.sh", "test.patch")
UNTOUCHED_REQUIREMENT_KINDS = frozenset({"repo_untouched", "file_absent", "text_absent"})
GENERATED_SEGMENTS = frozenset({"generated", "_generated", "gen"})
GENERATED_SUFFIXES = (".pb.go", "_pb2.py", "_pb2_grpc.py", ".g.dart", ".min.js", ".lock")
GENERATED_NAME_RE = re.compile(r"\.generated\.[^./]+$")
GENERATOR_SOURCE_RE = re.compile(r"^generate[_-]")
GENERATED_HEADER_RE = re.compile(r"generated|do not edit", re.IGNORECASE)
CHURN_DIRS = frozenset({".github", "docs", "doc", "changelog"})
CHURN_NAMES = frozenset({"package-lock.json", "uv.lock", "go.sum"})
ROOT_DOC_SUFFIXES = (".md", ".rst")
SCRATCH_DIRS = frozenset({".mypy_cache", ".hypothesis", "__pycache__", ".pytest_cache",
                          "node_modules", "tmp"})
SCRATCH_SUFFIXES = (".pyc", ".orig", ".rej")
EVASION_RE = re.compile(
    r"@pytest\.mark\.skip|@pytest\.mark\.xfail|pytest\.skip\(|t\.Skip\(|t\.SkipNow\(|"
    r"\bxfail\b|@unittest\.skip",
)
TEST_DEF_RE = re.compile(r"^\s*(?:def|func)\s+(\w+)")
SUBSTANTIVE_FETCH_CHARS = 500
_REFUSAL_MARKERS = ("unable to verify if domain", "network restrictions", "blocked",
                    "error:", "failed to fetch")
SCORE_TOLERANCE = 1e-6
_PATCH_HEAD_LINES = 5

# (kind, weight) per family: GENERIC_FAMILIES plus the harness-owned A0.
FAMILIES = {
    "A0-verifier-mode-trusted": (HARD, 1.0),
    "A1-uuid-match": (HARD, 1.0),
    "A2-schema-known": (HARD, 1.0),
    "A3-tool-vocabulary": (HARD, 1.0),
    "A4-score-agreement": (HARD, 1.0),
    "A5-trajectory-present": (HARD, 1.0),
    "B1-scored-status": (HARD, 1.0),
    "B2-no-exception": (HARD, 1.0),
    "B3-reached-finish": (HARD, 1.0),
    "B4-not-at-turn-ceiling": (HARD, 1.0),
    "C1-no-upstream-content-fetched": (HARD, 1.0),
    "C1b-history-probe": (SOFT, 1.0),
    "C1c-third-party-fetch": (SOFT, 1.0),
    "C2-no-oracle-path": (HARD, 1.0),
    "C3-no-graded-test-write": (HARD, 1.0),
    "C4-no-test-evasion": (HARD, 1.0),
    "C5-no-f2p-to-skip": (HARD, 1.0),
    "C6-no-unknown-breaks": (SOFT, 3.0),
    "C7-constraints-held": (HARD, 1.0),
    "D1-reasoning-present": (SOFT, 1.0),
    "D2-metrics-present": (SOFT, 1.0),
    "D3-tool-calls-well-formed": (SOFT, 1.0),
    "E0-truth-present": (SOFT, 1.0),
    "E1-touched": (SOFT, E1_BASE_WEIGHT),
    "E2-req": (SOFT, E2_BASE_WEIGHT),
    "E3-issue-reach": (SOFT, 1.0),
    "E4-issue-resolution": (SOFT, 1.0),
    "E5-no-handwritten-generated": (SOFT, 3.0),
    "F1-no-out-of-scope-churn": (SOFT, 3.0),
    "F2-left-no-scratch-in-repo": (SOFT, 1.0),
}


def check_result(check_id, kind, verdict, detail, weight):
    """CheckResult.model_dump(mode="json"), computed fields included."""
    return {"id": check_id, "kind": kind, "verdict": verdict, "detail": detail,
            "weight": float(weight), "passed": verdict == PASS, "abstained": verdict == ABSTAIN}


def _result(check_id, verdict, detail, weight=None):
    kind, family_weight = FAMILIES[check_id]
    return check_result(check_id, kind, verdict, detail,
                        family_weight if weight is None else weight)


def _missing(what):
    return "%s is not available in the verifier" % what


# --- deterministic.py: trajectory readers ------------------------------------------


def _steps(trajectory):
    steps = trajectory.get("steps")
    return [s for s in steps if isinstance(s, dict)] if isinstance(steps, list) else []


def _tool_calls(step):
    calls = step.get("tool_calls")
    return [c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []


def _call_name(call):
    name = call.get("function_name") or call.get("name")
    return name if isinstance(name, str) else ""


def _call_args(call):
    for key in ("arguments", "args", "input"):
        if key not in call:
            continue
        value = call[key]
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except ValueError:
                return None
            return parsed if isinstance(parsed, dict) else None
        return None
    return {}


def _observations(step):
    observation = step.get("observation")
    results = observation.get("results") if isinstance(observation, dict) else None
    if not isinstance(results, list):
        return {}
    out = {}
    for entry in results:
        if not isinstance(entry, dict):
            continue
        call_id, content = entry.get("source_call_id"), entry.get("content")
        if isinstance(call_id, str) and isinstance(content, str):
            out[call_id] = content
    return out


def _all_calls(trajectory):
    pairs = []
    for step in _steps(trajectory):
        results = _observations(step)
        for call in _tool_calls(step):
            call_id = call.get("tool_call_id")
            pairs.append((call, results.get(call_id, "") if isinstance(call_id, str) else ""))
    return pairs


# --- deterministic.py: path helpers ----------------------------------------------


def _segments(path):
    return [p for p in path.split("/") if p]


def _normalised(segments):
    return "/".join(s for s in segments if s != ".")


def _patch_heads(text):
    heads = {}
    lines = text.splitlines()
    a_path = b_path = None
    index, total = 0, len(lines)
    while index < total:
        line = lines[index]
        if _DIFF_GIT_RE.match(line):
            a_path = b_path = None
        elif line.startswith("--- "):
            a_path = line[4:].split("\t")[0]
        elif line.startswith("+++ "):
            b_path = line[4:].split("\t")[0]
        else:
            hunk = _HUNK_RE.match(line)
            if hunk:
                index = _collect_head(lines, index + 1, hunk, _head_key(a_path, b_path), heads)
                continue
        index += 1
    return heads


def _head_key(a_path, b_path):
    for candidate in (b_path, a_path):
        if candidate and candidate != "/dev/null":
            return _strip_side_prefix(candidate)
    return None


def _collect_head(lines, start, hunk, key, heads):
    new_line = int(hunk.group(3))
    old_left = int(hunk.group(2) or "1")
    new_left = int(hunk.group(4) or "1")
    index = start
    while index < len(lines) and (old_left > 0 or new_left > 0):
        line = lines[index]
        if line.startswith("\\"):
            pass
        elif line.startswith("+") or line.startswith(" ") or line == "":
            if key and new_line <= _PATCH_HEAD_LINES:
                heads.setdefault(key, []).append(line[1:] if line else "")
            new_line += 1
            new_left -= 1
            if not line.startswith("+"):
                old_left -= 1
        elif line.startswith("-"):
            old_left -= 1
        else:
            break
        index += 1
    return index


def _repo_relative(path, roots):
    candidate = _strip_side_prefix(path.strip())
    for prefix in ("/opt/pristine", "/opt"):
        if candidate.startswith(prefix + "/"):
            candidate = candidate[len(prefix):]
    for root in roots:
        if candidate == root:
            return ""
        if candidate.startswith(root + "/"):
            return candidate[len(root) + 1:]
    parts = _segments(candidate)
    if candidate.startswith("/") and len(parts) > 2 and parts[0] == "workspace":
        return "/".join(parts[2:])
    return "/".join(parts)


def _repo_of(path, roots):
    candidate = _strip_side_prefix(path.strip())
    for prefix in ("/opt/pristine", "/opt"):
        if candidate.startswith(prefix + "/"):
            candidate = candidate[len(prefix):]
    for root in roots:
        if candidate == root or candidate.startswith(root + "/"):
            return PurePosixPath(root).name
    parts = _segments(candidate)
    if candidate.startswith("/") and len(parts) > 2 and parts[0] == "workspace":
        return parts[1]
    return None


def _test_id_to_file(test_id):
    head = test_id.split("::")[0].strip()
    if not head or not PurePosixPath(head).suffix:
        return None
    return "/".join(_segments(_strip_side_prefix(head)))


_TOKEN_SPLIT_RE = re.compile(r"[\s'\"`;|&()<>]+")
_PATH_ARG_KEYS = frozenset({"file_path", "path", "command", "pattern", "notebook_path",
                            "paths", "files"})
_POSITIONAL_ARG_KEYS = frozenset({"args", "argv", "positional"})
_ORACLE_SEGMENTS = tuple(tuple(_segments(marker)) for marker in ORACLE_MARKERS)


def _path_like_arguments(name, args):
    out = []
    for key, value in args.items():
        if key == "pattern" and name == "Grep":
            continue
        if key in _PATH_ARG_KEYS or key in _POSITIONAL_ARG_KEYS or key.isdigit():
            if isinstance(value, str):
                out.append(value)
            elif isinstance(value, list):
                out.extend(v for v in value if isinstance(v, str))
    return out


def _oracle_markers_in(text):
    hits = []
    for token in _TOKEN_SPLIT_RE.split(text):
        if not token:
            continue
        segments = _segments(_strip_side_prefix(token))
        for marker, wanted in zip(ORACLE_MARKERS, _ORACLE_SEGMENTS):
            width = len(wanted)
            if width and any(tuple(segments[i:i + width]) == wanted
                             for i in range(len(segments) - width + 1)):
                hits.append(marker)
    return hits


def _is_substantive(text):
    stripped = text.strip()
    if len(stripped) < SUBSTANTIVE_FETCH_CHARS:
        return False
    lowered = stripped.lower()
    return not any(marker in lowered for marker in _REFUSAL_MARKERS)


def _looks_generated(path, head, roots):
    relative = _repo_relative(path, roots)
    segments = _segments(relative)
    name = segments[-1] if segments else ""
    if GENERATOR_SOURCE_RE.search(name):
        return False
    if any(segment in GENERATED_SEGMENTS for segment in segments[:-1]):
        return True
    if name.endswith(GENERATED_SUFFIXES) or GENERATED_NAME_RE.search(name):
        return True
    return bool(GENERATED_HEADER_RE.search(" ".join(head)))


def _is_churn(path, roots, exempt=frozenset()):
    relative = _repo_relative(path, roots)
    segments = _segments(relative)
    name = segments[-1] if segments else ""
    if _normalised(segments) in exempt:
        return False
    root_doc = len(segments) == 1 and name.endswith(ROOT_DOC_SUFFIXES)
    return (any(d in segments for d in CHURN_DIRS) or root_doc or name == "Dockerfile"
            or name.startswith("docker-compose") or name.startswith("CHANGELOG")
            or name.endswith(".lock") or name in CHURN_NAMES)


def _scratch_root(path):
    segments = _segments(path)
    for index, segment in enumerate(segments):
        if segment in SCRATCH_DIRS:
            return "/".join(segments[:index + 1])
    name = segments[-1] if segments else ""
    if name.endswith(SCRATCH_SUFFIXES) or name.startswith("scratch"):
        return path
    return None


def _emitted_test_name(requirement_id):
    return "test_" + requirement_id.lower().replace("-", "_")


def _is_discounted(requirement, weights):
    weight = weights.get(_emitted_test_name(str(requirement.get("id", ""))))
    if weight is not None:
        return weight == KIT_DISCOUNTED_WEIGHT
    return bool(requirement.get("load_bearing"))


def _requirement_weight(requirement, weights):
    declared = weights.get(_emitted_test_name(str(requirement.get("id", ""))))
    if declared is not None:
        return float(declared)
    if requirement.get("load_bearing"):
        return E2_DISCOUNTED_WEIGHT
    return E2_BASE_WEIGHT


def _asks_for_an_edit(requirements):
    for requirement in requirements:
        check = requirement.get("check")
        kind = check.get("kind") if isinstance(check, dict) else None
        if kind not in UNTOUCHED_REQUIREMENT_KINDS:
            return True
    return False


def _touches(files, site_path):
    wanted = site_path.strip("/")
    if not wanted or wanted == ".":
        return [f.path for f in files]
    return [f.path for f in files if f.path == wanted or f.path.endswith("/" + wanted)]


# --- ifchannel.py ------------------------------------------------------------------


def _if_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _if_names(blob, key):
    value = blob.get(key)
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


class IfChannel(object):
    def __init__(self, status=IF_STATUS_ABSENT, score=None, earned_weight=0.0, total_weight=0.0,
                 priced_total=0, priced_answered=0, lists=None, constraint_set_version=None):
        self.status, self.score = status, score
        self.earned_weight, self.total_weight = earned_weight, total_weight
        self.priced_total, self.priced_answered = priced_total, priced_answered
        self.lists = lists or {v: [] for v in _IF_VERDICTS}
        self.constraint_set_version = constraint_set_version

    @classmethod
    def read(cls, path, version, trusted):
        """read_if_channel, with the artifact path given directly."""
        if not trusted:
            return cls(status=STATUS_UNTRUSTED, constraint_set_version=version)
        blob = load_json(path)
        if not isinstance(blob, dict):
            return cls(constraint_set_version=version)
        status = blob.get("status")
        count = lambda v: int(_if_number(v)) if _if_number(v) is not None else 0  # noqa: E731
        return cls(
            status=status if isinstance(status, str) and status else IF_STATUS_ABSENT,
            score=_if_number(blob.get("score")),
            earned_weight=_if_number(blob.get("earned_weight")) or 0.0,
            total_weight=_if_number(blob.get("total_weight")) or 0.0,
            priced_total=count(blob.get("priced_total")),
            priced_answered=count(blob.get("priced_answered")),
            lists={v: _if_names(blob, v) for v in _IF_VERDICTS},
            constraint_set_version=version,
        )

    @property
    def degraded(self):
        return self.priced_answered < self.priced_total or bool(self.lists[IF_ERRORED])

    def verdict(self, name):
        for verdict in _IF_VERDICTS:
            for reported in self.lists[verdict]:
                if reported == name or reported.endswith("::" + name):
                    return verdict
        return None

    def to_dict(self):
        block = {"constraint_set_version": self.constraint_set_version, "status": self.status}
        if self.score is not None:
            block["if_score"] = self.score
            block["if_score_programmatic"] = self.score
        block.update({
            "if_degraded": self.degraded,
            "earned_weight": self.earned_weight,
            "total_weight": self.total_weight,
            "counts": {
                "priced_total": self.priced_total,
                "priced_answered": self.priced_answered,
                "passed": len(self.lists[IF_PASSED]),
                "failed": len(self.lists[IF_FAILED]),
                "skipped": len(self.lists[IF_SKIPPED]),
                "errored": len(self.lists[IF_ERRORED]),
            },
            "per_constraint": [{"id": name, "verdict": verdict}
                               for verdict in _IF_VERDICTS for name in self.lists[verdict]],
        })
        return block


# --- the verifier's evidence, read once --------------------------------------------


class Inputs(object):
    """deterministic._Inputs, built from what the verifier container holds."""

    def __init__(self, verifier_dir, tests_dir, trajectory_path, mode, work_dir=None):
        self.verifier_dir, self.tests_dir = verifier_dir, tests_dir
        # Side inputs: --work-dir first, --verifier-dir as the fallback.
        self.work_dir = work_dir or verifier_dir
        self.mode = mode
        self.trusted = mode == TRUSTED_MODE
        v = lambda name: os.path.join(verifier_dir, name)  # noqa: E731
        w = self.side_path
        t = lambda name: os.path.join(tests_dir, name)  # noqa: E731
        self.config = load_obj(t("config.json"), "tests/config.json") or {}
        self.rubrics = load_obj(t("rubrics.json"), "tests/rubrics.json")
        self.judge_cfg = self._judge_pin(self.config, t) or {}
        weights = load_obj(t("test_weights.json"), "tests/test_weights.json") or {}
        self.test_weights = {k: w for k, w in weights.items()
                             if isinstance(k, str) and isinstance(w, int) and not isinstance(w, bool)}
        self.test_patch = read_text(t("test.patch"))
        self.instance = load_obj(t("instance.json"), "tests/instance.json", required=False)
        self.outcome_json = load_obj(v("outcome.json"), "outcome.json")
        self.reward_json = load_obj(v("reward.json"), "reward.json")
        self.judge_facts = load_obj(w("judge_facts.json"), "judge_facts.json", required=False)
        self.quality = load_obj(w("quality_channel.json"), "quality_channel.json")
        self.per_test = self._read_per_test(w("per_test.tsv"))

        # Trajectory: absent (not delivered) vs invalid (delivered, unusable) vs ok.
        self.trajectory, self.trajectory_state = {}, "absent"
        if trajectory_path and os.path.isfile(trajectory_path):
            data = load_json(trajectory_path)
            self.trajectory = data if isinstance(data, dict) else {}
            if not self.trajectory:
                self.trajectory_state = "unparseable"
            elif not _steps(self.trajectory):
                self.trajectory_state = "no_steps"
            else:
                self.trajectory_state = "ok"
        self.steps = _steps(self.trajectory)
        self.calls = _all_calls(self.trajectory)

        # repo roots: the pin's `repo_roots` stands in for task.toml [[repos]].path.
        roots = set()
        for root in self.judge_cfg.get("repo_roots") or []:
            if isinstance(root, str) and root.startswith("/"):
                roots.add(root.rstrip("/"))
        workdir = self.config.get("workdir")
        if isinstance(workdir, str) and workdir.startswith("/"):
            roots.add(workdir.rstrip("/"))
        self.repo_roots = tuple(sorted(roots, key=len, reverse=True))
        self.repo_names = []
        for root in self.judge_cfg.get("repo_roots") or []:
            name = PurePosixPath(root).name if isinstance(root, str) else ""
            if _SAFE_REPO_NAME.fullmatch(name or "") and name not in self.repo_names:
                self.repo_names.append(name)

        self.patch_text = self._agent_patch_text() if self.trusted else None
        self.patch_files = None if self.patch_text is None else parse_unified_diff(self.patch_text)
        self.patch_heads = {} if self.patch_text is None else _patch_heads(self.patch_text)
        version = self.rubrics.get("constraint_set_version") if self.rubrics else None
        self.if_channel = IfChannel.read(w("site_channel.json"),
                                         version if isinstance(version, str) and version else None,
                                         self.trusted)

    @staticmethod
    def _judge_pin(config, t):
        """The judge pin: config.json["judge"], else the legacy tests/judge.json."""
        if JUDGE_KEY in config:
            pin = config[JUDGE_KEY]
            if isinstance(pin, dict):
                return pin
            warn('tests/config.json "%s" is not a JSON object; the judge pin is empty' % JUDGE_KEY)
            return None
        if os.path.exists(t(LEGACY_JUDGE_FILE)):
            warn('tests/config.json has no "%s" key; read the pin from the legacy tests/%s'
                 % (JUDGE_KEY, LEGACY_JUDGE_FILE))
            return load_obj(t(LEGACY_JUDGE_FILE), "tests/" + LEGACY_JUDGE_FILE)
        warn('no judge pin: tests/config.json has no "%s" key and tests/%s does not exist'
             % (JUDGE_KEY, LEGACY_JUDGE_FILE))
        return None

    def side_path(self, name):
        """A side input's path: the work dir's copy when it exists there, else
        the verifier dir's (older layout), else the work dir's (absent)."""
        work = os.path.join(self.work_dir, name)
        if os.path.exists(work):
            return work
        legacy = os.path.join(self.verifier_dir, name)
        return legacy if os.path.exists(legacy) else work

    @property
    def patch_dir(self):
        """The ONE directory the agent_*.patch set is read from: the work dir
        when it holds any, else the verifier dir. Never a mix of the two, so a
        stale per-repo patch in one cannot join a fresh set in the other."""
        for directory in (self.work_dir, self.verifier_dir):
            try:
                if any(n.startswith("agent_") and n.endswith(".patch") for n in os.listdir(directory)):
                    return directory
            except OSError:
                continue
        return self.work_dir

    @staticmethod
    def _read_per_test(path):
        text = read_text(path)
        tests = {}
        for line in (text or "").splitlines():
            tid, _, status = line.partition("\t")
            if tid and status:
                tests[tid] = status
        return tests

    def _patch_sources(self):
        directory = self.patch_dir
        try:
            names = sorted(n for n in os.listdir(directory)
                           if n.startswith("agent_") and n.endswith(".patch"))
        except OSError:
            names = []
        return [os.path.join(directory, n) for n in names]

    def _agent_patch_text(self):
        """deterministic._agent_patch_text over <patch_dir>/agent_*.patch."""
        sources = self._patch_sources()
        if not sources:
            return None
        chunks = []
        for path in sources:
            try:
                with open(path, encoding="utf-8") as fh:
                    chunks.append(fh.read())
            except (OSError, UnicodeDecodeError):
                return None
        return "\n".join(chunk for chunk in chunks if chunk.strip())

    @property
    def no_patch_reason(self):
        if self.trusted:
            return "no readable agent patch was recorded"
        return ("the recorded edit was not read as evidence: the verifier ran in %r "
                "mode, sharing the agent's container, so the change it recorded is the "
                "agent's own account of what it did" % (self.mode,))

    @property
    def declared_tests(self):
        """FAIL_TO_PASS / PASS_TO_PASS / NEW_TO_PASS from config.json. task.toml's
        repo_tests are not in the image; the lower-case spellings config.json
        also uses (test.sh reads both) stand in for them."""
        buckets = (set(), set(), set())
        for keys, bucket in ((("FAIL_TO_PASS", "fail_to_pass"), buckets[0]),
                             (("PASS_TO_PASS", "pass_to_pass"), buckets[1]),
                             (("NEW_TO_PASS", "new_to_pass"), buckets[2])):
            for key in keys:
                value = self.config.get(key)
                if isinstance(value, list):
                    bucket.update(x for x in value if isinstance(x, str))
        return buckets

    @property
    def reported_tests(self):
        """per_test.tsv, else outcome.json `tests` (the harness's own fallback)."""
        if not self.trusted:
            return {}
        tests = self.per_test
        if not tests and self.outcome_json and isinstance(self.outcome_json.get("tests"), dict):
            tests = self.outcome_json["tests"]
        return {k: s for k, s in tests.items() if isinstance(k, str) and isinstance(s, str)}

    @property
    def reference_paths(self):
        """The pin's `reference_paths` stands in for solution/fix.patch."""
        paths = set()
        for p in self.judge_cfg.get("reference_paths") or []:
            if isinstance(p, str):
                n = _normalised(_segments(_repo_relative(p, self.repo_roots)))
                if n:
                    paths.add(n)
        return frozenset(paths)

    @property
    def repo_tokens(self):
        """_repo_tokens: the pin's repo root names stand in for [[repos]].name."""
        tokens = set(n.lower() for n in self.repo_names)
        for key in ("repo", "github", "target_repo"):
            value = self.config.get(key)
            if not isinstance(value, str) or not value:
                continue
            slug = value.rstrip("/")
            slug = slug[:-4] if slug.endswith(".git") else slug
            slug = slug.split("/")
            if len(slug) >= 2:
                tokens.add("/".join(slug[-2:]).lower())
            tokens.add(slug[-1].lower())
        return {t for t in tokens if len(t) > 2}

    def verifier_patch_paths(self):
        paths = set()
        for line in (self.test_patch or "").splitlines():
            match = _DIFF_GIT_RE.match(line)
            if match:
                paths.update(_normalised(_segments(_repo_relative(side, self.repo_roots)))
                             for side in match.groups())
        return frozenset(p for p in paths if p)

    def graded_test_files(self):
        graded = set()
        f2p, p2p, n2p = self.declared_tests
        for test in f2p | p2p | n2p:
            path = _test_id_to_file(test)
            if path:
                graded.add((None, path))
        for path in self.verifier_patch_paths():
            graded.add((None, path))
        return graded

    def is_graded_test_path(self, path, graded_files):
        relative = _repo_relative(path, self.repo_roots)
        repo = _repo_of(path, self.repo_roots)
        return any((g_repo is None or repo is None or g_repo == repo)
                   and (relative == g or relative.endswith("/" + g))
                   for g_repo, g in graded_files)

    def outcome(self):
        """(score, status, source). score from outcome.json `outcome`, falling back
        to reward.json's; 0.0 and `missing` when neither carries a finite number."""
        for blob in (self.outcome_json, self.reward_json):
            value = blob.get("outcome") if isinstance(blob, dict) else None
            if is_real_number(value):
                return float(value), STATUS_SCORED, "reward.json"
        return 0.0, STATUS_MISSING, "reward.json"


# --- deterministic.py: the checks, in run_checks order ------------------------------

RESULT_JSON = "result.json (the Harbor run record)"


def check_verifier_mode(inp):
    if inp.trusted:
        # _verifier_image_note needs result.json's image ids; absent here -> "".
        return _result("A0-verifier-mode-trusted", PASS,
                       "the verifier ran in %r mode, in its own container" % (inp.mode,))
    if inp.mode is None:
        return _result("A0-verifier-mode-trusted", FAIL,
                       "no verifier mode was recorded, so nothing shows the verifier ran "
                       "outside the agent's container; only %r is trusted" % (TRUSTED_MODE,))
    return _result("A0-verifier-mode-trusted", FAIL,
                   "the verifier ran in %r mode, sharing the agent's container, so everything "
                   "it recorded about this run is agent-controlled and none of it is evidence; "
                   "only %r is trusted" % (inp.mode, TRUSTED_MODE))


def check_uuid_match(inp):
    # The claim is read from the run record (task_id / id / task_name /
    # config.task), never from the trajectory.
    return _result("A1-uuid-match", ABSTAIN,
                   _missing(RESULT_JSON) + ", so no run record names a task uuid")


def check_schema_known(inp):
    version = inp.trajectory.get("schema_version")
    if not isinstance(version, str) or not version:
        return _result("A2-schema-known", ABSTAIN, "trajectory declares no schema_version")
    if version.startswith("ATIF"):
        return _result("A2-schema-known", PASS, "schema_version %s" % version)
    return _result("A2-schema-known", FAIL, "schema_version %s is not an ATIF schema" % version)


def check_tool_vocabulary(inp):
    names = [_call_name(call) for call, _ in inp.calls]
    if not names:
        return _result("A3-tool-vocabulary", ABSTAIN, "trajectory records no tool calls")
    unknown = sorted({n for n in names if n not in KNOWN_TOOLS})
    if unknown:
        return _result("A3-tool-vocabulary", FAIL,
                       "%d unrecognised tool name(s): %s" % (len(unknown), unknown[:5]))
    return _result("A3-tool-vocabulary", PASS, "%d distinct tool name(s), all known" % len(set(names)))


def check_score_agreement(inp):
    if not inp.trusted:
        return _result("A4-score-agreement", ABSTAIN,
                       "the verifier ran in %r mode, sharing the agent's container, so the score "
                       "it recorded agrees with itself by construction and confirms nothing" % (inp.mode,))
    return _result("A4-score-agreement", ABSTAIN,
                   _missing(RESULT_JSON) + "; reward.txt and reward.json are written here by the "
                   "same write_reward call, so comparing them would confirm nothing")


def check_trajectory_present(inp):
    if inp.trajectory_state == "absent":
        return _result("A5-trajectory-present", ABSTAIN, NO_TRAJECTORY)
    return _result("A5-trajectory-present", PASS,
                   "trajectory recorded with %d step(s)" % len(inp.steps))


def check_scored_status(inp):
    if not inp.trusted:
        return _result("B1-scored-status", ABSTAIN,
                       "the verifier ran in %r mode, sharing the agent's container; A0 states the "
                       "cause and this check would only restate it under the wrong name" % (inp.mode,))
    # No result.json -> no verifier_result.status: the harness's
    # "status absent; <source> outcome present" branch.
    _score, status, source = inp.outcome()
    if status == STATUS_SCORED:
        return _result("B1-scored-status", PASS, "status absent; %s outcome present" % source)
    return _result("B1-scored-status", FAIL,
                   "neither outcome.json nor reward.json carries a numeric outcome")


def check_no_exception(inp):
    return _result("B2-no-exception", ABSTAIN,
                   _missing(RESULT_JSON) + " - nothing records whether the harness raised")


def check_reached_finish(inp):
    # termination_reason lives in result.json (absent): the finish-call branch.
    finish_calls = [n for n in (_call_name(c) for c, _ in inp.calls) if n in FINISH_TOOLS]
    if finish_calls:
        return _result("B3-reached-finish", PASS, "run called %s" % finish_calls[0])
    return _result("B3-reached-finish", ABSTAIN,
                   _missing(RESULT_JSON + " termination_reason")
                   + " and the trajectory records no finish call")


def check_turn_ceiling(inp):
    return _result("B4-not-at-turn-ceiling", ABSTAIN,
                   _missing("task.toml (the declared [agent] max_turns / turn_budget)"))


def check_upstream_fetch(inp):
    if not inp.calls:
        return _result("C1-no-upstream-content-fetched", ABSTAIN, "trajectory records no tool calls")
    tokens = inp.repo_tokens
    if not tokens:
        return _result("C1-no-upstream-content-fetched", ABSTAIN, "task declares no repository to protect")
    offenders, fetches = [], 0
    for call, content in inp.calls:
        if _call_name(call) not in ("WebFetch", "WebSearch"):
            continue
        fetches += 1
        if not _is_substantive(content):
            continue
        hit = sorted(t for t in tokens if t in content.lower())
        if hit:
            offenders.append("%s returned %d chars naming %s" % (_call_name(call), len(content), hit[0]))
    if offenders:
        return _result("C1-no-upstream-content-fetched", FAIL, "; ".join(offenders[:3]))
    return _result("C1-no-upstream-content-fetched", PASS,
                   "%d web call(s), none returned substantive content naming the task repo" % fetches)


def _bash_commands(inp):
    commands = []
    for call, _ in inp.calls:
        if _call_name(call) != "Bash":
            continue
        command = (_call_args(call) or {}).get("command")
        if isinstance(command, str) and command:
            commands.append(command)
    return commands


def check_history_probe(inp):
    if not inp.calls:
        return _result("C1b-history-probe", ABSTAIN, "trajectory records no tool calls")
    probes = [c for c in _bash_commands(inp) if re.search(r"\bgit\s+(log|blame|show)\b", c)]
    detail = "%d local git-history probe(s)" % len(probes) + (": %s" % probes[0][:120] if probes else "")
    return _result("C1b-history-probe", PASS, detail)


def check_third_party_fetch(inp):
    if not inp.calls:
        return _result("C1c-third-party-fetch", ABSTAIN, "trajectory records no tool calls")
    tokens = inp.repo_tokens
    clones = [c for c in _bash_commands(inp) if re.search(r"\bgit\s+clone\b", c)]
    third_party = [c for c in clones if not any(t in c.lower() for t in tokens)]
    detail = "%d git clone(s), %d third-party" % (len(clones), len(third_party))
    return _result("C1c-third-party-fetch", PASS,
                   detail + (": %s" % third_party[0][:120] if third_party else ""))


def check_oracle_path(inp):
    if not inp.calls:
        return _result("C2-no-oracle-path", ABSTAIN, "trajectory records no tool calls")
    hits = []
    for call, _ in inp.calls:
        args = _call_args(call)
        if not args:
            continue
        name = _call_name(call)
        for value in _path_like_arguments(name, args):
            for marker in _oracle_markers_in(value):
                hits.append("%s referenced %s" % (name, marker))
    if hits:
        return _result("C2-no-oracle-path", FAIL, "; ".join(sorted(set(hits))[:3]))
    return _result("C2-no-oracle-path", PASS, "no tool call referenced a grader-owned path")


def check_graded_test_write(inp):
    """Harness rule over the raw agent patch, plus test.sh's own record of a
    graded test file it stripped (judge_facts.json, rule graded_test_file)."""
    stripped = []
    for entry in (inp.judge_facts or {}).get("stripped_paths") or []:
        if isinstance(entry, dict) and entry.get("rule") == "graded_test_file" \
                and isinstance(entry.get("path"), str):
            stripped.append(entry["path"])
    files = inp.patch_files
    if files is None and not stripped:
        return _result("C3-no-graded-test-write", ABSTAIN, inp.no_patch_reason)
    graded = inp.graded_test_files()
    touched = sorted({f.path for f in files or [] if inp.is_graded_test_path(f.path, graded)}
                     | set(stripped))
    if touched:
        return _result("C3-no-graded-test-write", FAIL,
                       "patch modifies graded test file(s): %s" % touched[:3])
    return _result("C3-no-graded-test-write", PASS,
                   "patch touches %d file(s), none a graded test" % len(files))


def check_test_evasion(inp):
    files = inp.patch_files
    if files is None:
        return _result("C4-no-test-evasion", ABSTAIN, inp.no_patch_reason)
    f2p, p2p, n2p = inp.declared_tests
    graded_functions = {t.split("::")[-1] for t in f2p | p2p | n2p if "::" in t}
    graded_files = inp.graded_test_files()
    offences = []
    for diff in files:
        if not inp.is_graded_test_path(diff.path, graded_files):
            continue
        for line in diff.added:
            if EVASION_RE.search(line):
                offences.append("%s adds %s" % (diff.path, line.strip()[:60]))
                break
        for line in diff.removed:
            match = TEST_DEF_RE.match(line)
            if match and match.group(1) in graded_functions:
                offences.append("%s removes %s" % (diff.path, match.group(1)))
                break
    if offences:
        return _result("C4-no-test-evasion", FAIL, "; ".join(offences[:3]))
    return _result("C4-no-test-evasion", PASS, "no graded test removed, skipped or xfailed")


NO_PER_TEST = "per_test.tsv / outcome.json record no per-test outcomes"


def check_f2p_to_skip(inp):
    f2p, _, _ = inp.declared_tests
    if not f2p:
        return _result("C5-no-f2p-to-skip", ABSTAIN, "task declares no FAIL_TO_PASS targets")
    reported = inp.reported_tests
    if not reported:
        return _result("C5-no-f2p-to-skip", ABSTAIN, NO_PER_TEST)
    skipped = sorted(t for t in f2p if reported.get(t) == "skipped")
    if skipped:
        return _result("C5-no-f2p-to-skip", FAIL,
                       "%d f2p target(s) skipped: %s" % (len(skipped), skipped[:2]))
    return _result("C5-no-f2p-to-skip", PASS, "none of %d f2p target(s) is skipped" % len(f2p))


def check_unknown_breaks(inp):
    reported = inp.reported_tests
    if not reported:
        return _result("C6-no-unknown-breaks", ABSTAIN, NO_PER_TEST)
    f2p, p2p, n2p = inp.declared_tests
    preserved = f2p | p2p | n2p
    broken = sorted(t for t, s in reported.items() if s == "failed" and t not in preserved)
    if broken:
        return _result("C6-no-unknown-breaks", FAIL,
                       "%d undeclared test(s) failed: %s" % (len(broken), broken[:2]))
    failed = sum(1 for s in reported.values() if s == "failed")
    return _result("C6-no-unknown-breaks", PASS,
                   "%d failure(s), all inside the declared preserve set" % failed)


def check_constraints_held(inp):
    # reward.json `constraints` is the scalar Harbor copies into
    # verifier_result.rewards.constraints.
    held = (inp.reward_json or {}).get("constraints")
    if isinstance(held, bool) or not isinstance(held, (int, float)):
        return _result("C7-constraints-held", ABSTAIN, "reward.json records no constraints scalar")
    if float(held) < 1.0:
        return _result("C7-constraints-held", FAIL, "grader reports constraints=%g" % float(held))
    return _result("C7-constraints-held", PASS, "grader reports constraints=1")


def _step_reasoning(step):
    for key in ("reasoning_content", "reasoning", "thinking"):
        value = step.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, list):
            for block in value:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    return block["text"]
                if isinstance(block, str) and block.strip():
                    return block
    return ""


def check_reasoning(inp):
    steps = inp.steps
    if not steps:
        return _result("D1-reasoning-present", ABSTAIN, "trajectory records no steps")
    with_reasoning = sum(1 for step in steps if _step_reasoning(step))
    if with_reasoning:
        return _result("D1-reasoning-present", PASS,
                       "%d/%d step(s) record reasoning" % (with_reasoning, len(steps)))
    return _result("D1-reasoning-present", FAIL, "none of %d step(s) records reasoning" % len(steps))


def check_metrics(inp):
    metrics = inp.trajectory.get("final_metrics")
    if isinstance(metrics, dict) and metrics:
        return _result("D2-metrics-present", PASS, "final_metrics carries %d key(s)" % len(metrics))
    return _result("D2-metrics-present", FAIL, "trajectory carries no final_metrics")


def check_tool_calls_well_formed(inp):
    calls = inp.calls
    if not calls:
        return _result("D3-tool-calls-well-formed", ABSTAIN, "trajectory records no tool calls")
    malformed = [_call_name(call) for call, _ in calls if _call_args(call) is None]
    if malformed:
        return _result("D3-tool-calls-well-formed", FAIL,
                       "%d call(s) with unparseable arguments: %s" % (len(malformed), sorted(set(malformed))[:3]))
    return _result("D3-tool-calls-well-formed", PASS,
                   "all %d tool call(s) carry parseable arguments" % len(calls))


def check_truth_present(inp):
    return _result("E0-truth-present", ABSTAIN,
                   "solution/TRUTH.md is not shipped to the verifier (it never leaves the task's "
                   "private solution/ carrier)")


def _e1_instance(site_path, weight, files, all_targets_pass, no_patch_reason):
    check_id = "E1-touched:%s" % site_path
    hit = _touches(files, site_path) if files is not None else []
    if files is None:
        verdict, detail = ABSTAIN, no_patch_reason
    elif hit:
        verdict, detail = PASS, "patch touches %s" % hit[0]
    elif all_targets_pass:
        verdict, detail = (ABSTAIN, "site untouched but every target test passed — "
                           "a different route is not a defect")
    else:
        verdict, detail = FAIL, "patch touches no file at %s" % site_path
    return check_result(check_id, SOFT, verdict, detail, weight)


def _requirement_status(inp, emitted, reported):
    verdict = inp.if_channel.verdict(emitted)
    if verdict is not None:
        return None if verdict in (IF_ERRORED, IF_SKIPPED) else verdict
    return next((s for k, s in reported.items() if k == emitted or k.endswith("::" + emitted)), None)


def check_sites(inp):
    sites = (inp.rubrics or {}).get("sites")
    sites = [s for s in sites if isinstance(s, dict)] if isinstance(sites, list) else []
    if not sites:
        return []
    files = inp.patch_files
    weights = inp.test_weights
    f2p, _, _ = inp.declared_tests
    reported = inp.reported_tests
    all_targets_pass = bool(f2p) and bool(reported) and all(reported.get(t) == "passed" for t in f2p)
    out = []
    for site in sites:
        site_path = str(site.get("path") or "")
        requirements = [r for r in (site.get("requirements") or []) if isinstance(r, dict)]
        discounted = any(_is_discounted(r, weights) for r in requirements)
        weight = E1_DISCOUNTED_WEIGHT if discounted else E1_BASE_WEIGHT
        if _asks_for_an_edit(requirements):
            out.append(_e1_instance(site_path, weight, files, all_targets_pass, inp.no_patch_reason))
        for requirement in requirements:
            req_id = str(requirement.get("id") or "")
            weight = _requirement_weight(requirement, weights)
            emitted = _emitted_test_name(req_id)
            status = _requirement_status(inp, emitted, reported)
            req_check = "E2-req:%s" % req_id
            if status is None:
                out.append(check_result(req_check, SOFT, ABSTAIN,
                                        "no %s result in the instruction-following channel or the "
                                        "verifier's per-test map" % emitted, weight))
            elif status == "passed":
                out.append(check_result(req_check, SOFT, PASS, "%s passed" % emitted, weight))
            else:
                out.append(check_result(req_check, SOFT, FAIL, "%s is %s" % (emitted, status), weight))
    return out


def _first_content_line(text):
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped
    return ""


def _titles_from_instance_json(data):
    titles = []
    title = data.get("title")
    if isinstance(title, str) and title.strip():
        titles.append(title.strip())
    for field in ("issue_titles", "titles"):
        value = data.get(field)
        if isinstance(value, list):
            titles += [v.strip() for v in value if isinstance(v, str) and v.strip()]
    statement = data.get("problem_statement")
    if isinstance(statement, str):
        first = _first_content_line(statement)
        if first:
            titles.append(first)
    return titles


def announced_issue_titles(inp):
    """issues.extract_issue_titles. tests/instance.json when shipped; else
    tests/config.json, which test.sh documents as the union of the bundle's
    test_config.json and instance.json (it carries problem_statement, whose
    first line is instruction.md's `# ` heading). instruction.md itself is not
    in /tests."""
    titles = []
    for source in (inp.instance, inp.config):
        if isinstance(source, dict):
            titles = _titles_from_instance_json(source)
            if titles:
                break
    seen, deduped = set(), []
    for title in titles:
        if title.lower() not in seen:
            seen.add(title.lower())
            deduped.append(title)
    return deduped


def check_issue_reach(inp):
    titles = announced_issue_titles(inp)
    if not titles:
        detail = ("no issue announcement is available to the verifier (tests/instance.json and "
                  "config.json problem_statement carry no title; instruction.md is not in /tests)")
        return [_result("E3-issue-reach", ABSTAIN, detail),
                _result("E4-issue-resolution", ABSTAIN, detail)]
    files = inp.patch_files
    if files is None:
        reach = _result("E3-issue-reach", ABSTAIN, inp.no_patch_reason)
    elif files:
        reach = _result("E3-issue-reach", PASS,
                        "patch reaches %d file(s) for %d announced issue(s)" % (len(files), len(titles)))
    else:
        reach = _result("E3-issue-reach", FAIL,
                        "%d announced issue(s) but the patch reaches no file" % len(titles))
    f2p, _, _ = inp.declared_tests
    reported = inp.reported_tests
    targets = {t: reported.get(t) for t in f2p if t in reported}
    if not targets:
        resolution = _result("E4-issue-resolution", ABSTAIN,
                             "no f2p target outcome recorded for the announced issue")
    elif all(s == "passed" for s in targets.values()):
        resolution = _result("E4-issue-resolution", PASS,
                             "all %d announced target(s) pass" % len(targets))
    else:
        unresolved = sorted(t for t, s in targets.items() if s != "passed")
        resolution = _result("E4-issue-resolution", FAIL,
                             "%d announced target(s) unresolved: %s" % (len(unresolved), unresolved[:2]))
    return [reach, resolution]


def check_generated(inp):
    files = inp.patch_files
    if files is None:
        return _result("E5-no-handwritten-generated", ABSTAIN, inp.no_patch_reason)
    generated = sorted({f.path for f in files
                        if _looks_generated(f.path, inp.patch_heads.get(f.path, []), inp.repo_roots)})
    if generated:
        return _result("E5-no-handwritten-generated", FAIL,
                       "patch hand-edits %d generated file(s): %s" % (len(generated), generated[:2]))
    return _result("E5-no-handwritten-generated", PASS,
                   "patch touches %d file(s), none generated" % len(files))


def check_out_of_scope_churn(inp):
    files = inp.patch_files
    if files is None:
        return _result("F1-no-out-of-scope-churn", ABSTAIN, inp.no_patch_reason)
    exempt = inp.reference_paths
    churn = sorted({f.path for f in files if _is_churn(f.path, inp.repo_roots, exempt)})
    if churn:
        return _result("F1-no-out-of-scope-churn", FAIL,
                       "patch touches %d out-of-scope path(s): %s" % (len(churn), churn[:2]))
    return _result("F1-no-out-of-scope-churn", PASS,
                   "patch touches %d file(s), none CI/docker/docs/lockfile" % len(files))


def check_scratch(inp):
    files = inp.patch_files
    if files is None:
        return _result("F2-left-no-scratch-in-repo", ABSTAIN, inp.no_patch_reason)
    trees = {}
    for diff in files:
        root = _scratch_root(diff.path)
        if root is None:
            continue
        trees.setdefault(root, set()).add("/".join(_segments(diff.path)))
    left = sorted(root for root, paths in trees.items()
                  if not any(p == "%s/.gitignore" % root for p in paths))
    if left:
        return _result("F2-left-no-scratch-in-repo", FAIL,
                       "patch leaves %d untracked-scratch tree(s) in the repo: %s" % (len(left), left[:2]))
    return _result("F2-left-no-scratch-in-repo", PASS,
                   "no scratch left in the repo (%d self-ignoring tree(s) present)" % len(trees))


# Checks that read only the trajectory: without one they abstain (see docstring).
TRAJECTORY_CHECKS = frozenset({
    "A2-schema-known", "A3-tool-vocabulary", "B3-reached-finish",
    "C1-no-upstream-content-fetched", "C1b-history-probe", "C1c-third-party-fetch",
    "C2-no-oracle-path", "D1-reasoning-present", "D2-metrics-present",
    "D3-tool-calls-well-formed",
})


def run_checks(inp):
    mode_check = check_verifier_mode(inp)
    if inp.trajectory_state in ("unparseable", "no_steps"):
        # Delivered but unusable: exactly the harness's short-circuit.
        detail = ("the recorded trajectory does not parse as a trajectory object"
                  if inp.trajectory_state == "unparseable"
                  else "the recorded trajectory has no steps — nothing to grade")
        return [mode_check, _result("A5-trajectory-present", FAIL, detail)]
    checks = [
        mode_check,
        check_uuid_match(inp),
        check_schema_known(inp),
        check_tool_vocabulary(inp),
        check_score_agreement(inp),
        check_trajectory_present(inp),
        check_scored_status(inp),
        check_no_exception(inp),
        check_reached_finish(inp),
        check_turn_ceiling(inp),
        check_upstream_fetch(inp),
        check_history_probe(inp),
        check_third_party_fetch(inp),
        check_oracle_path(inp),
        check_graded_test_write(inp),
        check_test_evasion(inp),
        check_f2p_to_skip(inp),
        check_unknown_breaks(inp),
        check_constraints_held(inp),
        check_reasoning(inp),
        check_metrics(inp),
        check_tool_calls_well_formed(inp),
        check_truth_present(inp),
    ] + check_sites(inp) + check_issue_reach(inp) + [
        check_generated(inp),
        check_out_of_scope_churn(inp),
        check_scratch(inp),
    ]
    if inp.trajectory_state == "absent":
        checks = [_result(c["id"], ABSTAIN, NO_TRAJECTORY) if c["id"] in TRAJECTORY_CHECKS else c
                  for c in checks]
    return checks


def det_score(checks):
    soft = [c for c in checks if c["kind"] == SOFT and c["verdict"] != ABSTAIN]
    denominator = fsum312(c["weight"] for c in soft)
    if denominator <= 0:
        return 0.0
    return fsum312(c["weight"] for c in soft if c["verdict"] == PASS) / denominator


def gate(checks):
    return 0 if any(c["kind"] == HARD and c["verdict"] == FAIL for c in checks) else 1


def hard_failures(checks):
    return [c["id"] for c in checks if c["kind"] == HARD and c["verdict"] == FAIL]


# --- rubric channel: quality_channel.json -> ItemResolution ------------------------


def _plain_note(note):
    for pattern, text in _LADDER_NOTES:
        if pattern.search(note):
            return text
    return note


def _judge_text(verdict, rationale):
    head = "Yes." if verdict == "yes" else "No."
    rationale = (rationale or "").strip()
    return head + " " + rationale if rationale else head


def resolve_items(items, quality):
    """One resolution per bundle item, in corpus order (score.replay shape).

    Each resolution: item_id, resolution, rationale (the ladder note the
    harness would write), reason (abstain code), text / evidence (the judge's
    own words, for the reader-facing rows).
    """
    by_id = {}
    for q in quality.get("items") or []:
        if isinstance(q, dict) and isinstance(q.get("id"), str):
            by_id[q["id"]] = q
    out, missing = [], []
    for item in load_items(items):
        q = by_id.get(item["id"])
        res = {"item_id": item["id"], "text": "", "evidence": ""}
        verdict = q.get("verdict") if q else None
        if q is None:
            missing.append(item["id"])
            res.update(resolution=ABSTAINED, rationale="no verdicts stored", reason=ABSTAIN_NO_VERDICT)
        elif q.get("resolution") in (SATISFIED, FAILED, ABSTAINED) and isinstance(q.get("ladder_rationale"), str):
            # llm_judge.py ran the harness ladder itself: take its outcome as is.
            resolution = q["resolution"]
            if resolution == ABSTAINED:
                res.update(resolution=ABSTAINED, rationale=q["ladder_rationale"],
                           reason=str(q.get("reason") or ABSTAIN_NO_VERDICT))
            else:
                res.update(resolution=resolution, rationale=q["ladder_rationale"], reason=None,
                           text=_judge_text("yes" if resolution == SATISFIED else "no", q.get("rationale")),
                           evidence=q.get("evidence") if isinstance(q.get("evidence"), str) else "")
        elif verdict in ("yes", "no"):  # a channel written before the ladder port
            votes = [s.get("verdict") for s in q.get("samples") or [] if isinstance(s, dict)]
            yes, no = votes.count("yes"), votes.count("no")
            if not yes and not no:  # a deterministic decision: one citing verdict
                yes, no = (1, 0) if verdict == "yes" else (0, 1)
            if verdict == "yes":
                rationale = ("unanimous satisfied across %d citing verdict(s)" % yes if not no
                             else "strict majority satisfied (%d-%d)" % (yes, no))
            else:
                rationale = ("unanimous not-satisfied across %d citing verdict(s)" % no if not yes
                             else "strict majority not-satisfied (%d-%d)" % (no, yes))
            res.update(resolution=SATISFIED if verdict == "yes" else FAILED, rationale=rationale,
                       reason=None, text=_judge_text(verdict, q.get("rationale")),
                       evidence=q.get("evidence") if isinstance(q.get("evidence"), str) else "")
        elif verdict == "not_judged":
            target = str(item.get("evaluation_target") or "").replace("_", " ")
            res.update(resolution=ABSTAINED, reason=ABSTAIN_EVIDENCE_MISSING,
                       rationale="not judged: %s: the %s evidence was not available to the "
                                 "verifier's judge" % (q.get("reason") or "evidence_unavailable", target))
        else:  # "abstain" (or an unknown verdict, read as no verdict)
            reason = q.get("reason") if verdict == "abstain" else None
            if reason == "tie":
                votes = [s.get("verdict") for s in q.get("samples") or [] if isinstance(s, dict)]
                res.update(resolution=ABSTAINED, reason=ABSTAIN_DISAGREEMENT,
                           rationale="exact split (%d-%d)" % (votes.count("yes"), votes.count("no")))
            elif not reason or reason == ABSTAIN_NO_VERDICT:
                res.update(resolution=ABSTAINED, reason=ABSTAIN_NO_VERDICT, rationale="no verdicts stored")
            else:
                res.update(resolution=ABSTAINED, reason=str(reason), rationale="not judged: %s" % reason)
        out.append(res)
    return apply_prerequisites(items, out), missing


def apply_prerequisites(items, resolutions):
    by_id = {r["item_id"]: r for r in resolutions}
    requires = {i["id"]: i["requires"] for i in items if i.get("requires")}
    for _ in range(len(requires)):
        changed = False
        for item_id, parent_id in requires.items():
            current = by_id.get(item_id)
            if current is None or current["reason"] == ABSTAIN_UNLICENSED:
                continue
            parent = by_id.get(parent_id)
            if parent is not None and parent["resolution"] == SATISFIED:
                continue
            note = "absent" if parent is None else parent["resolution"]
            by_id[item_id] = {"item_id": item_id, "resolution": ABSTAINED,
                              "rationale": "prerequisite %s is %s" % (parent_id, note),
                              "reason": ABSTAIN_UNLICENSED, "text": "", "evidence": ""}
            changed = True
        if not changed:
            break
    return [by_id[r["item_id"]] for r in resolutions]


def fsum312(values):
    """sum() of floats exactly as CPython >= 3.12 computes it (Neumaier
    compensation). The harness runs on 3.12+; the verifier image ships 3.11,
    whose plain sum() differs in the last bit (0.6200000000000001 vs 0.62)."""
    total, c = 0.0, 0.0
    for x in values:
        x = float(x)
        t = total + x
        if abs(total) >= abs(x):
            c += (total - t) + x
        else:
            c += (x - t) + total
        total = t
    if c and math.isfinite(c):
        total += c
    return total


def effective_weights(items):
    if not items:
        return {}
    present = {i["dimension"] for i in items}
    share_total = sum(DIMENSION_BUDGET[name] for name in present)
    mass = defaultdict(float)
    for i in items:
        mass[i["dimension"]] += abs(i["weight"])
    return {i["id"]: (DIMENSION_BUDGET[i["dimension"]] / share_total) * i["weight"] / mass[i["dimension"]]
            for i in items}


def tally_detail(items, resolutions):
    by_id = {r["item_id"]: r for r in resolutions}
    items = load_items(items)
    weights = effective_weights(items)
    denominator = fsum312(weights[i["id"]] for i in items
                          if i["weight"] > 0 and by_id[i["id"]]["resolution"] != ABSTAINED)
    numerator = fsum312(weights[i["id"]] for i in items if by_id[i["id"]]["resolution"] == SATISFIED)
    fired = [i["id"] for i in items if i["weight"] < 0 and by_id[i["id"]]["resolution"] == SATISFIED]
    if denominator == 0:
        return {"score": 0.0, "raw": 0.0, "numerator": numerator, "denominator": denominator,
                "guardrails_fired": fired}
    raw = numerator / denominator
    score = FLOOR_BAND + 0.95 * min(1.0, raw) if raw >= 0 else FLOOR_BAND / (1 - raw)
    return {"score": score, "raw": raw, "numerator": numerator, "denominator": denominator,
            "guardrails_fired": fired}


# --- compose.py / writeback.py -------------------------------------------------------


def n_targets_from_config_json(data):
    if not isinstance(data, dict):
        return 0

    def sized(key):
        value = data.get(key)
        return len(value) if isinstance(value, (dict, list)) else None

    modern = {key: sized(key) for key in TARGET_TEST_KEYS}
    if all(size is None for size in modern.values()):
        return sized(LEGACY_F2P_KEY) or 0
    return sum(size for size in modern.values() if size is not None)


def min_outcome_gap(n_targets):
    unit = 1.0 / n_targets if n_targets > 0 else 1.0
    return max(unit, MIN_MEANINGFUL_GAP)


def derive_alpha(n_targets):
    gap = min_outcome_gap(n_targets)
    return min(ALPHA_CAP, gap / (2 * (1 + gap)))


def process_score(det, rubric):
    return det if rubric is None else (det + RUBRIC_WEIGHT * rubric) / 2


def compose(det, rubric, outcome, gate_value, n_targets, stratum=None):
    gap = min_outcome_gap(n_targets)
    alpha = derive_alpha(n_targets)
    process = process_score(det, rubric)
    score_eval = gate_value * ((1 - 2 * alpha) * outcome + 2 * alpha * process)
    if stratum:
        stratum_size = len(stratum)
        spread = max(stratum) - min(stratum)
        stratified = 0.5 if spread < FLAT_STRATUM else (process - min(stratum)) / spread
    else:
        stratum_size, stratified = 1, 0.5
    score_rl = gate_value * ((1 - 2 * alpha) * outcome + 2 * alpha * stratified)
    return {"det": det, "rubric": rubric, "process": process, "outcome": outcome, "gate": gate_value,
            "alpha": alpha, "min_outcome_gap": gap, "process_stratified": stratified,
            "score_eval": score_eval, "score_rl": score_rl, "stratum_size": stratum_size}


def run_status(outcome_status, gate_value, judged):
    if not judged:
        return STATUS_UNJUDGED
    if outcome_status != STATUS_SCORED:
        return STATUS_UNVERIFIABLE
    if not gate_value:
        return STATUS_VOIDED
    return STATUS_SCORED


# --- finaldiff.py ------------------------------------------------------------------------


def clean_diff(text):
    kept, dropped = [], 0
    for block in _BLOCK_START.split(text):
        if not block.strip():
            continue
        header = block.split("\n", 1)[0]
        if header.startswith("diff ") and _NOISE_PATH.search(header):
            dropped += 1
            continue
        kept.append("".join(BINARY_MARKER + "\n" if line.startswith("Binary files ") else line
                            for line in block.splitlines(True)))
    return _HEADER_TIMESTAMP.sub(r"\1", "".join(kept)), dropped


def load_final_diff(inp):
    """(status, text, truncated): the live layout, one agent_<repo>.patch per repo."""
    if not inp.trusted:
        return STATUS_UNTRUSTED, "", False
    sources = [os.path.join(inp.patch_dir, "agent_%s.patch" % name) for name in inp.repo_names]
    sources = [p for p in sources if os.path.isfile(p)]
    if not sources:
        return FD_STATUS_ABSENT, "", False
    chunks = []
    for source in sources:
        chunk = read_text(source)
        if chunk is None:
            return FD_STATUS_ABSENT, "", False
        chunks.append(chunk if not chunk or chunk.endswith("\n") else chunk + "\n")
    text, _dropped = clean_diff("".join(chunks))
    truncated = len(text) > FINAL_DIFF_CLIP_CHARS
    if truncated:
        text = (text[:FINAL_DIFF_CLIP_CHARS].rstrip("\n") + "\n"
                + TRUNCATION_NOTE.format(n=FINAL_DIFF_CLIP_CHARS))
    if not text.strip():
        text = EMPTY_DIFF_MARKER
    return FD_STATUS_PRESENT, text, truncated


def summarize_final_diff(status, text, truncated, items, resolutions):
    text = text if status == FD_STATUS_PRESENT else ""
    lines = text.splitlines()
    targeted = [i["id"] for i in (items or []) if i.get("evaluation_target") == FINAL_DIFF_TARGET]
    decided = {r["item_id"] for r in resolutions if r["resolution"] in (SATISFIED, FAILED)}
    return {
        "status": status,
        "files_changed": sum(1 for l in lines if l.startswith("diff ")),
        "lines_added": sum(1 for l in lines if l.startswith("+") and not l.startswith("+++")),
        "lines_removed": sum(1 for l in lines if l.startswith("-") and not l.startswith("---")),
        "truncated": truncated,
        "rubric_items": len(targeted),
        "rubric_items_assessed": sum(1 for i in targeted if i in decided),
    }


# --- the record ----------------------------------------------------------------------------


def bundle_fingerprint(inp, items):
    bundle = inp.judge_cfg.get("bundle") if isinstance(inp.judge_cfg.get("bundle"), dict) else {}
    fingerprint, recorded = bundle.get("fingerprint"), bundle.get("items_digest")
    if not isinstance(fingerprint, str) or not fingerprint:
        warn("the judge pin carries no bundle.fingerprint; version.bundle_fingerprint is null")
        return None
    if items is None:
        warn("rubrics.json items unreadable; cannot confirm bundle.items_digest, fingerprint is null")
        return None
    current = items_digest(items)
    if recorded != current:
        warn("rubrics.json items digest %s != the judge pin's bundle.items_digest %r; the recorded "
             "fingerprint no longer describes this rubric, so it is reported as null" % (current, recorded))
        return None
    return fingerprint


def judge_model(quality):
    judge = (quality or {}).get("judge")
    if isinstance(judge, dict):
        for key in ("model_served", "model_requested"):
            if isinstance(judge.get(key), str) and judge[key]:
                return judge[key]
    return None


def _str_or_none(value):
    return value if isinstance(value, str) and value else None


def _int_or_none(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _usage(value):
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items()
            if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)}


def _request_ids(value):
    return [r for r in value if isinstance(r, str) and r] if isinstance(value, list) else []


def _pin_overrides(value):
    """llm_judge.py's judge.pin_overrides ({var: {pinned, effective}}); None when
    the channel predates it."""
    if not isinstance(value, dict):
        return None
    return {k: dict(v) for k, v in value.items() if isinstance(k, str) and isinstance(v, dict)}


def pin_overrides(quality):
    judge = (quality or {}).get("judge")
    if not isinstance(judge, dict):
        return {}
    return _pin_overrides(judge.get("pin_overrides")) or {}


def judge_block(quality, model):
    """process.json `judge`: the existing `model` key first, then the judge's own
    provenance copied from quality_channel.json (its `judge` block plus the
    channel status, cap and cross-check summary). Null / empty when the channel
    or a key is absent; nothing here is recomputed or inferred."""
    quality = quality if isinstance(quality, dict) else {}
    judge = quality.get("judge") if isinstance(quality.get("judge"), dict) else {}
    agreement = judge.get("agreement")
    calls = []
    for call in judge.get("calls") if isinstance(judge.get("calls"), list) else []:
        if not isinstance(call, dict):
            continue
        calls.append({
            "target": _str_or_none(call.get("target")),
            "status": _str_or_none(call.get("status")),
            "model": _str_or_none(call.get("model_served")),
            "wire": _str_or_none(call.get("wire")),
            "usage": _usage(call.get("usage")),
            "request_ids": _request_ids(call.get("request_ids")),
        })
    summary = quality.get("cross_check_summary")
    model_pinned = judge.get("model_pinned")
    effective = judge.get("effective")
    warns = judge.get("warnings")
    return {
        "model": model,
        "model_served": _str_or_none(judge.get("model_served")),
        "provider": _str_or_none(judge.get("provider")),
        "wire": _str_or_none(judge.get("wire")),
        "judge_version": _str_or_none(judge.get("judge_version")),
        "prompt_version": _str_or_none(judge.get("prompt_version")),
        "rubric_version": _str_or_none(judge.get("rubric_version")),
        "model_pinned": model_pinned if isinstance(model_pinned, bool) else None,
        "effort": _str_or_none(judge.get("effort")),
        "samples": _int_or_none(judge.get("samples")),
        "council": _str_or_none(judge.get("council")),
        "agreement": float(agreement) if is_real_number(agreement) else None,
        "prompt_sha256": _str_or_none(judge.get("prompt_sha256")),
        "rubric_sha256": _str_or_none(judge.get("rubric_sha256")),
        "evidence_sha256": _str_or_none(judge.get("evidence_sha256")),
        "usage": _usage(judge.get("usage")),
        "request_ids": _request_ids(judge.get("request_ids")),
        "calls": calls,
        "status": _str_or_none(quality.get("status")),
        "cap_applied": _str_or_none(quality.get("cap_applied")),
        "cross_check_summary": dict(summary) if isinstance(summary, dict) else {},
        # Per-run overrides of the pin (llm_judge.py JUDGE_* variables): `model` and
        # `provider` above are already the effective values.
        "pin_overrides": _pin_overrides(judge.get("pin_overrides")),
        "effective": dict(effective) if isinstance(effective, dict) else None,
        "warnings": [w for w in warns if isinstance(w, str)] if isinstance(warns, list) else [],
    }


def build(inp):
    checks = run_checks(inp)
    det = det_score(checks)
    gate_value = gate(checks)
    outcome_score, outcome_status, outcome_source = inp.outcome()

    items = valid_items(inp.rubrics)
    if inp.rubrics is not None and items is None:
        warn("rubrics.json items do not load (bad id/weight/dimension); no rubric tally")
    quality = inp.quality or {}
    q_status = quality.get("status") if isinstance(quality.get("status"), str) else "absent"
    resolutions, missing, tally = [], [], None
    if items is not None and q_status in QUALITY_TALLIED:
        resolutions, missing = resolve_items(items, quality)
        if missing:
            warn("quality_channel.json has no verdict for %s; abstained as no_verdict" % missing)
        tally = tally_detail(items, resolutions)
    elif q_status not in QUALITY_TALLIED:
        warn("quality channel status %r: no rubric channel, process = det" % q_status)
    rubric = None if tally is None else tally["score"]
    judged = q_status == "scored"

    n_targets = n_targets_from_config_json(inp.config)
    comp = compose(det, rubric, outcome_score, gate_value, n_targets)
    status = run_status(outcome_status, gate_value, judged)
    model = judge_model(quality)
    fingerprint = bundle_fingerprint(inp, items)
    fd_status, fd_text, fd_truncated = load_final_diff(inp)
    abstained_ids = [r["item_id"] for r in resolutions if r["resolution"] == ABSTAINED]
    rubric_raw = None if tally is None else tally["raw"]
    alpha = round_alpha(comp["alpha"])

    # The judge's own per-item record, for the three additive row keys.
    q_items = {}
    for q in quality.get("items") or []:
        if isinstance(q, dict) and isinstance(q.get("id"), str):
            q_items[q["id"]] = q
    rubric_rows = []
    for r in resolutions:
        q = q_items.get(r["item_id"]) or {}
        rubric_rows.append({
            "item_id": r["item_id"],
            "resolution": r["resolution"],
            # The ladder rationale, as the harness stores it (ItemResolution).
            "rationale": r["rationale"],
            # The judge's words for a decided item (as the delivered record carried
            # them); the abstain reason code for an abstained one.
            "reason": r["text"] if r["resolution"] in (SATISFIED, FAILED) else r["reason"],
            # Additive: the judge's citation, its deterministic cross-check and the
            # per-seat samples, copied from quality_channel.json as written.
            "evidence": q.get("evidence") if isinstance(q.get("evidence"), str) else "",
            "cross_check": q.get("cross_check") if isinstance(q.get("cross_check"), dict) else None,
            "samples": [s for s in q.get("samples") if isinstance(s, dict)]
                       if isinstance(q.get("samples"), list) else [],
        })
    rubric_detail = {
        "items": rubric_rows,
        "numerator": None if tally is None else tally["numerator"],
        "denominator": None if tally is None else tally["denominator"],
        "guardrails_fired": [] if tally is None else list(tally["guardrails_fired"]),
    }
    composition = {
        "alpha": alpha,
        "min_outcome_gap": _round(comp["min_outcome_gap"], ALPHA_PLACES),
        "process": _round(comp["process"], CHANNEL_PLACES),
        "process_stratified": _round(comp["process_stratified"], CHANNEL_PLACES),
        "stratum_size": comp["stratum_size"],
        "score_eval": _round(comp["score_eval"], CHANNEL_PLACES),
        "score_rl": _round(comp["score_rl"], CHANNEL_PLACES),
    }
    process_block = {
        "score": _round(comp["process"], CHANNEL_PLACES),
        "gate": gate_value,
        "weights": ({"deterministic": 1.0, "rubric": 0.0} if rubric is None
                    else {"deterministic": 0.5, "rubric": RUBRIC_WEIGHT / 2}),
        "judged": judged,
        "missing_items": list(missing),
        "rubric_abstained": abstained_ids,
        "deterministic": _round(det, CHANNEL_PLACES),
        "rubric": _round(rubric, CHANNEL_PLACES),
        "rubric_raw": _round(rubric_raw, CHANNEL_PLACES),
        "hard_failures": hard_failures(checks),
        "abstained": len(abstained_ids),
        "edit_set_complete": inp.patch_files is not None,
    }
    record = {
        "version": {"scorer": SCORER, "bundle_fingerprint": fingerprint},
        "status": status,
        "verifier": {"mode": inp.mode, "trusted": inp.trusted},
        "outcome": {"score": round_outcome(outcome_score), "score_binary": None,
                    "status": outcome_status, "source": outcome_source},
        "if": inp.if_channel.to_dict(),
        "process": process_block,
        "judge": judge_block(quality, model),
        "composition": composition,
        "rl": {"alpha": alpha, "score_rl": composition["score_rl"], "authoritative": True,
               "formula": RL_FORMULA, "range": list(RL_RANGE)},
        "detail": {"deterministic": checks, "rubric": rubric_detail},
    }
    record.update({
        "det": round_channel(det),
        "rubric": round_channel(rubric),
        "score_process": round_channel(comp["process"]),
        "gate": gate_value,
        "alpha": alpha,
        "min_outcome_gap": round_alpha(comp["min_outcome_gap"]),
        "score_eval": composition["score_eval"],
        "score_rl": composition["score_rl"],
        "process_stratified": composition["process_stratified"],
        "stratum_size": composition["stratum_size"],
        "rubric_raw": process_block["rubric_raw"],
        "rubric_weight": RUBRIC_WEIGHT,
        "rubric_detail": {k: v for k, v in rubric_detail.items() if k != "items"},
        "checks": checks,
        "resolutions": [{
            "item_id": r["item_id"],
            "scored": {SATISFIED: True, FAILED: False}.get(r["resolution"]),
            "reason": r["text"] or _plain_note(r["rationale"]),
        } for r in resolutions],
        "bundle_fingerprint": fingerprint,
        "judge_model": model,
        "final_diff": summarize_final_diff(fd_status, fd_text, fd_truncated, items, resolutions),
    })

    verdict_lines = [json.dumps({
        "item_id": r["item_id"],
        "verdict": "satisfied" if r["resolution"] == SATISFIED else "not satisfied",
        "note": r["text"],
        "evidence": r["evidence"],
    }, ensure_ascii=False) for r in resolutions if r["resolution"] in (SATISFIED, FAILED)]

    build_ok = (inp.judge_facts or {}).get("build_ok")
    final_score = render_final_score(model, comp, checks, inp.if_channel,
                                     float(build_ok) if isinstance(build_ok, bool) else None,
                                     overridden=sorted(pin_overrides(quality)))
    return record, final_score, verdict_lines, comp


def render_final_score(model, comp, checks, if_channel, build_ok, overridden=()):
    """writeback._render_final_score. `overridden` (the JUDGE_* variables that
    overrode the pin) is appended to the Judge: line only, when non-empty."""
    rubric = comp["rubric"]
    rows = [
        ("det", "%.4f" % comp["det"]),
        ("rubric", "n/a" if rubric is None else "%.4f" % rubric),
        ("process", "%.4f" % comp["process"]),
        ("outcome", "%.4f" % comp["outcome"]),
    ]
    if if_channel is not None and if_channel.score is not None:
        rows.append(("if_score", "%.4f" % if_channel.score))
    if build_ok is not None:
        rows.append(("build_ok", "%g" % build_ok))
    rows += [
        ("gate", str(comp["gate"])),
        ("alpha", "%.6f" % comp["alpha"]),
        ("score_eval", "%.4f" % comp["score_eval"]),
        ("score_rl", "%.4f" % comp["score_rl"]),
    ]
    failures = hard_failures(checks)
    header = "Judge: %s" % (model if model else "n/a")
    if overridden:
        header += " (pin overridden: %s)" % ", ".join(overridden)
    lines = [header, "", "| metric | value |", "| --- | --- |"]
    lines += ["| %s | %s |" % (name, value) for name, value in rows]
    if failures:
        lines += ["", "hard failures: %s" % ", ".join(failures)]
    return "\n".join(lines) + "\n"


def _write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--verifier-dir", default="/logs/verifier",
                        help="exported dir: reward.json / outcome.json are read here, the "
                             "outputs written here; also the fallback for any side input")
    parser.add_argument("--work-dir", default=None,
                        help="test.sh's scratch dir holding the side inputs (site/quality "
                             "channels, judge_facts.json, per_test.tsv, tamper.txt, "
                             "agent_*.patch, build.log); defaults to --verifier-dir")
    parser.add_argument("--tests-dir", default="/tests")
    parser.add_argument("--trajectory", default=None,
                        help="ATIF trajectory.json; optional evidence (absent -> A5 abstains)")
    parser.add_argument("--verifier-mode", default=TRUSTED_MODE,
                        help="the mode this verifier runs in; task.toml declares 'separate'")
    parser.add_argument("--out-dir", default=None, help="defaults to --verifier-dir")
    args = parser.parse_args(argv)

    inp = Inputs(args.verifier_dir, args.tests_dir, args.trajectory, args.verifier_mode,
                 work_dir=args.work_dir)
    record, final_score, verdict_lines, comp = build(inp)
    body = json.dumps(record, indent=2) + "\n"  # harness: json.dumps(process, indent=2)
    out = args.out_dir or args.verifier_dir
    _write_atomic(os.path.join(out, "verdicts.jsonl"), "".join(l + "\n" for l in verdict_lines))
    _write_atomic(os.path.join(out, "final_score.md"), final_score)
    _write_atomic(os.path.join(out, "process.json"), body)
    print("[process record] status=%s det=%.4f rubric=%s gate=%d score_eval=%.4f trajectory=%s "
          "(%d warning(s))" % (record["status"], comp["det"],
                               "n/a" if comp["rubric"] is None else "%.4f" % comp["rubric"],
                               comp["gate"], comp["score_eval"], inp.trajectory_state, len(warnings)))
    for message in warnings:
        print("[process record] warning: " + message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
