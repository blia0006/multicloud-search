"""命令行入口的小工具。

主要解决一个高频体验问题：macOS 默认 shell 是 zsh，交互模式下默认关闭
`interactive_comments`，因此从文档/聊天里整段复制形如

    python3 tools/verify_all.py    # 70 项检查

的命令时，`#` 及其后文字会被当成真实参数传给脚本，导致 argparse 报
`unrecognized arguments`。这里统一在解析参数前把这类"伪参数"剥掉，
并在 stderr 给出一行提示（不静默吞掉，避免掩盖真正的拼写错误）。
"""

from __future__ import annotations

import sys
from typing import List, Optional

__all__ = ["strip_shell_comments"]


def strip_shell_comments(argv: Optional[List[str]] = None) -> List[str]:
    """丢弃第一个以 # 开头的参数及其之后的全部参数。

    >>> strip_shell_comments(["--verbose", "#", "70", "项检查"])
    ['--verbose']
    >>> strip_shell_comments(["--vcpu", "4"])
    ['--vcpu', '4']
    """
    args = list(sys.argv[1:] if argv is None else argv)
    for index, token in enumerate(args):
        if token.startswith("#"):
            dropped = args[index:]
            sys.stderr.write(
                "提示：忽略了被 shell 当成参数的注释内容 %r。\n"
                "      macOS 的 zsh 默认不识别行尾 # 注释，复制命令时请只复制命令本身，\n"
                "      或执行 setopt interactive_comments 开启注释支持。\n"
                % " ".join(dropped)
            )
            return args[:index]
    return args
