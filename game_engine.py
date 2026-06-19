"""
游戏逻辑引擎
包含：地图生成、移动计算、技能范围计算、回合结算、猜拳逻辑
"""

import random
import string
import time
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field

from characters import (
    Skill, Character, CHARACTER_TANJIRO, CHARACTER_AKAZA,
    DIRECTIONS, DIRECTION_NAMES
)

# 地图尺寸
ROWS = 6
COLS = 12
MIN_OBSTACLES = 8
MAX_OBSTACLES = 12


def generate_room_code() -> str:
    """生成6位房间码（大写字母+数字）"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(6))


@dataclass
class PlayerState:
    """单个玩家的状态"""
    player_id: int = 0          # 0或1
    name: str = ""              # 玩家名称
    character: Optional[Character] = None
    selected_skills: List[Skill] = field(default_factory=list)
    hp: float = 0
    max_hp: int = 0
    position: Tuple[int, int] = (0, 0)
    stunned: bool = False       # 是否晕眩
    connected: bool = False
    is_ai: bool = False          # 是否为AI玩家
    last_action: Optional[dict] = None  # 本回合的行动
    ws = None


class GameState:
    """游戏状态管理"""

    def __init__(self):
        self.map_grid: List[List[int]] = []  # 6×12, 0=空地, 1=障碍物
        self.players: List[PlayerState] = [
            PlayerState(player_id=0, position=(0, 0)),
            PlayerState(player_id=1, position=(5, 11)),
        ]
        self.turn: int = 0
        self.log: List[str] = []
        self.game_over: bool = False
        self.winner: Optional[int] = None
        self.pending_rps: bool = False  # 是否等待猜拳
        self.rps_player_id: int = 0     # 需要猜拳的玩家
        self.rps_skill_name: str = ""   # 触发猜拳的技能名
        self._rps_damage_pending: float = 0  # 猜拳中暂存的伤害值
        self.battle_history: List[dict] = []  # 完整战斗记录

    def generate_map(self):
        """随机生成地图（含障碍物）"""
        self.map_grid = [[0] * COLS for _ in range(ROWS)]

        # 障碍物不能生成在玩家初始位置及其相邻格子
        forbidden = set()
        for p in self.players:
            r, c = p.position
            forbidden.add((r, c))
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if self.in_bounds(r + dr, c + dc):
                        forbidden.add((r + dr, c + dc))

        num_obstacles = random.randint(MIN_OBSTACLES, MAX_OBSTACLES)
        available = [
            (r, c) for r in range(ROWS) for c in range(COLS)
            if (r, c) not in forbidden
        ]

        obstacles = random.sample(available, min(num_obstacles, len(available)))
        for r, c in obstacles:
            self.map_grid[r][c] = 1

    def in_bounds(self, r: int, c: int) -> bool:
        """检查坐标是否在地图范围内"""
        return 0 <= r < ROWS and 0 <= c < COLS

    def is_passable(self, r: int, c: int) -> bool:
        """检查格子是否可通过（在界内、非障碍、无其他玩家）"""
        if not self.in_bounds(r, c):
            return False
        if self.map_grid[r][c] == 1:
            return False
        for p in self.players:
            if p.position == (r, c):
                return False
        return True

    def get_movable_cells(self, player_id: int) -> List[Tuple[int, int]]:
        """获取某玩家当前可移动到的格子（8方向、1格）"""
        p = self.players[player_id]
        r, c = p.position
        cells = []
        for direction, (dr, dc) in DIRECTIONS.items():
            nr, nc = r + dr, c + dc
            if self.is_passable(nr, nc):
                cells.append((nr, nc))
        return cells

    def get_skill_coverage(self, skill: Skill, player_id: int,
                           direction: str = None) -> Tuple[List[Tuple[int, int]], Optional[Tuple[int, int]]]:
        """
        计算技能覆盖的格子
        返回: (受影响的格子列表, 施法者新位置或None)
        """
        p = self.players[player_id]
        r, c = p.position
        cells = []
        new_pos = None  # 施法者位移目标（AS效果）

        if skill.range_type == "line":
            # 直线：向指定方向延伸直到边界或障碍
            if direction is None:
                return [], None
            dr, dc = DIRECTIONS[direction]
            for k in range(1, COLS + 1):  # 最大延伸到地图边界
                nr, nc = r + dr * k, c + dc * k
                if not self.in_bounds(nr, nc):
                    break
                cells.append((nr, nc))
                if self.map_grid[nr][nc] == 1:
                    break  # 遇到障碍停止

        elif skill.range_type == "self_aura":
            # 自身全域光环：周围8格
            for dr, dc in [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]:
                nr, nc = r + dr, c + dc
                if self.in_bounds(nr, nc):
                    cells.append((nr, nc))

        elif skill.range_type == "square_3x3":
            # 3×3正方形：以指定方向1格处为中心
            if direction is None:
                return [], None
            dr, dc = DIRECTIONS[direction]
            center_r, center_c = r + dr, c + dc
            for i in range(center_r - 1, center_r + 2):
                for j in range(center_c - 1, center_c + 2):
                    if self.in_bounds(i, j):
                        cells.append((i, j))

        elif skill.range_type == "dash_surround":
            # 位移环绕：向指定方向突进2格，攻击路径及周围
            if direction is None:
                return [], None
            dr, dc = DIRECTIONS[direction]
            path_cells = []
            for k in range(1, 4):  # 最多移动3格
                nr, nc = r + dr * k, c + dc * k
                if not self.in_bounds(nr, nc):
                    break
                # 检查是否遇到其他玩家
                other_player = self.players[1 - player_id]
                if (nr, nc) == other_player.position:
                    break  # 不能移动到有人的格子
                if self.map_grid[nr][nc] == 1:
                    if "WL" in skill.effects:
                        break  # WL效果：遇障碍停止
                    # DB效果：破坏障碍
                    if "DB" in skill.effects:
                        self.map_grid[nr][nc] = 0
                path_cells.append((nr, nc))
                if self.map_grid[nr][nc] == 1 and "WL" in skill.effects:
                    break

            if path_cells:
                # 攻击路径上的所有格子
                cells.extend(path_cells)
                # 位移目标：路径最后一格
                if "AS" in skill.effects:
                    new_pos = path_cells[-1]
                # 也攻击路径周围的格子
                for (pr, pc) in list(path_cells):
                    for sdr, sdc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = pr + sdr, pc + sdc
                        if self.in_bounds(nr, nc) and (nr, nc) != (r, c):
                            if (nr, nc) not in cells:
                                cells.append((nr, nc))

        elif skill.range_type == "four_way":
            # 四向：上下左右各1格
            for dir_key in ["up", "down", "left", "right"]:
                dr, dc = DIRECTIONS[dir_key]
                nr, nc = r + dr, c + dc
                if self.in_bounds(nr, nc):
                    cells.append((nr, nc))

        elif skill.range_type == "multi_dash":
            # 多向无规则突进：8方向各1~2格
            for dir_key, (dr, dc) in DIRECTIONS.items():
                for k in range(1, 3):
                    nr, nc = r + dr * k, c + dc * k
                    if not self.in_bounds(nr, nc):
                        break
                    if self.map_grid[nr][nc] == 1:
                        if "DB" in skill.effects:
                            self.map_grid[nr][nc] = 0  # 破坏障碍
                            cells.append((nr, nc))
                        break
                    cells.append((nr, nc))

        return cells, new_pos

    def execute_action(self, player_id: int, action: dict) -> dict:
        """
        执行单个玩家的行动（在回合结算时调用）
        返回执行结果
        """
        p = self.players[player_id]
        result = {
            "player_id": player_id,
            "action": action,
            "moved_to": None,
            "attack_cells": [],
            "damage_dealt": 0.0,
            "effects_applied": [],
            "obstacles_destroyed": [],
            "attack_cancelled": False,
            "move_cancelled": False,
        }

        if p.stunned:
            # 晕眩中，无法行动
            result["effects_applied"].append("stunned_skip")
            return result

        action_type = action.get("action")

        if action_type == "move":
            # 纯移动
            direction = action.get("direction")
            if direction and direction in DIRECTIONS:
                r, c = p.position
                dr, dc = DIRECTIONS[direction]
                nr, nc = r + dr, c + dc
                if self.is_passable(nr, nc):
                    result["moved_to"] = (nr, nc)

        elif action_type == "skill":
            skill_index = action.get("skill_index", 0)
            direction = action.get("direction")
            if 0 <= skill_index < len(p.selected_skills):
                skill = p.selected_skills[skill_index]
                cells, new_pos = self.get_skill_coverage(skill, player_id, direction)

                # 如果技能有AS效果，记录新位置
                if "AS" in skill.effects and new_pos:
                    result["moved_to"] = new_pos

                # 如果技能有AD效果，记录攻击格子
                if "AD" in skill.effects:
                    result["attack_cells"] = cells

                # 如果是纯伤害技能（没有AD但有伤害），也记录攻击格子
                if "AD" not in skill.effects and skill.damage > 0:
                    result["attack_cells"] = cells

                result["skill_name"] = skill.name
                result["skill_damage"] = skill.damage
                result["skill_effects"] = skill.effects
                result["coverage_cells"] = cells

        return result

    def get_enemy_position_after_displacement(self, enemy_id: int,
                                               enemy_result: dict) -> Tuple[int, int]:
        """获取对手位移后的位置"""
        if enemy_result.get("moved_to"):
            return enemy_result["moved_to"]
        return self.players[enemy_id].position

    def player_at_cell(self, cells: List[Tuple[int, int]], pos: Tuple[int, int]) -> bool:
        """检查某个位置是否在格子列表中"""
        return pos in cells

    def resolve_turn(self, actions: Dict[int, dict]) -> Dict:
        """
        结算完整回合
        顺序：位移 → 攻击/伤害 → 控制效果 → 死亡检查
        """
        self.turn += 1
        turn_log = []
        results = {}

        # ===== Step 0: 执行双方行动（预计算） =====
        for pid in [0, 1]:
            if pid in actions:
                results[pid] = self.execute_action(pid, actions[pid])
            else:
                results[pid] = {
                    "player_id": pid,
                    "action": None,
                    "moved_to": None,
                    "attack_cells": [],
                    "damage_dealt": 0.0,
                    "effects_applied": [],
                    "attack_cancelled": False,
                    "move_cancelled": False,
                }

            # 晕眩处理
            if self.players[pid].stunned:
                results[pid]["attack_cancelled"] = True
                results[pid]["move_cancelled"] = True
                results[pid]["effects_applied"].append("stunned")
                turn_log.append(f"⚡ {self.players[pid].name} 处于晕眩状态，无法行动！")

        # ===== 检查 CAM 效果（取消攻击+移动） =====
        # 双方同时检查：如果玩家A在玩家B的CAM范围内，A的攻击和移动被取消
        for pid in [0, 1]:
            other_pid = 1 - pid
            other_result = results[other_pid]
            other_effects = other_result.get("skill_effects", [])

            if "CAM" in other_effects:
                # 获取对手技能覆盖范围
                enemy_coverage = other_result.get("coverage_cells", [])
                my_pos = self.players[pid].position

                if self.player_at_cell(enemy_coverage, my_pos):
                    if "ND" not in results[pid].get("skill_effects", []):
                        results[pid]["attack_cancelled"] = True
                        results[pid]["move_cancelled"] = True
                        skill_name = other_result.get("skill_name", "技能")
                        turn_log.append(f"🛡️ {self.players[pid].name} 受到 {skill_name} 的CAM效果，攻击和移动被取消！")

        # ===== Step A: 结算位移 =====
        for pid in [0, 1]:
            p = self.players[pid]
            r = results[pid]

            if r.get("move_cancelled"):
                continue  # 移动被取消

            if r.get("moved_to"):
                new_r, new_c = r["moved_to"]
                # 检查目标是否合法
                if self.is_passable(new_r, new_c) or (new_r, new_c) == p.position:
                    old_pos = p.position
                    p.position = (new_r, new_c)

                    # 检查技能是否破坏障碍
                    skill_effects = r.get("skill_effects", [])
                    if "DB" in skill_effects:
                        for cell in r.get("coverage_cells", []):
                            cr, cc = cell
                            if self.in_bounds(cr, cc) and self.map_grid[cr][cc] == 1:
                                self.map_grid[cr][cc] = 0
                                r.setdefault("obstacles_destroyed", []).append(cell)
                                turn_log.append(f"💥 障碍物在 ({cr},{cc}) 被破坏！")

                    direction_name = ""
                    action = actions.get(pid, {})
                    if action.get("action") == "move":
                        direction_name = DIRECTION_NAMES.get(action.get("direction", ""), "")
                    if direction_name:
                        turn_log.append(f"🚶 {p.name} 向{direction_name}移动到 ({new_r},{new_c})")
                    else:
                        turn_log.append(f"💨 {p.name} 使用位移技能到达 ({new_r},{new_c})")

        # ===== Step B: 结算攻击/伤害 =====
        for pid in [0, 1]:
            p = self.players[pid]
            r = results[pid]
            other_pid = 1 - pid
            other_p = self.players[other_pid]

            if r.get("attack_cancelled"):
                skill_name = r.get("skill_name", "")
                if skill_name:
                    turn_log.append(f"❌ {p.name} 的 {skill_name} 被取消！")
                continue

            attack_cells = r.get("attack_cells", [])
            if not attack_cells:
                continue

            # 检查对方是否在攻击范围内
            enemy_hit = self.player_at_cell(attack_cells, other_p.position)
            if not enemy_hit:
                # 检查是否有环境伤害（如障碍物被破坏后的溅射）
                # 简化：只检查直接命中
                skill_name = r.get("skill_name", "攻击")
                turn_log.append(f"💨 {p.name} 的 {skill_name} 未命中！")
                continue

            # 对方在攻击范围内
            skill_name = r.get("skill_name", "攻击")
            skill_damage = r.get("skill_damage", 1.0)

            if p.character and p.character.faction == "human":
                # 人方攻击鬼方 → 触发猜拳
                self.pending_rps = True
                self.rps_player_id = pid
                self.rps_skill_name = skill_name
                self._rps_damage_pending = skill_damage  # 暂存伤害值
                turn_log.append(f"⚔️ {p.name} 的 {skill_name} 命中！等待猜拳判定...")
            else:
                # 鬼方攻击人方 → 直接造成伤害
                actual_damage = self._calculate_demon_damage(skill_damage)
                other_p.hp -= actual_damage
                r["damage_dealt"] = actual_damage
                turn_log.append(f"💥 {p.name} 的 {skill_name} 造成 {actual_damage} 点伤害！")

        # ===== Step C: 结算控制效果 =====
        for pid in [0, 1]:
            r = results[pid]
            other_pid = 1 - pid
            other_p = self.players[other_pid]

            if r.get("attack_cancelled"):
                continue

            skill_effects = r.get("skill_effects", [])
            attack_cells = r.get("attack_cells", [])

            # FD1 晕眩效果
            if "FD1" in skill_effects:
                if self.player_at_cell(attack_cells, other_p.position):
                    other_p.stunned = True
                    r["effects_applied"].append("FD1")
                    skill_name = r.get("skill_name", "技能")
                    turn_log.append(f"💫 {other_p.name} 被 {skill_name} 晕眩，下回合无法行动！")

        # ===== 检查死亡 =====
        for pid in [0, 1]:
            p = self.players[pid]
            if p.hp <= 0:
                other_pid = 1 - pid
                self.game_over = True
                self.winner = other_pid
                turn_log.append(f"💀 {p.name} 被击败！")
                turn_log.append(f"🏆 {self.players[other_pid].name} 获胜！")

        # 双方同时死亡 → 平局
        if self.players[0].hp <= 0 and self.players[1].hp <= 0:
            self.winner = None  # 平局

        self.log.extend(turn_log)

        # 记录本回合到战斗历史
        turn_record = {
            "turn": self.turn,
            "players": [],
        }
        for pid in [0, 1]:
            p = self.players[pid]
            r = results.get(pid, {})
            turn_record["players"].append({
                "player_id": pid,
                "name": p.name,
                "action": actions.get(pid, {}).get("action", "pass"),
                "skill_name": r.get("skill_name", ""),
                "position": list(p.position),
                "hp": p.hp,
                "damage_dealt": r.get("damage_dealt", 0),
                "stunned": p.stunned,
                "attack_cancelled": r.get("attack_cancelled", False),
                "move_cancelled": r.get("move_cancelled", False),
            })
        turn_record["log"] = turn_log
        self.battle_history.append(turn_record)

        return {
            "turn": self.turn,
            "results": results,
            "log": turn_log,
            "game_over": self.game_over,
            "winner": self.winner,
            "pending_rps": self.pending_rps,
            "rps_player_id": self.rps_player_id if self.pending_rps else None,
            "rps_skill_name": self.rps_skill_name if self.pending_rps else None,
        }

    def resolve_rps(self, player_id: int, choice: str) -> Dict:
        """
        结算猜拳
        choice: "rock", "scissors", "paper"
        """
        if not self.pending_rps or player_id != self.rps_player_id:
            return {"error": "当前没有待处理的猜拳"}

        # 鬼方随机防御
        demon_choice = random.choice(["rock", "scissors", "paper"])
        human_choice = choice

        # 判定胜负
        # 石头赢剪刀，剪刀赢布，布赢石头
        win_map = {"rock": "scissors", "scissors": "paper", "paper": "rock"}

        if win_map[human_choice] == demon_choice:
            result = "win"
        elif human_choice == demon_choice:
            result = "draw"
        else:
            result = "lose"

        damage = self._rps_damage_pending if result == "win" else 0
        demon_pid = 1 - player_id

        if damage > 0:
            self.players[demon_pid].hp -= damage
            self.log.append(
                f"✊ {self.players[player_id].name} 猜拳 {human_choice} vs {demon_choice} —— 胜利！造成 {damage} 点伤害！"
            )
        elif result == "draw":
            # 平局：不清除 pending_rps，再来一次
            self.log.append(
                f"✊ {self.players[player_id].name} 猜拳 {human_choice} vs {demon_choice} —— 平局！再来一次！"
            )
            return {
                "result": "draw",
                "human_choice": human_choice,
                "demon_choice": demon_choice,
                "damage": 0,
                "game_over": False,
                "retry": True,
            }
        else:
            self.log.append(
                f"✊ {self.players[player_id].name} 猜拳 {human_choice} vs {demon_choice} —— 失败，无伤害！"
            )

        # 检查鬼方是否死亡
        if self.players[demon_pid].hp <= 0:
            self.game_over = True
            self.winner = player_id
            self.log.append(f"💀 {self.players[demon_pid].name} 被击败！")
            self.log.append(f"🏆 {self.players[player_id].name} 获胜！")

        self.pending_rps = False
        self.rps_player_id = 0

        return {
            "result": result,
            "human_choice": human_choice,
            "demon_choice": demon_choice,
            "damage": damage,
            "game_over": self.game_over,
            "winner": self.winner,
        }

    def _calculate_demon_damage(self, base_damage: float) -> float:
        """计算鬼方实际伤害（浮动）"""
        if base_damage == 1.5:
            return float(random.randint(1, 2))
        elif base_damage == 0.5:
            return 0.5
        else:
            return base_damage

    def end_turn_cleanup(self):
        """回合结束清理：解除晕眩等"""
        for p in self.players:
            p.stunned = False
            p.last_action = None

    def get_state_for_player(self, player_id: int) -> dict:
        """获取某个玩家视角的游戏状态"""
        p = self.players[player_id]
        other = self.players[1 - player_id]

        return {
            "turn": self.turn,
            "map": self.map_grid,
            "your_hp": p.hp,
            "your_max_hp": p.max_hp,
            "enemy_hp": other.hp,
            "enemy_max_hp": other.max_hp,
            "your_pos": list(p.position),
            "enemy_pos": list(other.position),
            "your_skills": [
                {"name": s.name, "range_type": s.range_type, "damage": s.damage,
                 "effects": s.effects, "description": s.description}
                for s in p.selected_skills
            ],
            "your_character": {
                "name": p.character.name if p.character else "",
                "faction": p.character.faction if p.character else "",
                "emoji": p.character.emoji if p.character else "",
            } if p.character else None,
            "enemy_character": {
                "name": other.character.name if other.character else "",
                "faction": other.character.faction if other.character else "",
                "emoji": other.character.emoji if other.character else "",
            } if other.character else None,
            "your_stunned": p.stunned,
            "enemy_stunned": other.stunned,
            "game_over": self.game_over,
            "winner": self.winner,
            "pending_rps": self.pending_rps and self.rps_player_id == player_id,
            "battle_history": self.battle_history if self.game_over else [],
            "movable_cells": self.get_movable_cells(player_id),
        }

    def get_movable_cells_with_direction(self, player_id: int) -> dict:
        """返回可移动格子和方向映射"""
        p = self.players[player_id]
        r, c = p.position
        cells_map = {}
        for direction, (dr, dc) in DIRECTIONS.items():
            nr, nc = r + dr, c + dc
            if self.is_passable(nr, nc):
                cells_map[direction] = (nr, nc)
        return cells_map


class GameRoom:
    """游戏房间，管理两个玩家的连接和消息"""

    def __init__(self, room_code: str):
        self.room_code = room_code
        self.state = GameState()
        self.ready_count = 0          # 已确认技能选择的玩家数
        self.turn_actions: Dict[int, dict] = {}  # 当前回合的行动缓存
        self.created_at = time.time()
        self.last_activity = time.time()
        self.empty_since: float = None  # 房间变空的时间（所有玩家离开时记录）
        self.host_player_id: str = ""   # 房主的玩家ID
        self.offline_mode: bool = False  # 是否为离线模式
        self.side_rps_choices: Dict[int, str] = {}  # 选边猜拳 {player_id: choice}
        self.side_rps_winner: int = None  # 猜拳胜者
        self.side_selected: bool = False  # 胜者是否已选边

    def is_expired(self) -> bool:
        """检查房间是否过期（15分钟无活动，或空房间超过10分钟）"""
        now = time.time()
        if self.empty_since is not None:
            return now - self.empty_since > 600  # 空房间保留10分钟
        return now - self.last_activity > 900

    def all_disconnected(self) -> bool:
        """所有玩家是否都断开了"""
        return all(not p.connected for p in self.state.players)

    async def handle_message(self, player_id: int, data: dict) -> dict:
        """处理玩家消息，返回响应"""
        self.last_activity = time.time()
        msg_type = data.get("type")

        if msg_type == "select_skills":
            # 选择技能
            skill_indices = data.get("skill_indices", [])
            p = self.state.players[player_id]

            if p.character is None:
                return {"type": "error", "message": "角色未设定"}

            if player_id == 0:
                # 人方从6个技能选3个
                if len(skill_indices) != 3:
                    return {"type": "error", "message": "请选择3个技能"}
                p.selected_skills = [p.character.skills[i] for i in skill_indices if 0 <= i < len(p.character.skills)]
                if len(p.selected_skills) != 3:
                    return {"type": "error", "message": "技能选择无效"}
            else:
                # 鬼方自动获得全部3个技能
                p.selected_skills = list(p.character.skills)

            p.hp = p.max_hp
            p.position = (0, 0) if player_id == 0 else (5, 11)
            self.ready_count += 1

            return {"type": "skills_confirmed", "message": "技能已确认"}

        elif msg_type == "select_action":
            # 提交回合行动
            p = self.state.players[player_id]

            if p.stunned:
                # 晕眩中，自动跳过
                self.turn_actions[player_id] = {"action": "pass"}
                return {"type": "action_confirmed", "message": "你处于晕眩状态，本回合跳过"}

            action_type = data.get("action")
            if action_type not in ("move", "skill"):
                return {"type": "error", "message": "无效的行动类型"}

            if action_type == "move":
                direction = data.get("direction")
                if direction not in DIRECTIONS:
                    return {"type": "error", "message": "无效的方向"}
                self.turn_actions[player_id] = {"action": "move", "direction": direction}

            elif action_type == "skill":
                skill_index = data.get("skill_index", 0)
                if not (0 <= skill_index < len(p.selected_skills)):
                    return {"type": "error", "message": "无效的技能索引"}

                skill = p.selected_skills[skill_index]
                # 自光环和四向、多向技能不需要方向
                direction_needed = skill.range_type in ("line", "square_3x3", "dash_surround")
                if direction_needed:
                    direction = data.get("direction")
                    if direction not in DIRECTIONS:
                        return {"type": "error", "message": "此技能需要选择方向"}
                else:
                    direction = None

                self.turn_actions[player_id] = {
                    "action": "skill",
                    "skill_index": skill_index,
                    "direction": direction,
                }

            return {"type": "action_confirmed", "message": "行动已确认，等待对手..."}

        elif msg_type == "rps_choice":
            # 猜拳选择
            choice = data.get("choice")
            if choice not in ("rock", "scissors", "paper"):
                return {"type": "error", "message": "无效的猜拳选择"}
            return self.state.resolve_rps(player_id, choice)

        return {"type": "error", "message": f"未知消息类型: {msg_type}"}

    def all_actions_received(self) -> bool:
        """是否双方都提交了行动"""
        # 晕眩的玩家自动视为已提交
        for pid in [0, 1]:
            if self.state.players[pid].stunned and pid not in self.turn_actions:
                self.turn_actions[pid] = {"action": "pass"}
        return len(self.turn_actions) >= 2

    def process_turn(self) -> dict:
        """结算当前回合"""
        result = self.state.resolve_turn(self.turn_actions)
        self.state.end_turn_cleanup()
        self.turn_actions = {}
        return result

    def all_ready(self) -> bool:
        """是否双方都确认了技能选择"""
        return self.ready_count >= 2

    def setup_characters(self):
        """分配角色：玩家0=人方(炭治郎)，玩家1=鬼方(猗窝座)"""
        self.state.players[0].character = CHARACTER_TANJIRO
        self.state.players[0].max_hp = CHARACTER_TANJIRO.max_hp
        self.state.players[1].character = CHARACTER_AKAZA
        self.state.players[1].max_hp = CHARACTER_AKAZA.max_hp

    def is_player_connected(self, player_id: int) -> bool:
        return self.state.players[player_id].connected

    def set_player_disconnected(self, player_id: int):
        self.state.players[player_id].connected = False
        # 如果所有玩家都断开了，记录时间，保留房间10分钟
        if self.all_disconnected() and self.empty_since is None:
            self.empty_since = time.time()
            print(f"房间 {self.room_code} 所有玩家离开，将保留10分钟")

    def set_player_connected(self, player_id: int):
        self.state.players[player_id].connected = True
        self.empty_since = None  # 有人回来了，重置计时
