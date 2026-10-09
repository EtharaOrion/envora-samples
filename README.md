GENERATED SECTION. DO NOT HAND-EDIT.

<p align="center"><img src="images/hero.svg" alt="envora" width="720"></p>

# envora: samples

<p align="center"><b>The samples lane: 3 of 30 Harbor task bundles.</b></p>

<p align="center"><a href="#summary"><img src="https://img.shields.io/badge/bundles-3_of_30-845EF7" alt="bundles: 3 of 30"></a> <a href="#evidence-status"><img src="https://img.shields.io/badge/sealed-0-845EF7" alt="sealed: 0"></a> <a href="#difficulty-tiers"><img src="https://img.shields.io/badge/difficulty-measured-845EF7" alt="difficulty: measured"></a></p>

<p align="center"><sub><a href="#abstract">Abstract</a> | <a href="#summary">Summary</a> | <a href="#difficulty-tiers">Difficulty tiers</a> | <a href="#evidence-status">Evidence status</a> | <a href="#coverage">Coverage</a> | <a href="#dataset-structure">Dataset structure</a> | <a href="#trajectory-structure">Trajectory structure</a> | <a href="#verification-and-quality-assurance">Verification and quality assurance</a> | <a href="#reproduction">Reproduction</a> | <a href="#cite">Cite</a> | <a href="#license">License</a> | <a href="#contact">Contact</a></sub></p>

## Abstract

The curated lane of this corpus: at most 30 Harbor task bundles, every anchor seated first and every other bundle in seal order. Bundles past that ceiling live in `delivery/`.

Each bundle is one Harbor task in a directory named by its content-derived uuid5, so the name doubles as an integrity check. This page is rendered from the resident bundles on every reconcile; a value a bundle does not carry reads `absent`, and the page never fills one in.

## Summary

| Property | Value |
| --- | --- |
| Bundles | 3 of 30 |
| Sealed | 0 of 3 |
| Registrations | adopted (3) |
| Audit verdicts | none (3) |
| Harbor schema | 1.4 (3) |

## Difficulty tiers

Difficulty is measured by the signed pilot alone and never declared in a bundle, so this page states no tier a bundle claims.

## Evidence status

The verdict is the audit outcome recorded at the sealed digest, and `none` means no verdict has landed for that digest yet. Only a FORGE invocation removes a bundle from this lane, so removal waits for the next one.

| uuid | Verdict | Sealed digest | Stream |
| --- | --- | --- | --- |
| 366c001e-3d60-58ba-a985-96418f6e2289 | none | absent | none |
| 954943fb-3f55-54c4-8f36-1d72defcce86 | none | absent | none |
| 96a0c708-442c-57ca-a015-73a1b357c119 | none | absent | none |

## Coverage

| Keyword | Bundles |
| --- | --- |
| crossrepo | 3 |
| go | 3 |
| read-across-edit-one | 3 |
| source-level | 3 |
| kvproto | 2 |
| bubbletea | 1 |
| pingcap | 1 |
| tikv | 1 |
| ultraviolet | 1 |

## Dataset structure

| Bundle | Task | Keywords | Registration | Sealed at |
| --- | --- | --- | --- | --- |
| [`366c001e-3d60-58ba-a985-96418f6e2289`](366c001e-3d60-58ba-a985-96418f6e2289/) | `ethara/envora-tidb-session-variable` | crossrepo, go, kvproto, pingcap, read-across-edit-one, source-level | adopted | unsealed |
| [`954943fb-3f55-54c4-8f36-1d72defcce86`](954943fb-3f55-54c4-8f36-1d72defcce86/) | `ethara/envora-pd-keyspace-error` | crossrepo, go, kvproto, read-across-edit-one, source-level, tikv | adopted | unsealed |
| [`96a0c708-442c-57ca-a015-73a1b357c119`](96a0c708-442c-57ca-a015-73a1b357c119/) | `ethara/envora-bubbletea-synchronized-output` | bubbletea, crossrepo, go, read-across-edit-one, source-level, ultraviolet | adopted | unsealed |

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#131a33","primaryTextColor":"#e8ecff","primaryBorderColor":"#845EF7","lineColor":"#22d3ee","fontFamily":"monospace"}}}%%
flowchart LR
    bundle["&lt;uuid&gt;/"]
    bundle --> n0["task.toml<br/>runner manifest"]
    bundle --> n1["instruction.md<br/>objective the agent reads"]
    bundle --> n2["environment/<br/>agent sandbox image"]
    bundle --> n3["tests/<br/>verifier, hidden from the agent"]
    bundle --> n4["solution/<br/>private oracle"]
    bundle --> n5["trajectories/<br/>private rollout evidence"]
```

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#131a33","primaryTextColor":"#e8ecff","primaryBorderColor":"#845EF7","lineColor":"#22d3ee","fontFamily":"monospace"}}}%%
flowchart LR
    staging["staging/"]
    staging --> samples["samples/<br/>3 of 30"]
    samples --> delivery["delivery/<br/>0 of 10000"]
    delivery --> stock["stock/<br/>0 of 10000"]
```

## Trajectory structure

3 of 3 resident bundles carry a `trajectories/` subtree of private rollout evidence. The signed pilot reads it; this page never restates a rollout.

## Verification and quality assurance

Each bundle's signed provenance carrier holds its screening roots, screening instant, and absolute expiry. Placement moves that carrier into the private derivation set, which this page never reads, so reconcile lists no root it cannot verify here.

## Reproduction

Each bundle directory is a complete Harbor task: `task.toml` is the runner manifest, `instruction.md` the objective, `environment/` the sandbox image, and `tests/` the verifier. Point a Harbor runner at one bundle directory to reproduce it; `solution/` and `trajectories/` stay private.

## Cite

The registered publication work is envora-benchmark. Cite the repository and the exact revision used for an experiment.

```bibtex
@misc{envora,
  author = {{Ethara.AI}},
  title = {envora: Multi-Repository Software Engineering Environments},
  howpublished = {https://github.com/EtharaOrion/envora},
  note = {Specify the repository revision used}
}
```

## License

See the preserved [LICENSE](LICENSE). Dataset and upstream repository licenses require separate review; the parent license does not grant rights to private or third-party material.

## Contact

Find the team at [Ethara.AI on GitHub](https://github.com/EtharaOrion). Report security or benchmark-integrity concerns to [security@ethara.ai](mailto:security@ethara.ai) under [SECURITY.md](SECURITY.md). Use [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution route.
