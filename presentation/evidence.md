# FastFence · llama-lovers · presentation evidence

**Release:** 1.0.7 · **Format:** approximately three minutes, English slides and Polish narration. Present the published product and recorded behavior; do not present a recording as a live session.

## Story and speaking cues

| Time | English slide message | Polish speaker cue |
| --- | --- | --- |
| 0:00–0:25 | **One policy layer for agents, tools and models.** REST, OpenAI-compatible, MCP and ACP interfaces share the protected execution pipeline. | „Agent potrzebuje dostępu do narzędzi i modeli. FastFence pośredniczy w tych wywołaniach, stosując wspólne zasady dostępu, ochrony danych i kosztów.” |
| 0:25–0:55 | **Fast local checks, then semantic assessment.** Default pipeline: authentication, allowlists, signatures, text rules and privacy controls precede Laya input/output assessment; blocked local requests avoid inference. | „Znane wzorce sprawdzamy lokalnie. Dla pozostałych żądań Laya ocenia znaczenie treści. Kontrolujemy też odpowiedź: możemy ją zablokować lub zredagować.” |
| 0:55–1:40 | **Change a rule. Observe the decision. Explain why.** Show ALLOW → policy update → BLOCK without restart, followed by the decision reason, policy version and resource usage. | „Najpierw żądanie przechodzi. Zmieniamy politykę i powtarzamy je. Teraz bramka blokuje wywołanie, a panel pokazuje powód i wersję reguł. To nagranie rzeczywistej aplikacji.” |
| 1:40–2:20 | **Bound the work; test the controls.** Waiting requests have count, byte and time limits. Disconnect cancels queued work. Reviewed semantic examples can be saved and replayed before activating a rule. | „Kolejka ma limity, a rozłączony klient nie pozostawia oczekującej pracy. Testy obejmują zarówno dozwolone, jak i blokowane lub redagowane przypadki. Reguły semantyczne sprawdzamy na jawnych przykładach przed aktywacją.” |
| 2:20–3:00 | **Measured evidence, explicit limits.** Published package, reproducible tests and local operation. `uv tool run fastfence` · fastfence.dev | „Pokazujemy osobno testy mechanizmów, pomiar wydajności i wywołania prawdziwych modeli. Klasyfikator semantyczny nadal popełnia błędy, dlatego nie obiecujemy wykrywania każdego ataku.” |

## Numbers that may appear on slides

| Claim | Exact scope and source |
| --- | --- |
| **1,484 tests · 93.28% coverage** | Complete source suite for release 1.0.7. Most tests use controlled providers; this is not model accuracy. [Release evidence](../evaluation/results/request-queue-1.0.7.json). |
| **406 installed-package checks passed** | Public PyPI 1.0.7, verified site-packages origin, external environment: security, admission and transport regressions. Private sanitized evidence: `state/private/queue-package-1.0.7-pypi.json`; do not bundle private state with the deck. |
| **12/12 real requests · 24 semantic assessments** | Candidate 1.0.7 wheel outside checkout, Laya/Qwen3:4b input/output assessment and actual Qwen3:0.6b generation. Twelve benign concurrent requests; two admitted at once, ten waited; counters drained. This is integration evidence, not attack accuracy or an SLO. [Report](../evaluation/results/request-queue-1.0.7.json). |
| **1,000 controlled requests completed** | Synthetic provider, eight active and 992 waiting. Demonstrates scheduling and cleanup, not 1,000 simultaneous model generations. [Report](../evaluation/results/request-queue-1.0.7.json). |
| **Historical deterministic p95: 0.248 ms** | Public package **1.0.2**, Apple M3 Pro, 2,000 measured short allowed calls after 100 warmups, concurrency one. Direct Python engine, synthetic zero-wait tool, semantic assessment disabled; excludes ingress transport and business-model generation. Exact value 0.2475 ms. [Report](../evaluation/results/installed-package-1.0.2-comparison.json). Keep this qualification beside the number. |

## Boundaries to retain in narration or notes

- Semantic errors remain: compound natural-language rules can miss intended denials, and benign content can be falsely blocked. Passing reviewed examples establishes those cases only. The alternative predicate classifier was **not shipped** after its mixed results. [Diagnostic](../evaluation/results/reviewed-predicate-plan-diagnostic.json).
- The historical 400-case Laya corpus recorded **14 false negatives and 13 false positives**; it was Qwen-generated/labelled development data, not a fresh independent 1.0.7 benchmark. [Report](../evaluation/results/training-prompts-laya.json).
- Fail-closed provider errors do not guarantee a correct semantic judgment. Cancellation after execution cannot undo remote effects. Queue limits concern one runtime; memory counters and audit reset on restart.
- Do not claim a security certification, universal detection, zero overhead, unlimited concurrency or a self-assigned competition score. Never display credentials, private policies or raw sensitive payloads in the recording.
