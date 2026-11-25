"""Offline ingestion (SPEC §8): sources.yaml -> fetch -> Docling -> chunks -> Qdrant + Postgres.

Runs from the `lumen` CLI on a laptop or in a GitHub Action, never inside the API.
Docling and its models come from the `ingest` dependency group only (CLAUDE.md rule 3).
"""
