# Invalidated pre-v3 data

The following v2 pilot tasks used quantity requirements that were not backed
by a complete model-visible evidence path:

- `T-21073fd44981`
- `T-5c87a3632801`
- `T-6165caa8f547`
- `T-f166b87d40b2`

They are invalid for benchmark claims and must not be included in aggregate
results. The original files remain recoverable from Git history for audit.
v3.0 quantity tasks use real order or reservation records plus explicit
instruction spans and are rejected at build time if any hard-constraint atom
lacks evidence.
