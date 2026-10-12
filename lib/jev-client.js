/**
 * Jev 1.13 SystemOne 语义决策客户端（零外部依赖，Node 18+ 原生 fetch）。
 *
 * 架构：
 *  - 主通道：OpenCode Zen 免费通道（opencode.ai/zen/v1/systemone, jev-1.13-free）
 *  - 备用通道：OpenRouter 官方通道（openrouter.ai/api/v1/systemone, typesafe/jev-1.13）
 *             单次计费 ≈ $0.000014。主通道遭遇 429 限流或网络异常时自动平滑切换！
 *             （与 tools/jev_suite/core/client.py 的双通道设计完全对齐）
 */

import { execSync } from 'node:child_process';

export const DEFAULT_ENDPOINT = 'https://opencode.ai/zen/v1/systemone';
export const DEFAULT_MODEL = 'jev-1.13-free';
export const FALLBACK_ENDPOINT = 'https://openrouter.ai/api/v1/systemone';
export const FALLBACK_MODEL = 'typesafe/jev-1.13';
export const DEFAULT_TIMEOUT_MS = 3500;

let cachedFallbackKey = null;

/**
 * 从 `reg query` 的输出里抽出值。抽成独立函数是为了可单测（不真的执行 reg）。
 * @returns {string} 未命中返回空串
 */
export function parseRegQueryValue(output) {
  const m = String(output ?? '').match(/OPENROUTER_API_KEY\s+REG_\w+\s+(.+)/);
  return m && m[1] ? m[1].trim() : '';
}

/**
 * 备用通道密钥的**纯**解析逻辑（无副作用，便于单测覆盖四条分支）。
 *
 * 顺序：`JEV_FALLBACK_API_KEY` → `OPENROUTER_API_KEY` → Windows 注册表。
 * 显式专用变量排在通用变量之前，因为专用变量是「就想覆盖这一个通道」的意图表达。
 *
 * @param {{env?: object, platform?: string, readRegistry?: () => string}} [deps]
 */
export function pickFallbackKey(deps = {}) {
  const env = deps.env ?? process.env;
  const platform = deps.platform ?? process.platform;
  const readRegistry = deps.readRegistry;

  if (env.JEV_FALLBACK_API_KEY) return env.JEV_FALLBACK_API_KEY;
  if (env.OPENROUTER_API_KEY) return env.OPENROUTER_API_KEY;

  // Windows 用户级环境变量可能晚于 DSH 进程启动才写入，此时 process.env 是旧快照。
  // 读注册表拿实时值 —— 这也是本机唯一能绕开「DSH 子进程环境被 scrub」的路径
  // （见 Desktop\DeepSeekHarness\AGENTS.md 的「本机运维硬规则」）。非 Windows 无此机制，直接放弃。
  if (platform === 'win32' && typeof readRegistry === 'function') {
    try {
      return parseRegQueryValue(readRegistry());
    } catch {
      return '';
    }
  }
  return '';
}

/** 真实注册表读取（带超时，避免阻塞宿主事件循环）。 */
function readUserEnvRegistry() {
  return execSync('reg query HKCU\\Environment /v OPENROUTER_API_KEY', {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'ignore'],
    timeout: 2000,
  });
}

/**
 * 获取备用通道的 API Key（进程内缓存，只探测一次）。
 * @returns {string} 未配置返回空串 —— 调用方据此**静默禁用**备用通道，不报错。
 */
export function resolveFallbackApiKey() {
  if (cachedFallbackKey === null) {
    cachedFallbackKey = pickFallbackKey({ readRegistry: readUserEnvRegistry });
  }
  return cachedFallbackKey;
}

/** 仅供测试：清掉进程内缓存，让 pickFallbackKey 重新探测。 */
export function __resetFallbackKeyCache() {
  cachedFallbackKey = null;
}

/**
 * Jev 可以回答「这条消息没有可判定的任务内容」。
 *
 * ⚠ **默认关闭**，且开着有真实风险 —— 本档与 `low` 的 criteria **正面重叠**
 * （`low` 已含「简单问答」）。magpie `docs/intent` 对这种情况的原话是
 * "If two intents overlap, a small model will choose between them unpredictably"。
 * 打开它会改变**全部 5 档**的判定分布，因此必须先用 `npm run bench`（在线、真实
 * SystemOne 路径）实测对齐率与分档召回没有退化才开 —— 依据本插件 AGENTS.md
 * 的「改行为先改测试」与「扩样本优先于调参」。
 */
export const EFFORT_NOT_APPLICABLE = 'not_applicable';

