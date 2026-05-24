"""使用示例 —— 登录并查询亲友健康数据。

运行前请确保：
1. 已在小米运动健康 App 中添加了亲友关系
2. 亲友已在 App 中授权共享数据

用法：
    uv run python examples/basic_usage.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mi_fitness import MiHealthClient, XiaomiAuth

TOKEN_PATH = Path("token.json")


async def main() -> None:
    # region 登录（首次运行需要）
    if not TOKEN_PATH.exists():
        print("首次使用，请扫码登录：")
        async with XiaomiAuth() as auth:
            await auth.login_qr()
            auth.save_token(TOKEN_PATH)
            print(f"登录成功！Token 已保存至 {TOKEN_PATH}")
    # endregion

    # region 查询数据（一步创建客户端）
    async with MiHealthClient.from_token(TOKEN_PATH) as client:
        # 1. 获取亲友列表
        relatives = await client.get_relatives()
        print(f"\n已绑定 {len(relatives)} 位亲友：")
        for r in relatives:
            print(f"  - [{r.relative_uid}] {r.relative_note or '(未设置备注)'}")

        if not relatives:
            print("未找到亲友，请先在 App 中添加亲友关系")
            return

        # 2. 查询第一位亲友的最近同步数据
        target = relatives[0]
        uid = target.relative_uid
        print(f"\n查询 [{target.relative_note}] (UID: {uid}) 的最近同步健康数据：")

        latest = await client.get_latest_data(uid)
        print(f"  可用指标: {', '.join(latest.available_keys)}")

        if latest.heart_rate:
            print(f"  最新心率: {latest.heart_rate.bpm} bpm")
        if latest.sleep:
            print(f"  最新睡眠: {latest.sleep.total_duration}分钟 评分{latest.sleep.sleep_score}/100")
        if latest.steps:
            print(f"  最新步数: {latest.steps.steps}步 / {latest.steps.distance}米 / {latest.steps.calories}卡")
        if latest.weight:
            print(f"  最新体重: {latest.weight.weight}kg BMI {latest.weight.bmi}")

        summary = await client.get_latest_daily_summary(uid)
        print(f"\n最近同步日摘要 ({summary.date})：")
        print(f"  心率: {summary.heart_rate or '暂无数据'}")
        print(f"  睡眠: {summary.sleep or '暂无数据'}")
        print(f"  步数: {summary.steps or '暂无数据'}")
    # endregion


if __name__ == "__main__":
    asyncio.run(main())
