# syntax=docker/dockerfile:1.6
FROM golang:1.25-bookworm@sha256:3b4a11519ad929d1e1d261a12cff056f0c85b735253d7d861346b9c6f8b36437

ARG TARGETARCH
ARG REPO_URL_ULTRAVIOLET="https://github.com/charmbracelet/ultraviolet.git"
ARG BASE_COMMIT_ULTRAVIOLET="9deacb990ee730bd234d9229d8b823b5b372b39f"
ARG REPO_URL_BUBBLETEA="https://github.com/charmbracelet/bubbletea.git"
ARG BASE_COMMIT_BUBBLETEA="8f17c3584f3df68f12703cb0f5e58f482f2e5d62"

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    LANG=C.UTF-8 \
    GIT_TERMINAL_PROMPT=0 \
    PIP_NO_INPUT=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

LABEL org.opencontainers.image.title="charmbracelet/bubbletea" \
      org.opencontainers.image.description="charmbracelet/bubbletea multi-repo Docker image" \
      org.opencontainers.image.source="https://github.com/charmbracelet/bubbletea.git" \
      org.opencontainers.image.revision="8f17c3584f3df68f12703cb0f5e58f482f2e5d62" \
      org.opencontainers.image.authors="https://www.ethara.ai/"

ENV WORKSPACE_ROOT=/workspace
WORKDIR ${WORKSPACE_ROOT}
RUN apt-get -o Acquire::Check-Date=false update && \
    apt-get install -y --no-install-recommends \
    git=1:2.39.5-0+deb12u3 patch=2.7.6-7 ca-certificates=20250419~deb12u1 \
    curl=7.88.1-10+deb12u15 procps=2:4.0.2-3 python3=3.11.2-1+b1 && \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    mkdir -p ${WORKSPACE_ROOT}/ultraviolet; \
    cd ${WORKSPACE_ROOT}/ultraviolet; \
    git init -q .; \
    git remote add origin "${REPO_URL_ULTRAVIOLET}"; \
    if ! git fetch --depth 1 --quiet origin "${BASE_COMMIT_ULTRAVIOLET}" 2>/dev/null; then \
        echo "shallow by-SHA fetch refused; falling back to full fetch in-layer"; \
        git fetch --quiet origin; \
    fi; \
    git checkout --detach "${BASE_COMMIT_ULTRAVIOLET}"; \
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
    test "$(git rev-parse HEAD)" = "$(git rev-parse "${BASE_COMMIT_ULTRAVIOLET}")"; \
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
    mkdir -p "/opt/repo-meta${WORKSPACE_ROOT}/ultraviolet"; \
    git rev-parse HEAD > "/opt/repo-meta${WORKSPACE_ROOT}/ultraviolet/commit"; \
    (git log -1 --format=%cs HEAD 2>/dev/null || echo 9999-99-99) > "/opt/repo-meta${WORKSPACE_ROOT}/ultraviolet/cdate"; \
    rm -rf .git; \
    find . -depth -name .git -exec rm -rf {} + 2>/dev/null || true

WORKDIR ${WORKSPACE_ROOT}/ultraviolet

RUN set -eux; \
    mkdir -p ${WORKSPACE_ROOT}/bubbletea; \
    cd ${WORKSPACE_ROOT}/bubbletea; \
    git init -q .; \
    git remote add origin "${REPO_URL_BUBBLETEA}"; \
    if ! git fetch --depth 1 --quiet origin "${BASE_COMMIT_BUBBLETEA}" 2>/dev/null; then \
        echo "shallow by-SHA fetch refused; falling back to full fetch in-layer"; \
        git fetch --quiet origin; \
    fi; \
    git checkout --detach "${BASE_COMMIT_BUBBLETEA}"; \
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
    test "$(git rev-parse HEAD)" = "$(git rev-parse "${BASE_COMMIT_BUBBLETEA}")"; \
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
    mkdir -p "/opt/repo-meta${WORKSPACE_ROOT}/bubbletea"; \
    git rev-parse HEAD > "/opt/repo-meta${WORKSPACE_ROOT}/bubbletea/commit"; \
    (git log -1 --format=%cs HEAD 2>/dev/null || echo 9999-99-99) > "/opt/repo-meta${WORKSPACE_ROOT}/bubbletea/cdate"; \
    rm -rf .git; \
    find . -depth -name .git -exec rm -rf {} + 2>/dev/null || true

WORKDIR ${WORKSPACE_ROOT}/bubbletea

RUN python3 - <<'PY'
import json, os, pathlib
declared = {'ultraviolet': {'name': 'ultraviolet', 'url': 'https://github.com/charmbracelet/ultraviolet.git', 'declared': '9deacb990ee730bd234d9229d8b823b5b372b39f'}, 'bubbletea': {'name': 'bubbletea', 'url': 'https://github.com/charmbracelet/bubbletea.git', 'declared': '8f17c3584f3df68f12703cb0f5e58f482f2e5d62'}}
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

