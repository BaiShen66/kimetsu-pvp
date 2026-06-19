/**
 * 战斗记录存储 - localStorage 持久化
 * 保存每场完整战斗数据，供日后训练 AI 或开发单人模式使用
 */

const BattleRecords = (() => {
    const STORAGE_KEY = 'kimetsu_battle_records';
    const MAX_RECORDS = 50; // 最多保存 50 场

    function loadAll() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch (e) {
            return [];
        }
    }

    function saveAll(records) {
        // 保持最新 N 条
        const trimmed = records.slice(-MAX_RECORDS);
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
        } catch (e) {
            // 存储空间不足，删除最旧的一半
            const half = trimmed.slice(-Math.floor(MAX_RECORDS / 2));
            localStorage.setItem(STORAGE_KEY, JSON.stringify(half));
        }
    }

    return {
        /** 保存一场战斗 */
        save(battleData) {
            const records = loadAll();
            records.push({
                id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
                savedAt: new Date().toISOString(),
                players: battleData.players || [],
                winner: battleData.winner,
                winnerName: battleData.winnerName || '',
                totalTurns: battleData.history ? battleData.history.length : 0,
                history: battleData.history || [],
            });
            saveAll(records);
            console.log(`战斗记录已保存，共 ${records.length} 场`);
        },

        /** 获取所有记录 */
        getAll() {
            return loadAll();
        },

        /** 获取最近 N 场 */
        getRecent(n = 10) {
            return loadAll().slice(-n).reverse();
        },

        /** 获取记录总数 */
        count() {
            return loadAll().length;
        },

        /** 清空所有记录 */
        clearAll() {
            localStorage.removeItem(STORAGE_KEY);
        },

        /** 导出为 JSON */
        exportJSON() {
            return JSON.stringify(loadAll(), null, 2);
        },
    };
})();

window.BattleRecords = BattleRecords;
