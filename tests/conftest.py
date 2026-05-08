import sys
import types


class FakeTextPart:
    def __init__(self, text):
        self.text = text
        self.marked_temp = False

    def mark_as_temp(self):
        self.marked_temp = True
        return self


astrbot_module = sys.modules.setdefault("astrbot", types.ModuleType("astrbot"))
core_module = sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
agent_module = sys.modules.setdefault("astrbot.core.agent", types.ModuleType("astrbot.core.agent"))
message_module = types.ModuleType("astrbot.core.agent.message")
message_module.TextPart = FakeTextPart
sys.modules["astrbot.core.agent.message"] = message_module
setattr(astrbot_module, "core", core_module)
setattr(core_module, "agent", agent_module)
setattr(agent_module, "message", message_module)
