"""Tests for the repo tools in tools/ (sync_shared, lint_repo, smoke_live).

tools/ is a folder of scripts, not a package, so tests load each script
by path with load_tool().
"""

import importlib.util
import os
import sys

from tests import _paths

TOOLS_DIR = os.path.join(_paths.REPO_ROOT, "tools")


def load_tool(name):
    """Import tools/<name>.py as a module (cached in sys.modules as tool_<name>)."""
    module_name = "tool_" + name
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(TOOLS_DIR, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
