"""
FastAPI 服务器 + WebSocket 端点
管理游戏房间、WebSocket 通信、静态文件服务
"""

import json
import asyncio
import sys
import io
import time
import random
import httpx
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from game_engine import GameRoom, generate_room_code

# 修复 Windows GBK 编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    asyncio.create_task(cleanup_rooms())
    print("极限格斗 PVP 鬼灭之刀 服务器已启动！")
    print("访问 http://localhost:8000 开始游戏")
    yield
    # 关闭
    pass


app = FastAPI(title="极限格斗 PVP 鬼灭之刀", lifespan=lifespan)

# 静态文件和模板
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 直接使用 jinja2.Environment 避免 Starlette 版本兼容问题
from jinja2 import Environment, FileSystemLoader
jinja_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), auto_reload=True)

# 房间管理
rooms: dict[str, GameRoom] = {}


def render_template(name: str) -> HTMLResponse:
    """渲染模板并返回 HTMLResponse"""
    template = jinja_env.get_template(name)
    html = template.render()
    return HTMLResponse(content=html)


@app.get("/", response_class=HTMLResponse)
async def index():
    """主页：创建/加入房间"""
    return render_template("index.html")


@app.get("/game", response_class=HTMLResponse)
async def game_page():
    """游戏页面"""
    return render_template("game.html")


async def _process_and_broadcast_turn(room):
    """处理回合并广播结果"""
    turn_result = room.process_turn()

    for pidx in [0, 1]:
        p = room.state.players[pidx]
        if p.ws:
            try:
                st = room.state.get_state_for_player(pidx)
                st["type"] = "turn_result"
                st["for_player"] = pidx
                st["turn_log"] = turn_result["log"]
                st["pending_rps"] = room.state.pending_rps and room.state.rps_player_id == pidx
                if st["pending_rps"]:
                    st["rps_skill_name"] = room.state.rps_skill_name
                await p.ws.send_text(json.dumps(st, ensure_ascii=False))
            except Exception:
                pass

    if room.state.game_over:
        for pidx in [0, 1]:
            p = room.state.players[pidx]
            if p.ws:
                try:
                    await p.ws.send_text(json.dumps({
                        "type": "game_over",
                        "winner": room.state.winner,
                        "winner_name": room.state.players[room.state.winner].name if room.state.winner is not None else "",
                        "message": f"{room.state.players[room.state.winner].name} 获胜！" if room.state.winner is not None else "平局！",
                        "battle_history": room.state.battle_history,
                    }, ensure_ascii=False))
                except Exception:
                    pass


# ====== AI 向导代理 ======
GUIDE_API_KEY = os.environ.get("GUIDE_API_KEY", "")
GUIDE_API_URL = os.environ.get("GUIDE_API_URL", "https://api.deepseek.com/v1/chat/completions")
GUIDE_MODEL = os.environ.get("GUIDE_MODEL", "deepseek-chat")


@app.post("/api/guide")
async def guide_proxy(request: Request):
    """代理 AI 请求，API Key 存在服务端"""
    if not GUIDE_API_KEY:
        return {"error": "服务器未配置 GUIDE_API_KEY"}

    body = await request.json()
    messages = body.get("messages", [])

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                GUIDE_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {GUIDE_API_KEY}",
                },
                json={
                    "model": GUIDE_MODEL,
                    "messages": messages,
                    "max_tokens": 250,
                    "temperature": 0.7,
                },
            )
            data = resp.json()
            if resp.status_code != 200:
                return {"error": f"API错误({resp.status_code}): {data.get('error', {}).get('message', '未知')}"}
            return {"reply": data.get("choices", [{}])[0].get("message", {}).get("content", "")}
    except Exception as e:
        return {"error": f"请求失败: {str(e)}"}


@app.get("/api/rooms")
async def list_rooms():
    """返回所有活跃房间列表（空房间保留10分钟）"""
    result = []
    for code, room in rooms.items():
        if room.state.game_over:
            continue
        if room.is_expired():
            continue
        connected = sum(1 for p in room.state.players if p.connected)
        max_players = len(room.state.players)
        in_game = room.ready_count >= 2

        result.append({
            "room_code": code,
            "host_name": room.state.players[0].name,
            "host_player_id": room.host_player_id,
            "players": connected,
            "max_players": max_players,
            "in_game": in_game,
            "created_seconds_ago": int(time.time() - room.created_at),
            "empty_seconds": int(time.time() - room.empty_since) if room.empty_since else 0,
        })
    return {"rooms": result}


