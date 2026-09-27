# syntax=docker/dockerfile:1.6
FROM golang:1.26-bookworm@sha256:e8c859f5632dcfde7b32d2012b4351728f6437930887c2f6a91ea242459e5514

ARG TARGETARCH
ARG REPO_URL_KVPROTO="https://github.com/pingcap/kvproto.git"
ARG BASE_COMMIT_KVPROTO="b41e86365ce0e0fba482005c0dfa5e2ca967d74c"
ARG REPO_URL_PD="https://github.com/tikv/pd.git"
ARG BASE_COMMIT_PD="4ae1408fef038e2c41526556d83c9b7c0e98e021"

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    LANG=C.UTF-8 \
    GIT_TERMINAL_PROMPT=0 \
    PIP_NO_INPUT=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

LABEL org.opencontainers.image.title="tikv/pd" \
      org.opencontainers.image.description="tikv/pd multi-repo Docker image" \
      org.opencontainers.image.source="https://github.com/tikv/pd.git" \
      org.opencontainers.image.revision="4ae1408fef038e2c41526556d83c9b7c0e98e021" \
      org.opencontainers.image.authors="https://www.ethara.ai/"

ENV WORKSPACE_ROOT=/workspace
WORKDIR ${WORKSPACE_ROOT}
RUN apt-get -o Acquire::Check-Date=false update && \
    apt-get install -y --no-install-recommends \
    git=1:2.39.5-0+deb12u3 patch=2.7.6-7 ca-certificates=20250419~deb12u1 \
    curl=7.88.1-10+deb12u15 procps=2:4.0.2-3 python3=3.11.2-1+b1 && \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    mkdir -p ${WORKSPACE_ROOT}/kvproto; \
    cd ${WORKSPACE_ROOT}/kvproto; \
    git init -q .; \
    git remote add origin "${REPO_URL_KVPROTO}"; \
    if ! git fetch --depth 1 --quiet origin "${BASE_COMMIT_KVPROTO}" 2>/dev/null; then \
        echo "shallow by-SHA fetch refused; falling back to full fetch in-layer"; \
        git fetch --quiet origin; \
    fi; \
    git checkout --detach "${BASE_COMMIT_KVPROTO}"; \
    git remote remove origin 2>/dev/null || true; \
    git for-each-ref --format='%(refname)' refs/heads refs/remotes refs/tags refs/replace \
      | xargs -r -n1 git update-ref -d; \
    git reflog expire --expire=now --all; \
    git reflog expire --expire-unreachable=now --all; \
    git gc --prune=now --aggressive; \
    git repack -a -d -l --quiet; \
    rm -f .git/objects/info/alternates; \
    git config --local gc.auto 0; \
    git config --local fetch.recurseSubmodules false; \
    git config --local remote.pushDefault ""; \
    test "$(git rev-parse HEAD)" = "$(git rev-parse "${BASE_COMMIT_KVPROTO}")"; \
    test -z "$(git for-each-ref refs/heads refs/remotes refs/tags refs/replace)"; \
    test -z "$(git remote)"; \
    test "$(git rev-list --all --count)" = "$(git rev-list HEAD --count)"; \
    if [ -f .gitmodules ]; then \
        git submodule foreach --recursive ' \
            git checkout --detach HEAD; \
            git remote remove origin 2>/dev/null || true; \
            git for-each-ref --format="%(refname)" refs/heads refs/remotes refs/tags refs/replace \
                | xargs -r -n1 git update-ref -d; \
            git reflog expire --expire=now --all; \
            git reflog expire --expire-unreachable=now --all; \
            git gc --prune=now --aggressive; \
            rm -f .git/objects/info/alternates; \
        '; \
    fi; \
    mkdir -p "/opt/repo-meta${WORKSPACE_ROOT}/kvproto"; \
    git rev-parse HEAD > "/opt/repo-meta${WORKSPACE_ROOT}/kvproto/commit"; \
    (git log -1 --format=%cs HEAD 2>/dev/null || echo 9999-99-99) > "/opt/repo-meta${WORKSPACE_ROOT}/kvproto/cdate"; \
    rm -rf .git; \
    find . -depth -name .git -exec rm -rf {} + 2>/dev/null || true

WORKDIR ${WORKSPACE_ROOT}/kvproto

