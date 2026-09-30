import importlib.util
import os
import tempfile
from pathlib import Path


def load_app_module():
    with tempfile.TemporaryDirectory() as data_dir:
        os.environ["MACVOICEFLOW_DATA_DIR"] = data_dir
        os.environ["MACVOICEFLOW_CACHE_DIR"] = data_dir
        source = Path(__file__).parents[1] / "src/macvoiceflow/realtime_app.py"
        spec = importlib.util.spec_from_file_location("macvoiceflow_realtime_app", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


app = load_app_module()
result = app.clean_and_format_transcript(
    "[00:00:01] 嗯\n[00:00:02] 这是第一句。\n[00:00:03] 这是第二句。"
)

assert "嗯" not in result
assert result.startswith("[00:00:02] 这是第一句。")
assert "这是第二句。" in result
print("transcript formatting: ok")
