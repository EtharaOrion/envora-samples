Ignoring potentially dangerous file name /opt/pristine/workspace/tidb/pkg/distsql/context/context.go
patching file ./pkg/distsql/context/context.go
Ignoring potentially dangerous file name /opt/pristine/workspace/tidb/pkg/distsql/request_builder.go
patching file ./pkg/distsql/request_builder.go
Ignoring potentially dangerous file name /opt/pristine/workspace/tidb/pkg/kv/kv.go
patching file ./pkg/kv/kv.go
Ignoring potentially dangerous file name /opt/pristine/workspace/tidb/pkg/store/copr/coprocessor.go
patching file ./pkg/store/copr/coprocessor.go
[apply] agent patch applied to the clean checkout
Checking patch pkg/distsql/context/context_test.go...
Checking patch pkg/distsql/request_builder_test.go...
Checking patch pkg/store/copr/copr_test/coprocessor_test.go...
Checking patch pkg/store/copr/coprocessor_cache_test.go...
Checking patch pkg/store/copr/coprocessor_test.go...
Applied patch pkg/distsql/context/context_test.go cleanly.
Applied patch pkg/distsql/request_builder_test.go cleanly.
Applied patch pkg/store/copr/copr_test/coprocessor_test.go cleanly.
Applied patch pkg/store/copr/coprocessor_cache_test.go cleanly.
Applied patch pkg/store/copr/coprocessor_test.go cleanly.
[apply] graded test patch applied via git-apply
site checks: 1 requirement(s) from rubrics.json sites[]

PASS    test_s1_untouched  repo_untouched w=5       kvproto is byte-identical to its checkout

status           : scored
priced answered  : 1/1
weight           : 5/5
score            : 1.0000
channel artifact : /logs/verifier/site_channel.json

passed=1 failed=0 skipped=0 errored=0
───── site checks finished rc=0 (reward unaffected) ─────
f2p=0 p2p=1 outcome=0 constraints=1.0
[outcome.json] {"reward_authority": "outcome", "outcome": 0.0, "resolved": false, "all_f2p_green": false, "all_p2p_green": true, "reference_ok": false, "constraints": 1.0, "aggregate_deterministic": 0.0, "reward": 0.3333333333333333, "test_patch_apply_path": "git-apply", "tamper": 0, "tamper_reasons": [], "stripped_paths": [], "f2p_declared": 6, "f2p_ran": 6, "f2p_passed": 2, "p2p_declared": 3, "p2p_ran": 3, "p2p_passed": 3, "unmatched_declared": 0, "tests": {"pkg/store/copr/coprocessor_test.go::TestBuildPagingTasksDisablePagingForSmallLimit": "passed", "pkg/distsql/request_builder_test.go::TestRequestBuilder1": "passed", "pkg/distsql/request_builder_test.go::TestRequestBuilder2": "passed", "pkg/store/copr/coprocessor_test.go::TestBuildCopTasksWithPagingSizeBytes": "failed", "pkg/store/copr/coprocessor_cache_test.go::TestBuildCacheKey": "failed", "pkg/store/copr/coprocessor_cache_test.go::TestGetSet": "failed", "pkg/store/copr/copr_test/coprocessor_test.go::TestBuildCopIteratorWithBatchStoreCopr": "failed", "pkg/distsql/request_builder_test.go::TestRequestBuilderKeepsPagingSizeBytesWhenPagingDisabled": "passed", "pkg/distsql/context/context_test.go::TestContextDetach": "passed"}}
