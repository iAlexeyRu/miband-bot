"""小米账号认证子包。

对外只暴露 ``XiaomiAuth``，内部按登录方式拆分为独立模块。
"""

from mi_fitness.auth.manager import XiaomiAuth

__all__ = ["XiaomiAuth"]
