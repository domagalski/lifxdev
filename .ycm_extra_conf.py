import pathlib

_ROOT = pathlib.Path(__file__).parent


def Settings(**kwargs):
    return {"interpreter_path": _ROOT / ".venv/lifxdev/bin/python3"}
