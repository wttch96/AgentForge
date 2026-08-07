"""DeepSeek 客户端封装。

DeepSeek 提供 OpenAI 兼容接口：
  base_url = https://api.deepseek.com
  model    = deepseek-chat（V3，默认） / deepseek-reasoner（R1 推理）

使用方式：
    from agents._shared.deepseek import DeepSeekClient
    client = DeepSeekClient()
    content = client.chat(system=..., user=...)
"""

import os

from openai import OpenAI

DEEPSEEK_BASE_URL = "https://api.deepseek.com"   # DeepSeek OpenAI 兼容接口地址
DEEPSEEK_MODEL = "deepseek-chat"                  # 默认模型：deepseek-chat（V3）
DEEPSEEK_TIMEOUT = 120                            # 请求超时（秒），生成日报文本较慢需放宽


class DeepSeekError(RuntimeError):
    """DeepSeek API 调用失败（统一异常，供上层捕获提示）。"""


class DeepSeekClient:
    """DeepSeek 对话客户端（OpenAI SDK 兼容）。

    依赖环境变量 DEEPSEEK_API_KEY，或构造时显式传入 api_key。
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEEPSEEK_MODEL,
        base_url: str = DEEPSEEK_BASE_URL,
    ) -> None:
        """初始化客户端。

        参数:
            api_key:   DeepSeek API 密钥；为 None 时从环境变量 DEEPSEEK_API_KEY 读取
            model:     模型名，默认 deepseek-chat
            base_url:  API 基础地址，默认官方地址

        异常:
            DeepSeekError: 未提供 api_key 且环境变量为空
        """
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not self.api_key:
            raise DeepSeekError(
                "缺少 DEEPSEEK_API_KEY，请设置环境变量或在初始化时传入 api_key。"
            )
        self.model = model
        self.client = OpenAI(api_key=self.api_key, base_url=base_url, timeout=DEEPSEEK_TIMEOUT)

    def chat(self, system: str, user: str, temperature: float = 0.7) -> str:
        """单轮对话，返回助手回复文本。

        参数:
            system:       系统提示词（角色设定 / 输出约束）
            user:         用户提示词（任务内容，通常含搜索到的数据）
            temperature:  采样温度，越低越保守（去重比对用 0.1）

        返回:
            助手回复的纯文本内容

        异常:
            DeepSeekError: API 调用失败或返回空内容
        """
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as exc:  # noqa: BLE001 - 统一包装为 DeepSeekError，便于上层统一提示
            raise DeepSeekError(f"DeepSeek API 调用失败: {exc}") from exc

        content = resp.choices[0].message.content
        if not content:
            raise DeepSeekError("DeepSeek 返回空内容。")
        return content
