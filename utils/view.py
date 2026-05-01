import asyncio
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain

from ..domain import InternalCFG


class HelpHint:
    """提供用户提示文本"""

    def msg_searching(self, query: str) -> str:
        return f"正在搜索 '{query}'..."

    def msg_rendering(self, mode: str) -> str:
        return "正在整理菜单..."

    def msg_empty_result(self, mode: str, query: str | None) -> str:
        target = "事件监听器" if mode == "event" else "插件或指令"
        if query:
            return f"未找到包含 '{query}' 的{target}。"
        return f"当前没有可显示的{target}。"


class MsgRecall:
    """负责发送提示消息, 并在完成后撤回"""

    async def send_wait(
        self, event: AstrMessageEvent, text: str
    ) -> int | str | None:
        """发送提示并返回消息ID"""
        bot = getattr(event, "bot", None)
        payload = event.plain_result(text)

        # OneBot API
        if bot and hasattr(event, "_parse_onebot_json") and hasattr(bot, "call_action"):
            try:
                chain = payload.chain if hasattr(payload, "chain") else payload
                if not isinstance(chain, list):
                    chain = [chain]

                # 构建 OneBot 消息体
                msg_chain = MessageChain(chain=chain)
                obmsg = await event._parse_onebot_json(msg_chain)

                params = {"message": obmsg}
                # 确定发送目标
                if gid := event.get_group_id():
                    params["group_id"] = int(gid)
                    action = "send_group_msg"
                elif uid := event.get_sender_id():
                    params["user_id"] = int(uid)
                    action = "send_private_msg"
                else:
                    raise ValueError("无法确定发送目标")

                resp = await bot.call_action(action, **params)
                return self._extract_message_id(resp)

            except Exception as e:
                logger.debug(f"[TextMenu] OneBot 发送尝试失败，回退通用接口: {e}")

        # 兜底: 通用接口
        try:
            resp = await event.send(payload)
            return self._extract_message_id(resp)
        except Exception as e:
            logger.error(f"[TextMenu] 发送等待消息失败: {e}")
            return None

    async def recall(self, event: AstrMessageEvent, message_id: int | str | None):
        """撤回指定消息"""
        if not message_id:
            return
        bot = getattr(event, "bot", None)
        if not bot:
            logger.debug("[TextMenu] 无法获取 Bot 实例，撤回可能失效")
            return

        # 稍等避免闪撤
        await asyncio.sleep(InternalCFG.DELAY_SEND)

        try:
            # delete_msg
            if hasattr(bot, "delete_msg"):
                await bot.delete_msg(message_id=message_id)
            # recall_message
            elif hasattr(bot, "recall_message"):
                try:
                    await bot.recall_message(int(message_id))
                except (ValueError, TypeError):
                    logger.debug(f"[TextMenu] recall_message 不支持 ID: {message_id}")
            else:
                logger.debug("[TextMenu] 未找到撤回方法")
        except Exception as e:
            logger.warning(f"[TextMenu] 撤回消息 {message_id} 失败: {e}")

    def _extract_message_id(self, resp: Any) -> int | str | None:
        """提取 Message ID"""
        if not resp:
            return None

        # 直接是 ID
        if isinstance(resp, (int, str)):
            return resp

        # 字典结构
        if isinstance(resp, dict):
            data = resp.get("data")
            if isinstance(data, dict):
                if "message_id" in data:
                    return data["message_id"]
                if "res_id" in data:
                    return data["res_id"]
                if "forward_id" in data:
                    return data["forward_id"]

            # 外层字段
            if "message_id" in resp:
                return resp["message_id"]
            if "id" in resp:
                return resp["id"]
            return None

        # 对象属性(Telegram)
        if val := getattr(resp, "message_id", None):
            return val

        # 兜底
        if val := getattr(resp, "id", None):
            return val

        return None