@app.websocket("/ws/{room_code}/{player_id}")
async def websocket_endpoint(ws: WebSocket, room_code: str, player_id: str):
    """WebSocket 连接端点"""
    await ws.accept()

    # 转换 player_id
    pid = int(player_id) if player_id.isdigit() else 0

    # 如果是已知房间，更新 WebSocket 引用；只在重连时标记 connected
    room = rooms.get(room_code)
    if room and pid in (0, 1):
        room.state.players[pid].ws = ws
        # 只有已注册过的玩家才自动标记为连接（重连场景）
        if room.state.players[pid].name:
            room.state.players[pid].connected = True
            print(f"玩家 {pid} 重新连接到房间 {room_code}")

    try:
        while True:
            data = await ws.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")

            if msg_type == "create_room":
                # 生成唯一房间码
                new_code = generate_room_code()
                while new_code in rooms:
                    new_code = generate_room_code()

                room = GameRoom(new_code)
                rooms[new_code] = room
                room.setup_characters()
                room.state.players[0].name = message.get("player_name", "玩家1")
                room.state.players[0].ws = ws
                room.state.players[0].connected = True
                room.host_player_id = message.get("player_id", "")  # 记录房主ID

                await ws.send_text(json.dumps({
                    "type": "room_created",
                    "room_code": new_code,
                    "player_id": 0,
                    "character": {
                        "name": room.state.players[0].character.name,
                        "title": room.state.players[0].character.title,
                        "faction": room.state.players[0].character.faction,
                        "emoji": room.state.players[0].character.emoji,
                        "max_hp": room.state.players[0].character.max_hp,
                        "skills": [
                            {"index": i, "name": s.name, "range_type": s.range_type,
                             "damage": s.damage, "effects": s.effects,
                             "description": s.description}
                            for i, s in enumerate(room.state.players[0].character.skills)
                        ]
                    }
                }, ensure_ascii=False))

            elif msg_type == "create_single_player":
                # 线下热座模式：玩家操控双方
                new_code = generate_room_code()
                while new_code in rooms:
                    new_code = generate_room_code()

                room = GameRoom(new_code)
                rooms[new_code] = room
                room.setup_characters()
                room.state.players[0].name = message.get("player_name", "玩家")
                room.state.players[0].ws = ws
                room.state.players[0].connected = True
                # 玩家1也是同一个玩家
                room.state.players[1].name = message.get("player_name", "玩家") + "(鬼方)"
                room.state.players[1].ws = ws
                room.state.players[1].connected = True
                room.host_player_id = message.get("player_id", "")
                room.offline_mode = True

                # 确认鬼方技能
                try:
                    result = await room.handle_message(1, {"type": "select_skills", "skill_indices": [0, 1, 2]})
                    print(f"[DEBUG] create_single_player 鬼方技能确认: {result}, ready_count={room.ready_count}")
                except Exception as e:
                    print(f"离线鬼方技能确认失败: {e}")

                await ws.send_text(json.dumps({
                    "type": "room_created",
                    "room_code": new_code,
                    "player_id": 0,
                    "single_player": True,
                    "offline": True,
                    "character": {
                        "name": room.state.players[0].character.name,
                        "title": room.state.players[0].character.title,
                        "faction": room.state.players[0].character.faction,
                        "emoji": room.state.players[0].character.emoji,
                        "max_hp": room.state.players[0].character.max_hp,
                        "skills": [
                            {"index": i, "name": s.name, "range_type": s.range_type,
                             "damage": s.damage, "effects": s.effects,
                             "description": s.description}
                            for i, s in enumerate(room.state.players[0].character.skills)
                        ]
                    }
                }, ensure_ascii=False))

            elif msg_type == "join_room":
                join_code = message.get("room_code", "").strip().upper()
                room = rooms.get(join_code)

                if room is None:
                    await ws.send_text(json.dumps({
                        "type": "error", "message": "房间不存在或已过期"
                    }, ensure_ascii=False))
                    continue

                if room.state.players[1].connected:
                    await ws.send_text(json.dumps({
                        "type": "error", "message": "房间已满"
                    }, ensure_ascii=False))
                    continue

                # 禁止加入自己的房间
                joiner_id = message.get("player_id", "")
                if joiner_id and room.host_player_id and joiner_id == room.host_player_id:
                    await ws.send_text(json.dumps({
                        "type": "error", "message": "不能加入自己创建的房间！请换一个浏览器或无痕模式"
                    }, ensure_ascii=False))
                    continue

                room.state.players[1].name = message.get("player_name", "玩家2")
                room.state.players[1].ws = ws
                room.state.players[1].connected = True

                # 通知加入者
                await ws.send_text(json.dumps({
                    "type": "room_joined",
                    "room_code": join_code,
                    "player_id": 1,
                    "character": {
                        "name": room.state.players[1].character.name,
                        "title": room.state.players[1].character.title,
                        "faction": room.state.players[1].character.faction,
                        "emoji": room.state.players[1].character.emoji,
                        "max_hp": room.state.players[1].character.max_hp,
                        "skills": [
                            {"index": i, "name": s.name, "range_type": s.range_type,
                             "damage": s.damage, "effects": s.effects,
                             "description": s.description}
                            for i, s in enumerate(room.state.players[1].character.skills)
                        ]
                    }
                }, ensure_ascii=False))

                # 通知房主：对手已加入 → 开始选边猜拳
                room.side_rps_choices = {}
                room.side_rps_winner = None
                room.side_selected = False
                for pidx in [0, 1]:
                    p = room.state.players[pidx]
                    if p.ws:
                        try:
                            await p.ws.send_text(json.dumps({
                                "type": "side_rps_start",
                                "message": "猜拳决定谁选阵营！石头剪刀布！",
                                "opponent_name": room.state.players[1 - pidx].name,
                            }, ensure_ascii=False))
                        except Exception:
                            pass

            elif msg_type == "side_rps_choice":
                # 选边猜拳
                if room is None:
                    await ws.send_text(json.dumps({"type": "error", "message": "未加入房间"}, ensure_ascii=False))
                    continue
                choice = message.get("choice", "")
                if choice not in ("rock", "scissors", "paper"):
                    continue
                room.side_rps_choices[pid] = choice

                if len(room.side_rps_choices) >= 2:
                    c0 = room.side_rps_choices.get(0, "")
                    c1 = room.side_rps_choices.get(1, "")
                    win_map = {"rock": "scissors", "scissors": "paper", "paper": "rock"}

                    if c0 == c1:
                        # 平局重来
                        room.side_rps_choices = {}
                        for pidx in [0, 1]:
                            p = room.state.players[pidx]
                            if p.ws:
                                try:
                                    await p.ws.send_text(json.dumps({
                                        "type": "side_rps_retry",
                                        "c0": c0, "c1": c1,
                                        "message": f"双方都出了{c0}，平局！再来！",
                                    }, ensure_ascii=False))
                                except Exception:
                                    pass
                    else:
                        winner = 0 if win_map[c0] == c1 else 1
                        room.side_rps_winner = winner
                        loser = 1 - winner
                        for pidx in [0, 1]:
                            p = room.state.players[pidx]
                            if p.ws:
                                try:
                                    await p.ws.send_text(json.dumps({
                                        "type": "side_rps_result",
                                        "winner": winner,
                                        "winner_name": room.state.players[winner].name,
                                        "c0": c0, "c1": c1,
                                        "message": f"{room.state.players[winner].name} 猜拳获胜！请选择阵营",
                                    }, ensure_ascii=False))
                                except Exception:
                                    pass
                else:
                    # 等待另一位玩家
                    await ws.send_text(json.dumps({"type": "side_rps_waiting"}, ensure_ascii=False))

            elif msg_type == "side_select":
                # 胜者选择阵营 - 交换角色对象（不交换玩家ws）
                if room is None or room.side_rps_winner is None:
                    await ws.send_text(json.dumps({"type": "error", "message": "无权选边"}, ensure_ascii=False))
                    continue
                if pid != room.side_rps_winner:
                    await ws.send_text(json.dumps({"type": "error", "message": "不是猜拳胜者"}, ensure_ascii=False))
                    continue

                pick = message.get("pick", "human")
                if pick not in ("human", "demon"):
                    continue

                winner_pid = room.side_rps_winner
                loser_pid = 1 - winner_pid

                # 人方=pid0的角色，鬼方=pid1的角色
                # 如果胜者选的和当前分配的相反，交换两个slot的角色对象
                if (pick == "human" and winner_pid != 0) or (pick == "demon" and winner_pid != 1):
                    p0 = room.state.players[0]
                    p1 = room.state.players[1]
                    # 交换角色
                    p0.character, p1.character = p1.character, p0.character
                    p0.max_hp, p1.max_hp = p1.max_hp, p0.max_hp
                    p0.position, p1.position = p1.position, p0.position
                    # 交换名字
                    p0.name, p1.name = p1.name, p0.name
                    # 交换ws（让ws跟随角色，这样pid=0的ws始终操控人方）
                    p0.ws, p1.ws = p1.ws, p0.ws
                    print(f"[选边] {p0.name}(pid0)={p0.character.name} | {p1.name}(pid1)={p1.character.name}")

                room.side_selected = True

                # 通知双方开始选技能
                for pidx in [0, 1]:
                    p = room.state.players[pidx]
                    if p.ws:
                        try:
                            await p.ws.send_text(json.dumps({
                                "type": "side_confirmed",
                                "your_side": p.character.faction,
                                "your_character": {
                                    "name": p.character.name,
                                    "faction": p.character.faction,
                                    "emoji": p.character.emoji,
                                    "skills": [
                                        {"index": i, "name": s.name, "range_type": s.range_type,
                                         "damage": s.damage, "effects": s.effects,
                                         "description": s.description}
                                        for i, s in enumerate(p.character.skills)
                                    ]
                                }
                            }, ensure_ascii=False))
                        except Exception:
                            pass

            elif msg_type == "select_skills":
                if room is None:
                    await ws.send_text(json.dumps({
                        "type": "error", "message": "未加入房间"
                    }, ensure_ascii=False))
                    continue

                # 确定正确的 player_id
                actual_pid = pid
                response = await room.handle_message(actual_pid, message)
                await ws.send_text(json.dumps(response, ensure_ascii=False))

                # 检查双方是否都准备好了（离线模式鬼方在create时已确认）
                print(f"[DEBUG] select_skills ready_count={room.ready_count} all_ready={room.all_ready()} offline={getattr(room, 'offline_mode', False)}")
                if not room.all_ready():
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "message": f"等待对手确认(ready={room.ready_count})"
                    }, ensure_ascii=False))
                if room.all_ready():
                    room.state.generate_map()

                    # 通知双方游戏开始
                    for pidx in [0, 1]:
                        p = room.state.players[pidx]
                        if p.ws:
                            try:
                                st = room.state.get_state_for_player(pidx)
                                st["type"] = "game_start"
                                st["player_id"] = pidx
                                st["for_player"] = pidx
                                st["player_name"] = p.name
                                st["offline"] = getattr(room, 'offline_mode', False)
                                await p.ws.send_text(json.dumps(st, ensure_ascii=False))
                            except Exception:
                                pass

            elif msg_type == "select_action":
                if room is None:
                    await ws.send_text(json.dumps({
                        "type": "error", "message": "未加入房间"
                    }, ensure_ascii=False))
                    continue

                actual_pid = pid
                response = await room.handle_message(actual_pid, message)
                await ws.send_text(json.dumps(response, ensure_ascii=False))

                # 检查双方是否都提交了行动
                if room.all_actions_received():
                    await _process_and_broadcast_turn(room)

            elif msg_type == "offline_turn":
                # 线下模式：同时提交双方行动
                if room is None:
                    await ws.send_text(json.dumps({"type": "error", "message": "未加入房间"}, ensure_ascii=False))
                    continue

                actions = message.get("actions", {})
                for pid_str, action in actions.items():
                    pid_val = int(pid_str)
                    # 补上 type 字段，handle_message 需要它
                    action["type"] = "select_action"
                    await room.handle_message(pid_val, action)

                if room.all_actions_received():
                    await _process_and_broadcast_turn(room)
                    # pending_rps 已在 _process_and_broadcast_turn 的每条消息中发送，不重复

            elif msg_type == "rps_choice":
                if room is None:
                    await ws.send_text(json.dumps({
                        "type": "error", "message": "未加入房间"
                    }, ensure_ascii=False))
                    continue

                # 猜拳玩家是人方
                human_pid = room.state.rps_player_id
                response = await room.handle_message(human_pid, message)

                # 通知人方猜拳结果
                human_player = room.state.players[human_pid]
                if human_player.ws:
                    try:
                        response["type"] = "rps_result"
                        await human_player.ws.send_text(json.dumps(response, ensure_ascii=False))
                    except Exception:
                        pass

                # 平局：重新发猜拳请求
                if response.get("retry"):
                    if human_player.ws:
                        try:
                            st = room.state.get_state_for_player(human_pid)
                            st["type"] = "turn_result"
                            st["pending_rps"] = True
                            st["rps_skill_name"] = room.state.rps_skill_name
                            st["for_player"] = human_pid
                            await human_player.ws.send_text(json.dumps(st, ensure_ascii=False))
                        except Exception:
                            pass
                elif room.state.game_over:
                    for pidx in [0, 1]:
                        p = room.state.players[pidx]
                        if p.ws:
                            try:
                                await p.ws.send_text(json.dumps({
                                    "type": "game_over",
                                    "winner": room.state.winner,
                                    "winner_name": room.state.players[room.state.winner].name if room.state.winner is not None else "",
                                    "message": f"{room.state.players[room.state.winner].name} 获胜！" if room.state.winner is not None else "平局！",
                                    "battle_history": room.state.battle_history,
                                }, ensure_ascii=False))
                            except Exception:
                                pass
                else:
                    for pidx in [0, 1]:
                        p = room.state.players[pidx]
                        if p.ws:
                            try:
                                st = room.state.get_state_for_player(pidx)
                                st["type"] = "rps_turn_end"
                                st["for_player"] = pidx
                                await p.ws.send_text(json.dumps(st, ensure_ascii=False))
                            except Exception:
                                pass

            elif msg_type == "get_state":
                if room is None:
                    await ws.send_text(json.dumps({
                        "type": "error", "message": "房间不存在"
                    }, ensure_ascii=False))
                    continue

                actual_pid = pid

                st = room.state.get_state_for_player(actual_pid)
                st["type"] = "game_state"
                st["player_id"] = actual_pid
                st["for_player"] = actual_pid
                await ws.send_text(json.dumps(st, ensure_ascii=False))

                # 离线模式：同时发送另一方状态
                if getattr(room, 'offline_mode', False):
                    other_pid = 1 - actual_pid
                    st2 = room.state.get_state_for_player(other_pid)
                    st2["type"] = "game_state"
                    st2["player_id"] = other_pid
                    st2["for_player"] = other_pid
                    await ws.send_text(json.dumps(st2, ensure_ascii=False))

            else:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "message": f"未知消息类型: {msg_type}"
                }, ensure_ascii=False))

    except WebSocketDisconnect:
        if room:
            # 只有断开的是该玩家当前活跃连接时才标记离线
            # 避免 lobby WS 断开时误伤已重连的 game WS
            if room.state.players[pid].ws == ws:
                room.set_player_disconnected(pid)
                other_pid = 1 - pid
                other_p = room.state.players[other_pid]
                if other_p.ws:
                    try:
                        await other_p.ws.send_text(json.dumps({
                            "type": "player_disconnected",
                            "message": "对手已断线，请等待..."
                        }, ensure_ascii=False))
                    except Exception:
                        pass
    except Exception as e:
        print(f"WebSocket 错误: {e}")
        if room and room.state.players[pid].ws == ws:
            room.set_player_disconnected(pid)


# 定期清理过期房间
async def cleanup_rooms():
    """定期清理过期房间"""
    while True:
        await asyncio.sleep(300)  # 每5分钟检查一次
        expired = [code for code, r in rooms.items() if r.is_expired()]
        for code in expired:
            del rooms[code]
        if expired:
            print(f"清理了 {len(expired)} 个过期房间")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
