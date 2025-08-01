#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Convenience wrapper that refreshes PR data, renders plots, and updates README.

Rather than running four separate commands, execute:

    python update_all.py

Steps executed (in order):
1. accumulate_pr_data.main()   – downloads / updates `pr_data.csv`
2. plot_pr_delays.main()       – saves latency box-plot to `pr_delays.png`
3. plot_pr_counts.main()       – saves monthly count bar chart to `pr_counts.png`
4. generate_pr_links_table.main() – rewrites PR-links table in *README.md*

Each sub-script is invoked as a library function so the entire pipeline runs in
one Python process.  Command-line arguments intended for *update_all.py* are
not forwarded to the individual tools; they always execute with their default
settings.
"""
from __future__ import annotations

import importlib
import logging
import sys
from contextlib import contextmanager
from types import ModuleType
from typing import Callable, List, Tuple, Iterator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# (module_name, callable_name) in execution order
_STEPS: List[Tuple[str, str]] = [
    ("accumulate_pr_data", "main"),
    ("plot_pr_delays", "main"),
    ("plot_pr_counts", "main"),
    ("generate_pr_links_table", "main"),
]


@contextmanager
def _clean_argv() -> "Iterator[None]":
    """Context manager that temporarily resets sys.argv to a single placeholder.

    This prevents sub-modules that use argparse from accidentally parsing the
    command-line intended for *update_all.py*.
    """
    original_argv = sys.argv
    sys.argv = [original_argv[0]]
    try:
        yield
    finally:
        sys.argv = original_argv


def _run_step(module_name: str, func_name: str) -> None:
    logging.info("Running %s.%s()", module_name, func_name)
    module: ModuleType = importlib.import_module(module_name)
    func: Callable = getattr(module, func_name)
    with _clean_argv():
        func()
    logging.info("Finished %s.%s()", module_name, func_name)


def main() -> None:
    for module_name, func_name in _STEPS:
        _run_step(module_name, func_name)
    logging.info("All steps completed successfully.")


if __name__ == "__main__":
    main()
