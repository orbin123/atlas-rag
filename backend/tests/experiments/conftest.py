from __future__ import annotations

import importlib.util

_ML_MODULES = ("faiss", "numpy", "sentence_transformers", "torch", "transformers")

if any(importlib.util.find_spec(module) is None for module in _ML_MODULES):
    collect_ignore = ["test_embedding_context_benchmark.py"]
else:
    collect_ignore = []
