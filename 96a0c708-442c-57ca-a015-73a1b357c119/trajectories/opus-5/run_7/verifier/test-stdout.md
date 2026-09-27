[workspace] derived the agent patch from /tmp/agent_workspace.tgz (stock tarball hand-off)
Ignoring potentially dangerous file name /opt/pristine/workspace/bubbletea/cursed_renderer.go
patching file ./cursed_renderer.go
Ignoring potentially dangerous file name /opt/pristine/workspace/bubbletea/go.mod
patching file ./go.mod
Ignoring potentially dangerous file name /opt/pristine/workspace/bubbletea/go.sum
patching file ./go.sum
Ignoring potentially dangerous file name /opt/pristine/workspace/bubbletea/input.go
patching file ./input.go
Ignoring potentially dangerous file name /opt/pristine/workspace/bubbletea/mode.go
patching file ./mode.go
Ignoring potentially dangerous file name /opt/pristine/workspace/bubbletea/tea.go
patching file ./tea.go
[apply] agent patch applied to the clean checkout
Checking patch screen_test.go...
Checking patch testdata/TestClearMsg/bg_fg_cur_color.golden...
Checking patch testdata/TestClearMsg/clear_screen.golden...
Checking patch testdata/TestClearMsg/read_set_clipboard.golden...
Checking patch testdata/TestViewModel/altscreen.golden...
Checking patch testdata/TestViewModel/altscreen_autoexit.golden...
Checking patch testdata/TestViewModel/bg_set_color.golden...
Checking patch testdata/TestViewModel/bp_stop_start.golden...
Checking patch testdata/TestViewModel/cursor_hide.golden...
Checking patch testdata/TestViewModel/cursor_hideshow.golden...
Checking patch testdata/TestViewModel/kitty_stop_startreleases.golden...
Checking patch testdata/TestViewModel/mouse_allmotion.golden...
Checking patch testdata/TestViewModel/mouse_cellmotion.golden...
Checking patch testdata/TestViewModel/mouse_disable.golden...
Applied patch screen_test.go cleanly.
Applied patch testdata/TestClearMsg/bg_fg_cur_color.golden cleanly.
Applied patch testdata/TestClearMsg/clear_screen.golden cleanly.
Applied patch testdata/TestClearMsg/read_set_clipboard.golden cleanly.
Applied patch testdata/TestViewModel/altscreen.golden cleanly.
Applied patch testdata/TestViewModel/altscreen_autoexit.golden cleanly.
Applied patch testdata/TestViewModel/bg_set_color.golden cleanly.
Applied patch testdata/TestViewModel/bp_stop_start.golden cleanly.
Applied patch testdata/TestViewModel/cursor_hide.golden cleanly.
Applied patch testdata/TestViewModel/cursor_hideshow.golden cleanly.
Applied patch testdata/TestViewModel/kitty_stop_startreleases.golden cleanly.
Applied patch testdata/TestViewModel/mouse_allmotion.golden cleanly.
Applied patch testdata/TestViewModel/mouse_cellmotion.golden cleanly.
Applied patch testdata/TestViewModel/mouse_disable.golden cleanly.
[apply] graded test patch applied via git-apply
site checks: 7 requirement(s) from rubrics.json sites[]

PASS    test_s1_text       text_present   w=3       cursed_renderer.go matches (?s)buf\b.*(Flush|Write)
PASS    test_s2_text       text_present   w=3       renderer.go matches (?s)(flush|render)
PASS    test_s3_text       text_present   w=3       screen.go matches (?s)(Msg|Cmd)
PASS    test_s4_text       text_present   w=3       tea.go matches (?s)(Msg|Cmd)
PASS    test_s5_text       text_present   w=3       input.go matches (?s)(Msg|mode|2026|[Ss]ync)
PASS    test_s6_text       text_present   w=3       nil_renderer.go matches (?s)(func|Render)
PASS    test_s7_untouched  repo_untouched w=3       ultraviolet is byte-identical to its checkout

status           : scored
priced answered  : 7/7
weight           : 21/21
score            : 1.0000
channel artifact : /logs/verifier/site_channel.json

passed=7 failed=0 skipped=0 errored=0
───── site checks finished rc=0 (reward unaffected) ─────
f2p=0 p2p=1 outcome=0 constraints=1.0
[outcome.json] {"reward_authority": "outcome", "outcome": 0.0, "resolved": false, "all_f2p_green": false, "all_p2p_green": true, "reference_ok": false, "constraints": 1.0, "aggregate_deterministic": 0.0, "reward": 0.0, "test_patch_apply_path": "git-apply", "tamper": 0, "tamper_reasons": [], "stripped_paths": [], "f2p_declared": 2, "f2p_ran": 2, "f2p_passed": 0, "p2p_declared": 2, "p2p_ran": 2, "p2p_passed": 2, "unmatched_declared": 0, "tests": {"screen_test.go::TestViewModel": "failed", "screen_test.go::TestClearMsg": "failed", "tea_test.go::TestTeaModel": "passed", "commands_test.go::TestBatch": "passed"}}
