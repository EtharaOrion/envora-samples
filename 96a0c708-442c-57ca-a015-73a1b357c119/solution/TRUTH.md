# TRUTH.md - 96a0c708-442c-57ca-a015-73a1b357c119

## Defect
Repository topology:
- target (fix lands here, editable): `bubbletea` @ `8f17c3584f3df68f12703cb0f5e58f482f2e5d62`, at `bubbletea`.
- context (read-only upstream): `ultraviolet` @ `9deacb990ee730bd234d9229d8b823b5b372b39f`, at `ultraviolet`. This is a source-level read-across-edit-one task: only `bubbletea` is edited and graded, while `ultraviolet` is a co-checked-out read-only checkout of the terminal-rendering library that `bubbletea` consumes as a Go module. There is no `replace` onto that checkout: the image resolves both the base and the post-change dependency state from a pre-warmed offline module cache, so the module requirement itself has to move.

Announced issues:
1. charmbracelet/bubbletea#1542 ("v2: Support mode 2026 (synchronized output updates)"): the program never asks the terminal whether it supports synchronized output, so every screen update is bracketed by a cursor hide and a cursor show instead - the wrong technique, and a visible flicker, on terminals that do support the mode. This is the target PR.
2. The upstream `ultraviolet` change that withdraws terminal-state bookkeeping from the shared renderer and reshapes how a frame is handed to it. Its merge commit is the pinned read-only commit.

The reference change touches 16 file(s) across 1 repo(s) in go. 2 target test(s) observe the result and 2 preserve test(s) must keep passing. The oracle patch carries no test content — the graded tests arrive separately through `tests/test.patch` and are re-applied by the harness, so they are not the agent's work product.

## Load-bearing upstream fact
This task cannot be completed without reading `ultraviolet` at the pinned commit `9deacb99`. At that commit the shared terminal renderer stops owning two pieces of terminal state it used to own on the caller's behalf, and changes the shape of a third entry point: the methods that showed and hid the text cursor are gone outright, with nothing equivalent left on the type, so the caller must emit that control itself; alternate-screen entry and exit remain, but the flag telling the renderer to treat the screen as full rather than inline is renamed, and the renderer no longer infers the relative-cursor setting from it; and the call that pushes an unmanaged line above the managed frame now takes the caller's own cell buffer as a leading argument, because the renderer no longer keeps a reference to it.

None of that is visible from the module version the checkout currently requires, which still carries the old contract; it is visible only in the `ultraviolet` checkout. Advancing the module requirement without reading it leaves the target uncompilable, and the compiler error names the removed methods without saying what replaced them, because nothing did. The same bump drags `github.com/charmbracelet/x/ansi` forward through minimal version selection, and that module renamed its whole family of mode-setting escape-sequence constants in the same window, so the call sites that write those sequences move too. A measured ablation confirms this: with the dependency pinned back below the context commit the target does not compile.

## Load-bearing work
The reference change lands in 8 file(s):
- `bubbletea` (target):
  - `cursed_renderer.go` — the concrete renderer: owns cursor visibility and alt-screen state, buffers each update, and brackets it with the synchronized-output pair or the cursor hide/show pair.
  - `renderer.go` — the renderer interface loses its four alt-screen and cursor operations and gains the single flag-setting operation.
  - `nil_renderer.go` — the no-op renderer implements the new interface.
  - `tea.go` — program start-up issues the mode query for trustworthy terminals, and the event loop switches the flag on when the reply says the mode exists and is off.
  - `screen.go` — the new message type carrying a terminal mode report.
  - `input.go` — translation of the upstream mode-report event into that message.
  - `go.mod` — advances the `ultraviolet` requirement onto the pinned commit, and `x/ansi` with it.
  - `tutorials/go.mod` — advances the same requirements in the nested tutorials module.
- `ultraviolet` (context): none — read-only, supplies the reshaped renderer contract as a given.

The remaining 8 touched files are incidental: the root and nested lockfiles, the examples module manifest, and four example programs that only follow a renamed upstream option. None of them is exercised by the graded tests.

## Verification
Run the target tests recorded in `tests/config.json` (2) and confirm the preserve set (2) still passes. Only `bubbletea` is editable; `ultraviolet` is read-only, so the boundary the grader defends is that context checkout (it must not be edited) and the graded test tree: `tests/test.sh` rebuilds the graded tree from a clean checkout in the separate verifier, applies only the admissible paths of the agent's patch, and re-applies the graded test patch. Both graded targets are golden-file tests: they drive a program against an in-memory writer and compare the exact byte stream, so they observe the ordering and bracketing of the control sequences, not just their presence. The preserve pair is drawn from files the upstream PR never touched - one end-to-end program run through the same renderer, one pure command-combinator test - so a regression in the rewrite surfaces as a preserve failure rather than hiding inside an expectation the same patch updated. Measured on the built image with no network: RED - base plus the graded test patch scores 0.0, both targets failing on the recorded byte stream while both preserve tests pass; GREEN - all four pass, outcome 1.0 and constraints 1.0; ABLATION - with the dependency pinned back below the context commit the target does not compile. Weight the behavioural account here over the raw target-set pass count: each graded test is a table of sub-cases over a golden directory, so the count is small while the surface it covers is not.

## Root cause
At the base commit the program has no notion of synchronized output. Its renderer hides the text cursor before writing an update and shows it again afterwards, unconditionally, which is the portable-but-crude way to keep a partially drawn frame from being seen. It never asks the terminal whether the better mechanism is available, and has no message type in which such an answer could arrive. Compounding this, it delegates alt-screen and cursor-visibility state to the shared upstream library and writes its updates straight through to the output writer rather than into a buffer it controls, so there is no single point at which a whole update could be wrapped in anything - and at the pinned `ultraviolet` commit the library no longer tracks that state at all.

