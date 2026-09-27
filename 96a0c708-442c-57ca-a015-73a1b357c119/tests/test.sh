#!/bin/bash
# Grades one trial. reward/outcome come from the graded tests only (F2P/P2P ids in
# /tests/config.json): reward = fraction of F2P passed, 0.0 on any P2P regression;
# outcome = 1.0 only when all F2P and P2P pass.
# Side channels, measured after and never feeding the outcome: if_score from
# /tests/test_output.py via pytest; quality_score from /tests/llm_judge.py;
# process.json / final_score.md / verdicts.jsonl from /tests/process_record.py.
# /logs/verifier exports exactly seven files: reward.json, reward.txt,
# outcome.json, process.json, final_score.md, verdicts.jsonl and test-stdout.txt
# (written by Harbor from stdout). Everything else goes to the scratch dir $WORK;
# VERIFIER_DEBUG=1 copies it to /logs/verifier/debug/.
set -uo pipefail

WORKSPACE_ROOT="${WORKSPACE_ROOT:-/workspace}"
# ── task identity ─────────────────────────────────────────────────────────
# EDITABLE_REPO = basename of config.json `workdir`; SIBLING_REPO / SIBLING_MODULE
# come from the judge.bundle pin (legacy /tests/judge.json) and may be empty.
# An unusable config is reported as INVALID_TASK once the EXIT trap is set.
TASK_IDENTITY="$(python3 - 2>/dev/null <<'TASK_IDENTITY_PY'
import json, os, re

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def text(value):
    return value.strip() if isinstance(value, str) else ""


cfg = load("/tests/config.json")
workdir = text(cfg.get("workdir")).rstrip("/") if cfg is not None else ""
editable = os.path.basename(workdir)
if cfg is None:
    print("ERR\n/tests/config.json is missing or not a JSON object")
elif not NAME.match(editable):
    print("ERR\n/tests/config.json has no usable 'workdir' (the repo the agent edits): %r"
          % cfg.get("workdir"))
else:
    judge = cfg.get("judge")
    if not isinstance(judge, dict):
        judge = load("/tests/judge.json") or {}
    bundle = judge.get("bundle") if isinstance(judge.get("bundle"), dict) else {}
    sibling = text(bundle.get("sibling_repo"))
    if not sibling:
        roots = bundle.get("repo_roots")
        roots = roots if isinstance(roots, list) else judge.get("repo_roots")
        for root in roots if isinstance(roots, list) else []:
            name = os.path.basename(text(root).rstrip("/"))
            if name and name != editable:
                sibling = name
                break
    if not NAME.match(sibling) or sibling == editable:
        sibling = ""
    module = text(bundle.get("sibling_module"))
    if not module or re.search(r"\s", module):
        module = ""
    print("OK\n%s\n%s\n%s" % (editable, sibling, module))
TASK_IDENTITY_PY
)"
TASK_INVALID=""
EDITABLE_REPO=""; SIBLING_REPO=""; SIBLING_MODULE=""
{ read -r _ti_status; read -r _ti_1; read -r _ti_2; read -r _ti_3; } <<< "$TASK_IDENTITY"
if [ "${_ti_status:-}" = "OK" ]; then
  EDITABLE_REPO="$_ti_1"; SIBLING_REPO="${_ti_2:-}"; SIBLING_MODULE="${_ti_3:-}"
elif [ "${_ti_status:-}" = "ERR" ]; then
  TASK_INVALID="${_ti_1:-/tests/config.json is unusable}"
else
  TASK_INVALID="could not derive the task identity from /tests/config.json"
fi
WORKDIR="$WORKSPACE_ROOT/$EDITABLE_REPO"   # relative to WORKSPACE_ROOT
mkdir -p /logs/verifier

# Scratch dir for non-exported artifacts, emptied so no earlier run leaks in.
WORK=/tmp/verifier_work
rm -rf /tmp/verifier_work 2>/dev/null || true
mkdir -p "$WORK"

# Which graded-test-patch apply path ran: git-apply, patch-F0, failed or none.
apply_path="none"

# Per-test verdicts (`id<TAB>status`), created up front for the EXIT trap.
PER_TEST="$WORK/per_test.tsv"
: > "$PER_TEST"

# Tamper ledger, one line per finding; empty means nothing was found.
TAMPER_LOG="$WORK/tamper.txt"
: > "$TAMPER_LOG"
tamper=0

# Clear exported files (not Harbor's test-stdout.txt) so no earlier run's survive.
rm -f /logs/verifier/reward.json /logs/verifier/reward.txt /logs/verifier/outcome.json \
      /logs/verifier/process.json /logs/verifier/final_score.md \
      /logs/verifier/verdicts.jsonl 2>/dev/null || true
rm -rf /logs/verifier/debug 2>/dev/null || true
apply_status="no_patch"
build_ok=""   # 1 / 0 once the build check runs; empty means "not measured"