RUN set -eux; \
    mkdir -p ${WORKSPACE_ROOT}/pd; \
    cd ${WORKSPACE_ROOT}/pd; \
    git init -q .; \
    git remote add origin "${REPO_URL_PD}"; \
    if ! git fetch --depth 1 --quiet origin "${BASE_COMMIT_PD}" 2>/dev/null; then \
        echo "shallow by-SHA fetch refused; falling back to full fetch in-layer"; \
        git fetch --quiet origin; \
    fi; \
    git checkout --detach "${BASE_COMMIT_PD}"; \
    git remote remove origin 2>/dev/null || true; \
    git for-each-ref --format='%(refname)' refs/heads refs/remotes refs/tags refs/replace \
      | xargs -r -n1 git update-ref -d; \
    git reflog expire --expire=now --all; \
    git reflog expire --expire-unreachable=now --all; \
    git gc --prune=now --aggressive; \
    git repack -a -d -l --quiet; \
    rm -f .git/objects/info/alternates; \
    git config --local gc.auto 0; \
    git config --local fetch.recurseSubmodules false; \
    git config --local remote.pushDefault ""; \
    test "$(git rev-parse HEAD)" = "$(git rev-parse "${BASE_COMMIT_PD}")"; \
    test -z "$(git for-each-ref refs/heads refs/remotes refs/tags refs/replace)"; \
    test -z "$(git remote)"; \
    test "$(git rev-list --all --count)" = "$(git rev-list HEAD --count)"; \
    if [ -f .gitmodules ]; then \
        git submodule foreach --recursive ' \
            git checkout --detach HEAD; \
            git remote remove origin 2>/dev/null || true; \
            git for-each-ref --format="%(refname)" refs/heads refs/remotes refs/tags refs/replace \
                | xargs -r -n1 git update-ref -d; \
            git reflog expire --expire=now --all; \
            git reflog expire --expire-unreachable=now --all; \
            git gc --prune=now --aggressive; \
            rm -f .git/objects/info/alternates; \
        '; \
    fi; \
    mkdir -p "/opt/repo-meta${WORKSPACE_ROOT}/pd"; \
    git rev-parse HEAD > "/opt/repo-meta${WORKSPACE_ROOT}/pd/commit"; \
    (git log -1 --format=%cs HEAD 2>/dev/null || echo 9999-99-99) > "/opt/repo-meta${WORKSPACE_ROOT}/pd/cdate"; \
    rm -rf .git; \
    find . -depth -name .git -exec rm -rf {} + 2>/dev/null || true

WORKDIR ${WORKSPACE_ROOT}/pd

RUN python3 - <<'PY'
import json, os, pathlib
declared = {'kvproto': {'name': 'kvproto', 'url': 'https://github.com/pingcap/kvproto.git', 'declared': 'b41e86365ce0e0fba482005c0dfa5e2ca967d74c'}, 'pd': {'name': 'pd', 'url': 'https://github.com/tikv/pd.git', 'declared': '4ae1408fef038e2c41526556d83c9b7c0e98e021'}}
WORKSPACE_ROOT = os.environ.get("WORKSPACE_ROOT", "/workspace")
out = {}
for rel, meta in declared.items():
    path = os.path.join(WORKSPACE_ROOT, rel)   # rel is relative to WORKSPACE_ROOT
    resolved = pathlib.Path("/opt/repo-meta" + path + "/commit").read_text().strip()
    if resolved != meta["declared"]:
        raise SystemExit(
            f"commit manifest mismatch at {path}: "
            f"declared {meta['declared']} but image holds {resolved}"
        )
    out[path] = {"name": meta["name"], "url": meta["url"], "commit": resolved}
pathlib.Path("/opt/commit_manifest.json").write_text(
    json.dumps(out, indent=2, sort_keys=True) + "\n"
)
PY

