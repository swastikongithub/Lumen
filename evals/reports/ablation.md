# Retrieval ablation

Measured 2026-11-26 07:20 UTC with `evals/ablations.py` on Windows 11, Intel64 Family 6 Model 183 Stepping 1, GenuineIntel, 24 logical cores.
Corpus: `kb_chunks`, 1685 chunks from 88 documents (chunk size 384 tokens, origins: lpu.in, ums).
Golden set: 60 questions (40 answerable, 10 multi-part, 10 unanswerable); the retrieval metrics use the answerable and multi-part ones.
Hybrid search fetches 30 dense + 30 BM25 candidates and fuses them with RRF; re-rankers score the fused top 20 (or 10) and the top 10 are scored. Latency is per question on CPU, one question at a time.

## Configurations

| Config | Hit@5 | Recall@5 | MRR@10 | Retrieve p50 (ms) | Re-rank p50 (ms) | Re-rank p95 (ms) |
|---|---|---|---|---|---|---|
| Dense only | 0.940 | 0.900 | 0.688 | 11 | - | - |
| BM25 only | 0.800 | 0.740 | 0.662 | 6 | - | - |
| Hybrid (RRF) | 0.880 | 0.840 | 0.733 | 16 | - | - |
| Hybrid + MiniLM-L-6 re-rank | 0.960 | 0.940 | 0.857 | 42 | 822 | 898 |
| Hybrid + MiniLM-L-12 re-rank | 0.960 | 0.930 | 0.880 | 45 | 1251 | 3403 |
| Hybrid + bge-reranker-base | 0.880 | 0.830 | 0.769 | 38 | 2954 | 3254 |
| Hybrid (10 candidates) + MiniLM-L-6 | 0.920 | 0.880 | 0.833 | 39 | 633 | 718 |
| Hybrid (10 candidates) + MiniLM-L-12 | 0.920 | 0.880 | 0.853 | 39 | 851 | 905 |

Best: **Hybrid + MiniLM-L-12 re-rank** (highest Hit@5, then MRR@10, then Recall@5).

### Best configuration by question type

| Question type | Questions | Hit@5 | Recall@5 | MRR@10 |
|---|---|---|---|---|
| answerable | 40 | 0.950 | 0.950 | 0.863 |
| multi | 10 | 1.000 | 0.850 | 0.950 |

No relevant chunk in its top 5: q010, q019.

## Chunk size (Hybrid + MiniLM-L-12 re-rank)

Each size is a side collection built from the same parsed documents (`app/evals/chunk_size.py`); relevance is by page and heading, so the same labels apply to every size.

| Chunk size | Chunks | Hit@5 | Recall@5 | MRR@10 |
|---|---|---|---|---|
| 256 tokens | 2102 | 0.940 | 0.920 | 0.871 |
| 384 tokens | 1685 | 0.960 | 0.930 | 0.880 |
| 512 tokens | 1473 | 0.960 | 0.940 | 0.831 |

## Abstention threshold τ

τ is applied to the best re-rank score (raw cross-encoder logits). The chosen τ abstains on the most unanswerable questions while keeping false abstains on answerable ones at 5% or less (SPEC §11.4). Unanswerable questions that pass τ still reach the LLM, which is told to answer "not found".

| Re-ranker | Chosen τ | Unanswerable abstained | False abstains |
|---|---|---|---|
| Hybrid + MiniLM-L-6 re-rank | -7.0 | 20% | 2% |
| Hybrid + MiniLM-L-12 re-rank | -3.5 | 30% | 4% |
| Hybrid + bge-reranker-base | -5.5 | 10% | 0% |

Sweep for the configured re-ranker (ms-marco-MiniLM-L-12-v2):

| τ | Unanswerable that abstain | Answerable that abstain (false) |
|---|---|---|
| -6.0 | 10% | 2% |
| -5.5 | 20% | 2% |
| -5.0 | 20% | 2% |
| -4.5 | 20% | 2% |
| -4.0 | 20% | 4% |
| -3.5 ← | 30% | 4% |
| -3.0 | 30% | 6% |
| -2.5 | 30% | 8% |
| -2.0 | 40% | 12% |
| -1.5 | 50% | 12% |
| -1.0 | 70% | 12% |
| -0.5 | 70% | 14% |
| +0.0 | 70% | 16% |
| +0.5 | 80% | 18% |
| +1.0 | 80% | 20% |
| +1.5 | 80% | 22% |
| +2.0 | 80% | 26% |
| +2.5 | 80% | 30% |
| +3.0 | 80% | 44% |
| +3.5 | 80% | 48% |
| +4.0 | 80% | 54% |
| +4.5 | 90% | 58% |
| +5.0 | 100% | 62% |
| +5.5 | 100% | 68% |
| +6.0 | 100% | 74% |

## Reproduce

```bash
cd backend
uv run python ../evals/ablations.py --chunk-sizes 256 384 512 --build
```