# `set -o pipefail` is a bash builtin; Docker's default /bin/sh (dash) rejects it.
# Switch the shell before the failure-accumulating blocks below.
SHELL ["/bin/bash", "-c"]
# Dependency linking, and why it is NOT a `go mod edit -replace` onto the sibling.
#
# The reference change advances the module requirement on
# github.com/charmbracelet/ultraviolet to the pinned read-only commit, and that
# bump drags github.com/charmbracelet/x/ansi forward through minimal version
# selection. A replace directive onto /workspace/ultraviolet would make the
# requirement inert and grade a solution that never moved the pin, so the target
# resolves both dependency states from a pre-warmed offline module cache instead.
#
# ── offline module warm, pt.1: the BASE (pristine) dependency state ──────────
# This is also the base-state build gate. Unguarded on purpose: it is the canary
# proving the image can resolve, compile and link the graded package against the
# pins the checkout ships with, and it aborts the build if it cannot. All 4
# graded ids (2 fail-to-pass, 2 preserve) are root-package *_test.go files, and
# the root package compiles clean at base, so any break here is a real defect.
#
# `go mod download all` rewrites go.sum as a side effect, so go.mod/go.sum are
# snapshotted before the warm and restored after it — /opt/pristine must hold the
# checkout exactly as the commit does.
RUN set -euxo pipefail; \
    cd ${WORKSPACE_ROOT}/bubbletea; \
    cp go.mod /tmp/go.mod.pristine; \
    cp go.sum /tmp/go.sum.pristine; \
    go mod download all; \
    go test -run 'ZZZ_NO_SUCH_TEST_ZZZ' . ; \
    cp /tmp/go.mod.pristine go.mod; \
    cp /tmp/go.sum.pristine go.sum; \
    rm -f /tmp/go.mod.pristine /tmp/go.sum.pristine; \
    echo "GOPREP: base dependency state warmed"

# ── offline module warm, pt.2: the POST-CHANGE dependency state ──────────────
# Derived from the CONTEXT repository only: the sibling checkout's own commit and
# its parents are resolved to module versions and cached, so the graded run can
# move the requirement forward with no network. Nothing here reads solution/.
#
# Guarded: the last step is expected to stop at the real defect, because the
# sibling's newer API is incompatible with the target's current source. Seeing it
# stop exactly there is positive evidence the defect is genuine.
RUN set -eux; \
    rm -rf /tmp/ctxmeta /tmp/postfix; \
    git clone -q --filter=blob:none --no-checkout \
        "${REPO_URL_ULTRAVIOLET}" /tmp/ctxmeta; \
    REVS="$(cd /tmp/ctxmeta && git rev-parse \
        "${BASE_COMMIT_ULTRAVIOLET}" \
        "${BASE_COMMIT_ULTRAVIOLET}^1" \
        "${BASE_COMMIT_ULTRAVIOLET}^2" 2>/dev/null \
        || (cd /tmp/ctxmeta && git rev-parse "${BASE_COMMIT_ULTRAVIOLET}"))"; \
    echo "context revisions to cache: ${REVS}"; \
    cp -a ${WORKSPACE_ROOT}/bubbletea /tmp/postfix; \
    cd /tmp/postfix; \
    for rev in ${REVS}; do \
        go get "github.com/charmbracelet/ultraviolet@${rev}" \
            || echo "revision ${rev} not published as a module version — skipped"; \
    done; \
    go test -run 'ZZZ_NO_SUCH_TEST_ZZZ' . \
        || echo "post-change dependency state does not compile against the unmodified target — as expected"; \
    cd /; rm -rf /tmp/ctxmeta /tmp/postfix; \
    echo "GOPREP: post-change dependency state warmed"

# ── make the module cache a self-sufficient offline proxy ────────────────────
# The proxy's list endpoint was mirrored during the warms and advertises versions
# whose archives were never fetched; offline, resolving one of those is a hard
# error with a misleading message. Reduce every list to the versions this image
# actually holds an archive for, and drop the orphaned metadata.
RUN python3 - <<'PY'
import pathlib

root = pathlib.Path("/go/pkg/mod/cache/download")
pruned = rewritten = 0
for vdir in root.rglob("@v"):
    if not vdir.is_dir():
        continue
    have = {p.name[:-4] for p in vdir.glob("*.zip")}
    for p in vdir.iterdir():
        if p.is_dir() or p.name == "list":
            continue
        stem, _, ext = p.name.rpartition(".")
        if ext in ("info", "zip", "ziphash", "lock") and stem.startswith("v") and stem not in have:
            p.unlink()
            pruned += 1
    lf = vdir / "list"
    if lf.exists():
        keep = sorted(v for v in lf.read_text().split() if v in have)
        lf.write_text("".join(v + "\n" for v in keep))
        rewritten += 1
print(f"offline proxy: dropped {pruned} unfetched entries, rewrote {rewritten} version lists")
PY

# Resolve modules from the warmed cache and never from the network. The checksum
# database is unreachable offline; every hash the graded build needs is already
# in the checkout's go.sum, so verification stays local.
#
# Nothing here relies on a layer, cache or credential outside this bundle: the
# same Dockerfile yields the same image for anyone holding it.
ENV GOPROXY=file:///go/pkg/mod/cache/download \
    GOSUMDB=off \
    GOTOOLCHAIN=local

RUN python3 - <<'PY'
import os
ROOT = os.path.join(os.environ.get('WORKSPACE_ROOT', '/workspace'), 'bubbletea')
LEAKS = ['https://github.com/charmbracelet/bubbletea/pull/1542', 'pull/1542']
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
RUN find ${WORKSPACE_ROOT}/bubbletea -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

RUN for r in ${WORKSPACE_ROOT}/ultraviolet ${WORKSPACE_ROOT}/bubbletea; do \
      mkdir -p "/opt/pristine$(dirname "$r")" \
      && cp -a "$r" "/opt/pristine$r"; \
    done

RUN printf '%s\n' \
  '#!/bin/bash' \
  'set -uo pipefail' \
  'WS="${WORKSPACE_ROOT:-/workspace}"' \
  'for repo in "$WS/ultraviolet" "$WS/bubbletea"; do' \
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
WORKDIR ${WORKSPACE_ROOT}/bubbletea
CMD ["/bin/bash"]
