/**
 * 玩家系统 - localStorage 持久化
 * 每个浏览器自动获得唯一 ID，名称可随时修改
 */

const PlayerSystem = (() => {
    const STORAGE_KEY = 'kimetsu_player';

    // 生成简短唯一 ID
    function generateId() {
        const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
        let id = '';
        for (let i = 0; i < 8; i++) {
            id += chars[Math.floor(Math.random() * chars.length)];
        }
        return id;
    }

    // 读取玩家数据
    function load() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (raw) {
                const data = JSON.parse(raw);
                if (data.id && data.name) {
                    return data;
                }
            }
        } catch (e) {
            // 数据损坏，重新创建
        }
        return null;
    }

    // 保存玩家数据
    function save(data) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (e) {
            console.warn('无法保存玩家数据:', e);
        }
    }

    // 初始化或读取
    let data = load();
    if (!data) {
        const id = generateId();
        data = {
            id: id,
            name: '玩家_' + id.slice(0, 4),
            createdAt: Date.now(),
        };
        save(data);
    }

    return {
        /** 获取玩家 ID（不可修改） */
        getId() {
            return data.id;
        },

        /** 获取当前显示名称 */
        getName() {
            return data.name;
        },

        /** 修改显示名称 */
        setName(newName) {
            const trimmed = (newName || '').trim();
            if (!trimmed || trimmed.length > 12) return false;
            data.name = trimmed;
            data.updatedAt = Date.now();
            save(data);
            return true;
        },

        /** 获取玩家完整信息 */
        getInfo() {
            return {
                id: data.id,
                name: data.name,
                createdAt: data.createdAt,
            };
        },

        /** 重置玩家（清除数据） */
        reset() {
            localStorage.removeItem(STORAGE_KEY);
            data = {
                id: generateId(),
                name: '玩家_' + generateId().slice(0, 4),
                createdAt: Date.now(),
            };
            save(data);
        },
    };
})();

// 暴露到全局
window.Player = PlayerSystem;