RUN TARGET="${WORKSPACE_ROOT}/pd"; for pair in "${WORKSPACE_ROOT}/kvproto|0|github.com/pingcap/kvproto"; do \
      sib="${pair%%|*}"; rest="${pair#*|}"; \
      req="${rest%%|*}"; hint="${rest#*|}"; \
      subpath=""; linked=0; \
      if [ -f "$TARGET/.gitmodules" ] && [ -n "$hint" ]; then \
        subpath="$(awk -v h="$hint" '/^\[submodule/{p=""} /path[ \t]*=/{sub(/^.*=[ \t]*/,"");p=$0} /url[ \t]*=/{sub(/^.*=[ \t]*/,"");if(index($0,h)>0&&p!=""){print p;exit}}' "$TARGET/.gitmodules")"; \
      fi; \
      if [ -n "$subpath" ] && [ -d "$TARGET/$subpath" ] \
         && [ -z "$(ls -A "$TARGET/$subpath" 2>/dev/null)" ]; then \
        cp -a "$sib/." "$TARGET/$subpath/" && linked=1 && \
          echo "CROSSREPO-LINK: populated vendored submodule $subpath from $sib"; \
      fi; \
    \
      if [ "$linked" = 1 ]; then \
        echo "CROSSREPO-LINK: ok go $sib -> $TARGET (vendored submodule)"; \
      elif ! { [ -n "$hint" ] && grep -q "$hint" "$TARGET/go.mod" 2>/dev/null; }; then \
        echo "CROSSREPO-LINK: skip go $sib (no go manifest or not a declared dependency — context-only sibling)"; \
        if [ "$req" = 1 ]; then \
          echo "  but editable_install = true says it MUST link" >&2; exit 1; \
        fi; \
      elif { gomod="$(find "$sib" -maxdepth 2 -name go.mod -print -quit 2>/dev/null)"; \
      if [ -n "$gomod" ]; then \
        mod="$(awk '/^module /{print $2; exit}' "$gomod")"; dir="$(dirname "$gomod")"; \
      else \
        mod="$hint"; dir="$sib"; \
        [ -n "$mod" ] && ( cd "$dir" && go mod init "$mod" >/dev/null 2>&1 ) && \
          echo "CROSSREPO-LINK: synthesized go.mod ($mod) for pre-modules $sib"; \
      fi; \
      [ -n "$mod" ] && {         n=0;         for tm in $(find "$TARGET" -maxdepth 3 -name go.mod                       -not -path "*/vendor/*" -not -path "*/testdata/*"); do           grep -q "$mod" "$tm" 2>/dev/null || continue;           ( cd "$(dirname "$tm")" && go mod edit -replace "$mod=$dir" ) &&             n=$((n+1)) && echo "CROSSREPO-LINK: replaced $mod in ${tm#$TARGET/}";         done;         [ "$n" -gt 0 ];       }; }; then \
        echo "CROSSREPO-LINK: ok go $sib -> $TARGET"; \
      else \
        echo "CROSSREPO-LINK: FAILED go $sib" >&2; \
        if [ "$req" = 1 ]; then \
          echo "  (declared editable_install = true, so this is fatal)" >&2; \
          exit 1; \
        fi; \
      fi; \
    done; \
    if [ -f "$TARGET/.gitmodules" ]; then \
      for d in $(awk '/path[ \t]*=/{sub(/^.*=[ \t]*/,"");print}' "$TARGET/.gitmodules"); do \
        if [ -d "$TARGET/$d" ] && [ -z "$(ls -A "$TARGET/$d" 2>/dev/null)" ]; then \
          echo "CROSSREPO-LINK: WARNING undeclared submodule still empty: $d (add it to [[repos]] with a pinned commit if the build needs it)" >&2; \
        fi; \
      done; \
    fi
# `set -o pipefail` is a bash builtin; Docker's default /bin/sh (dash) rejects it.
# Switch the shell before the failure-accumulating blocks below.
SHELL ["/bin/bash", "-c"]
RUN set -euo pipefail; \
    goprep_failures=0; \
    for m in $(find ${WORKSPACE_ROOT}/pd -maxdepth 3 -name go.mod -not -path "*/vendor/*" -not -path "*/testdata/*"); do \
      d="$(dirname "$m")"; echo "GOPREP: $d"; \
      ( cd "$d" && go mod tidy ) \
        || { echo "GOPREP-FAIL: go mod tidy in $d" >&2; goprep_failures=$((goprep_failures+1)); }; \
      if [ -d "$d/vendor" ]; then \
        echo "CROSSREPO-LINK: re-vendoring against replaced siblings in $d"; \
        ( cd "$d" && go mod vendor ) \
          || { echo "GOPREP-FAIL: go mod vendor in $d" >&2; goprep_failures=$((goprep_failures+1)); }; \
      fi; \
      ( cd "$d" && go mod download ) \
        || { echo "GOPREP-FAIL: go mod download in $d" >&2; goprep_failures=$((goprep_failures+1)); }; \
    done; \
    if [ "$goprep_failures" -gt 0 ]; then \
      echo "GOPREP: aborting image build ($goprep_failures failure(s) above)" >&2; \
      exit 1; \
    fi
