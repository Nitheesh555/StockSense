"""Runtime compatibility guards for optional local dependencies."""

import sys
import types


def _install_pyarrow_stub():
    pyarrow = types.ModuleType("pyarrow")
    pyarrow.__version__ = "0.0.0"
    pyarrow.Array = type("Array", (), {})
    pyarrow.ChunkedArray = type("ChunkedArray", (), {})
    pyarrow.Scalar = type("Scalar", (), {})
    compute = types.ModuleType("pyarrow.compute")
    sys.modules["pyarrow"] = pyarrow
    sys.modules["pyarrow.compute"] = compute


def disable_blocked_pyarrow():
    """
    Some Windows environments expose pyarrow but block its DLLs by policy.
    Pandas can run without pyarrow, so mark it unavailable before pandas imports.
    """
    try:
        import pyarrow.compute  # noqa: F401
    except Exception:
        _install_pyarrow_stub()
