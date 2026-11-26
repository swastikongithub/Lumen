"""Evaluation (SPEC §11): golden set, retrieval metrics, answer metrics, ablations.

The scripts in `evals/` at the repository root are thin command-line wrappers around
this package, so the logic is linted and tested with the rest of the backend.
Nothing here is imported by the API. `answers.py` needs the `eval` dependency group
(RAGAS) and `chunk_size.py` needs the `ingest` group (Docling); both import them lazily.
"""
