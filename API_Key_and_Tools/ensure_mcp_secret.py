
from pathlib import Path
import re
import secrets

from dotenv import dotenv_values


# MCP 鉴权密钥专用文件
ENV_PATH = (
    Path(__file__).resolve().parent / "MCP_TOKEN_SECRET.env"
).resolve()


def ensure_mcp_token_secret() -> None:
    """密钥不存在或无效时生成并保存；已有有效密钥时不重新生成。"""

    # 确保配置目录存在
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 读取现有配置
    content = (
        ENV_PATH.read_text(encoding="utf-8")
        if ENV_PATH.exists()
        else ""
    )

    config = dotenv_values(str(ENV_PATH))
    current_secret = config.get("MCP_TOKEN_SECRET")

    # 已有至少 32 字节的密钥：保留，不重新生成
    if (
        isinstance(current_secret, str)
        and len(current_secret.encode("utf-8")) >= 32
    ):
        print("MCP_TOKEN_SECRET 已存在，保留现有密钥。")
        return

    # 生成 32 字节的随机密钥，以十六进制形式保存
    new_secret = secrets.token_hex(32)

    # 如果文件中有旧的密钥配置，就替换它；否则追加
    pattern = re.compile(
        r"(?m)^\s*(?:export\s+)?MCP_TOKEN_SECRET\s*=.*$"
    )

    if pattern.search(content):
        content = pattern.sub(
            f"MCP_TOKEN_SECRET={new_secret}",
            content,
        )
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"MCP_TOKEN_SECRET={new_secret}\n"

    ENV_PATH.write_text(content, encoding="utf-8")

    print(f"已生成并保存 MCP_TOKEN_SECRET：{ENV_PATH}")
    print("密钥内容不会显示在终端中。")


if __name__ == "__main__":
    ensure_mcp_token_secret()

# 运行方式
# cd D:\pycharm\split_Langgraph_RAG_teaching_agent
# python API_Key_and_Tools\ensure_mcp_secret.py