write_reward() {  # args: outcome f2p p2p constraints apply_path per_test_tsv
  python3 - "$@" <<'PY'
import json, sys
outcome, f2p, p2p, constraints = float(sys.argv[1]), sys.argv[2] == "1", sys.argv[3] == "1", float(sys.argv[4])
apply_path = sys.argv[5] if len(sys.argv) > 5 else "none"

# Tamper reasons: `stripped: ` lines are evidence; any other line forces tamper=1.
tamper_reasons = []
tamper_log = sys.argv[7] if len(sys.argv) > 7 else ""
if tamper_log:
    try:
        with open(tamper_log) as fh:
            tamper_reasons = [line.strip() for line in fh if line.strip()]
    except OSError:
        pass

_forced = [r for r in tamper_reasons if not r.startswith("stripped: ")]
_stripped_paths = [r[len("stripped: "):] for r in tamper_reasons if r.startswith("stripped: ")]

tests = {}
per_test = sys.argv[6] if len(sys.argv) > 6 else ""
if per_test:
    try:
        with open(per_test) as fh:
            for line in fh:
                tid, _, status = line.rstrip("\n").partition("\t")
                if tid and status:
                    tests[tid] = status
    except OSError:
        pass

resolved = outcome >= 1.0

# unmatched_declared separates a did-not-run zero from a measured zero.
def _declared_ids(cfg, *keys):
    """The first present id list among `keys`; config.json uses both the
    snake_case and the SCREAMING spelling depending on its producer."""
    for key in keys:
        value = cfg.get(key)
        if isinstance(value, list):
            return [str(item) for item in value]
    return []

_cfg = {}
try:
    with open("/tests/config.json") as fh:
        _cfg = json.load(fh)
except (OSError, ValueError):
    _cfg = {}
_f2p_ids = _declared_ids(_cfg, "fail_to_pass", "FAIL_TO_PASS")
_p2p_ids = _declared_ids(_cfg, "pass_to_pass", "PASS_TO_PASS")
counts = {
    "f2p_declared": len(_f2p_ids),
    "f2p_ran": sum(1 for t in _f2p_ids if t in tests),
    "f2p_passed": sum(1 for t in _f2p_ids if tests.get(t) == "passed"),
    "p2p_declared": len(_p2p_ids),
    "p2p_ran": sum(1 for t in _p2p_ids if t in tests),
    "p2p_passed": sum(1 for t in _p2p_ids if tests.get(t) == "passed"),
    "unmatched_declared": sum(1 for t in (_f2p_ids + _p2p_ids) if t not in tests),
}

# reward = fraction of F2P passed; 0.0 on any P2P failure or with no declared F2P.
if not p2p or not counts["f2p_declared"]:
    reward_value = 0.0
else:
    reward_value = counts["f2p_passed"] / counts["f2p_declared"]

blob = {
    "reward_authority": "outcome",
    "outcome": outcome, "resolved": resolved,
    "all_f2p_green": f2p, "all_p2p_green": p2p,
    "reference_ok": resolved, "constraints": constraints,
    "aggregate_deterministic": outcome,
    "reward": reward_value,
    "test_patch_apply_path": apply_path,
    "tamper": int(bool(_forced)),
    "tamper_reasons": _forced,
    "stripped_paths": _stripped_paths,
    **counts,
    "tests": tests,
}
# reward.json is numbers only (Harbor rejects any non-numeric value) and carries
# graded-test results only; strings and the per-test map go to outcome.json.
reward = {
    "reward": reward_value, "outcome": outcome, "constraints": constraints,
    "resolved": int(resolved), "all_f2p_green": int(f2p),
    "all_p2p_green": int(p2p), "reference_ok": int(resolved),
    "tamper": int(bool(_forced)),
}
# An empty tests map means the runners never ran, not that everything failed.
if not tests:
    del blob["tests"]


json.dump(blob, open("/logs/verifier/outcome.json", "w"), indent=2)
json.dump(reward, open("/logs/verifier/reward.json", "w"), indent=2)
open("/logs/verifier/reward.txt", "w").write(f"{reward_value}\n")
print("[outcome.json]", json.dumps(blob))
PY
}
# ── export discipline ─────────────────────────────────────────────────────
# Optional debug copy of $WORK, then remove each /logs/verifier entry outside the
# allow-list by its own path (never a glob rm). Cannot fail the script.
VERIFIER_EXPORTS="reward.json reward.txt outcome.json process.json final_score.md verdicts.jsonl test-stdout.txt"
debug_copied=0
_finalize_exports() {
  if [ "${VERIFIER_DEBUG:-}" = "1" ]; then
    if [ "$debug_copied" != 1 ] && [ -d "$WORK" ]; then
      mkdir -p /logs/verifier/debug 2>/dev/null \
        && cp -a "$WORK"/. /logs/verifier/debug/ 2>/dev/null && debug_copied=1
    fi
  fi
  local _entry _name _keep _allowed
  for _entry in /logs/verifier/* /logs/verifier/.[!.]* /logs/verifier/..?*; do
    [ -e "$_entry" ] || [ -L "$_entry" ] || continue   # unmatched pattern
    _name="${_entry##*/}"
    _keep=0
    for _allowed in $VERIFIER_EXPORTS; do
      [ "$_name" = "$_allowed" ] && { _keep=1; break; }
    done
    [ "$_name" = "debug" ] && [ "${VERIFIER_DEBUG:-}" = "1" ] && [ -d "$_entry" ] && [ ! -L "$_entry" ] && _keep=1
    [ "$_keep" = 1 ] && continue
    if [ -d "$_entry" ] && [ ! -L "$_entry" ]; then
      rm -rf -- "$_entry" 2>/dev/null || true
    else
      rm -f -- "$_entry" 2>/dev/null || true
    fi
  done
  return 0
}

# EXIT trap: write the reward artifacts even on early exit, then the allow-list.
trap 'write_reward "${outcome:-0}" "${f2p:-0}" "${p2p:-0}" "${constraints:-0}" "${apply_path:-none}" "${PER_TEST:-}" "${TAMPER_LOG:-}"; _finalize_exports >/dev/null 2>&1 || true' EXIT

if [ -n "$TASK_INVALID" ]; then
  echo "INVALID_TASK: $TASK_INVALID" >&2
  exit 1
fi

# ── language-aware test runner: dispatch by the test id's file extension ──
_file_of() { printf '%s' "${1%%::*}"; }
_name_of() { printf '%s' "${1##*::}"; }

_maven_module() {  # nearest ancestor dir (relative to WORKDIR) containing pom.xml
  local d; d="$(dirname "$1")"
  while [ "$d" != "." ] && [ "$d" != "/" ] && [ -n "$d" ]; do
    [ -f "$WORKDIR/$d/pom.xml" ] && { printf '%s' "$d"; return; }
    d="$(dirname "$d")"
  done
  printf ''
}

# ── no-match guard ──────────────────────────────────────────────────────────
# A selector matching nothing exits 0 and must never score green. _guard
# <regex> -- <cmd...> fails unless cmd succeeds AND its output shows a test ran.
_guard() {
  local must="$1"; shift; [ "$1" = "--" ] && shift
  local out st
  out="$("$@" 2>&1)"; st=$?
  printf '%s\n' "$out"
  if [ $st -ne 0 ]; then return 1; fi
  if ! printf '%s' "$out" | grep -qE "$must"; then
    echo "NO-MATCH-GUARD: '$*' exited 0 but no test appears to have run;" >&2
    echo "  treating as FAILURE (a non-matching selector must never score GREEN)." >&2
    return 1
  fi
  return 0
}

_go_pkg() {  # id's file part -> the package spec to hand `go test`
  local f="$1"
  case "$f" in
    *.go) printf './%s' "$(dirname "$f")" ;;
    *)
      # A package id: a dotted first segment is an import path, else prefix ./.
      case "${f%%/*}" in
        *.*) printf '%s' "$f" ;;
        *)   printf './%s' "$f" ;;
      esac ;;
  esac
}

_go_re() {  # test name -> anchored -run regex, honouring subtests
  # go test -run matches per level, so a subtest must become ^Parent$/^Child$.
  local n="$1" out="" part IFS=/
  for part in $n; do out="$out/^${part}\$"; done
  printf '%s' "${out#/}"
}

