from enum import Enum

from astrbot.core.star.star_handler import EventType


class InternalCFG:
    """内部常量"""

    EVENT_TYPE_MAP: dict[EventType, str] = {
        EventType.OnAstrBotLoadedEvent: "系统启动 (Loaded)",
        EventType.OnPlatformLoadedEvent: "平台就绪 (Platform)",
        EventType.AdapterMessageEvent: "消息监听 (Message)",
        EventType.OnLLMRequestEvent: "LLM 请求前 (Pre-LLM)",
        EventType.OnLLMResponseEvent: "LLM 响应后 (Post-LLM)",
        EventType.OnDecoratingResultEvent: "消息修饰 (Decorate)",
        EventType.OnAfterMessageSentEvent: "发送回执 (Sent)",
    }

    # 时序
    DELAY_SEND: float = 1

    # 文本输出
    TEXT_CHUNK_LIMIT: int = 3600


class DefaultCFG:
    """兜底: 配置默认值"""

    # 过滤设置
    # config.py 负责 list → set
    IGNORED_PLUGINS: set[str] = {
        "astrbot",
        "astrbot-web-searcher",
        "astrbot-python-interpreter",
        "session_controller",
        "builtin_commands",
        "astrbot-reminder",
        "astrbot_plugin_help_typst",
        "astrbot_plugin_text_menu",
    }


class RenderMode(str, Enum):
    """枚举"""

    COMMAND = "command"
    EVENT = "event"
    FILTER = "filter"
