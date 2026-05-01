from dataclasses import dataclass

from astrbot.api import AstrBotConfig, logger

from . import DefaultCFG


@dataclass
class TextMenuConfig:
    """插件全局配置。"""

    enable_waiting_message: bool
    ignored_plugins: set[str]

    @classmethod
    def load(cls, raw_config: AstrBotConfig) -> "TextMenuConfig":
        enable_wait = raw_config.get("enable_waiting_message", False)

        ignored_list = raw_config.get("ignored_plugins", None)
        ignored_set = (
            set(ignored_list)
            if ignored_list is not None
            else DefaultCFG.IGNORED_PLUGINS.copy()
        )

        logger.debug(
            f"[TextMenu] 配置加载完毕: ignored_plugins={len(ignored_set)}"
        )

        return cls(
            enable_waiting_message=enable_wait,
            ignored_plugins=ignored_set,
        )
