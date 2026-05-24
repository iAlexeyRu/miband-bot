"""二维码扫码登录，获取 Token。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import qrcode
import qrcode.constants

from mi_fitness.auth import XiaomiAuth
from mi_fitness.exceptions import AuthError

TOKEN_FILE = Path("token.json")


def _print_qr_to_terminal(data: str) -> None:
    """用 Unicode 半块字符将二维码紧凑渲染到终端。"""
    qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()

    # 补齐奇数行
    if len(matrix) % 2:
        matrix.append([False] * len(matrix[0]))

    # 每两行像素合并为一行字符：用 ▀▄█ 和空格表示四种组合
    # False = 白色模块（前景色块），True = 黑色模块（背景留空）
    for r in range(0, len(matrix), 2):
        line: list[str] = []
        for c in range(len(matrix[0])):
            top_white = not matrix[r][c]
            bot_white = not matrix[r + 1][c]
            if top_white and bot_white:
                line.append("\u2588")  # █
            elif top_white:
                line.append("\u2580")  # ▀
            elif bot_white:
                line.append("\u2584")  # ▄
            else:
                line.append(" ")
        print("".join(line))


async def _qr_login() -> None:
    async def show_qr(qr_image_url: str, login_url: str) -> None:
        print("\n📱 请用小米账号 APP 扫描二维码登录\n")
        if login_url:
            _print_qr_to_terminal(login_url)
        print(f"\n   二维码图片: {qr_image_url}")
        if login_url:
            print(f"   浏览器打开: {login_url}")
        print("\n⏳ 等待扫码...\n")

    async with XiaomiAuth() as auth:
        try:
            await auth.login_qr(qr_callback=show_qr)
        except AuthError as e:
            print(f"❌ 扫码登录失败: {e}")
            raise

        auth.save_token(TOKEN_FILE)
        print(f"✅ 扫码登录成功！user_id = {auth.token.user_id}")
        print(f"   Token 已保存至 {TOKEN_FILE.resolve()}")


def main() -> None:
    """CLI 入口。"""
    asyncio.run(_qr_login())


if __name__ == "__main__":
    main()