# Base-state build gate.
#
# This is a cross-repository-repair task: at base the target has not yet consumed
# a definition the pinned read-only sibling carries, so part of this tree does not
# compile by construction. `go build ./...` over everything therefore cannot be
# the gate -- it would fail on every build, for the reason the task exists.
#
# Measured at this commit, one unimplemented method cascades widely:
# keyspacepb.KeyspaceServer.LoadKeyspaceByID, which the pinned read-only kvproto
# adds and server.KeyspaceServer does not yet satisfy, breaks 76 packages across
# the root and tools modules. Listing all 76 as exclusions would leave a gate that
# accepts everything and proves nothing, so the gate is declared positively.
#
# GATED -- must compile at base, and aborts the build if it does not:
#   client   the module the graded tests run from. All 9 graded ids (4
#            fail-to-pass, 5 preserve) are client/*_test.go, and this module
#            compiles clean at base, so any break here is a real defect.
#
# NOT GATED -- carries the defect under repair, and compiles once
# solution/fix.patch lands. That is the task:
#   .        the root module (server, cmd, pkg/dashboard/*, tests/*)
#   tools    imports server, so it inherits the same failure
#
# Dependency resolution stays gated for EVERY module by the GOPREP step above,
# which is where "dependency fetch errors are ignored" is actually caught. This
# change narrows what must compile; it does not weaken dependency checking.
#
# Nothing here relies on a layer, cache or credential outside this bundle: the
# same Dockerfile yields the same image for anyone holding it.
ARG BASE_BUILD_GATED_MODULES="client"
RUN set -euo pipefail; \
    gobuild_failures=0; gated_total=0; \
    for rel in ${BASE_BUILD_GATED_MODULES}; do \
      d="${WORKSPACE_ROOT}/pd/${rel}"; \
      if [ ! -f "$d/go.mod" ]; then \
        echo "GOBUILD: declared gated module '$rel' has no go.mod at $d" >&2; \
        exit 1; \
      fi; \
      echo "GOBUILD: $d"; \
      gated_total=$((gated_total + $(cd "$d" && go list -e ./... 2>/dev/null | wc -l))); \
      ( cd "$d" && go build ./... ) \
        || { echo "GOBUILD-FAIL: $d" >&2; gobuild_failures=$((gobuild_failures+1)); }; \
    done; \
    echo "GOBUILD: gated $gated_total package(s) across module(s): ${BASE_BUILD_GATED_MODULES}"; \
    if [ "$gated_total" -eq 0 ]; then \
      echo "GOBUILD: no package was gated, so this gate proved nothing" >&2; \
      exit 1; \
    fi; \
    if [ "$gobuild_failures" -gt 0 ]; then \
      echo "GOBUILD: aborting image build ($gobuild_failures module(s) failed to build)" >&2; \
      exit 1; \
    fi

RUN python3 - <<'PY'
import os
ROOT = os.path.join(os.environ.get('WORKSPACE_ROOT', '/workspace'), 'pd')
LEAKS = ['https://github.com/tikv/pd/pull/10911', 'pull/10911']
EXTS = ('.py','.go','.java','.kt','.ts','.tsx','.js','.jsx','.mjs','.cjs',
        '.c','.cc','.cpp','.cxx','.h','.hpp','.hh','.hxx','.rs')
def _is_comment(line):
    s = line.lstrip()
    return s.startswith(('#', '//', '*', '/*'))
redacted = 0
for dirpath, _dirs, files in os.walk(ROOT):
    if "/.git" in dirpath:
        continue
    for fn in files:
        if not fn.endswith(EXTS):
            continue
        p = os.path.join(dirpath, fn)
        try:
            lines = open(p, encoding="utf-8").read().splitlines(keepends=True)
        except Exception:
            continue
        out, hits = [], 0
        for l in lines:
            if _is_comment(l):
                for k in LEAKS:
                    if k in l:
                        l = l.replace(k, "[redacted]")
                        hits += 1
            out.append(l)
        if hits:
            open(p, "w", encoding="utf-8").writelines(out)
            redacted += hits
print(f"leak-strip: redacted {redacted} reference(s) in {ROOT}")
PY
RUN find ${WORKSPACE_ROOT}/pd -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

