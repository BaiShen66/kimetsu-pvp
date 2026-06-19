/**
 * 极限格斗 PVP 鬼灭之刀 - 前端游戏逻辑
 */

// ========== 工具函数 ==========
const $ = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);

// ========== 从 URL 获取参数 ==========
const urlParams = new URLSearchParams(window.location.search);
const ROOM_CODE = urlParams.get('room') || '';
const PLAYER_ID = parseInt(urlParams.get('player') || '0');

// ========== 游戏状态 ==========
const state = {
    ws: null,
    map: [],               // 6×12 grid (0=空地, 1=障碍)
    yourPos: [0, 0],
    enemyPos: [5, 11],
    yourHP: 4,
    yourMaxHP: 4,
    enemyHP: 4,
    enemyMaxHP: 4,
    yourSkills: [],
    yourCharacter: null,
    enemyCharacter: null,
    yourStunned: false,
    enemyStunned: false,
    turn: 0,
    selectedAction: null,      // 'move' | 'skill'
    selectedSkillIndex: 0,
    selectedDirection: null,
    highlightedCells: [],       // [{r, c, type}]
    actionConfirmed: false,
    gameOver: false,
    pendingRPS: false,
    rpsTimer: null,
    rpsSeconds: 5,
};

// ========== 重连状态 ==========
let reconnectAttempts = 0;
const MAX_RECONNECT = 10;
const RECONNECT_DELAYS = [1, 2, 3, 5, 8, 10, 15, 20, 30, 30]; // 秒