## Solution shape
The renderer stops writing to the output stream directly and writes into a buffer it owns, flushing that buffer itself once per update and once on close; the upstream renderer is pointed at that buffer instead of at the writer. Because the whole update is now a single byte range, the renderer brackets it with either the synchronized-output begin and end sequences or the old cursor hide/show pair, but never both, chosen by a flag on the renderer. The renderer interface loses its four alt-screen and cursor-visibility operations and gains a single operation that sets that flag. Alt-screen entry, cursor visibility and relative-cursor mode become the concrete renderer's own responsibility, emitted as explicit control sequences and only when the view actually changes them. A new message type carries a terminal mode report, the input path translates the upstream event into it, program start-up issues the mode query only for terminals where the answer is trustworthy, and the event loop switches the flag on when the reply says the mode exists and is off. The module requirement moves onto the pinned `ultraviolet` commit, with no replace directive.

## Ordered plan
1. Treat `ultraviolet` (`ultraviolet` @ `9deacb99`) as a read-only source of the reshaped contract; enumerate what the shared renderer no longer does for the caller and which entry point changed arity, without mutating it.
2. Advance the module requirement onto that commit, letting minimal version selection pull `x/ansi` forward with it, and update the lockfiles and nested modules to match. Do not add a replace directive onto the checkout.
3. Give the concrete renderer an output buffer of its own, point the upstream renderer at it, and flush it once per update and once on close.
4. Move alt-screen, relative-cursor and cursor-visibility ownership into the concrete renderer as explicit control sequences, applied only when the view changes them, and follow the renamed escape-sequence constants at every call site including the examples.
5. Replace the interface's four alt-screen/cursor operations with the single flag-setting operation, and implement it in both renderers.
6. Add the mode-report message, translate the upstream event into it, query at start-up for trustworthy terminals only, and set the flag when the reply says the mode is available.
7. Bracket each buffered update with the synchronized-output pair when the flag is set and with the cursor hide/show pair otherwise, and confirm the two target tests and the two preserve tests pass without editing a graded test or the context checkout.

## Graded tests
2 target test(s) must move from failing to passing:
- `screen_test.go::TestViewModel`
- `screen_test.go::TestClearMsg`

2 preserve test(s) must keep passing:
- `tea_test.go::TestTeaModel`
- `commands_test.go::TestBatch`

## Pitfalls
- Adding a replace directive onto the `ultraviolet` checkout, or pinning the module to a release current at the base commit: the release still carries the old contract, so the work either compiles against the wrong API or grades a solution that never moved the requirement. `tests/test.sh` also drops any go.mod hunk that adds a replace directive.
- Emitting both bracketing techniques: the goldens record the exact byte stream, so a stray cursor hide alongside the synchronized-output pair is a mismatch even though the rendered result would look identical.
- Leaving the renderer writing straight to the output stream: without a buffer it owns there is no boundary to wrap, and the sequences land interleaved with the frame.
- Re-emitting alt-screen or cursor-visibility control on every update rather than only when the view changes it: the goldens capture one sequence per real transition.
- Conflating the renderer's new output buffer with the cell buffer the prepend path now requires: both live on the renderer and only one of them is a frame.
- Following the renamed escape-sequence constants in the library but not in the nested example and tutorial modules: those carry their own requirements and lockfiles.
- Modifying or skipping a graded test to make it pass: the graded tree is rebuilt from a clean checkout and the graded test patch is re-applied, so edits to graded tests are dropped and score nothing.
- Reaching the graded run through machinery the graded test files do not cover - an undeclared `*_test.go` carrying `TestMain` or `init()`, a new `go.work`, or an edit under `vendor/` or `testdata/`: `tests/test.sh` drops each of these paths from the agent patch before it reaches the tree, and a runner that reports failures while exiting 0 forces the outcome to zero, recording the reason.

## Provenance
```yaml
# ── canonical head: the 11 keys every shipping TRUTH.md carries, in THIS order ──
uuid: 96a0c708-442c-57ca-a015-73a1b357c119
instance_id: 96a0c708-442c-57ca-a015-73a1b357c119
fix_patch_sha256: c4758a1f83cefe4642278dd56fadedc7c59d2d6d95b119b71ea691c8202b749e
language: go
targets_total: 2
authored_by: generated
status: verified_reference
golden_score_measured: 1.0
golden_score_runs: 1
golden_score_verified_by: recorded_test_results
caveat: >
  Difficulty is unmeasured (difficulty_band and human_review owed). The graded contract
  diverges from the adapter's output - the oracle was reduced to its source-only half and
  both graded lists were re-derived - so a regeneration would regress it. instruction.md
  states the required behaviour in full but deliberately withholds every symbol name on the
  context repository's side of the boundary; that omission is the task, not an under-specified
  brief.

# ── multi-repo extension: append AFTER the head, never interleaved ──
category: crossrepo
adapter: multirepo-adapter
schema_version: "1.6"
parent_commit: 8f17c3584f3df68f12703cb0f5e58f482f2e5d62
repos:
  - { name: bubbletea,   role: target,  commit: 8f17c3584f3df68f12703cb0f5e58f482f2e5d62, path: bubbletea }
  - { name: ultraviolet, role: context, commit: 9deacb990ee730bd234d9229d8b823b5b372b39f, path: ultraviolet }
upstream_commit: 9deacb990ee730bd234d9229d8b823b5b372b39f
repos_touched: 1
files_touched_total: 16
load_bearing_files: 8
preserve_total: 2
tests_verified: true
source_pr_url: https://github.com/charmbracelet/bubbletea/pull/1542
```