_run_go() {
  local id rc=0
  # Group by package: plain names share one ^(A|B)$ run, subtests run alone.
  local pkgs=()
  for id in "$@"; do pkgs+=("$(_go_pkg "$(_file_of "$id")")"); done
  local upkgs; upkgs="$(printf '%s\n' "${pkgs[@]}" | sort -u)"

  local pkg
  for pkg in $upkgs; do
    local plain=() subs=() n
    for id in "$@"; do
      [ "$(_go_pkg "$(_file_of "$id")")" = "$pkg" ] || continue
      n="$(_name_of "$id")"
      case "$n" in */*) subs+=("$n") ;; *) plain+=("$n") ;; esac
    done
    local patterns=()
    if [ "${#plain[@]}" -gt 0 ]; then
      local nre; nre="$(printf '%s|' "${plain[@]}")"; patterns+=("^(${nre%|})\$")
    fi
    for n in ${subs[@]+"${subs[@]}"}; do patterns+=("$(_go_re "$n")"); done
    # Test from the nearest go.mod at or below $WORKDIR (nested modules).
    local _absdir="$WORKDIR/${pkg#./}" _moddir="$WORKDIR" _d="$WORKDIR/${pkg#./}"
    while [ "$_d" != "$WORKDIR" ] && [ "$_d" != "/" ] && [ -n "$_d" ]; do
      if [ -f "$_d/go.mod" ]; then _moddir="$_d"; break; fi
      _d="$(dirname "$_d")"
    done
    local _relpkg="./${_absdir#$_moddir/}"
    [ "$_moddir" = "$_absdir" ] && _relpkg="."
    local p out st
    for p in "${patterns[@]}"; do
      out="$( cd "$_moddir" && go test -v -run "$p" "$_relpkg" 2>&1 )"; st=$?
      printf '%s\n' "$out"
      if [ $st -ne 0 ]; then rc=1; continue; fi
      if printf '%s' "$out" | grep -q 'no tests to run'; then
        echo "NO-MATCH-GUARD: go selector '$p' matched nothing in $pkg" >&2; rc=1; continue
      fi
      printf '%s' "$out" | grep -qE '^=== RUN|^--- PASS' || {
        echo "NO-MATCH-GUARD: no go test executed for '$p' in $pkg" >&2; rc=1; }
      # FORCED-PASS GUARD: go cannot exit 0 with a failing test, so exit 0 with
      # failures in the output means a forced exit status, recorded as tamper.
      if printf '%s' "$out" | grep -qE '^[[:space:]]*--- FAIL|^FAIL[[:space:]]'; then
        echo "FORCED-PASS-GUARD: exit 0 but output reports failures in $pkg" >&2
        echo "forced-pass: go reported a test failure in $pkg while exiting 0" >> "$TAMPER_LOG"
        tamper=1; rc=1
      fi
    done
  done
  return $rc
}

_run_java() {
  local sel=() gradle_args=() module="" id
  for id in "$@"; do
    local f cls m; f="$(_file_of "$id")"; cls="$(basename "$f")"; cls="${cls%.*}"
    m="$(_name_of "$id")"
    sel+=("${cls}#${m}")
    gradle_args+=(--tests "*.${cls}.${m}")
    [ -z "$module" ] && module="$(_maven_module "$f")"
  done
  local IFS=,; local tests="${sel[*]}"; unset IFS
  # Maven when there is a pom (possibly in a submodule), else Gradle.
  if [ -n "$module" ] || [ -f "$WORKDIR/pom.xml" ]; then
    local pl=(); [ -n "$module" ] && pl=(-pl "$module" -am)
    # failIfNoSpecifiedTests=false for -am siblings; "Tests run: N" guards.
    _guard 'Tests run: [1-9]' -- env -C "$WORKDIR" \
      mvn -B -o "${pl[@]}" -Dsurefire.failIfNoSpecifiedTests=false -Dtest="$tests" test
  elif [ -f "$WORKDIR/build.gradle" ] || [ -f "$WORKDIR/build.gradle.kts" ]; then
    # Prefer the repo's gradlew; --offline because the network is closed.
    local gcmd="gradle"
    [ -x "$WORKDIR/gradlew" ] && gcmd="./gradlew"
    _guard '[1-9][0-9]* tests? completed|BUILD SUCCESSFUL' -- env -C "$WORKDIR" \
      "$gcmd" --offline test "${gradle_args[@]}"
  else
    echo "no pom.xml / build.gradle under $WORKDIR — cannot run JVM tests" >&2
    return 2
  fi
}

_run_node() {
  local files=() names=() id
  for id in "$@"; do files+=("$(_file_of "$id")"); names+=("$(_name_of "$id")"); done
  local nre; nre="$(printf '%s|' "${names[@]}")"; nre="(${nre%|})"
  local runner
  if   [ -x "$WORKDIR/node_modules/.bin/vitest" ]; then runner="node_modules/.bin/vitest run"
  elif [ -x "$WORKDIR/node_modules/.bin/jest" ];   then runner="node_modules/.bin/jest"
  elif [ -x "$WORKDIR/node_modules/.bin/mocha" ];  then runner="node_modules/.bin/mocha"
  else runner="npx --no-install jest"; fi
  local rc=0 f
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    _guard 'Tests?:?[^0-9]*[1-9][0-9]* (passed|passing)|[1-9][0-9]* passing|✓' \
      -- env -C "$WORKDIR" sh -c "$runner \"\$1\" -t \"\$2\"" _ "$f" "$nre" || rc=1
  done < <(printf '%s\n' "${files[@]}" | sort -u)
  return $rc
}

_run_rust() {
  local rc=0 id
  for id in "$@"; do
    local f n; f="$(_file_of "$id")"; n="$(_name_of "$id")"
    local tgt=(--lib) filt="$n"
    case "$f" in
      tests/*)
        # tests/<target>[/<module path>].rs: deeper segments prefix the filter.
        local rest="${f#tests/}" first
        first="${rest%%/*}"
        if [ "$first" = "$rest" ]; then
          tgt=(--test "${first%.rs}")
        else
          tgt=(--test "$first")
          local modp="${rest#*/}"; modp="${modp%.rs}"
          modp="$(printf '%s' "$modp" | sed 's#/#::#g')"
          filt="${modp}::${n}"
        fi ;;
    esac
    # Try --exact, then a substring, then the bare name; all guarded.
    _guard '^test .* \.\.\. ok' -- env -C "$WORKDIR" \
        cargo test --offline "${tgt[@]}" -- --exact "$filt" \
      || _guard '^test .* \.\.\. ok' -- env -C "$WORKDIR" \
        cargo test --offline "${tgt[@]}" -- "$filt" \
      || _guard '^test .* \.\.\. ok' -- env -C "$WORKDIR" \
        cargo test --offline "${tgt[@]}" -- "$n" \
      || rc=1
  done
  return $rc
}

_c_configure() {  # make sure a build system is bootstrapped; autotools needs it
  [ -f "$WORKDIR/Makefile" ] && return 0
  ( cd "$WORKDIR" || exit 1
    if [ -f CMakeLists.txt ]; then
      cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug -DCMAKE_PREFIX_PATH=/opt/crossrepo
    elif [ -f meson.build ]; then
      meson setup build
    elif [ -f configure ] || [ -f autogen.sh ] || [ -f configure.ac ]; then
      { [ -f configure ] || ./autogen.sh || autoreconf -fi; } && ./configure
    fi ) >/dev/null 2>&1
  return 0
}

_run_c_binaries() {
  # No per-test selector: tests/foo.c builds tests/foo; its exit status is the verdict.
  local rc=0 f bin out st built=0
  for f in "$@"; do
    bin="${f%.*}"
    ( cd "$WORKDIR" && make "$bin" ) >/dev/null 2>&1 \
      || ( cd "$WORKDIR" && make check ) >/dev/null 2>&1 || true
    if [ ! -x "$WORKDIR/$bin" ]; then
      echo "NO-MATCH-GUARD: no test executable at $bin after make" >&2; rc=1; continue
    fi
    built=1
    out="$( cd "$WORKDIR" && "./$bin" 2>&1 )"; st=$?
    printf '%s\n' "$out"
    [ $st -eq 0 ] || rc=1
  done
  [ "$built" = 1 ] || return 1
  return $rc
}

_run_c() {  # C and C++ share a runner: the build system, not the language, picks it
  local names=() files=() id
  for id in "$@"; do names+=("$(_name_of "$id")"); files+=("$(_file_of "$id")"); done
  local nre; nre="$(printf '%s|' "${names[@]}")"; nre="^(${nre%|})\$"
  local gre; gre="$(printf '%s:' "${names[@]}")"; gre="${gre%:}"
  local ufiles; ufiles="$(printf '%s\n' "${files[@]}" | sort -u)"
  _c_configure

  if [ -f "$WORKDIR/CMakeLists.txt" ]; then
    [ -d "$WORKDIR/build" ] || ( cd "$WORKDIR" && cmake -S . -B build \
        -DCMAKE_BUILD_TYPE=Debug -DCMAKE_PREFIX_PATH=/opt/crossrepo ) >/dev/null 2>&1
    ( cd "$WORKDIR" && cmake --build build -j"$(nproc)" ) >/dev/null 2>&1
    # 1) CTest by registered test name.
    if _guard '100% tests passed|[1-9][0-9]* +tests? +passed' -- env -C "$WORKDIR" \
         ctest --test-dir build --output-on-failure -R "$nre"; then
      return 0
    fi
    # 2) Fall back to a GoogleTest binary filter (ids like `f.cpp::Suite.Name`).
    local bin
    bin="$(find "$WORKDIR/build" -type f -perm -u+x -name '*test*' 2>/dev/null | head -1)"
    if [ -n "$bin" ]; then
      _guard '\[  PASSED  \] [1-9]' -- "$bin" --gtest_filter="$gre" && return 0
    fi
    return 1
  fi
  if [ -f "$WORKDIR/meson.build" ]; then
    _guard '[1-9][0-9]*/[0-9]+ +.*OK|Ok: +[1-9]' -- env -C "$WORKDIR" \
      meson test -C build "${names[@]}"
    return $?
  fi
  if [ -f "$WORKDIR/Makefile" ]; then
    # Prefer the named test executables; fall back to `make check`.
    # shellcheck disable=SC2086
    if _run_c_binaries $ufiles; then return 0; fi
    _guard 'PASS|ok|passed' -- env -C "$WORKDIR" make check
    return $?
  fi
  echo "no CMakeLists.txt / meson.build / Makefile under $WORKDIR (tried cmake, meson, autotools bootstrap)" >&2
  return 2
}