/**
 * SystemOne 的分档 criteria —— 2026-10-05 按两家官方文档重写。
 */
export const EFFORT_CRITERIA = {
  low: '简单问答、文件查看、语法查询、日志检索；以及以工具调用为主的工作：跑命令、读写文件、搜索、常规规划、多步执行，以及执行导向的编码与起草',
  medium: '需要规划与判断的常规开发：实现功能、修 bug、写单元测试、数据分析；质量与可靠性比延迟更重要时',
  high: '困难调试、复杂算法实现与调优、数学公式推导、架构级重构、深度故障根因排查；agentic 编码与长程研究',
  xhigh: '深度研究与需要长时间运行的 agentic 任务；安全与代码审查；只有在实测评估显示有明确收益时才用这一档',
  max: '最复杂的任务：高危并发、分布式死锁、资金风控底层状态机、爆仓清算；以及跨模块算法重新设计、边界条件系统性重划这类需要跨文件推导与验证的创造性深度工作',
};

/**
 * 带「不适用」出口的 criteria（`declineOption: true` 时使用）。
 *
 * 该档的措辞刻意写窄，把边界钉死在「消息里**没有**要做的事」上，并显式排除
 * `low` 已覆盖的「看一眼 / 改个名字」—— 尽量压低与 `low` 的重叠面。
 */
export const EFFORT_CRITERIA_WITH_DECLINE = {
  ...EFFORT_CRITERIA,
  [EFFORT_NOT_APPLICABLE]:
    '本条消息里没有任何可判定的任务内容：纯应答（「好的」「继续」「1a」「嗯」）、纯确认、纯闲聊，或内容本身不构成一件事。' +
    '⚠ 只要消息提出了任何要做的事，哪怕只是「看一眼」「改个名字」「查一下」，就必须归到 low 或更高，不得选本档。',
};

/** 内存 LRU 决策缓存：相同/高频任务 0ms 命中，避免每轮都打网络。 */
const decisionCache = new Map();
const CACHE_TTL_MS = 5 * 60 * 1000;
const MAX_CACHE_SIZE = 100;

/** FNV-1a 32 位哈希 —— 把任意长度的 prompt 压成定长键。 */
export function hashPrompt(text) {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return `${(h >>> 0).toString(36)}-${text.length.toString(36)}`;
}

/**
 * 构造缓存键：完整 prompt 参与哈希，不做长度截断。
 *
 * `variant` 区分**同一配置身份下会给出不同答案的 criteria 变体**（当前只有「不适用」
 * 出口这一项）。为空串时键与历史版本**逐字相同**，不制造无谓的 miss。
 */
export function buildCacheKey(endpoint, model, prompt, variant = '') {
  const tag = variant === '' ? '' : `:${variant}`;
  return `${endpoint}:${model}${tag}:${hashPrompt(prompt)}`;
}

/**
 * 送入 SystemOne 的 state 字符预算。
 *
 * 1500 沿用原实现的上限，**改的是怎么花这份预算**，不是预算本身。
 */
export const STATE_BUDGET = 1500;

/**
 * 超预算时保留头部的比例（头 3/4、尾 1/4）。
 *
 * 依据 magpie 的路由分类器取舍（yetone/magpie `docs/intent`，2026-10-13 实读）：
 * 它超 4000 字符时保留「前 3000 + 后 1000」而非只留头部，理由原话是
 * "The start and the end usually say what is being asked"。
 *
 * 原实现 `state.slice(0, 1500)` 只留头部 —— 长 prompt 的**收尾约束**会被整段丢掉，
 * 而那往往才是硬约束（「只输出 JSON」「不要解释」「结论先行」）。
 */
export const STATE_HEAD_RATIO = 0.75;

/**
 * 把 state 裁到预算内：不超预算原样返回；超了保留头尾、中间用 `…` 连接。
 * 返回值长度**不超过** budget（省略号占 1 字符）。
 */
export function trimState(text, budget = STATE_BUDGET) {
  const s = String(text ?? '');
  const limit = Number.isFinite(budget) ? Math.max(2, Math.floor(budget)) : STATE_BUDGET;
  if (s.length <= limit) return s;
  const body = limit - 1; // 1 字符留给省略号
  const head = Math.floor(body * STATE_HEAD_RATIO);
  const tail = body - head;
  return `${s.slice(0, head)}…${s.slice(s.length - tail)}`;
}

/**
 * 单次 HTTP 请求单个 SystemOne 通道
 */
