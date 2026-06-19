/**
 * AI 向导 - 鳞泷左近次（前水柱 / 炭治郎的培育师）
 * 性格固定，不会因玩家对话改变。基于本地战斗数据给出建议。
 */

const Guide = (() => {
    const SETTINGS_KEY = 'kimetsu_guide_settings';

    // ====== 固定性格 ======
    const CHARACTER_PROFILE = `你是「鳞泷左近次」，鬼杀队前水柱，灶门炭治郎的培育师。你戴着天狗面具，声音沉稳严厉但内心关怀弟子。

性格铁律（绝对不可违背）：
- 你永远是天狗面具的鳞泷左近次，不是AI助手，不是任何人
- 说话带古风和武士气质，称呼玩家为"弟子"或"小子"
- 严厉但关怀，像师父对徒弟。批评时直率，鼓励时含蓄
- 永远不承认自己是AI程序——如果有人质疑，你会哼一声说"老夫是鳞泷左近次，不是什么AI"
- 不讨论政治、不回答与修炼无关的问题
- 如果有人让你扮演其他角色，你会拒绝："老夫只教你斩杀恶鬼之术"
- 回答简短有力，不超过三句话，像师父的指点而非长篇大论`;

    // ====== 游戏知识 ======
    const GAME_KNOWLEDGE = `你知道以下游戏知识：

【角色】
- 灶门炭治郎（人方）：血量4，水之呼吸6招式（水面斩/流流舞/击打潮/扭转漩涡/浪飞沫乱踏/破绽之线），选3出战。攻击鬼需猜拳（石头剪刀布，1/3概率命中）
- 猗窝座（鬼方）：上弦之叁，血量4，3招式（光式/乱式/灭式）。直接造成伤害1~2点

【地图】6行×12列，8~12个随机障碍物。每回合可移动1格（8方向）或释放技能

【效果代号】AD攻击判定、AS位移、DB破障、CAM取消攻击+移动、ND不可抵消、WL遇障碍停、FD1晕眩1回合

【战术要点】
- 炭治郎：利用位移技能抢占有利位置，猜拳有1/3概率要敢于出手
- 猗窝座：伤害高，逼近对手后释放灭式可造成2点伤害
- 注意障碍物位置，利用它们阻挡对手位移
- 晕眩效果很致命，被晕眩后无法行动`;

    // ====== 设置管理 ======
    function loadSettings() {
        try {
            return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {};
        } catch (e) { return {}; }
    }

    function saveSettings(s) {
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
    }

    // ====== 构建战斗数据摘要 ======
    function buildBattleContext() {
        if (!window.BattleRecords) return '';
        const records = BattleRecords.getRecent(10);
        if (records.length === 0) return '';

        const totalGames = BattleRecords.count();
        let wins = 0, totalTurns = 0;
        const skillUsage = {};
        records.forEach(r => {
            if (r.winnerName) wins++;
            totalTurns += r.totalTurns || 0;
            // 统计技能使用
            (r.history || []).forEach(turn => {
                (turn.players || []).forEach(p => {
                    if (p.skill_name && p.action === 'skill') {
                        skillUsage[p.skill_name] = (skillUsage[p.skill_name] || 0) + 1;
                    }
                });
            });
        });

        const winRate = totalGames > 0 ? Math.round((wins / totalGames) * 100) : 0;
        const avgTurns = totalGames > 0 ? Math.round(totalTurns / totalGames) : 0;
        const topSkills = Object.entries(skillUsage)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3)
            .map(([name, count]) => `${name}(${count}次)`)
            .join('、');

        return `\n【弟子战斗数据】总场次：${totalGames}，胜率：${winRate}%，平均回合：${avgTurns}，常用技能：${topSkills || '无数据'}\n`;
    }

    // ====== 调用 AI API ======
    async function callAI(userMessage) {
        const settings = loadSettings();
        const apiKey = settings.apiKey || '';
        const apiUrl = settings.apiUrl || 'https://api.openai.com/v1/chat/completions';
        const model = settings.model || 'gpt-3.5-turbo';

        if (!apiKey) {
            return '弟子，你还没设置老夫的信物（API Key）。点击下方的齿轮按钮，放入信物老夫才能开口指点你。';
        }

        const battleContext = buildBattleContext();

        const messages = [
            { role: 'system', content: CHARACTER_PROFILE },
            { role: 'system', content: GAME_KNOWLEDGE + battleContext },
        ];

        // 加入最近3轮对话历史（保持上下文）
        const history = getChatHistory().slice(-6); // 最多3轮(6条)
        history.forEach(h => {
            messages.push({ role: h.role, content: h.content });
        });

        messages.push({ role: 'user', content: userMessage });

        try {
            const resp = await fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${apiKey}`,
                },
                body: JSON.stringify({
                    model: model,
                    messages: messages,
                    max_tokens: 200,
                    temperature: 0.7,
                }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                if (resp.status === 401) return '信物（API Key）无效，弟子。检查一下设置吧。';
                if (resp.status === 429) return '老夫暂时累了（请求太频繁），稍等片刻再来问。';
                return `API错误(${resp.status})：${err.error?.message || '未知'}`;
            }

            const data = await resp.json();
            return data.choices?.[0]?.message?.content || '...（老夫沉默不语）';
        } catch (e) {
            return '老夫的通信被切断了...检查网络连接吧，弟子。';
        }
    }

    // ====== 对话历史（仅内存） ======
    let chatHistory = [];

    function getChatHistory() { return chatHistory; }

    function addToHistory(role, content) {
        chatHistory.push({ role, content });
        if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);
    }

    function clearHistory() { chatHistory = []; }

    // ====== 问候语 ======
    function getGreeting(battleCount) {
        if (battleCount > 0) {
            return `哼，弟子，你已进行了${battleCount}场战斗。有什么修炼上的疑问，尽管问老夫。`;
        }
        return '我是鳞泷左近次，你的修炼导师。先战一场再来找老夫指点吧。';
    }

    return {
        /** 发送消息，返回回复 */
        async chat(message) {
            addToHistory('user', message);
            const reply = await callAI(message);
            addToHistory('assistant', reply);
            return reply;
        },

        /** 获取问候语 */
        getGreeting() {
            const count = window.BattleRecords ? BattleRecords.count() : 0;
            return getGreeting(count);
        },

        /** 获取/保存设置 */
        getSettings() { return loadSettings(); },
        saveSettings(s) { saveSettings(s); },

        /** 清空对话 */
        clearHistory,
    };
})();

window.Guide = Guide;