_run_php() {
  local methods=() id
  for id in "$@"; do methods+=("$(_name_of "$id")"); done
  local nre; nre="$(printf '%s|' "${methods[@]}")"; nre="${nre%|}"
  local phpunit
  if   [ -x "$WORKDIR/vendor/bin/phpunit" ]; then phpunit="vendor/bin/phpunit"
  elif command -v phpunit >/dev/null 2>&1;   then phpunit="phpunit"
  else echo "no phpunit found under $WORKDIR or in PATH" >&2; return 2; fi
  _guard 'OK \([1-9]|Tests: [1-9]' -- env -C "$WORKDIR" \
    "$phpunit" --filter "^(${nre})$"
}

# Task language (config.json test_lang), used for ids without a file extension.
TASK_LANG="$(python3 -c 'import json
try:
    c = json.load(open("/tests/config.json"))
    print(c.get("test_lang") or "")
except Exception:
    print("")' 2>/dev/null)"

_lang_of() {  # test-id file part -> logical runner (mirrors languages.py _EXT_LANG)
  case "$1" in
    *.go)                              echo go ;   return ;;
    *.java|*.kt)                       echo java ; return ;;
    *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs) echo node ; return ;;
    *.py)                              echo python ; return ;;
    *.rs)                              echo rust ; return ;;
    *.c|*.h|*.cc|*.cpp|*.cxx|*.hpp|*.hh|*.hxx) echo c ; return ;;
  esac
  # Check the basename: import paths contain dots but no extension.
  case "${1##*/}" in
    *.php) echo php ;;
    *.*) echo unknown ;;
    # No extension at all: a package-path id. Use the task-level language.
    *)   echo "${TASK_LANG:-unknown}" ;;
  esac
}

run_ids() {  # $@ = ids "relpath::Name"; returns 0 iff all selected tests pass
  [ "$#" -eq 0 ] && return 0
  # Dispatch per language group, so a mixed set never goes to one runner.
  local id l rc=0 langs
  langs="$(for id in "$@"; do _lang_of "$(_file_of "$id")"; done | sort -u)"
  for l in $langs; do
    local group=()
    for id in "$@"; do
      [ "$(_lang_of "$(_file_of "$id")")" = "$l" ] && group+=("$id")
    done
    case "$l" in
      go)     _run_go     "${group[@]}" || rc=1 ;;
      java)   _run_java   "${group[@]}" || rc=1 ;;
      node)   _run_node   "${group[@]}" || rc=1 ;;
      rust)   _run_rust   "${group[@]}" || rc=1 ;;
      c)      _run_c      "${group[@]}" || rc=1 ;;
      python) python3 /tests/run_tests.py "${group[@]}" || rc=1 ;;
      php)    _run_php    "${group[@]}" || rc=1 ;;
      *) echo "unknown test id type: $(_file_of "${group[0]}")" >&2; rc=1 ;;
    esac
  done
  return $rc
}

# ── per-test attribution ──────────────────────────────────────────────────
# Every declared id gets a verdict (a missing P2P id vetoes the reward). Only a
# red group is re-run id by id; the isolated result wins.
_mark() {  # $1 = status, $@ = ids
  local st="$1"; shift
  local id; for id in "$@"; do printf '%s\t%s\n' "$id" "$st" >> "$PER_TEST"; done
}

run_ids_scored() {  # same contract as run_ids, and records a verdict per id
  [ "$#" -eq 0 ] && return 0
  if run_ids "$@"; then _mark passed "$@"; return 0; fi
  if [ "$#" -eq 1 ]; then _mark failed "$1"; return 1; fi
  echo "[attribute] group is RED — re-running $# ids individually to attribute" >&2
  local id
  for id in "$@"; do
    if run_ids "$id"; then _mark passed "$id"; else _mark failed "$id"; fi
  done
  return 1
}

# /opt/pristine holds each repo's agent-start tree (there is no .git).
_pris() { printf '/opt/pristine%s' "$1"; }   # abs repo path -> pristine snapshot


cd "$WORKDIR" || { echo "workspace missing: $WORKDIR"; exit 1; }

constraints=1.0
_cfg_ids() {  # $1/$2 = snake_case / SCREAMING_CASE key of an id list in config.json
  python3 -c 'import json,sys
c=json.load(open("/tests/config.json"))
for t in (c.get(sys.argv[1]) or c.get(sys.argv[2]) or []): print(t)' "$1" "$2"
}
mapfile -t F2P < <(_cfg_ids fail_to_pass FAIL_TO_PASS)
mapfile -t P2P < <(_cfg_ids pass_to_pass PASS_TO_PASS)

# Empty F2P is a task defect, not a pass.
if [ "${#F2P[@]}" -eq 0 ]; then
  echo "INVALID_TASK: empty F2P set (no FAIL_TO_PASS ids in /tests/config.json)" >&2
  exit 1
fi

TEST_FILES=()
for id in "${F2P[@]}"; do TEST_FILES+=("${id%%::*}"); done
for id in "${P2P[@]:-}"; do [ -n "$id" ] && TEST_FILES+=("${id%%::*}"); done
# Also protect every file test.patch targets, so the graded patch still applies.
if [ -s /tests/test.patch ]; then
  _patch_targets="$(sed -n 's|^diff --git a/\(.*\) b/.*|\1|p' /tests/test.patch | sort -u)"
  for tf in $_patch_targets; do
    case " ${TEST_FILES[*]} " in
      *" $tf "*) ;;
      *) TEST_FILES+=("$tf") ;;
    esac
  done
fi
PRIS="$(_pris "$WORKDIR")"

# ── reconstruction: agent work arrives as an artifact patch against /opt/pristine;
# only admissible paths are applied to this clean checkout. Every dropped path is
# recorded as `stripped:` in the tamper log.
AGENT_PATCH=/logs/artifacts/agent.patch
# Stock harness: derive the same patch from the workspace tarball, in a staging dir.
if [ ! -s "$AGENT_PATCH" ]; then
  for _tgz in /logs/artifacts/agent_workspace.tgz /tmp/agent_workspace.tgz \
              /logs/artifacts/tmp/agent_workspace.tgz; do
    [ -f "$_tgz" ] || continue
    _stage="$(mktemp -d)"
    if tar -C "$_stage" -xzf "$_tgz" 2>/dev/null && [ -d "$_stage/workspace/$EDITABLE_REPO" ]; then
      ( cd "$_stage/workspace/$EDITABLE_REPO" \
          && diff -ruN "/opt/pristine$WORKSPACE_ROOT/$EDITABLE_REPO" . ) \
        > "$WORK/agent.from-tarball.patch" 2>/dev/null
      AGENT_PATCH="$WORK/agent.from-tarball.patch"
      echo "[workspace] derived the agent patch from $_tgz (stock tarball hand-off)"
      # Also write one diff per repo (sibling included) for the judge and site checks.
      for _repo in "$SIBLING_REPO" "$EDITABLE_REPO"; do
        [ -n "$_repo" ] && [ -d "$_stage/workspace/$_repo" ] || continue
        ( cd "$_stage/workspace/$_repo" \
            && diff -ruN "/opt/pristine$WORKSPACE_ROOT/$_repo" . ) \
          > "$WORK/agent_${_repo}.patch" 2>/dev/null || true
      done
    else
      echo "WARN: workspace tarball present at $_tgz but did not unpack" >&2
    fi
    rm -rf "$_stage"
    break
  done
