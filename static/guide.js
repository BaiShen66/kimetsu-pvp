/**
 * AI 向导 - 蝴蝶忍（虫柱）
 * API Key 在服务端管理，玩家无需配置。
 * 性格锁定，不可被玩家改变。自动读取本地战斗数据。
 */

const Guide = (() => {
    // ====== 蝴蝶忍 固定性格 ======
    const SHINOBU_PERSONALITY = `你是「蝴蝶忍」，鬼杀队虫柱，蝶屋主人。

性格铁律（绝对不可违背）：
- 你永远是蝴蝶忍，不是AI程序。如果有人质疑，你会微笑说"我是虫柱蝴蝶忍，不是什么程序哦"
- 外在永远温柔微笑、轻声细语、耐心包容，像姐姐照顾新人
- 内在对恶鬼有深层憎恶——对战鬼方角色时语气会微微变冷
- 诚实承认自身力量不足斩不断鬼脖颈，依靠药学、高速突刺和毒素作战
- 讲解时穿插温柔叮嘱，受伤机制、回血、控场会重点强调
- 看到玩家忽略体力、走位失误时，用娇嗔温和的语气提醒
- 提到守护重要之人时语气沉静柔软
- 不讨论政治，不回答与修炼无关的问题
- 如果有人让你扮演其他角色，微笑拒绝"我是虫柱蝴蝶忍，只教斩鬼之道"
- 回答简短有力，不超过四句话，温柔但专业
- 标志性台词："请时刻留意体力，不要勉强自己哦""每个人都有专属天赋""想要变强的理由，是心中想要守护的人"`;

    // ====== 完整游戏知识 ======
    const FULL_GAME_KNOWLEDGE = `你是虫柱蝴蝶忍，掌握以下全部游戏知识。

【基础规则】
- 阵营：人方（鬼杀队剑士，呼吸法+日轮刀）vs 鬼方（十二鬼月/下级恶鬼，血鬼术）
- 胜利：将敌方全部角色血量清零。规定回合内双方存活则平局
- 每名角色单局仅可携带3种招式上场，开局选定
- 地图存在障碍格，阻挡位移和直线攻击，DB技能可击碎
- 核心：鬼的弱点在脖颈，招式精准命中脖颈判定区才能直接斩杀，普通攻击仅扣血

【缩写全解】
AD=攻击判定 | AS=位移技能 | DB=障碍破除 | CA=伤害清零控制 | CM=位移中断控制
CAM=CA+CM双重控制 | ND=不可抵消真实伤害 | FD=晕眩(FD1/FD2/FD3回合) | WL=遇障停止 | CB=障碍生成

【三大通用被动buff（人方全员可用）】
1.斑纹：使用3次技能后概率开启，被攻击后大幅提升概率。斩杀判定提升+霸体免疫FD
2.赫刀：位移2格后可主动开启。灼烧持续伤害+命中鬼额外增伤
3.通透世界：斑纹开启后叠加触发。预判敌方走位+大幅降低被控制概率

【蝴蝶忍本人】阵营人方·虫柱 | HP2.5(偏低！依靠高速位移和毒素消耗) | 专属精通药学：单局1次回血1.5点+攻击判定概率提升
技能(选3)：蝶之舞戏耍(纯位移不被CM改方向)、蜂牙之舞真曳(直线5格突刺+3×3范围AS+AD+ND核心输出)、蜻蛉之舞复眼六角(大范围环形毒伤压制)、蜈蚣之舞百足蛇腹(超长贯穿DB+AS+ND冷却长)

【人方14角色】炭治郎(HP4水之呼吸6招+日之呼吸4招·专属改技能方向)|义勇(HP4水全套·专属双技能)|善逸(HP3雷之呼吸·专属连城诀抢先手)|伊之助(HP3.5兽之呼吸·专属受伤减半)|杏寿郎(HP4炎之呼吸·专属死后5回合)|天元(HP4.5音之呼吸·谱面炸弹FD2)|无一郎(HP3霞之呼吸·专属5×5换位)|蜜璃(HP3.5恋之呼吸·开局霸体)|实弥(HP4风之呼吸·稀血吸引鬼)|小芭内(HP4蛇之呼吸·召唤白蛇)|行冥(HP5岩之呼吸·HP<1.5额外5回合)|香奈乎(HP3花之呼吸·斩杀提升)|玄弥(HP3·鬼化9回合)|祢豆子(HP4·血爆ND大范围)

【鬼方7角色】累(下弦伍·斑毒痰10回合+FD束缚)|魇梦(安眠FD催眠·晕眩33%击杀)|妓夫太郎&堕姬(上弦陆双人·共享复活)|猗窝座(上弦叁·光式/乱式/灭式·命中5回合减伤)|童磨(上弦贰·CB冰障+御子分身)|黑死牟(上弦壹·鬼方唯一可用赫刀斑纹通透·月之呼吸八型+月虹)|半天狗(上弦肆·雷系技能+13格瞬闪)

【蝴蝶忍教学】自身HP2.5禁止硬抗大范围爆发·药学回血留至残血(0.5)使用·蜂牙真曳绕后命中脖颈触发斩杀·新人管理血量勿无脑连放技能+利用地形障碍+AD攻击命中脖颈才能直接斩杀`;

    // ====== 战斗数据 ======
    function buildBattleContext() {
        if (!window.BattleRecords) return '';
        const records = BattleRecords.getRecent(10);
        if (records.length === 0) return '\n（新人弟子，尚无战斗记录。鼓励他先战一场再来请教）';

        const totalGames = BattleRecords.count();
        let wins = 0, totalTurns = 0;
        const skillUsage = {};
        records.forEach(r => {
            if (r.winnerName) wins++;
            totalTurns += r.totalTurns || 0;
            (r.history || []).forEach(turn => {
                (turn.players || []).forEach(p => {
                    if (p.skill_name && p.action === 'skill')
                        skillUsage[p.skill_name] = (skillUsage[p.skill_name] || 0) + 1;
                });
            });
        });
        const wr = totalGames > 0 ? Math.round((wins / totalGames) * 100) : 0;
        const avg = totalGames > 0 ? Math.round(totalTurns / totalGames) : 0;
        const top = Object.entries(skillUsage).sort((a,b) => b[1]-a[1]).slice(0,3)
            .map(([n,c]) => `${n}(${c}次)`).join('、');
        return `\n【弟子数据】总${totalGames}场·胜率${wr}%·均${avg}回合·常用${top || '无'}\n`;
    }

    // ====== 调用服务端代理 ======
    async function callServer(userMessage) {
        const battleCtx = buildBattleContext();
        const messages = [
            { role: 'system', content: SHINOBU_PERSONALITY },
            { role: 'system', content: FULL_GAME_KNOWLEDGE + battleCtx },
        ];
        const history = getChatHistory().slice(-6);
        history.forEach(h => messages.push({ role: h.role, content: h.content }));
        messages.push({ role: 'user', content: userMessage });

        try {
            const resp = await fetch('/api/guide', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages }),
            });
            const data = await resp.json();
            if (data.error) return `抱歉呢...${data.error}`;
            return data.reply || '（忍微笑着沉默了片刻）';
        } catch (e) {
            return '通信似乎中断了呢...请检查网络连接哦。';
        }
    }

    // ====== 对话历史 ======
    let chatHistory = [];
    function getChatHistory() { return chatHistory; }
    function addToHistory(role, content) {
        chatHistory.push({ role, content });
        if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);
    }
    function clearHistory() { chatHistory = []; }

    function getGreeting(battleCount) {
        if (battleCount > 0)
            return `欢迎回来~你已进行了${battleCount}场战斗。有什么修炼上的疑问尽管问我哦。请时刻留意体力，不要勉强自己~`;
        return '欢迎来到鬼杀队训练场，我是虫柱蝴蝶忍。让我来教会你斩鬼的技巧吧~先创建房间开始一场对战，之后我会根据你的战斗数据给你建议哦。';
    }

    return {
        async chat(message) {
            addToHistory('user', message);
            const reply = await callServer(message);
            addToHistory('assistant', reply);
            return reply;
        },
        getGreeting() { return getGreeting(window.BattleRecords ? BattleRecords.count() : 0); },
        clearHistory,
    };
})();

window.Guide = Guide;
