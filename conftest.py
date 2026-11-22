"""pytest 配置：确保仓库根目录位于 sys.path，便于导入 deeppeel 包。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