fi
FILTERED="$WORK/agent.filtered.patch"

# A collected patch is mirrored to the per-repo name the judge reads.
if [ -s "$AGENT_PATCH" ] && [ ! -f "$WORK/agent_${EDITABLE_REPO}.patch" ]; then
  cp "$AGENT_PATCH" "$WORK/agent_${EDITABLE_REPO}.patch"
fi

if [ -s "$AGENT_PATCH" ]; then
  # Keep only admissible per-file chunks; the module policy goes to module_policy.tsv.
  rm -f "$WORK/module_policy.tsv" 2>/dev/null
  if ! _stripped="$(python3 - "$AGENT_PATCH" "$FILTERED" "$(_pris "$WORKDIR")/go.mod" \
                      "$SIBLING_MODULE" "$WORK/module_policy.tsv" \
                      ${TEST_FILES[@]+"${TEST_FILES[@]}"} <<'FILTER'
import re, sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
pristine_gomod, sibling_module, policy_out = Path(sys.argv[3]), sys.argv[4], Path(sys.argv[5])
graded = set(sys.argv[6:])

TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "testdata", "e2e"}
TEST_INFRA = re.compile(
    r"^(conftest\.py|pytest\.ini|tox\.ini|noxfile\.py|setup\.cfg|\.coveragerc"
    r"|(jest|vitest)\.(config|setup)\..*|karma\.conf\..*|\.mocharc.*"
    r"|setupTests\..*|phpunit\.xml.*|.*\.snap)$", re.DOTALL)
TEST_FILE = re.compile(
    r"^(test_.*\.py|.*_test\.py|.*_test\.go|.*\.(test|spec)\.[jt]sx?"
    r"|.*Tests?\.java|.*_test\.rs|.*\.uts)$", re.DOTALL)
# Always stripped: graded test files, test infra, test paths, vendor/, go.work*.
# Module policy from the pristine go.mod: strict if it replaces the sibling module
# (go.mod/go.sum stripped too); else bump-allowed (go.mod/go.sum admissible, but a
# go.mod that adds a replace is dropped whole). No pristine go.mod: only go.work*
# applies; unreadable: fail closed to strict.
WORK_FILES = {"go.work", "go.work.sum"}
MANIFEST_FILES = {"go.mod", "go.sum"}
REPLACE = re.compile(r"^\s*(replace\b|\S+(\s+\S+)?\s+=>\s)")


def replaced_modules(text):
    """Module paths on the left of every replace directive in a go.mod, both
    `replace a vX => b` lines and the lines of a `replace ( ... )` block.
    Comments are stripped first, so a commented-out replace does not count."""
    found, in_block = [], False
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if in_block:
            if line == ")":
                in_block = False
            elif "=>" in line:
                left = line.split("=>", 1)[0].split()
                if left:
                    found.append(left[0].strip('"'))
            continue
        if re.match(r"^replace\s*\($", line):
            in_block = True
            continue
        m = re.match(r"^replace\s+(\S+)", line)
        if m and "=>" in line:
            found.append(m.group(1).strip('"'))
    return found


def module_policy():
    """(policy, reason, go.mod replace rule on?)"""
    try:
        text = pristine_gomod.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ("bump-allowed", "no pristine go.mod at %s; only go.work* is inadmissible" % pristine_gomod,
                False)
    except OSError as exc:
        return ("strict", "pristine go.mod unreadable (%s); failing closed" % exc.__class__.__name__, True)
    if not sibling_module:
        return ("bump-allowed", "no sibling module declared; go.mod may not add a replace", True)
    if sibling_module in replaced_modules(text):
        return ("strict", "pristine go.mod replaces %s" % sibling_module, True)
    return ("bump-allowed", "pristine go.mod does not replace %s; go.mod may not add a replace"
            % sibling_module, True)


MODULE_POLICY, POLICY_REASON, REPLACE_RULE = module_policy()
MODULE_FILES = WORK_FILES | (MANIFEST_FILES if MODULE_POLICY == "strict" else set())
policy_out.write_text("%s\t%s\n" % (MODULE_POLICY, POLICY_REASON), encoding="utf-8")

def adds_replace(body):
    added = {l[1:].strip() for l in body[2:] if l.startswith("+") and REPLACE.match(l[1:])}
    removed = {l[1:].strip() for l in body[2:] if l.startswith("-") and REPLACE.match(l[1:])}
    return bool(added - removed)

def rule_for(path, body):
    if path in graded:
        return "graded_test_file"
    parts = path.split("/"); base, dirs = parts[-1], parts[:-1]
    if base in MODULE_FILES:
        return "module_resolution"
    if REPLACE_RULE and base == "go.mod" and adds_replace(body):
        return "module_resolution"
    if "vendor" in dirs:
        return "vendored_dependency"
    if TEST_INFRA.match(base) or "__snapshots__" in dirs:
        return "test_infra"
    if TEST_DIRS.intersection(dirs) or TEST_FILE.match(base):
        return "test_path"
    return None

if not src.is_file():
    dst.write_text("", encoding="utf-8")
    raise SystemExit(0)

lines = src.read_text(encoding="utf-8", errors="surrogateescape").splitlines(keepends=True)
kept, current, path, i = [], None, None, 0
chunks = []
while i < len(lines):
    line = lines[i]
    if line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
        path = lines[i + 1][4:].split("\t")[0].strip()
        if path.startswith("./"):
            path = path[2:]
        current = [line, lines[i + 1]]
        chunks.append((path, current))
        i += 2
        continue
    if line.startswith("diff ") or line.startswith("Only in "):
        current = None
    elif current is not None:
        current.append(line)
    i += 1

for path, body in chunks:
    rule = rule_for(path, body)
    if rule is None:
        kept.extend(body)
    else:
        print("%s\t%s" % (rule, path))
dst.write_text("".join(kept), encoding="utf-8", errors="surrogateescape")
FILTER
  )"; then
    echo "INVALID_TASK: the collected agent patch could not be read" >&2
    exit 1
  fi
  module_policy=""; module_policy_reason=""
  if [ -s "$WORK/module_policy.tsv" ]; then
    IFS=$'\t' read -r module_policy module_policy_reason < "$WORK/module_policy.tsv"
    echo "[filter] module policy: ${module_policy} (${module_policy_reason})"
  fi
  if [ -n "$_stripped" ]; then
    printf '%s\n' "$_stripped" | sed 's/^/STRIPPED: /'
    printf '%s\n' "$_stripped" | sed 's/^/stripped: /' >> "$TAMPER_LOG"
    # A touched graded test file is tampering: a forced reason zeroes the outcome.
    if printf '%s\n' "$_stripped" | grep -q '^graded_test_file'; then
      echo "graded test file modified by agent (stripped before grading)" >> "$TAMPER_LOG"
      tamper=1
    fi
  fi
  if [ -s "$FILTERED" ]; then
    # -F0: no fuzz, so a hunk cannot land in the wrong place.
    if patch -p0 -F0 --no-backup-if-mismatch -d "$WORKDIR" -i "$FILTERED" 2>&1; then
      apply_status="applied"
      echo "[apply] agent patch applied to the clean checkout"
    else
      apply_status="failed"
      echo "INVALID_TASK: the agent patch does not apply to the clean checkout" >&2
      exit 1
    fi
  else
    apply_status="no_admissible_change"
    echo "[apply] the agent patch carried no admissible change"
  fi
