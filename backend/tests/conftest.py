"""pytest 配置：让 tests/ 下的用例能直接 `import app.*`。

把 backend/ 加进 sys.path，这样 clone 下来不用装包、不用设 PYTHONPATH 就能跑。
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
