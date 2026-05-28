"""copy_workflow — 中英社交文案生成工作流的 Python 包。

Streamlit 单文件应用 (`app.py`) 不依赖此包；它有自己的实现以保持单文件可部署。
此包为 CLI 路径 (`copy-workflow ...`) 和需要程序化调用的场景提供。
"""

from .config import Config, get_config
from .llm import DeepSeekClient, call_with_validation, parse_json_strict
from .models import Extract, Post

__version__ = "0.2.0"

__all__ = [
    "Config",
    "DeepSeekClient",
    "Extract",
    "Post",
    "__version__",
    "call_with_validation",
    "get_config",
    "parse_json_strict",
]