else
  apply_status="no_patch"
  echo "[apply] no agent patch was collected; grading the base tree"
fi

# ── graded-tree snapshot, for the quality judge ────────────────────────────
# Taken before test.patch and P2P, so the judge sees only the agent's change.
rm -rf /tmp/graded_tree 2>/dev/null
cp -a "$WORKDIR" /tmp/graded_tree \
  || echo "WARN: could not snapshot the graded tree for the quality judge" >&2

# ── PASS_TO_PASS is measured on pristine tests, BEFORE test.patch ──
# After it, a graded test naming post-fix symbols can break the package build and
# fail P2P for a no-op agent. Invariant: test.patch must not touch any P2P id.

# Empty P2P is a task defect, not a pass.
if [ "${#P2P[@]}" -eq 0 ]; then
  echo "INVALID_TASK: empty P2P set (no PASS_TO_PASS regression guard)" > "$WORK/p2p.log"
  p2p=0
elif run_ids_scored "${P2P[@]}" > "$WORK/p2p.log" 2>&1; then p2p=1; else p2p=0; fi
echo "── PASS_TO_PASS (pristine tests) ──"
cat "$WORK/p2p.log" 2>/dev/null || true

if [ -s /tests/test.patch ]; then
  # A patch that does not apply is fatal. git apply, then patch -F0; path recorded.
  if git apply --whitespace=nowarn --verbose /tests/test.patch 2>&1; then
    apply_path="git-apply"
  elif patch -p1 -F0 --no-backup-if-mismatch -i /tests/test.patch 2>&1; then
    apply_path="patch-F0"
    echo "NOTE: graded test patch applied via the patch(1) fallback, not git apply" >&2
  else
    apply_path="failed"
    echo "INVALID_TASK: graded test patch failed to apply — refusing to grade against unpatched tests" >&2
    exit 1
  fi
  echo "[apply] graded test patch applied via ${apply_path}"
fi

# ── outcome: PASS_TO_PASS (pristine, above) then FAIL_TO_PASS (patched) ──
if run_ids_scored "${F2P[@]}" > "$WORK/f2p.log" 2>&1; then f2p=1; else f2p=0; fi
echo "── FAIL_TO_PASS (graded tests) ──"
cat "$WORK/f2p.log" 2>/dev/null || true

if [ "$f2p" = 1 ] && [ "$p2p" = 1 ]; then outcome=1; else outcome=0; fi

# Tamper zeroes the outcome itself, not only constraints.
if [ "${tamper:-0}" = 1 ]; then
  outcome=0
  constraints=0.0
  echo "TAMPER: outcome forced to 0; reasons in outcome.json tamper_reasons" >&2
fi

# ── constraints: no forbidden strings (the sibling repo is never collected) ──
DIFF=$(diff -ruN "$PRIS" "$WORKDIR" 2>/dev/null || true)
for s in "AWS_SECRET" "BEGIN RSA PRIVATE KEY" "xoxb-" "AKIA"; do
  printf '%s' "$DIFF" | grep -q "$s" && constraints=0.0
done

# The last line of the graded flow. Everything after it is a side step.
echo "f2p=$f2p p2p=$p2p outcome=$outcome constraints=$constraints"

# ══ Side channels ═════════════════════════════════════════════════════════
# Runs after outcome, reward inputs, tamper and constraints are final and cannot
# change them: no -e, every command guarded, exit statuses only recorded.
# stdout discipline: the tail runs in one brace group redirected to
# $WORK/side_channels.log; each step prints exactly one `[side] <step>: ...`
# line to real stdout via fd 3.

# `key=value ...` from a JSON artifact for a [side] line; never fails.
_side_fields() {  # $1 = json file, then key[:fmt] ...
  python3 - "$@" 2>/dev/null <<'SIDE_FIELDS_PY' || echo "status=unreadable"
import json, sys
try:
    with open(sys.argv[1]) as fh:
        blob = json.load(fh)
    if not isinstance(blob, dict):
        raise ValueError("not an object")
except (OSError, ValueError):
    print("status=absent")
    raise SystemExit(0)
out = []
for spec in sys.argv[2:]:
    key, _, fmt = spec.partition(":")
    value = blob.get(key)
    if fmt and isinstance(value, (int, float)) and not isinstance(value, bool):
        value = format(value, fmt)
    out.append("%s=%s" % (key, "n/a" if value is None else value))
print(" ".join(out))
SIDE_FIELDS_PY
}