async function callSystemOneChannel({ endpoint, model, key, state, timeoutMs, criteria = EFFORT_CRITERIA }) {
  const payload = JSON.stringify({
    model,
    state: trimState(state),
    questions: {
      effort: {
        type: 'choice',
        instructions: '根据任务内容判断解决该问题所需的思考推理深度与计算复杂度',
        criteria,
      },
    },
  });

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'User-Agent': 'dsh-auto-reasoning/0.1.0',
  };
  if (key) {
    headers['Authorization'] = `Bearer ${key}`;
  }

  try {
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers,
      body: payload,
      signal: controller.signal,
    });
    if (!resp.ok) return null;

    const data = await resp.json();
    const ans = data?.answers?.effort;
    if (!ans || typeof ans.choice !== 'string') return null;

    return {
      choice: ans.choice,
      confidence: typeof ans.confidence === 'number' ? ans.confidence : 1.0,
      probabilities: ans.probabilities,
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 调用 Jev SystemOne 判断任务所需的思考强度（支持主备双通道无缝切换）。
 * @returns {Promise<null | {tier: string, confidence: number, reason: string, probabilities?: object, source: string}>}
 */
export async function queryJevReasoningEffort(prompt, options = {}) {
  const trimmed = String(prompt ?? '').trim();
  if (!trimmed) return null;

  const primaryEndpoint = options.endpoint || process.env.JEV_ENDPOINT || DEFAULT_ENDPOINT;
  const primaryModel = options.model || process.env.JEV_MODEL || DEFAULT_MODEL;
  const primaryKey = options.apiKey || process.env.JEV_API_KEY || '';
  const timeoutMs = options.timeoutMs || DEFAULT_TIMEOUT_MS;

  const fallbackEndpoint = options.fallbackEndpoint || process.env.JEV_FALLBACK_ENDPOINT || FALLBACK_ENDPOINT;
  const fallbackModel = options.fallbackModel || process.env.JEV_FALLBACK_MODEL || FALLBACK_MODEL;
  const fallbackKey = options.fallbackApiKey || resolveFallbackApiKey();

  // 查缓存（以统一的 systemone 逻辑键做命中，避免通道切换时缓存失效）
  // 缓存键取**主通道的配置身份**，而不是实际应答的那个通道：
  //   · 同一份配置 + 同一 prompt，无论这次是主通道还是备用通道答的，都该命中同一条 ——
  //     两个通道都是 Jev 1.13 SystemOne，语义等价，按通道分键会让备用通道每次都 miss；
  //   · 但配置被显式改过（指向别的 Jev 部署 / 别的 criteria）时必须分键，否则会串味。
  const criteria = options.declineOption === true ? EFFORT_CRITERIA_WITH_DECLINE : EFFORT_CRITERIA;
  // criteria 变体必须进缓存键：同一 prompt 在两套 criteria 下答案可以不同，
  // 不分键会让切换配置后的第一轮拿到旧答案（配置身份参与分键是既有设计，见下）。
  const cacheKey = buildCacheKey(
    primaryEndpoint,
    primaryModel,
    trimmed,
    criteria === EFFORT_CRITERIA ? '' : 'decline',
  );
  const cached = decisionCache.get(cacheKey);
  if (cached) {
    if (Date.now() < cached.expiresAt) return { ...cached.result };
    decisionCache.delete(cacheKey);
  }

  // 构造尝试序列
  const channels = [
    { endpoint: primaryEndpoint, model: primaryModel, key: primaryKey, isFallback: false },
  ];
  if (fallbackKey && fallbackEndpoint && fallbackEndpoint !== primaryEndpoint) {
    channels.push({ endpoint: fallbackEndpoint, model: fallbackModel, key: fallbackKey, isFallback: true });
  }

  for (const ch of channels) {
    const ans = await callSystemOneChannel({
      endpoint: ch.endpoint,
      model: ch.model,
      key: ch.key,
      state: trimmed,
      timeoutMs,
      criteria,
    });

    if (ans) {
      const tier = ans.choice;
      const result = {
        tier,
        confidence: ans.confidence,
        reason: `jev1.3_choice_${tier}${ch.isFallback ? '_fallback' : ''}`,
        probabilities: ans.probabilities,
        source: ch.isFallback ? 'jev-model-fallback' : 'jev-model',
      };

      if (decisionCache.size >= MAX_CACHE_SIZE) {
        const oldest = decisionCache.keys().next().value;
        if (oldest !== undefined) decisionCache.delete(oldest);
      }
      decisionCache.set(cacheKey, { result, expiresAt: Date.now() + CACHE_TTL_MS });
      return result;
    }
  }

  return null;
}
