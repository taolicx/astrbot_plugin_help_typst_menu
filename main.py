import asyncio
from pathlib import Path

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, StarTools

from .domain import InternalCFG, PluginMetadata, RenderNode, TextMenuConfig
from .utils import HelpHint, MsgRecall
from .core import CommandAnalyzer, EventAnalyzer, FilterAnalyzer


class TextMenuPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 1. 静态资源路径
        self.plugin_dir = Path(__file__).parent
        self.data_dir = StarTools.get_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 2. 配置加载
        self.config = config
        self.plugin_config = TextMenuConfig.load(config)

        # 3. 初始化组件
        self.hint = HelpHint()
        self.msg = MsgRecall()

        # 4. 分析器
        self.cmd_analyzer = CommandAnalyzer(context, self.plugin_config)
        self.evt_analyzer = EventAnalyzer(context, self.plugin_config)
        self.flt_analyzer = FilterAnalyzer(context, self.plugin_config)

        self.prefixes: list[str] = []

    async def initialize(self):
        """异步初始化"""
        self._init_prefixes(self.context)
        logger.info("[TextMenu] 初始化完成")

    async def terminate(self):
        """周期 hook。"""
        await self._perform_cleanup()

    async def _perform_cleanup(self):
        try:
            # glob 匹配
            temp_files = list(self.data_dir.glob("temp_*"))
            if not temp_files:
                return

            logger.debug(f"[TextMenu] 清理 {len(temp_files)} 个缓存文件...")
            
            for f in temp_files:
                try:
                    if f.exists(): # 双重检查
                        f.unlink()
                except OSError:
                    pass

        except Exception as e:
            logger.warning(f"[TextMenu] 清理失败: {e}")

    async def _safe_reload(self, pm, plugin_name):
        """延迟重载"""
        await asyncio.sleep(InternalCFG.DELAY_SEND)
        try:
            logger.info(f"[TextMenu] 正在执行自我重载: {plugin_name}")
            await pm.reload(plugin_name)
        except Exception as e:
            logger.error(f"[TextMenu] 自我重载异常: {e}")

    async def _handle_request(
        self,
        event: AstrMessageEvent,
        analyzer,
        title: str,
        mode: str,
        query: str | None,
    ):
        """通用请求处理逻辑：分析插件数据并输出纯文字菜单。"""
        wait_msg_id = None

        if self.plugin_config.enable_waiting_message:
            # 1. 发送提示
            hint_text = (
                self.hint.msg_searching(query) if query else self.hint.msg_rendering(mode)
            )
            wait_msg_id = await self.msg.send_wait(event, hint_text)

        try:
            plugins = analyzer.get_plugins(query)
        except Exception as e:
            logger.error(f"[TextMenu] 菜单分析失败: {e}", exc_info=True)
            plugins = []

        if wait_msg_id:
            await self.msg.recall(event, wait_msg_id)

        if not plugins:
            yield event.plain_result(self.hint.msg_empty_result(mode, query))
            return

        display_title = f'搜索结果: "{query}"' if query else title
        text = self._format_text_menu(plugins, display_title, mode, query)
        for chunk in self._split_text(text):
            yield event.plain_result(chunk)

    def _format_text_menu(
        self,
        plugins: list[PluginMetadata],
        title: str,
        mode: str,
        query: str | None,
    ) -> str:
        if mode == "plugin_index":
            return self._format_plugin_index(plugins)
        return self._format_plugin_details(plugins, title, mode, query)

    def _format_plugin_index(self, plugins: list[PluginMetadata]) -> str:
        lines = ["功能菜单", f"共 {len(plugins)} 个可用插件", ""]
        for index, plugin in enumerate(plugins, start=1):
            name = self._plugin_label(plugin)
            count = self._count_nodes(plugin.nodes)
            desc = self._compact_desc(plugin.desc)
            lines.append(f"{index}. {name} ({count} 条指令)")
            if desc:
                lines.append(f"   {desc}")
        lines.extend(
            [
                "",
                "查看详情：",
                "发送 /helps 序号，例如 /helps 1",
                "也可以发送 /helps 插件名称，例如 /helps 每日签到",
            ]
        )
        return "\n".join(lines)

    def _format_plugin_details(
        self,
        plugins: list[PluginMetadata],
        title: str,
        mode: str,
        query: str | None,
    ) -> str:
        lines = [title, f"共 {len(plugins)} 项匹配结果"]
        if query:
            lines.append(f"关键词：{query}")
        lines.append("")

        for plugin in plugins:
            name = self._plugin_label(plugin)
            desc = self._compact_desc(plugin.desc)
            header = name
            if plugin.version:
                header += f" · {plugin.version}"
            lines.append(header)
            if desc:
                lines.append(desc)
            if plugin.nodes:
                lines.extend(self._format_nodes(plugin.nodes, level=1))
            else:
                lines.append("  暂无可展示项目")
            lines.append("")

        return "\n".join(lines).strip()

    def _format_nodes(self, nodes: list[RenderNode], level: int) -> list[str]:
        lines: list[str] = []
        indent = "  " * level
        for node in nodes:
            tag = " [管理]" if node.tag == "admin" else ""
            if node.children:
                desc = f"：{node.desc}" if node.desc else ""
                lines.append(f"{indent}- {node.name}{tag}{desc}")
                lines.extend(self._format_nodes(node.children, level + 1))
            else:
                desc = f" - {node.desc}" if node.desc else ""
                lines.append(f"{indent}- /{node.name}{tag}{desc}")
        return lines

    def _plugin_label(self, plugin: PluginMetadata) -> str:
        return plugin.display_name or plugin.name

    def _compact_desc(self, desc: str | None) -> str:
        if not desc:
            return ""
        text = " ".join(str(desc).replace("\n", " ").split())
        return text[:80] + "..." if len(text) > 80 else text

    def _count_nodes(self, nodes: list[RenderNode]) -> int:
        total = 0
        for node in nodes:
            if node.children:
                total += self._count_nodes(node.children)
            else:
                total += 1
        return total

    def _split_text(self, text: str) -> list[str]:
        limit = InternalCFG.TEXT_CHUNK_LIMIT
        if len(text) <= limit:
            return [text]

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in text.splitlines():
            line_len = len(line) + 1
            if current and current_len + line_len > limit:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += line_len
        if current:
            chunks.append("\n".join(current))
        return chunks

    async def _handle_plugin_index_request(self, event: AstrMessageEvent):
        """输出一级菜单：只展示插件/系统名称，选择后再看详细指令。"""
        async for r in self._handle_request(
            event,
            self.cmd_analyzer,
            "功能菜单",
            "plugin_index",
            None,
        ):
            yield r

    def _resolve_menu_query(self, query: str) -> str:
        """支持用一级菜单序号进入插件详情，例如：helps 3。"""
        cleaned = query.strip()
        if not cleaned.isdigit():
            return cleaned

        plugins = self.cmd_analyzer.get_plugins(None)
        index = int(cleaned) - 1
        if 0 <= index < len(plugins):
            return plugins[index].name
        return cleaned

    async def _cleanup_task(self, files: list[Path]):
        """异步清理任务"""
        await asyncio.sleep(InternalCFG.DELAY_SEND)
        for p in files:
            try:
                if p.exists():
                    p.unlink()
            except Exception as e:
                logger.warning(f"[TextMenu] 临时文件清理失败 {p}: {e}")

    def _init_prefixes(self, context: Context):
        """唤醒词"""
        try:
            global_config = context.get_config()
            raw = global_config.get("wake_prefix", ["/"])
            self.prefixes = [raw] if isinstance(raw, str) else list(raw)
        except Exception as e:
            logger.warning(f"[TextMenu] 获取唤醒词失败，使用默认值 '/': {e}")
            self.prefixes = ["/"]

    @filter.command("helps")
    async def show_menu(self, event: AstrMessageEvent, query: str = ""):
        """显示指令菜单"""
        if not query or not query.strip():
            async for r in self._handle_plugin_index_request(event):
                yield r
            return

        query = self._resolve_menu_query(query)
        async for r in self._handle_request(
            event, self.cmd_analyzer, "AstrBot 指令菜单", "command", query
        ):
            yield r

    @filter.command("events")
    async def show_events(self, event: AstrMessageEvent, query: str = ""):
        """显示事件监听列表"""
        async for r in self._handle_request(
            event, self.evt_analyzer, "AstrBot 事件监听", "event", query
        ):
            yield r

    @filter.command("filters")
    async def show_filters(self, event: AstrMessageEvent, query: str = ""):
        """显示过滤器详情"""
        async for r in self._handle_request(
            event, self.flt_analyzer, "AstrBot 过滤器分析", "filter", query
        ):
            yield r
