"""
角色和技能数据定义
包含 MVP 两个角色：灶门炭治郎（人方）和猗窝座（鬼方）
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Skill:
    """技能数据类"""
    name: str               # 技能名称
    range_type: str         # 范围类型: line / self_aura / square_3x3 / dash_surround / four_way / multi_dash
    damage: float           # 伤害值（0.5=持续, 1.0=常规, 1.5=浮动, 2.0=高额）
    effects: List[str]      # 效果代号列表: AD, AS, DB, CAM, ND, WL, FD1, CA, CM
    description: str        # 技能描述
    cooldown: int = 0       # 冷却回合数（0=无冷却）


@dataclass
class Character:
    """角色数据类"""
    name: str               # 角色名称
    title: str              # 称号
    faction: str            # 阵营: "human" 或 "demon"
    max_hp: int             # 最大血量
    skills: List[Skill]     # 技能池
    description: str        # 角色描述
    emoji: str = "⚔️"       # 角色图标


# ========== 灶门炭治郎 技能池（6招） ==========

TANJIRO_SKILLS = [
    Skill(
        name="一之型·水面斩",
        range_type="line",
        damage=1.0,
        effects=["AD"],
        description="直线斩击，对路径上敌人造成伤害"
    ),
    Skill(
        name="三之型·流流舞",
        range_type="dash_surround",
        damage=1.0,
        effects=["AS", "WL"],
        description="位移环绕攻击，遇障碍停止"
    ),
    Skill(
        name="四之型·击打潮",
        range_type="line",
        damage=1.0,
        effects=["AD", "FD1"],
        description="直线多段击打，命中使敌人晕眩1回合"
    ),
    Skill(
        name="六之型·扭转漩涡",
        range_type="four_way",
        damage=1.0,
        effects=["CAM", "DB", "AS"],
        description="四向旋转斩击，取消敌人攻击移动，破坏障碍"
    ),
    Skill(
        name="八之型·浪飞沫·乱踏",
        range_type="dash_surround",
        damage=1.0,
        effects=["CAM", "AS", "ND"],
        description="4向位移斩击，不可抵消，取消敌人攻击移动"
    ),
    Skill(
        name="九之型·破绽之线",
        range_type="line",
        damage=1.0,
        effects=["CAM"],
        description="直线锁定弱点，取消敌人攻击移动"
    ),
]


# ========== 猗窝座 技能池（3招） ==========

AKAZA_SKILLS = [
    Skill(
        name="破坏杀·光式",
        range_type="self_aura",
        damage=0.5,
        effects=["ND"],
        description="自身全域持续伤害光环，不可抵消"
    ),
    Skill(
        name="破坏杀·乱式",
        range_type="multi_dash",
        damage=1.5,
        effects=["DB"],
        description="多向无规则突进，破坏障碍物"
    ),
    Skill(
        name="破坏杀·灭式",
        range_type="square_3x3",
        damage=2.0,
        effects=["DB"],
        description="近距离3×3正方形高额冲击，破坏障碍"
    ),
]


# ========== 预定义角色 ==========

CHARACTER_TANJIRO = Character(
    name="灶门炭治郎",
    title="鬼杀队剑士",
    faction="human",
    max_hp=4,
    skills=TANJIRO_SKILLS,
    description="使用水之呼吸的鬼杀队少年，以灵活的剑技斩杀恶鬼。攻击鬼时需要猜拳判定。",
    emoji="⚔️"
)

CHARACTER_AKAZA = Character(
    name="猗窝座",
    title="上弦之叁",
    faction="demon",
    max_hp=4,
    skills=AKAZA_SKILLS,
    description="十二鬼月上弦之叁，以压倒性的破坏力著称。攻击直接造成伤害。",
    emoji="👹"
)


def get_character_by_name(name: str) -> Character:
    """根据名称获取角色"""
    name_lower = name.lower()
    if "tanjiro" in name_lower or "炭治郎" in name_lower:
        return CHARACTER_TANJIRO
    elif "akaza" in name_lower or "猗窝座" in name_lower or "猗窩座" in name_lower:
        return CHARACTER_AKAZA
    return None


# 9个移动方向 (dr, dc)，含原地不动
DIRECTIONS = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
    "ul": (-1, -1),
    "ur": (-1, 1),
    "dl": (1, -1),
    "dr": (1, 1),
    "stay": (0, 0),
}

# 方向对应的显示名称
DIRECTION_NAMES = {
    "up": "上",
    "down": "下",
    "left": "左",
    "right": "右",
    "ul": "左上",
    "ur": "右上",
    "dl": "左下",
    "dr": "右下",
}