// ========== WebSocket 连接 ==========
function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws/${ROOM_CODE}/${PLAYER_ID}`;
    state.ws = new WebSocket(wsUrl);

    state.ws.onopen = () => {
        console.log('WebSocket 已连接');
        // 隐藏重连提示
        hideReconnectOverlay();
        reconnectAttempts = 0;

        if (state.gameOver) return;

        // 如果是重连，显示提示
        if (reconnectAttempts === 0 && state.turn > 0) {
            // 这不是重连，是首次连接
        }

        // 请求当前游戏状态
        send({ type: 'get_state' });
    };

    state.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
    };

    state.ws.onclose = () => {
        console.log('WebSocket 已断开');
        if (!state.gameOver && reconnectAttempts < MAX_RECONNECT) {
            attemptReconnect();
        } else if (!state.gameOver) {
            addLog('⚠️ 连接已断开，重连次数已用完，请刷新页面');
            showReconnectOverlay(false);
        }
    };

    state.ws.onerror = (err) => {
        console.error('WebSocket 错误:', err);
        // onclose 会在 onerror 之后自动触发，重连逻辑在 onclose 中处理
    };
}

function attemptReconnect() {
    const delay = RECONNECT_DELAYS[Math.min(reconnectAttempts, RECONNECT_DELAYS.length - 1)];
    reconnectAttempts++;
    showReconnectOverlay(true, delay, reconnectAttempts);

    console.log(`重连中... 第 ${reconnectAttempts} 次，${delay}秒后`);

    setTimeout(() => {
        if (state.ws && state.ws.readyState === WebSocket.CLOSED) {
            connect();
        }
    }, delay * 1000);
}

function showReconnectOverlay(showCountdown, delaySeconds, attempt) {
    const overlay = $('reconnect-overlay');
    if (!overlay) return;

    if (showCountdown && delaySeconds) {
        overlay.classList.remove('hidden');
        $('reconnect-countdown').textContent = delaySeconds;
        $('reconnect-attempt').textContent = `第 ${attempt} 次重连`;
        $('reconnect-auto').classList.remove('hidden');
        $('reconnect-manual').classList.add('hidden');

        // 倒计时
        let remaining = delaySeconds;
        if (state._reconnectInterval) clearInterval(state._reconnectInterval);
        state._reconnectInterval = setInterval(() => {
            remaining--;
            if (remaining <= 0) {
                clearInterval(state._reconnectInterval);
            } else {
                $('reconnect-countdown').textContent = remaining;
            }
        }, 1000);
    } else {
        overlay.classList.remove('hidden');
        $('reconnect-auto').classList.add('hidden');
        $('reconnect-manual').classList.remove('hidden');
    }
}

function hideReconnectOverlay() {
    const overlay = $('reconnect-overlay');
    if (overlay) overlay.classList.add('hidden');
    if (state._reconnectInterval) {
        clearInterval(state._reconnectInterval);
        state._reconnectInterval = null;
    }
}

// 手动重连按钮
function manualReconnect() {
    reconnectAttempts = 0;
    connect();
}

function send(msg) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(msg));
    }
}

// ========== 消息处理 ==========
function handleMessage(msg) {
    console.log('收到消息:', msg);

    switch (msg.type) {
        case 'game_state':
        case 'game_start':
            if (IS_OFFLINE && msg.for_player !== undefined) {
                state.bothStates = state.bothStates || {};
                state.bothStates[msg.for_player] = msg;
                updateFullState(msg);
            } else {
                updateFullState(msg);
            }
            if (msg.type === 'game_start') {
                addLog('⚔️ 战斗开始！');
            }
            break;

        case 'turn_result':
            if (IS_OFFLINE && msg.for_player !== undefined) {
                // 离线模式：存储双方视角
                state.bothStates = state.bothStates || {};
                state.bothStates[msg.for_player] = msg;
                // 只取最后一方的日志
                if (msg.for_player === 0 && msg.turn_log) {
                    msg.turn_log.forEach(log => addLog(log));
                }
                // 双方都收到后，用当前操控方的视角更新
                if (state.bothStates[0] && state.bothStates[1]) {
                    updateFullState(state.bothStates[state.controllingPlayer]);
                    state.actionConfirmed = false;
                    state.offlineActions = {};
                    resetActionUI();
                }
            } else {
                updateFullState(msg);
                if (msg.turn_log) {
                    msg.turn_log.forEach(log => addLog(log));
                }
                state.actionConfirmed = false;
                state.offlineActions = {};
                if (IS_OFFLINE) {
                    state.controllingPlayer = 0;
                    switchControllingPlayer();
                }
                resetActionUI();
            }

            // 检查是否有待处理的猜拳
            if (msg.pending_rps && (!IS_OFFLINE || msg.for_player === 0)) {
                showRPSModal(msg.rps_skill_name);
            }

            // 检查游戏结束
            if (msg.game_over) {
                state.gameOver = true;
                saveBattleRecord(msg);
                showGameOver(msg);
            }
            break;

        case 'rps_result':
            hideRPSModal();
            addLog(`猜拳结果：你出 ${getRPSName(msg.human_choice)}，鬼出 ${getRPSName(msg.demon_choice)} — ${msg.result === 'win' ? '胜利！' : msg.result === 'draw' ? '平局' : '失败'}`);
            if (msg.damage > 0) {
                addLog(`💥 造成 ${msg.damage} 点伤害！`);
            }
            if (msg.game_over) {
                state.gameOver = true;
                showGameOver(msg);
            }
            // 猜拳结束但游戏继续？等待 rps_turn_end 来重置 UI
            break;

        case 'rps_turn_end':
            // 猜拳回合结束，游戏继续
            updateFullState(msg);
            state.actionConfirmed = false;
            resetActionUI();
            break;

        case 'game_over':
            state.gameOver = true;
            saveBattleRecord(msg);
            showGameOver(msg);
            break;

        case 'player_disconnected':
            addLog('⚠️ 对手已断线，请等待...');
            break;

        case 'error':
            addLog(`❌ ${msg.message}`);
            break;
    }
}

function updateFullState(msg) {
    if (msg.map) state.map = msg.map;
    if (msg.your_hp !== undefined) state.yourHP = msg.your_hp;
    if (msg.your_max_hp) state.yourMaxHP = msg.your_max_hp;
    if (msg.enemy_hp !== undefined) state.enemyHP = msg.enemy_hp;
    if (msg.enemy_max_hp) state.enemyMaxHP = msg.enemy_max_hp;
    if (msg.your_pos) state.yourPos = msg.your_pos;
    if (msg.enemy_pos) state.enemyPos = msg.enemy_pos;
    if (msg.your_skills) state.yourSkills = msg.your_skills;
    if (msg.your_character) state.yourCharacter = msg.your_character;
    if (msg.enemy_character) state.enemyCharacter = msg.enemy_character;
    if (msg.your_stunned !== undefined) state.yourStunned = msg.your_stunned;
    if (msg.enemy_stunned !== undefined) state.enemyStunned = msg.enemy_stunned;
    if (msg.turn) state.turn = msg.turn;
    if (msg.game_over !== undefined) state.gameOver = msg.game_over;

    updateUI();
    renderMap();
}

// ========== UI 更新 ==========
function updateUI() {
    // 房间信息
    $('room-display').textContent = `房间：${ROOM_CODE}`;
    $('turn-number').textContent = state.turn;

    // 己方信息
    if (state.yourCharacter) {
        $('your-emoji').textContent = state.yourCharacter.emoji || '⚔️';
        $('your-name').textContent = state.yourCharacter.name || '你';
    }

    // 敌方信息
    if (state.enemyCharacter) {
        $('enemy-emoji').textContent = state.enemyCharacter.emoji || '👹';
        $('enemy-name').textContent = state.enemyCharacter.name || '对手';
    }

    // 血量条
    updateHPBar('your', state.yourHP, state.yourMaxHP);
    updateHPBar('enemy', state.enemyHP, state.enemyMaxHP);

    // 状态徽章
    updateStatusBadge('your-status', state.yourStunned);
    updateStatusBadge('enemy-status', state.enemyStunned);

    // 技能按钮
    updateSkillButtons();

    // 敌方技能
    updateEnemySkills();
}

function updateHPBar(player, hp, maxHP) {
    const percent = Math.max(0, Math.min(100, (hp / maxHP) * 100));
    const bar = $(`${player}-hp-bar`);
    const text = $(`${player}-hp-text`);

    if (bar) bar.style.width = `${percent}%`;
    if (text) text.textContent = `${hp}/${maxHP}`;

    // 颜色变化
    if (percent <= 25) {
        if (bar) bar.style.background = 'linear-gradient(90deg, #ff0000, #cc0000)';
    } else if (percent <= 50) {
        if (bar) bar.style.background = player === 'your'
            ? 'linear-gradient(90deg, #ff8800, #cc6600)'
            : 'linear-gradient(90deg, #ff8800, #cc6600)';
    }
}

function updateStatusBadge(elementId, stunned) {
    const el = $(elementId);
    if (!el) return;
    if (stunned) {
        el.textContent = '💫 晕眩';
        el.className = 'status-badge stunned';
    } else {
        el.textContent = '';
        el.className = 'status-badge';
    }
}

function updateSkillButtons() {
    for (let i = 0; i < 3; i++) {
        const btn = $(`btn-skill-${i}`);
        if (!btn) continue;

        if (i < state.yourSkills.length) {
            const skill = state.yourSkills[i];
            btn.textContent = skill.name;
            btn.disabled = state.actionConfirmed || state.yourStunned;
        } else {
            btn.textContent = `技能${i + 1}`;
            btn.disabled = true;
        }
    }

    // 移动按钮
    const moveBtn = $('btn-move');
    if (moveBtn) {
        moveBtn.disabled = state.actionConfirmed || state.yourStunned;
    }
}

function updateEnemySkills() {
    const container = $('enemy-skills');
    if (!container || !state.enemyCharacter) return;

    // 简化：显示对手已选技能
    container.innerHTML = '';
    // 敌人技能从角色推断
    const faction = state.enemyCharacter.faction;
    const skillNames = faction === 'demon'
        ? ['破坏杀·光式', '破坏杀·乱式', '破坏杀·灭式']
        : ['水之呼吸·壹', '水之呼吸·叁', '水之呼吸·肆'];
    skillNames.forEach(name => {
        const div = document.createElement('div');
        div.className = 'skill-item';
        div.textContent = `▸ ${name}`;
        container.appendChild(div);
    });
}

// ========== 地图渲染 ==========
function renderMap() {
    const container = $('game-map');
    if (!container) return;

    container.innerHTML = '';

    for (let r = 0; r < 6; r++) {
        for (let c = 0; c < 12; c++) {
            const cell = document.createElement('div');
            cell.className = 'map-cell';
            cell.dataset.row = r;
            cell.dataset.col = c;

            // 障碍物
            if (state.map[r] && state.map[r][c] === 1) {
                cell.classList.add('obstacle');
            }

            // 己方位置
            if (state.yourPos[0] === r && state.yourPos[1] === c) {
                cell.classList.add('self');
                cell.textContent = state.yourCharacter?.emoji || '⚔️';
            }

            // 敌方位置
            if (state.enemyPos[0] === r && state.enemyPos[1] === c) {
                cell.classList.add('enemy');
                cell.textContent = state.enemyCharacter?.emoji || '👹';
            }

            // 高亮
            const highlight = state.highlightedCells.find(h => h.r === r && h.c === c);
            if (highlight) {
                if (highlight.type === 'move') {
                    cell.classList.add('move-highlight');
                } else if (highlight.type === 'attack') {
                    cell.classList.add('attack-highlight');
                } else if (highlight.type === 'direction') {
                    cell.classList.add('direction-highlight');
                }
            }

            // 坐标标签
            const coord = document.createElement('span');
            coord.className = 'coord-label';
            coord.textContent = `${r},${c}`;
            cell.appendChild(coord);

            // 点击事件
            cell.addEventListener('click', () => onCellClick(r, c));

            container.appendChild(cell);
        }
    }
}

// ========== 格子点击处理 ==========
function onCellClick(r, c) {
    if (state.actionConfirmed || state.gameOver || state.yourStunned) return;

    // 检查是否是高亮格子
    const highlight = state.highlightedCells.find(h => h.r === r && h.c === c);

    if (state.selectedAction === 'move' && highlight && highlight.type === 'move') {
        // 确定移动方向
        const direction = getDirectionFromPos(state.yourPos, [r, c]);
        if (direction) {
            state.selectedDirection = direction;
            updateDirectionPicker(direction);
        }
    } else if (state.selectedAction === 'skill' && highlight && highlight.type === 'attack') {
        // 技能目标：根据技能类型可能需要方向
        const skill = state.yourSkills[state.selectedSkillIndex];
        if (skill && needsDirection(skill.range_type)) {
            // 以该格子确定方向
            const direction = getDirectionFromPos(state.yourPos, [r, c]);
            if (direction) {
                state.selectedDirection = direction;
                updateDirectionPicker(direction);
            }
        }
    } else if (state.selectedAction === 'skill' && !needsDirection(getCurrentSkillRangeType())) {
        // 不需要方向的技能，点击任意攻击格子即可
        if (highlight && highlight.type === 'attack') {
            state.selectedDirection = null;
            updateDirectionPicker(null);
        }
    }

    updateConfirmButton();
}

function getDirectionFromPos(from, to) {
    const dr = to[0] - from[0];
    const dc = to[1] - from[1];

    // 归一化到 -1, 0, 1
    const ndr = dr === 0 ? 0 : (dr > 0 ? 1 : -1);
    const ndc = dc === 0 ? 0 : (dc > 0 ? 1 : -1);

    const map = {
        '-1,-1': 'ul', '-1,0': 'up', '-1,1': 'ur',
        '0,-1': 'left', '0,1': 'right',
        '1,-1': 'dl', '1,0': 'down', '1,1': 'dr',
    };

    return map[`${ndr},${ndc}`] || null;
}

function needsDirection(rangeType) {
    return ['line', 'square_3x3', 'dash_surround'].includes(rangeType);
}

function getCurrentSkillRangeType() {
    if (state.selectedAction === 'skill' && state.yourSkills[state.selectedSkillIndex]) {
        return state.yourSkills[state.selectedSkillIndex].range_type;
    }
    return null;
}

// ========== 方向选择器 ==========
function updateDirectionPicker(direction) {
    const picker = $('direction-picker');
    const needsDir = state.selectedAction === 'move' ||
        (state.selectedAction === 'skill' && needsDirection(getCurrentSkillRangeType()));

    if (!needsDir || !state.selectedAction) {
        picker.classList.add('hidden');
        $$('.dir-btn').forEach(b => b.classList.remove('selected'));
        return;
    }

    picker.classList.remove('hidden');
    $$('.dir-btn').forEach(b => {
        b.classList.remove('selected');
        if (b.dataset.dir === direction) {
            b.classList.add('selected');
        }
    });
}

function updateConfirmButton() {
    const btn = $('btn-confirm-action');
    const cancelBtn = $('btn-cancel-action');

    if (!state.selectedAction) {
        btn.disabled = true;
        cancelBtn.classList.add('hidden');
        return;
    }

    const needsDir = state.selectedAction === 'move' ||
        (state.selectedAction === 'skill' && needsDirection(getCurrentSkillRangeType()));

    if (needsDir && !state.selectedDirection) {
        btn.disabled = true;
    } else {
        btn.disabled = false;
    }

    cancelBtn.classList.remove('hidden');
}

// ========== 行动选择 ==========
$('btn-move').addEventListener('click', () => {
    if (state.actionConfirmed || state.yourStunned) return;

    clearActionHighlights();
    state.selectedAction = 'move';
    state.selectedDirection = null;

    // 高亮行动按钮
    $$('.btn-action').forEach(b => b.classList.remove('active'));
    $('btn-move').classList.add('active');

    // 高亮可移动格子
    // 计算8方向可移动格子
    const [r, c] = state.yourPos;
    const directions = [
        [-1, -1], [-1, 0], [-1, 1],
        [0, -1],           [0, 1],
        [1, -1],  [1, 0],  [1, 1]
    ];

    state.highlightedCells = [];
    for (const [dr, dc] of directions) {
        const nr = r + dr;
        const nc = c + dc;
        if (nr >= 0 && nr < 6 && nc >= 0 && nc < 12) {
            // 不能移动到障碍物或敌人位置
            const isObstacle = state.map[nr] && state.map[nr][nc] === 1;
            const isEnemy = state.enemyPos[0] === nr && state.enemyPos[1] === nc;
            if (!isObstacle && !isEnemy) {
                state.highlightedCells.push({ r: nr, c: nc, type: 'move' });
            }
        }
    }

    $('direction-picker').classList.remove('hidden');
    updateDirectionPicker(null);
    updateConfirmButton();
    renderMap();
});

for (let i = 0; i < 3; i++) {
    const btn = $(`btn-skill-${i}`);
    if (btn) {
        btn.addEventListener('click', () => {
            if (state.actionConfirmed || state.yourStunned) return;
            if (i >= state.yourSkills.length) return;

            clearActionHighlights();
            state.selectedAction = 'skill';
            state.selectedSkillIndex = i;
            state.selectedDirection = null;

            // 高亮行动按钮
            $$('.btn-action').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // 计算技能覆盖范围（前端预估）
            const skill = state.yourSkills[i];
            const coverage = estimateSkillCoverage(skill.range_type, state.yourPos, state.enemyPos, state.map);

            state.highlightedCells = coverage.map(([cr, cc]) => ({ r: cr, c: cc, type: 'attack' }));

            const needsDir = needsDirection(skill.range_type);
            if (needsDir) {
                $('direction-picker').classList.remove('hidden');
                updateDirectionPicker(null);
            } else {
                $('direction-picker').classList.add('hidden');
                updateDirectionPicker(null);
            }

            updateConfirmButton();
            renderMap();
        });
    }
}

// ========== 前端技能范围预估 ==========
function estimateSkillCoverage(rangeType, pos, enemyPos, map) {
    const [r, c] = pos;
    const cells = [];

    switch (rangeType) {
        case 'line':
            // 直线：4个正交方向延伸3格
            for (const [dr, dc] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
                for (let k = 1; k <= 4; k++) {
                    const nr = r + dr * k, nc = c + dc * k;
                    if (nr < 0 || nr >= 6 || nc < 0 || nc >= 12) break;
                    cells.push([nr, nc]);
                    if (map[nr] && map[nr][nc] === 1) break;
                }
            }
            break;

        case 'self_aura':
            for (const [dr, dc] of [[-1,-1],[-1,0],[-1,1],[0,-1],[0,1],[1,-1],[1,0],[1,1]]) {
                const nr = r + dr, nc = c + dc;
                if (nr >= 0 && nr < 6 && nc >= 0 && nc < 12) cells.push([nr, nc]);
            }
            break;

        case 'square_3x3':
            // 以敌人位置为中心的3x3（预估）
            const center = enemyPos;
            for (let i = center[0] - 1; i <= center[0] + 1; i++) {
                for (let j = center[1] - 1; j <= center[1] + 1; j++) {
                    if (i >= 0 && i < 6 && j >= 0 && j < 12) cells.push([i, j]);
                }
            }
            break;

        case 'dash_surround':
            // 4个方向延伸3格 + 周围
            for (const [dr, dc] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
                for (let k = 1; k <= 3; k++) {
                    const nr = r + dr * k, nc = c + dc * k;
                    if (nr < 0 || nr >= 6 || nc < 0 || nc >= 12) break;
                    cells.push([nr, nc]);
                    if (map[nr] && map[nr][nc] === 1) break;
                    // 也加周围格子
                    for (const [sdr, sdc] of [[-1,0],[1,0],[0,-1],[0,1]]) {
                        const sr = nr + sdr, sc = nc + sdc;
                        if (sr >= 0 && sr < 6 && sc >= 0 && sc < 12 && (sr !== r || sc !== c)) {
                            cells.push([sr, sc]);
                        }
                    }
                }
            }
            break;

        case 'four_way':
            for (const [dr, dc] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
                const nr = r + dr, nc = c + dc;
                if (nr >= 0 && nr < 6 && nc >= 0 && nc < 12) cells.push([nr, nc]);
            }
            break;

        case 'multi_dash':
            // 8方向各2格
            for (const [dr, dc] of [[-1,-1],[-1,0],[-1,1],[0,-1],[0,1],[1,-1],[1,0],[1,1]]) {
                for (let k = 1; k <= 2; k++) {
                    const nr = r + dr * k, nc = c + dc * k;
                    if (nr < 0 || nr >= 6 || nc < 0 || nc >= 12) break;
                    cells.push([nr, nc]);
                    if (map[nr] && map[nr][nc] === 1) break;
                }
            }
            break;
    }

    // 去重
    const unique = [];
    const seen = new Set();
    for (const [cr, cc] of cells) {
        const key = `${cr},${cc}`;
        if (!seen.has(key)) {
            seen.add(key);
            unique.push([cr, cc]);
        }
    }
    return unique;
}

// ========== 方向选择器事件 ==========
$$('.dir-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const dir = btn.dataset.dir;
        if (!dir) return;

        state.selectedDirection = dir;
        updateDirectionPicker(dir);
        updateConfirmButton();

        // 高亮对应方向的格子
        if (state.selectedAction === 'move') {
            const [r, c] = state.yourPos;
            const dirMap = { ul: [-1, -1], up: [-1, 0], ur: [-1, 1], left: [0, -1], right: [0, 1], dl: [1, -1], down: [1, 0], dr: [1, 1] };
            const [dr, dc] = dirMap[dir];
            const nr = r + dr, nc = c + dc;
            state.highlightedCells = [{ r: nr, c: nc, type: 'direction' }];
            renderMap();
        }
    });
});

// ========== 确认/取消 ==========
$('btn-confirm-action').addEventListener('click', () => {
    if (state.actionConfirmed) return;

    const action = {};
    if (state.selectedAction === 'move') {
        action.action = 'move';
        action.direction = state.selectedDirection;
    } else if (state.selectedAction === 'skill') {
        action.action = 'skill';
        action.skill_index = state.selectedSkillIndex;
        action.direction = state.selectedDirection;
    }

    if (IS_OFFLINE) {
        // 线下模式：存储当前玩家的行动，切换到另一玩家
        const cp = state.controllingPlayer;
        state.offlineActions[cp] = action;
        state.actionConfirmed = true;
        clearActionHighlights();
        renderMap();

        // 检查双方是否都确认了
        if (state.offlineActions[0] && state.offlineActions[1]) {
            // 发送双方行动
            send({
                type: 'offline_turn',
                actions: {
                    '0': state.offlineActions[0],
                    '1': state.offlineActions[1],
                }
            });
            state.offlineActions = {};
            showWaiting();
        } else {
            // 切换到另一方
            switchControllingPlayer();
            state.actionConfirmed = false;
            addLog(`✅ ${cp === 0 ? '炭治郎' : '猗窝座'} 行动已确认，请为另一方选择`);
        }
        return;
    }

    // 线上模式：直接发送
    send(action);

    state.actionConfirmed = true;
    clearActionHighlights();
    renderMap();
    showWaiting();
});

$('btn-cancel-action').addEventListener('click', resetActionUI);

function clearActionHighlights() {
    state.highlightedCells = [];
    state.selectedAction = null;
    state.selectedSkillIndex = 0;
    state.selectedDirection = null;
    $$('.btn-action').forEach(b => b.classList.remove('active'));
    $('direction-picker').classList.add('hidden');
}

function resetActionUI() {
    clearActionHighlights();
    $('btn-confirm-action').disabled = true;
    $('btn-cancel-action').classList.add('hidden');
    $('waiting-indicator').classList.add('hidden');
    // 重新启用所有行动按钮
    $$('.btn-action').forEach(b => b.disabled = false);
    updateSkillButtons();
    updateConfirmButton();
    renderMap();
}

function showWaiting() {
    $('btn-confirm-action').disabled = true;
    $('btn-cancel-action').classList.add('hidden');
    $('waiting-indicator').classList.remove('hidden');
    $('direction-picker').classList.add('hidden');
    $$('.btn-action').forEach(b => b.disabled = true);
}

// ========== 猜拳弹窗 ==========
function showRPSModal(skillName) {
    state.pendingRPS = true;
    state.rpsSeconds = 5;

    $('rps-skill-name').textContent = skillName ? `${skillName} 命中！猜拳决定伤害` : '技能命中，猜拳决定伤害';
    $('rps-countdown').textContent = state.rpsSeconds;
    $('rps-countdown').parentElement.classList.remove('urgent');
    $('rps-modal').classList.remove('hidden');

    // 倒计时
    if (state.rpsTimer) clearInterval(state.rpsTimer);
    state.rpsTimer = setInterval(() => {
        state.rpsSeconds--;
        $('rps-countdown').textContent = state.rpsSeconds;
        if (state.rpsSeconds <= 2) {
            $('rps-countdown').parentElement.classList.add('urgent');
        }
        if (state.rpsSeconds <= 0) {
            clearInterval(state.rpsTimer);
            // 超时随机选择
            const randomChoice = ['rock', 'scissors', 'paper'][Math.floor(Math.random() * 3)];
            submitRPS(randomChoice);
        }
    }, 1000);
}

function hideRPSModal() {
    $('rps-modal').classList.add('hidden');
    state.pendingRPS = false;
    if (state.rpsTimer) {
        clearInterval(state.rpsTimer);
        state.rpsTimer = null;
    }
}

function submitRPS(choice) {
    if (!state.pendingRPS) return;
    send({ type: 'rps_choice', choice: choice });
    hideRPSModal();
}

$$('.rps-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        submitRPS(btn.dataset.choice);
    });
});

function getRPSName(choice) {
    const names = { rock: '✊石头', scissors: '✌️剪刀', paper: '🖐️布' };
    return names[choice] || choice;
}

// ========== 战斗日志 ==========
function addLog(message) {
    const log = $('battle-log');
    if (!log) return;

    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.textContent = `[回合${state.turn}] ${message}`;
    log.insertBefore(entry, log.firstChild);

    // 最多保留50条
    while (log.children.length > 50) {
        log.removeChild(log.lastChild);
    }
}

// ========== 游戏结束 ==========
function showGameOver(msg) {
    const modal = $('game-over-modal');
    const title = $('game-over-title');
    const message = $('game-over-message');

    modal.classList.remove('hidden');

    // 判断胜负
    const iWon = (PLAYER_ID === 0 && msg.winner === 0) || (PLAYER_ID === 1 && msg.winner === 1);
    const isDraw = msg.winner === null || msg.winner === undefined;

    if (isDraw) {
        title.textContent = '🤝 平局！';
        title.className = 'draw';
        message.textContent = '双方同时倒下，不分胜负！';
    } else if (iWon) {
        title.textContent = '🏆 胜利！';
        title.className = 'win';
        message.textContent = msg.message || '你击败了对手！';
    } else {
        title.textContent = '💀 败北';
        title.className = 'lose';
        message.textContent = msg.message || '你被对手击败了...';
    }
}

// ========== 键盘快捷键 ==========
document.addEventListener('keydown', (e) => {
    if (state.pendingRPS) {
        // 猜拳快捷键 1=石头 2=剪刀 3=布
        if (e.key === '1') submitRPS('rock');
        if (e.key === '2') submitRPS('scissors');
        if (e.key === '3') submitRPS('paper');
        return;
    }

    if (state.gameOver || state.actionConfirmed) return;

    // 移动快捷键 WASD
    if (e.key === 'w' || e.key === 'W') { $('btn-move').click(); state.selectedDirection = 'up'; updateDirectionPicker('up'); updateConfirmButton(); }
    if (e.key === 's' || e.key === 'S') { $('btn-move').click(); state.selectedDirection = 'down'; updateDirectionPicker('down'); updateConfirmButton(); }
    if (e.key === 'a' || e.key === 'A') { $('btn-move').click(); state.selectedDirection = 'left'; updateDirectionPicker('left'); updateConfirmButton(); }
    if (e.key === 'd' || e.key === 'D') { $('btn-move').click(); state.selectedDirection = 'right'; updateDirectionPicker('right'); updateConfirmButton(); }

    // 确认 Enter
    if (e.key === 'Enter' && !$('btn-confirm-action').disabled) {
        $('btn-confirm-action').click();
    }

    // 取消 Escape
    if (e.key === 'Escape') {
        resetActionUI();
    }
});

// ========== 线下模式 ==========
const IS_OFFLINE = urlParams.get('offline') === '1';
state.offlineMode = IS_OFFLINE;
state.controllingPlayer = 0;  // 当前操控哪个玩家
state.offlineActions = {};     // {0: action, 1: action}

function switchControllingPlayer() {
    const newPid = 1 - state.controllingPlayer;
    state.controllingPlayer = newPid;

    // 用存好的对方视角更新UI
    if (state.bothStates && state.bothStates[newPid]) {
        updateFullState(state.bothStates[newPid]);
    }

    const name = newPid === 0
        ? (state.yourCharacter?.name || '炭治郎')
        : (state.enemyCharacter?.name || '猗窝座');
    $('controlling-label').textContent = `当前操控: ${name}`;
    $('controlling-panel').classList.remove('hidden');

    clearActionHighlights();
    $$('.btn-action').forEach(b => b.disabled = false);
    updateSkillButtons();
    renderMap();
    updateConfirmButton();
}

// ========== 初始化 ==========
console.log('⚔️ 极限格斗 PVP 鬼灭之刀 - 游戏客户端已就绪');
$('room-display').textContent = `房间：${ROOM_CODE}`;

// 显示玩家信息
if (window.Player) {
    $('player-name-display').textContent = `🎮 ${Player.getName()}`;
}

if (IS_OFFLINE) {
    $('controlling-panel').classList.remove('hidden');
    switchControllingPlayer();
}

// ========== 战斗记录保存 ==========
function saveBattleRecord(msg) {
    if (!window.BattleRecords) return;
    if (!msg.battle_history || msg.battle_history.length === 0) return;

    const record = {
        history: msg.battle_history,
        winner: msg.winner,
        winnerName: msg.winner_name || '',
        players: [],
    };

    const firstTurn = msg.battle_history[0];
    if (firstTurn && firstTurn.players) {
        record.players = firstTurn.players.map(p => ({
            name: p.name,
            player_id: p.player_id,
        }));
    }

    BattleRecords.save(record);
    console.log('战斗记录已保存到本地');
}

// 连接 WebSocket
connect();
