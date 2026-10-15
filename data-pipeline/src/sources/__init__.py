"""Data source adapters.

Each adapter implements `SourceAdapter` (see base.py) and is responsible for
fetching raw data from one external source and emitting a list of `Model`
records (possibly partial — fields outside the adapter's scope remain at
their default `None` / `[]`).
"""
