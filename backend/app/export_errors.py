"""Closed, non-sensitive export failures; no native framework imports here."""
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError


EXPORT_EXIT_ERRORS = {
    73: "ONNX_DEPENDENCY_UNAVAILABLE",
    74: "ONNX_MODEL_INVALID",
    75: "ONNX_OPERATOR_UNSUPPORTED",
    76: "ONNX_RUNTIME_FAILED",
}


EXPORT_DIAGNOSTICS = (
    "graph_read", "graph_parse", "graph_guard", "graph_checker",
    "compare_shape_dtype", "compare_nonfinite", "compare_tolerance",
    "final_integrity", "unknown",
)


class ExportGraphError(ValueError):
    def __init__(self, message, diagnostic):
        if type(diagnostic) is not str or diagnostic not in EXPORT_DIAGNOSTICS:
            raise ValueError("unknown export diagnostic")
        self.diagnostic = diagnostic
        super().__init__(message)


class ExportFailure(ValueError):
    def __init__(self, exit_code: int, *, diagnostic="unknown"):
        if type(exit_code) is not int or exit_code not in EXPORT_EXIT_ERRORS:
            raise ValueError("unknown export failure")
        if type(diagnostic) is not str or diagnostic not in EXPORT_DIAGNOSTICS:
            raise ValueError("unknown export diagnostic")
        self.diagnostic = diagnostic if exit_code == 74 else "unknown"
        self.exit_code = exit_code
        # Never retain or expose an upstream exception's text in the public code.
        super().__init__(EXPORT_EXIT_ERRORS[exit_code])


def unsupported_operator():
    return ExportFailure(75)


@contextmanager
def export_boundary(stage: str, *, passthrough: tuple[type[Exception], ...] = (), diagnostic="unknown"):
    if stage not in {"dependency", "graph", "runtime"}:
        raise ValueError("unknown export boundary")
    if type(diagnostic) is not str or diagnostic not in EXPORT_DIAGNOSTICS:
        raise ValueError("unknown export diagnostic")
    try:
        yield
    except ExportFailure:
        raise
    except (PackageNotFoundError, ImportError) as exc:
        raise ExportFailure(73) from exc
    except OSError:
        # Filesystem errors keep the existing STORAGE_UNAVAILABLE protocol.
        raise
    except Exception as exc:
        if isinstance(exc, passthrough):
            raise
        # Exact SDK exception identities only. Never classify by error text.
        native = (type(exc).__module__, type(exc).__name__)
        if native in {
            ("onnxruntime.capi.onnxruntime_pybind11_state", "NotImplemented"),
            ("torch.onnx.errors", "UnsupportedOperatorError"),
        }:
            code = 75
        else:
            code = 74 if stage == "graph" else 76
        detail = exc.diagnostic if type(exc) is ExportGraphError else diagnostic
        raise ExportFailure(code, diagnostic=detail) from exc
