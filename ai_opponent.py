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
            # 晕眩时随便发个合法行动，handle_message会自动跳过
            return {"action": "move", "direction": "up"}

        # 计算到敌人的距离
        dist = abs(my_pos[0] - enemy_pos[0]) + abs(my_pos[1] - enemy_pos[1])

        # 随机犯错
        if random.random() < self.config["mistake_rate"]:
            return self._random_action(movable, skills, my_pos)

        # 策略：有技能在范围就用技能，否则向敌人移动
        if skills and dist <= 3:
            best_skill = max(range(len(skills)), key=lambda i: skills[i].get("damage", 0))
            skill = skills[best_skill]
            direction = self._direction_toward(my_pos, enemy_pos)

            if skill.get("range_type") in ("self_aura", "four_way", "multi_dash"):
                return {"action": "skill", "skill_index": best_skill}
            return {"action": "skill", "skill_index": best_skill, "direction": direction}

        # 向敌人移动
        if movable:
            best_move = min(movable, key=lambda cell: abs(cell[0] - enemy_pos[0]) + abs(cell[1] - enemy_pos[1]))
            direction = self._direction_from_to(my_pos, best_move)
            if direction:
                return {"action": "move", "direction": direction}

        # 无路可走时随便选个方向（会被is_passable拦截，但格式合法）
        return {"action": "move", "direction": random.choice(list(DIRECTIONS.keys()))}

    def _random_action(self, movable: list, skills: list, my_pos: list) -> dict:
        """随机行动（用于低难度），方向从合法移动中选"""
        options = []
        if movable:
            # 从合法移动中随机选一个
            target = random.choice(movable)
            direction = self._direction_from_to(my_pos, target)
            if direction:
                options.append({"action": "move", "direction": direction})
        if skills:
            idx = random.randrange(len(skills))
            skill = skills[idx]
            if skill.get("range_type") in ("self_aura", "four_way", "multi_dash"):
                options.append({"action": "skill", "skill_index": idx})
            else:
                options.append({"action": "skill", "skill_index": idx, "direction": random.choice(list(DIRECTIONS.keys()))})
        if not options:
            return {"action": "move", "direction": random.choice(list(DIRECTIONS.keys()))}
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
        """使用 API 做决策（高难度）- 同步HTTP，超时3秒回退规则"""
        skills_info = []
        for i, s in enumerate(state.get("your_skills", [])):
            skills_info.append(f"[{i}] {s['name']} 伤害{s['damage']} 类型{s['range_type']}")

        prompt = f"""鬼灭PVP游戏。你是{state.get('your_character', {}).get('name', 'AI')}。
回合{state.get('turn',0)}，HP{state.get('your_hp',0)}，敌HP{state.get('enemy_hp',0)}。
位置({state['your_pos'][0]},{state['your_pos'][1]})，敌({state['enemy_pos'][0]},{state['enemy_pos'][1]})。
技能：{'|'.join(skills_info)}
可移动：{state.get('movable_cells', [])[:6]}
只返回JSON：{{"action":"move","direction":"方向"}}或{{"action":"skill","skill_index":0,"direction":"方向"}}
方向：up/down/left/right/ul/ur/dl/dr"""

        try:
            # 用同步httpx，不嵌套事件循环
            import httpx
            with httpx.Client(timeout=3) as client:
                resp = client.post(
                    self.api_url,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "只返回JSON动作，不解释。"},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 80,
                        "temperature": 0.2,
                    },
                )
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                import re
                match = re.search(r'\{[^}]+\}', text)
                if match:
                    action = json.loads(match.group())
                    if action.get("action") in ("move", "skill"):
                        return action
        except Exception:
            pass
        # 任何失败回退规则AI
        return self._rule_decide(state, pid)
