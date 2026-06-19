"""
AI 对手引擎 - 单人模式
AI 与玩家同时行动，不能预知玩家动作。
根据本地战斗数据提供不同难度。
"""

import random
import json
from typing import Tuple, List, Optional
from characters import DIRECTIONS, Character


class AIOpponent:
    """AI 对手，使用 API 或规则做出决策"""

    # 难度配置
    DIFFICULTIES = {
        "easy": {"mistake_rate": 0.4, "use_api": False},
        "normal": {"mistake_rate": 0.15, "use_api": False},
        "hard": {"mistake_rate": 0.0, "use_api": True},
    }

    def __init__(self, difficulty: str = "normal", api_key: str = "",
                 api_url: str = "", model: str = ""):
        self.difficulty = difficulty
        self.config = self.DIFFICULTIES.get(difficulty, self.DIFFICULTIES["normal"])
        self.api_key = api_key
        self.api_url = api_url
        self.model = model

    def decide_action(self, game_state: dict, player_id: int) -> dict:
        """
        根据当前游戏状态决定行动。
        重要：AI 只能看到当前状态，不能看到玩家的本回合行动。
        """
        if self.config["use_api"] and self.api_key:
            return self._api_decide(game_state, player_id)
        return self._rule_decide(game_state, player_id)

    def _rule_decide(self, state: dict, pid: int) -> dict:
        """基于规则的决策"""
        my_pos = state["your_pos"]
        enemy_pos = state["enemy_pos"]
        skills = state.get("your_skills", [])
        stunned = state.get("your_stunned", False)
        movable = state.get("movable_cells", [])

        if stunned:
            return {"action": "pass"}

        # 计算到敌人的距离
        dist = abs(my_pos[0] - enemy_pos[0]) + abs(my_pos[1] - enemy_pos[1])

        # 随机犯错
        if random.random() < self.config["mistake_rate"]:
            return self._random_action(movable, skills)

        # 策略：有技能在范围就用技能，否则向敌人移动
        if skills and dist <= 3:
            # 选择伤害最高的技能
            best_skill = max(range(len(skills)), key=lambda i: skills[i].get("damage", 0))
            skill = skills[best_skill]
            direction = self._direction_toward(my_pos, enemy_pos)

            # 对于不需要方向的技能，不传direction
            if skill.get("range_type") in ("self_aura", "four_way", "multi_dash"):
                return {"action": "skill", "skill_index": best_skill}
            return {"action": "skill", "skill_index": best_skill, "direction": direction}

        # 向敌人移动
        if movable:
            # 选最接近敌人的可移动格
            best_move = min(movable, key=lambda cell: abs(cell[0] - enemy_pos[0]) + abs(cell[1] - enemy_pos[1]))
            direction = self._direction_from_to(my_pos, best_move)
            if direction:
                return {"action": "move", "direction": direction}

        return {"action": "pass"}

    def _random_action(self, movable: list, skills: list) -> dict:
        """随机行动（用于低难度）"""
        options = []
        if movable:
            options.append({"action": "move", "direction": random.choice(list(DIRECTIONS.keys()))})
        if skills:
            idx = random.randrange(len(skills))
            skill = skills[idx]
            if skill.get("range_type") in ("self_aura", "four_way", "multi_dash"):
                options.append({"action": "skill", "skill_index": idx})
            else:
                options.append({"action": "skill", "skill_index": idx, "direction": random.choice(list(DIRECTIONS.keys()))})
        if not options:
            return {"action": "pass"}
        return random.choice(options)

    def _direction_toward(self, from_pos: list, to_pos: list) -> str:
        """计算朝向敌人的最佳方向"""
        dr = to_pos[0] - from_pos[0]
        dc = to_pos[1] - from_pos[1]
        ndr = -1 if dr < 0 else (1 if dr > 0 else 0)
        ndc = -1 if dc < 0 else (1 if dc > 0 else 0)
        mapping = {
            (-1,-1): "ul", (-1,0): "up", (-1,1): "ur",
            (0,-1): "left", (0,1): "right",
            (1,-1): "dl", (1,0): "down", (1,1): "dr",
        }
        return mapping.get((ndr, ndc), "right")

    def _direction_from_to(self, from_pos: list, to_pos: list) -> Optional[str]:
        dr = to_pos[0] - from_pos[0]
        dc = to_pos[1] - from_pos[1]
        ndr = -1 if dr < 0 else (1 if dr > 0 else 0)
        ndc = -1 if dc < 0 else (1 if dc > 0 else 0)
        if ndr == 0 and ndc == 0:
            return None
        mapping = {
            (-1,-1): "ul", (-1,0): "up", (-1,1): "ur",
            (0,-1): "left", (0,1): "right",
            (1,-1): "dl", (1,0): "down", (1,1): "dr",
        }
        return mapping.get((ndr, ndc))

    def _api_decide(self, state: dict, pid: int) -> dict:
        """使用 API 做决策（高难度）- 同步版本，由调用方在线程中执行"""
        skills_info = []
        for i, s in enumerate(state.get("your_skills", [])):
            skills_info.append(f"[{i}] {s['name']} 伤害{s['damage']} 类型{s['range_type']} 效果{','.join(s.get('effects',[]))}")

        prompt = f"""你正在玩鬼灭之刃PVP对战游戏。你是{state.get('your_character', {}).get('name', 'AI')}。
当前回合{state.get('turn',0)}，地图6行×12列。你的HP{state.get('your_hp',0)}，敌人HP{state.get('enemy_hp',0)}。
你的位置({state['your_pos'][0]},{state['your_pos'][1]})，敌人位置({state['enemy_pos'][0]},{state['enemy_pos'][1]})。
{'你处于晕眩状态，只能跳过。' if state.get('your_stunned') else ''}

可用技能：
{chr(10).join(skills_info)}

可移动格子（坐标）：{state.get('movable_cells', [])}

障碍物位置（1=障碍）：{state.get('map', [])}

请选择最优行动，只返回JSON（不要其他文字）：
{{"action":"move","direction":"方向"}} 或 {{"action":"skill","skill_index":数字,"direction":"方向"}} 或 {{"action":"pass"}}
方向：up/down/left/right/ul/ur/dl/dr"""

        try:
            import httpx
            import asyncio

            async def _call():
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        self.api_url,
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": "你是一个鬼灭之刃PVP游戏AI。只返回JSON，不返回其他内容。"},
                                {"role": "user", "content": prompt},
                            ],
                            "max_tokens": 100,
                            "temperature": 0.3,
                        },
                    )
                    data = resp.json()
                    text = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                    # 提取JSON
                    import re
                    match = re.search(r'\{[^}]+\}', text)
                    if match:
                        return json.loads(match.group())
                    return {"action": "pass"}
            return asyncio.run(_call())
        except Exception:
            # API 失败时回退到规则
            return self._rule_decide(state, pid)