RUN for r in ${WORKSPACE_ROOT}/kvproto ${WORKSPACE_ROOT}/pd; do \
      mkdir -p "/opt/pristine$(dirname "$r")" \
      && cp -a "$r" "/opt/pristine$r"; \
    done

RUN printf '%s\n' \
  '#!/bin/bash' \
  'set -uo pipefail' \
  'WS="${WORKSPACE_ROOT:-/workspace}"' \
  'for repo in "$WS/kvproto" "$WS/pd"; do' \
  '  [ -d "$repo" ] || { echo "workspace_corrupted"; exit 0; }' \
  'done' \
  'use=$(df -P "$WS" | awk "NR==2 {gsub(/%/,\"\",\$5); print \$5}")' \
  '[ -n "${use:-}" ] && [ "$use" -ge 95 ] && { echo "disk_exhausted"; exit 0; }' \
  'echo ok' \
  > /usr/local/bin/unrecoverable_detector.sh && chmod +x /usr/local/bin/unrecoverable_detector.sh


# --- Agent runtime, baked in ---------------------------------------------
# The OpenHands venv the agent phase runs from. Baked here rather than
# installed at trial time so the pinned image is self-contained and the
# agent phase needs no network. Mirrors the harness prebake exactly
# (crossrepo_harness/runner/tasks.py::PREBAKE_OPENHANDS, uv 0.11.22,
# openhands-ai 1.6.0).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    git=1:2.39.5-0+deb12u3 tmux=3.3a-3 build-essential=12.9 \
 && rm -rf /var/lib/apt/lists/*
# uv 0.11.22 installed from the static musl release archive rather than the
# astral.sh install script: the script selects the *-gnu build on bookworm
# (glibc >= 2.31), which segfaults under qemu-user during cross-arch
# (multi-arch) image builds. The musl build is what the official uv Docker
# images ship and runs identically on native and emulated CPUs.
RUN case "${TARGETARCH}" in \
      amd64) UV_TRIPLE=x86_64-unknown-linux-musl ;; \
      arm64) UV_TRIPLE=aarch64-unknown-linux-musl ;; \
      *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && curl -LsSf "https://github.com/astral-sh/uv/releases/download/0.11.22/uv-${UV_TRIPLE}.tar.gz" -o /tmp/uv.tar.gz \
 && tar -xzf /tmp/uv.tar.gz -C /tmp \
 && mkdir -p /root/.local/bin \
 && mv "/tmp/uv-${UV_TRIPLE}/uv" "/tmp/uv-${UV_TRIPLE}/uvx" /root/.local/bin/ \
 && rm -rf /tmp/uv.tar.gz "/tmp/uv-${UV_TRIPLE}"
ENV PATH="/root/.local/bin:${PATH}"
RUN uv --version | grep -q "0.11.22" \
 || (echo "uv resolved to an unpinned version; expected 0.11.22" >&2 && exit 1)
RUN uv python install 3.13 \
 && uv venv /opt/openhands-venv --python 3.13 \
 && SKIP_VSCODE_BUILD=true uv pip install --python /opt/openhands-venv/bin/python --no-cache-dir --prerelease=allow "openhands-ai==1.6.0"
RUN /opt/openhands-venv/bin/python -m openhands.core.main --version
RUN chmod -R a+rX /opt/openhands-venv /root/.local/share/uv /root/.local/bin || true

# --- Agent LLM output ceiling --------------------------------------------
# A model served through a custom api_base is absent from LiteLLM's registry,
# so harbor finds no model_info and never sets LLM_MAX_OUTPUT_TOKENS
# (harbor/agents/installed/openhands.py:955, whose own comment predicts this).
# LiteLLM then falls back to 4096, which Opus-class models exhaust inside the
# thinking block: finish_reason "length", empty turns, and the stuck-detector
# kills the agent before it edits anything. Declared here as a floor, not a
# lock -- harbor passes agent env with `docker exec -e`, so an explicit
# --ae LLM_MAX_OUTPUT_TOKENS=... from the operator still overrides it, and a
# model harbor *does* know keeps winning through model_info.
ENV LLM_MAX_OUTPUT_TOKENS=32000

RUN mkdir -p /logs/verifier /logs/agent
WORKDIR ${WORKSPACE_ROOT}/pd
CMD ["/bin/bash"]