exec 3>&1
{

# ── build check: a deterministic fact for the quality judge ─────────────────
# `go build` of only the packages owning the declared F2P/P2P tests (as in
# _run_go), offline, one 900s timeout; ./... exceeds the budget. Non-Go: null.
build_scope=""
if [ "${TASK_LANG:-}" = "go" ]; then
  _build_specs=()   # "<module dir>|<package relative to it>"
  _build_pkgs=()    # the _go_pkg spec, relative to $WORKDIR, for the scope string
  for _id in "${F2P[@]}" ${P2P[@]+"${P2P[@]}"}; do
    [ -n "$_id" ] || continue
    [ "$(_lang_of "$(_file_of "$_id")")" = "go" ] || continue
    _pkg="$(_go_pkg "$(_file_of "$_id")")"
    case " ${_build_pkgs[*]-} " in *" ${_pkg%/.} "*) continue ;; esac
    _build_pkgs+=("${_pkg%/.}")   # "./." (a root-level test file) reads as "."
    case "$_pkg" in
      ./*)
        _absdir="$WORKDIR/${_pkg#./}"; _moddir="$WORKDIR"; _d="$_absdir"
        while [ "$_d" != "$WORKDIR" ] && [ "$_d" != "/" ] && [ -n "$_d" ]; do
          if [ -f "$_d/go.mod" ]; then _moddir="$_d"; break; fi
          _d="$(dirname "$_d")"
        done
        _relpkg="./${_absdir#$_moddir/}"
        [ "$_moddir" = "$_absdir" ] && _relpkg="."
        ;;
      *) _moddir="$WORKDIR"; _relpkg="$_pkg" ;;   # a full import path
    esac
    _build_specs+=("$_moddir|$_relpkg")
  done
  if [ "${#_build_specs[@]}" -gt 0 ]; then
    build_scope="declared packages: ${_build_pkgs[*]}"
    if timeout 900 bash -c '
        rc=0
        for spec in "$@"; do
          dir="${spec%%|*}"; pkg="${spec#*|}"
          # A test-only package (no non-test Go files, e.g. a copr_test/ dir)
          # has nothing to build; `go build` errors on it, which is not a
          # broken tree. Skip it and say so.
          if [ "$( cd "$dir" && go list -f "{{len .GoFiles}}" "$pkg" 2>/dev/null )" = "0" ]; then
            echo "= (cd $dir && go build $pkg) skipped: no non-test Go files"
            continue
          fi
          echo "+ (cd $dir && go build $pkg)"
          ( cd "$dir" && go build "$pkg" ) || rc=1
        done
        exit $rc' _ "${_build_specs[@]}" > "$WORK/build.log" 2>&1; then
      build_ok=1
    else
      build_ok=0
    fi
    echo "───── build check: go build ($build_scope) build_ok=$build_ok (reward unaffected) ─────"
    echo "[side] build check: build_ok=$build_ok build_scope=\"$build_scope\"" >&3
  else
    build_ok=""
    build_scope="skipped: no declared Go test package"
    echo "build check skipped: no declared F2P/P2P id resolves to a Go package" \
      > "$WORK/build.log" 2>&1 || true
    echo "[side] build check: skipped (no declared Go test package)" >&3
  fi
else
  build_ok=""
  build_scope="skipped: TASK_LANG=${TASK_LANG:-none}"
  echo "build check skipped: TASK_LANG='${TASK_LANG:-}' has no package build step" \
    > "$WORK/build.log" 2>&1 || true
  echo "[side] build check: skipped (TASK_LANG=${TASK_LANG:-none})" >&3
fi

# ── site checks: the instruction-following channel ─────────────────────
# pytest runs /tests/test_output.py; its junit XML becomes site_channel.json.
# repo_untouched reads the per-repo agent patches via AGENT_PATCH_DIR.
rm -f "$WORK/site_pytest.xml" 2>/dev/null
AGENT_PATCH_DIR="$WORK" PYTHONDONTWRITEBYTECODE=1 timeout 600 python3 -m pytest /tests/test_output.py -rA \
    -p no:cacheprovider -p no:randomly -o junit_logging=system-out \
    --junitxml="$WORK/site_pytest.xml" > "$WORK/site_checks.log" 2>&1
site_rc=$?

# junit XML -> site_channel.json: no child = passed, skipped = abstain, error or
# "BUNDLE DEFECT" = errored (unweighted), other failure = failed. Only names in
# test_weights.json are scored. Unreadable XML yields "errored" with score 0.0.
python3 - "$WORK" >> "$WORK/site_checks.log" 2>&1 <<'SITE_CHANNEL_PY'
import json, os, sys

WORK = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else "/tmp/verifier_work"
JUNIT = os.path.join(WORK, "site_pytest.xml")
CHANNEL = os.path.join(WORK, "site_channel.json")
WEIGHTS_FILE = "/tests/test_weights.json"
BUNDLE_DEFECT = "BUNDLE DEFECT"

# Worst verdict wins when a name reports twice.
RANK = {"passed": 0, "skipped": 1, "failed": 2, "errored": 3}
LABEL = {"passed": "PASS", "failed": "FAIL", "skipped": "ABSTAIN", "errored": "ERROR"}


def _write(channel):
    os.makedirs(os.path.dirname(CHANNEL), exist_ok=True)
    with open(CHANNEL, "w") as fh:
        json.dump(channel, fh, indent=2)


def _message(elem):
    """The first line of a verdict element's message, falling back to its text.
    pytest.fail(..., pytrace=False) puts the raw text in `message`; a traced
    failure prefixes it with "Failed: ", which is stripped for the defect test."""
    msg = (elem.get("message") or elem.text or "").strip()
    if msg.startswith("Failed: "):
        msg = msg[len("Failed: "):]
    return msg.splitlines()[0] if msg else ""


def _classify(case):
    for tag in ("error", "failure"):
        elem = case.find(tag)
        if elem is not None:
            msg = _message(elem)
            if tag == "error" or msg.startswith(BUNDLE_DEFECT):
                return "errored", msg or tag
            return "failed", msg or "failed"
    elem = case.find("skipped")
    if elem is not None:
        return "skipped", _message(elem) or "skipped"
    # The reason is the last captured-output line outside pytest's banners.
    out = case.find("system-out")
    why = [l.strip() for l in ((out.text or "") if out is not None else "").splitlines()
           if l.strip() and not (l.startswith("---") and "Captured" in l)]
    return "passed", (why[-1] if why else "passed")


def main():
    try:
        with open(WEIGHTS_FILE) as fh:
            weights = json.load(fh)
        if not isinstance(weights, dict):
            weights = {}
    except (OSError, ValueError):
        weights = {}

    def price(name):
        w = weights.get(name)
        return w if isinstance(w, (int, float)) and not isinstance(w, bool) else None

    verdicts = {}   # name -> (verdict, why); insertion order = report order
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(JUNIT).getroot()
        for case in root.iter("testcase"):
            name = case.get("name") or ""
            if not name:
                continue
            verdict, why = _classify(case)
            prev = verdicts.get(name)
            if prev is None or RANK[verdict] > RANK[prev[0]]:
                verdicts[name] = (verdict, why)
    except Exception as exc:  # absent, truncated, or not XML at all
        note = "pytest produced no readable junit XML (%s: %s)" % (type(exc).__name__, exc)
        _write({
            "status": "errored", "score": 0.0,
            "earned_weight": 0.0, "total_weight": 0.0,
            "priced_total": sum(1 for n in weights if price(n) is not None),
            "priced_answered": 0,
            "passed": [], "failed": [], "skipped": [], "errored": [],
            "note": note,
        })
        print("site checks: " + note)
        print("status           : errored")
        print("score            : 0.0000")
        print("channel artifact : %s" % CHANNEL)
        return 1

    passed, failed, skipped, errored = [], [], [], []
    buckets = {"passed": passed, "failed": failed, "skipped": skipped, "errored": errored}
    earned = total = 0.0
    priced_total = priced_answered = 0
    rows = []
    for name, (verdict, why) in verdicts.items():
        buckets[verdict].append(name)
        weight = price(name)
        if weight is not None:
            priced_total += 1
            # A skip or a bundle defect moves neither side of the fraction.
            if verdict in ("passed", "failed"):
                priced_answered += 1
                total += float(weight)
                if verdict == "passed":
                    earned += float(weight)
        rows.append((verdict, name, weight, why))

    if priced_total == 0:
        status = "no_priced_checks"
    elif priced_answered == 0:
        status = "all_abstained"
    else:
        status = "scored"

    channel = {
        "status": status,
        "score": (earned / total) if total else 0.0,
        "earned_weight": earned,
        "total_weight": total,
        "priced_total": priced_total,
        "priced_answered": priced_answered,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errored": errored,
    }
    _write(channel)

    width = max([len(r[1]) for r in rows] + [4])
    print("")
    print("site checks: %d test(s) from /tests/test_output.py (rubrics.json sites[])" % len(rows))
    print("")
    for verdict, name, weight, why in rows:
        print("%-7s %-*s  %-9s %s" % (
            LABEL[verdict], width, name,
            ("w=%s" % weight) if weight is not None else "unpriced", why))
    print("")
    print("status           : %s" % status)
    print("priced answered  : %d/%d" % (priced_answered, priced_total))
    print("weight           : %g/%g" % (earned, total))
    print("score            : %.4f" % channel["score"])
    print("channel artifact : %s" % CHANNEL)
    print("")
    print("passed=%d failed=%d skipped=%d errored=%d" % (
        len(passed), len(failed), len(skipped), len(errored)))
    return 0


try:
    sys.exit(main())
except SystemExit:
    raise
except Exception as exc:  # last resort: the artifact must exist
    _write({"status": "errored", "score": 0.0, "earned_weight": 0.0,
            "total_weight": 0.0, "priced_total": 0, "priced_answered": 0,
            "passed": [], "failed": [], "skipped": [], "errored": [],
            "note": "site channel converter crashed: %s: %s" % (type(exc).__name__, exc)})
    print("site channel converter crashed: %s: %s" % (type(exc).__name__, exc))
    sys.exit(1)
SITE_CHANNEL_PY
site_conv_rc=$?
[ "$site_conv_rc" -eq 0 ] || echo "WARN: site channel converter rc=$site_conv_rc" >&2
echo "───── site checks finished rc=$site_rc (reward unaffected) ─────"
echo "[side] site checks: $(_side_fields "$WORK/site_channel.json" status score:.4f)" >&3

# ── quality channel: LLM rubric judge on the final diff ─────────────────────
# Judges /tmp/graded_tree against /opt/pristine, given judge_facts.json.
if python3 - "${tamper:-0}" "${build_ok:-}" "${apply_status:-no_patch}" "$WORK" \
     "${SIBLING_REPO:+agent_${SIBLING_REPO}.patch}" "${build_scope:-}" \
     "${module_policy:-}" "${module_policy_reason:-}" <<'JUDGE_FACTS_PY'
import json, os, sys

tamper_arg, build_arg, apply_status = sys.argv[1], sys.argv[2], sys.argv[3]
VERIFIER = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else "/tmp/verifier_work"
SIBLING_PATCH_NAME = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else ""
BUILD_SCOPE = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] else None
# The filter's module policy and reason; null when no patch was filtered.
MODULE_POLICY = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] else None
MODULE_POLICY_REASON = sys.argv[8] if len(sys.argv) > 8 and sys.argv[8] else None


def read_lines(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except OSError:
        return None


# "stripped: <rule>\t<path>" -- the filter's record of what it kept out.
stripped = []
for line in read_lines(VERIFIER + "/tamper.txt") or []:
    if line.startswith("stripped: "):
        rule, _, path = line[len("stripped: "):].partition("\t")
        stripped.append({"rule": rule.strip(), "path": path.strip()})

# Sibling diff: null = not collected, false = collected and untouched.
SIBLING_PATCH = os.path.join(VERIFIER, SIBLING_PATCH_NAME) if SIBLING_PATCH_NAME else None
sibling = read_lines(SIBLING_PATCH) if SIBLING_PATCH else None
sibling_paths = []
if sibling is None:
    sibling_modified = None
else:
    try:
        sibling_modified = os.path.getsize(SIBLING_PATCH) > 0
    except OSError:
        sibling_modified = None
    for line in sibling:
        if line.startswith("+++ "):
            path = line[4:].split("\t")[0].strip()
        elif line.startswith("Binary files ") and line.endswith(" differ"):
            path = line[len("Binary files "):-len(" differ")].rpartition(" and ")[2].strip()
        else:
            continue
        path = path[2:] if path.startswith("./") else path
        if path and path not in sibling_paths:
            sibling_paths.append(path)

build_ok = {"1": True, "0": False}.get(build_arg)
build_tail = read_lines(VERIFIER + "/build.log") or []

facts = {
    "tamper": 1 if tamper_arg == "1" else 0,
    "stripped_paths": stripped,
    "sibling_modified": sibling_modified,
    "sibling_paths": sibling_paths,
    "build_ok": build_ok,
    "build_scope": BUILD_SCOPE,
    "build_output_tail": "\n".join(build_tail[-40:]),
    "apply_status": apply_status,
    "module_policy": MODULE_POLICY,
    "module_policy_reason": MODULE_POLICY_REASON,
}
with open(VERIFIER + "/judge_facts.json", "w") as fh:
    json.dump(facts, fh, indent=2)
print("[judge_facts.json]", json.dumps({k: v for k, v in facts.items() if k != "build_output_tail"}))
JUDGE_FACTS_PY
then
  echo "[side] judge facts: written" >&3
else
  echo "WARN: could not write $WORK/judge_facts.json" >&2
  echo "[side] judge facts: failed" >&3
fi

# Judge model pinned in /tests/config.json "judge". No API key gives status
# skipped_no_credentials (quality_judged=0, not a zero). The timeout keeps it in
# the verifier budget. Empty forwarded env vars are unset so the SDK defaults apply.
[ -n "${ANTHROPIC_BASE_URL:-}" ] || unset ANTHROPIC_BASE_URL
[ -n "${ANTHROPIC_API_KEY:-}" ] || unset ANTHROPIC_API_KEY
JUDGE_TRAJ_ARGS=()
[ -s /logs/agent/trajectory.json ] && JUDGE_TRAJ_ARGS=(--trajectory /logs/agent/trajectory.json)
JUDGE_REPO_ARGS=(--target-root "$WORKSPACE_ROOT/$EDITABLE_REPO")
[ -n "$SIBLING_REPO" ] && JUDGE_REPO_ARGS+=(--sibling-root "$WORKSPACE_ROOT/$SIBLING_REPO")
[ -n "$SIBLING_MODULE" ] && JUDGE_REPO_ARGS+=(--sibling-module "$SIBLING_MODULE")
timeout 1500 python3 /tests/llm_judge.py \
    --pristine "/opt/pristine$WORKDIR" \
    --graded /tmp/graded_tree \
    --rubric /tests/rubrics.json \
    --task-config /tests/config.json \
    --facts "$WORK/judge_facts.json" \
    --out-dir "$WORK" \
    "${JUDGE_REPO_ARGS[@]}" \
    ${JUDGE_TRAJ_ARGS[@]+"${JUDGE_TRAJ_ARGS[@]}"} \
    > "$WORK/quality_judge.log" 2>&1
judge_rc=$?
if [ ! -s "$WORK/quality_channel.json" ]; then
  printf '{"status":"error","quality_score":0.0,"error":"judge produced no artifact (rc=%d)"}\n' \
    "$judge_rc" > "$WORK/quality_channel.json" 2>/dev/null || true
fi
echo "───── quality judge finished rc=$judge_rc (reward unaffected) ─────"
echo "[side] quality judge: $(_side_fields "$WORK/quality_channel.json" status)" >&3

# ── process record: the verifier-side roll-up of every channel ──────────────
# write_reward runs once first so process_record.py reads this run's
# outcome.json; the EXIT trap rewrites the same files.
write_reward "${outcome:-0}" "${f2p:-0}" "${p2p:-0}" "${constraints:-0}" \
    "${apply_path:-none}" "${PER_TEST:-}" "${TAMPER_LOG:-}" > /dev/null 2>&1 \
  || echo "WARN: early write_reward for the process record failed (the EXIT trap still runs)" >&2
PROCESS_TRAJ_ARGS=()
[ -s /logs/agent/trajectory.json ] && PROCESS_TRAJ_ARGS=(--trajectory /logs/agent/trajectory.json)
if timeout 300 python3 /tests/process_record.py --verifier-dir /logs/verifier \
     --work-dir "$WORK" --tests-dir /tests \
     ${PROCESS_TRAJ_ARGS[@]+"${PROCESS_TRAJ_ARGS[@]}"}; then
  echo "[side] process record: written" >&3
else
  echo "WARN: process record (process.json / final_score.md / verdicts.jsonl) not written (reward unaffected)" >&2
  echo "[side] process record: failed" >&3
fi
cat /logs/verifier/final_score.md 2>/dev/null || true
echo "───── process record finished (reward unaffected) ─────"

# ── debug copy + export allow-list ──────────────────────────────────────────
# Last, so the copy holds the full scratch dir; the EXIT trap repeats the pass.
_finalize_exports
if [ "${VERIFIER_DEBUG:-}" = "1" ]; then
  if [ "$debug_copied" = 1 ]; then
    echo "[side] debug copy: /logs/verifier/debug" >&3
  else
    echo "[side] debug copy: failed" >&3
  fi
else
  echo "[side] debug copy: off" >&3
fi
} > "$WORK/side_channels.log" 2>&1
exec 3>&-

# outcome.json / reward.json / reward.txt written by the EXIT trap
