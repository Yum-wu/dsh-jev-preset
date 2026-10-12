/**
 * dsh-jev-preset 运行时半区 —— 自动思考程度（Auto Reasoning Effort）+ 发射台账
 *
 * ⚠ 2026-10-13 起本文件由独立包 `dsh-auto-reasoning` **并入** `dsh-jev-preset`
 *   （声明行 id 由 `plugin-auto-reasoning` 改为 `plugin-jev-runtime`，自挂本包）。
 *   并入理由见 `cordis.patch.yml` 末尾那一段：同 id 的重复 insert 在 cordis 里
 *   按「后者胜」静默去重，本包写在该行的 config 会被对方 bundle 层整体覆盖。
 *   `export const name` 与客户端 id 仍留 `dsh-auto-reasoning`（纯标识，改名无收益、
 *   有触雷风险 —— 宿主/客户端侧可能有按 id 的引用）。
 *
 * 模型配置里写 `reasoningEffort: auto` 时，cordis 的档位枚举并不接受它
 * （合法档位只有 off/minimal/low/medium/high/xhigh/max），会在 dsh-llm 的
 * resolveCallWithInfo 里抛 UNSUPPORTED_REASONING_EFFORT。本插件在
 * `agent/request` 瀑布上把 'auto' 哨兵换成按任务复杂度投影出的该模型合法档位。
 *
 * 挂 `agent/request` 而不是 `llm/stream`：loop 请求的 options 是 deepFreeze 的，
 * 且 cordis 的 next() 不吃实参，改不动；agent/request 的返回值直接喂给 llm.prepareCall。
 *
 * 发射台账（2026-10-13 加）挂 `tools/post-execute`，数「本轮实际发射了几路」，
 * 在 delegation 类工具结果尾部追加一行 —— 让 JEV persona §三 3.1 那条
 * 「裁决时记录本轮实际发射数」从**纯提示词自觉**变成**有客观计数**。
 */

import { decideReasoningEffort, decideReasoningEffortAsync } from './auto-reasoning.js';

export const name = 'dsh-auto-reasoning';
export const inject = ['llm', 'connection'];

/** 模型配置里写 `reasoningEffort: auto` 时的哨兵值。 */
export const AUTO_EFFORT_SENTINEL = 'auto';

/** 保留的会话决策条数上限；超出后按插入序淘汰最旧的会话。 */
export const AUTO_DECISION_CAP = 50;

/**
 * 本插件【接管所有模型】，但不是所有模型都有档位可投影。三条退出去向必须**显式**
 * 记录，否则「auto 没生效」时分不清是插件没挂、模型没档、还是决策崩了：
 *   - `no-ladder`  该模型 adapter 没返回 reasoning.efforts（dsh-llm normalizeModelInfo:2126
 *                   对 reasoning===undefined 直接 return，不抛），无从投影 → 回落模型默认档
 *   - `error`      adapter 抛错（典型是 efforts:[] 触发 INVALID_MODEL_REASONING，
 *                   dsh-llm normalizeModelInfo:2127）→ 回落模型默认档
 *   - `no-prompt`  接管到了但取不到任何提示词文本，评分为默认 2（routine），仍会出档
 */
export const SKIP_NONE = null;
export const SKIP_NO_LADDER = 'no-ladder';
export const SKIP_ERROR = 'error';
export const SKIP_NO_PROMPT = 'no-prompt';

/** 一次自动档位决策，按会话 id 归档供客户端胶囊读取。 */
export function createAutoEffortDecision(init) {
  return {
    sessionId: init.sessionId,
    effort: init.effort ?? null,
    score: init.score ?? null,
    reason: init.reason ?? null,
    source: init.source ?? 'unknown',
    via: init.via ?? 'unknown',
    model: init.model,
    ladder: init.ladder ?? [],
    singleTier: Boolean(init.singleTier ?? (Array.isArray(init.ladder) && init.ladder.length === 1)),
    skipped: init.skipped ?? SKIP_NONE,
    skippedDetail: init.skippedDetail ?? null,
    depth: init.depth ?? 0,
    at: new Date().toISOString(),
  };
}

/**
 * 取当前异步驱动链上的 Agent。agent/request 由 agent 作用域派发，
 * 若宿主把 agent 注入进载荷就用载荷，否则退回 initiator 边界。
 */
function currentAgent(ctx) {
  try {
    const registry = ctx?.agents ?? ctx?.get?.('agents');
    return registry?.currentInitiator?.();
  } catch {
    return undefined;
  }
}

/** 把一条消息的文本块拼成纯文本。 */
export function textOfContent(content) {
  if (!Array.isArray(content)) return '';
  return content
    .filter((block) => block?.type === 'text')
    .map((block) => String(block.text ?? ''))
    .join('\n')
    .trim();
}

/**
 * 从 agent 冻结的本轮消息里取最后一条真实用户文本。
 * 判据用 `message.source.kind === 'user'`：AGENTS.md / runtime-context / skill-catalog
 * 也被当成 user 消息注入且排在真实提示词之后，只看 role 会取到技能目录。
 */
export function promptFromFrozenMessages(agent) {
  const messages = agent?.frozenMessages;
  if (!Array.isArray(messages)) return '';
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message?.role !== 'user') continue;
    const kind = message?.source?.kind;
    if (kind !== undefined && kind !== 'user') continue;
    const text = textOfContent(message.content);
    if (text) return text;
  }
  return '';
}

/**
 * 从 agent 的持久 inbox 取待处理用户输入。
 *
 * 时序依据（dsh-agent-loop/lib/index.js）：
 *   L906   inbox.claim()                        从 inbox 取走本轮输入
 *   L1050  prepareRequest()
 *   L1179    └ waterfall("agent/request")      ← 本插件挂载点
 *   L1061  session.append("user/message")      ← 用户消息【之后】才写进日志
 *   L1063  buildRequest()
 * 所以在 agent/request 那一刻 deriveMessages / snapshotEvents / user/message
 * 三条路都取不到本轮提示词，inbox 是唯一有货的源。
 */
export function promptFromInbox(agent) {
  let inbox;
  try {
    inbox = agent?.inbox;
    if (inbox === null || typeof inbox !== 'object') return '';
  } catch {
    return '';
  }
  for (const target of ['nextTurn', 'nextStep']) {
    let list;
    try {
      list = inbox[target];
    } catch {
      continue;
    }
    if (!Array.isArray(list)) continue;
    for (let i = list.length - 1; i >= 0; i--) {
      const message = list[i];
      if (message?.role !== 'user') continue;
      const kind = message?.source?.kind;
      if (kind !== undefined && kind !== 'user') continue;
      const text = textOfContent(message.content);
      if (text) return text;
    }
  }
  return '';
}

/**
 * 从**原始会话事件日志**倒序取最后一条真实用户消息。
 * 官方 dsh-session-title 取首条提示词也是走 snapshotEvents()。
 */
export function promptFromEvents(session) {
  const events = typeof session?.snapshotEvents === 'function' ? session.snapshotEvents() : undefined;
  if (!Array.isArray(events)) return '';
  for (let i = events.length - 1; i >= 0; i--) {
    const event = events[i];
    if (event?.type !== 'user/message' || event?.data?.source?.kind !== 'user') continue;
    const text = textOfContent(event.data.content);
    if (text) return text;
  }
  return '';
}

/** 历史兜底：surface 已投影时的取数路径。 */
export function lastUserPromptText(session) {
  const messages = typeof session?.deriveMessages === 'function' ? session.deriveMessages() : [];
  if (!Array.isArray(messages)) return '';
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message?.role !== 'user' || !Array.isArray(message.content)) continue;
    const kind = message.source?.kind;
    if (kind !== undefined && kind !== 'user') continue;
    const text = textOfContent(message.content);
    if (text) return text;
  }
  return '';
}

/**
 * 判定本次请求是否该由本插件接管。
 *
 * ## 默认就是接管（2026-10-05 用户要求，语义较上一版反转）
 *
 * 上一版是「默认跟随 UI，点胶囊才强制接管」。现在改成**默认接管**，
 * 只有**用户手选思考档位**才中断。实现上不需要任何新状态：
 *
 *   auto 接管后会把自己选的档位写进 session request header，于是下一轮
 *   incoming === 「我上次写的」→ `isMyEcho` → 继续接管（每轮重评）。
 *   用户一旦手选，incoming 变成**别的具体档位** → 既不是 `isMyEcho`、也不是哨兵 /
 *   undefined → **那就是手选** → 中断接管，放行用户的选择。
 *
 * ## 四个命中条件
 *   a) incoming === 'auto' 哨兵 —— 会话首次请求，seed 来自 AgentOptions
 *   b) incoming === 本会话上次我写进去的档位 —— 那是我的回音，命中即「每轮重评」
 *   c) incoming === undefined —— **换模型的子代理**。宿主 dsh-subagent 在
 *      `resolveChildAgentOptions()` 里对「路由变了且未显式指定档位」执行
 *      `delete resolved.reasoningEffort`（lib/index.js:450），把父会话的 auto 哨兵
 *      一并删掉，子代理因此完全脱离 auto。接管 undefined 才能把它捞回来。
 *   d) 用户点了胶囊的「强制接管」(`strict`) —— 无条件接管，连手选也压过，
 *      这是「手选期间想回到 auto」的唯一出口（UI 下拉框里**没有** Auto 项）。
 *
 * ## 为什么 (d) 技术上做得到
 * 本插件以 `prepend: true` 挂 `agent/request`，是**最外层**，拿到的 resolved 已被内层
 * `dsh-agent/lib/index.js:181-192` 的后置拾取器用 UI selection 覆盖过 —— 实测旧会话里
 * `lastIncoming: max` 正是那个值，不是 AgentOptions 里的 `auto`。故改写返回值即可压过。
 *
 * @param strict 该会话是否被用户显式设为「强制接管」（点过胶囊）
 * @returns {{take: boolean, via: 'sentinel'|'echo'|'orphan'|'forced'|'handpicked'|'none'}}
 */
export function shouldTakeOver(resolved, previousMine, strict = false) {
  const isStrict = strict === true;
  const isSentinel = resolved.reasoningEffort === AUTO_EFFORT_SENTINEL;
  const isMyEcho = previousMine !== undefined && resolved.reasoningEffort === previousMine;
  const isOrphan = resolved.reasoningEffort === undefined;

  if (isStrict) return { take: true, via: 'forced' };
  if (isSentinel) return { take: true, via: 'sentinel' };
  if (isMyEcho) return { take: true, via: 'echo' };
  if (isOrphan) return { take: true, via: 'orphan' };
  // 走到这里 = incoming 是个具体档位，且不是本插件写的 → 用户手选 → 中断接管。
  return { take: false, via: 'handpicked' };
}

export function apply(ctx, config = {}) {
  const enabled = config.enabled !== false;
  const decisionCap = Number.isFinite(config.decisionCap) ? config.decisionCap : AUTO_DECISION_CAP;

  const autoStats = {
    seen: 0,
    takenOver: 0,
    lastIncoming: 'never',
    lastOutgoing: 'never',
    lastTakeoverVia: 'never',
    lastAgentSource: 'never',
    lastPromptText: '',
    lastPromptSource: '',
    lastSkipReason: 'never',
    lastHandpickedEffort: 'never',
    lastHandpicked: 0,
    lastCacheSize: 0,
  };

  // 用户手选让位时记一笔，供胶囊显示「已让位给手选档位 X」。
  const lastHandpickedEffort = new Map();

  // 决策按会话隔离：agent/request 是全局瀑布，单槽会让所有会话的胶囊显示同一条。
  const autoDecisions = new Map();
  const rememberDecision = (decision) => {
    autoDecisions.delete(decision.sessionId);
    autoDecisions.set(decision.sessionId, decision);
    while (autoDecisions.size > decisionCap) {
      const oldest = autoDecisions.keys().next().value;
      if (oldest === undefined) break;
      autoDecisions.delete(oldest);
    }
  };

  // 用户显式设为「强制接管」的会话集合。
  // ⚠ 语义已随 2026-10-05 的需求反转：**默认就是接管**，这个集合是【加强项】而非开关 ——
  //   加入 = 无条件接管（连用户手选也压过）；不在集合 = 默认接管，但用户手选时中断。
  //   它存在的唯一理由：UI 档位下拉框里**没有 Auto 项**，手选之后只能靠这里回到 auto。
  // 内存态、有上限：重启即失效，不会留下"静默接管"的暗状态；上限防泄漏。
  const forcedSessions = new Set();
  const rememberForced = (sessionId) => {
    forcedSessions.add(sessionId);
    while (forcedSessions.size > decisionCap) {
      const oldest = forcedSessions.values().next().value;
      if (oldest === undefined) break;
      forcedSessions.delete(oldest);
    }
  };

  // ── 发射台账(2026-10-13)──────────────────────────────────────────────────
  // 判据来源:persona §三 3.1 要求「裁决时记录本轮实际发射数(含补派)」,
  //   并明写「纯 prompt 无程序拦截,这个数是唯一的事后审计入口」。
  //   实测反例:C3F 30 题里 11 题(36.7%)派出 4~5 路,标识仍写 3/3。
  // 现在同一事实由运行时数:模型在工具结果里看得到,外部也查得到。
  const emissionLedgerOn = config.emissionLedger !== false;
  const emissionBudget = Number.isFinite(config.emissionBudget) ? config.emissionBudget : 3;
  /** 算作「一路发射」的工具名。⚠ `workflow` 一次调用扇出 N 路,这里按 1 计(保守,不虚报)。 */
  const DELEGATION_TOOLS = new Set([
    'subagent',
    'subagent_fork',
    'subagent_codex',
    'subagent_claude_code',
    'workflow',
  ]);
  const emissions = new Map();
  /** ⚠ 必须与 cachePrompt 同一套 id 派生(session.id),否则「新一轮重置」对不上。 */
  const emissionKey = (agent) => String(agent?.session?.id ?? agent?.id ?? 'default');
  const emissionsOf = (key) => emissions.get(key) ?? { count: 0, byTool: {}, lastAt: null };
  const resetEmissions = (key) => {
    if (key !== '') emissions.delete(key);
  };
  const noteEmission = (key, toolName) => {
    const current = emissionsOf(key);
    const next = {
      count: current.count + 1,
      byTool: { ...current.byTool, [toolName]: (current.byTool[toolName] ?? 0) + 1 },
      lastAt: new Date().toISOString(),
    };
    emissions.delete(key);
    emissions.set(key, next);
    while (emissions.size > decisionCap) {
      const oldest = emissions.keys().next().value;
      if (oldest === undefined) break;
      emissions.delete(oldest);
    }
    return next;
  };
  const ledgerLine = (state) => {
    const used = state.count;
    const parts = Object.entries(state.byTool)
      .map(([tool, n]) => `${tool}×${n}`)
      .join(' ');
    const verdict =
      used > emissionBudget
        ? `⚠ 已超预算 ${emissionBudget} —— persona §三 3.1:标识路数必须按**实际可用路数**降级,不得写满额标识`
        : used === emissionBudget
          ? `预算用尽(${emissionBudget}) —— 再补派必须显式放弃另一路,并把少发那路按缺失计入降级`
          : `预算剩 ${emissionBudget - used}`;
    return `[JEV 发射台账] 本轮实际发射 ${used} 路(${parts});${verdict}。`;
  };

  // 真实人类提示词缓存 —— 挂 `agent/inbox/spliced`，**不是** `user/message`。
  // 唯一早于 agent/request 的入口：用户提交那一刻的 inbox 写入事件。
  // 双索引：宿主里 agent.id 与 session.id 未必同串，故同时按会话对象(WeakMap，引用相等)
  // 与按 id 字符串(Map，兜底)存一份。
  const promptBySession = new WeakMap();
  const lastHumanPrompts = new Map();
  const cachePrompt = (session, text) => {
    if (text === '') return;
    // 新一轮人类输入 = 上一轮的发射台账作废(预算按轮重置)。
    resetEmissions(String(session?.id ?? ''));
    if (session !== null && typeof session === 'object') promptBySession.set(session, text);
    const id = String(session?.id ?? '');
    if (id === '') return;
    lastHumanPrompts.delete(id);
    lastHumanPrompts.set(id, text);
    while (lastHumanPrompts.size > decisionCap) {
      const oldest = lastHumanPrompts.keys().next().value;
      if (oldest === undefined) break;
      lastHumanPrompts.delete(oldest);
    }
  };

  ctx.on('session/event', (session, event) => {
    if (event?.type === 'agent/inbox/spliced') {
      const splice = event.data ?? {};
      if (splice.target !== 'next-turn' || !Array.isArray(splice.inserted)) return;
      for (const message of splice.inserted) {
        if (message?.role !== 'user') continue;
        const kind = message?.source?.kind;
        if (kind !== undefined && kind !== 'user') continue;
        cachePrompt(session, textOfContent(message.content));
      }
      return;
    }
    if (event?.type === 'user/message' && event?.data?.source?.kind === 'user') {
      cachePrompt(session, textOfContent(event.data.content));
    }
  }, { global: true });

  ctx.on('agent/request', async (payload, next) => {
    const resolved = await next();
    const agent = payload?.agent ?? currentAgent(ctx);
    const sessionId = String(agent?.id ?? agent?.session?.id ?? 'default');
    autoStats.seen += 1;
    autoStats.lastAgentSource = payload?.agent ? 'payload' : agent ? 'initiator' : 'none';
    autoStats.lastIncoming = resolved?.reasoningEffort === undefined ? '<absent>' : String(resolved.reasoningEffort);

    const passthrough = () => {
      autoStats.lastOutgoing = autoStats.lastIncoming;
      return resolved;
    };
    if (!enabled || !resolved) return passthrough();

    const previous = autoDecisions.get(sessionId);
    const previousMine = previous?.effort;
    const { take, via } = shouldTakeOver(resolved, previousMine, forcedSessions.has(sessionId));
    if (!take) {
      // via==='handpicked' = 用户手选了思考档位，本插件主动让位。
      // 这不是异常，是设计；但要让胶囊能显示出来，别静默。
      autoStats.lastTakeoverVia = via;
      autoStats.lastHandpicked += 1;
      if (via === 'handpicked') {
        lastHandpickedEffort.set(sessionId, String(resolved.reasoningEffort));
        autoStats.lastHandpickedEffort = String(resolved.reasoningEffort);
        ctx.logger?.info?.(
          `auto-reasoning: 检测到用户手选档位 ${String(resolved.reasoningEffort)}，本会话让位不接管` +
            `（点胶囊可强制回到 auto）`,
        );
      }
      return passthrough();
    }
    lastHandpickedEffort.delete(sessionId);
    autoStats.lastTakeoverVia = via;
    autoStats.takenOver += 1;

    // 兜底：拿不到合法档位时【不带】reasoningEffort，让模型用自己的默认档。
    // 绝不能把 'auto' 原样交回宿主（会在 resolveCallWithInfo 抛 UNSUPPORTED_REASONING_EFFORT）。
    const { reasoningEffort: _sentinel, ...withoutSentinel } = resolved;
    const depth = Number(agent?.options?.subagentDepth ?? 0);
    const skip = (skipped, detail, ladder = []) => {
      autoStats.lastOutgoing = `<omitted:${skipped}>`;
      autoStats.lastSkipReason = skipped;
      rememberDecision(
        createAutoEffortDecision({
          sessionId,
          effort: null,
          skipped,
          skippedDetail: detail,
          model: resolved.model,
          ladder,
          via,
          depth,
        }),
      );
      ctx.logger?.warn?.(`auto-reasoning[${via}] ${resolved.model}: ${skipped} — ${detail}；已回落模型默认档位`);
      return withoutSentinel;
    };

    try {
      const info = await ctx.llm?.resolveModelInfo?.(resolved.provider, resolved.model);
      const ladder = (info?.reasoning?.efforts ?? []).map((effort) => String(effort.id));
      if (ladder.length === 0) {
        return skip(SKIP_NO_LADDER, 'adapter 未返回 reasoning.efforts，该模型无档位可投影', ladder);
      }

      const byObject =
        agent?.session !== null && typeof agent?.session === 'object' ? promptBySession.get(agent.session) : undefined;
      const candidates = [
        ['cache-obj', byObject ?? ''],
        ['cache-id', lastHumanPrompts.get(sessionId) ?? ''],
        ['cache-session', lastHumanPrompts.get(String(agent?.session?.id ?? '')) ?? ''],
        ['inbox', promptFromInbox(agent)],
        ['frozen', promptFromFrozenMessages(agent)],
        ['events', promptFromEvents(agent?.session)],
        ['derive', lastUserPromptText(agent?.session)],
      ];
      const hit = candidates.find(([, text]) => text !== '');
      const promptText = hit === undefined ? '' : hit[1];
      autoStats.lastPromptText = promptText.slice(0, 80);
      autoStats.lastPromptSource = hit === undefined ? '<none>' : hit[0];
      autoStats.lastCacheSize = lastHumanPrompts.size;
      autoStats.lastSkipReason = SKIP_NONE;

      const decision = await decideReasoningEffortAsync(promptText, ladder, {
        // 「不适用」出口默认关（config.declineOption），理由见 jev-client.js 的 EFFORT_NOT_APPLICABLE。
        declineOption: config.declineOption === true,
      });
      rememberDecision(
        createAutoEffortDecision({
          sessionId,
          effort: decision.matchedEffort,
          score: decision.score,
          reason: decision.reason,
          source: decision.source,
          skipped: promptText === '' ? SKIP_NO_PROMPT : SKIP_NONE,
          skippedDetail:
            promptText === '' ? '本轮取不到任何真实用户提示词，评分按默认 2（routine）处理' : null,
          model: resolved.model,
          ladder,
          via,
          depth,
        }),
      );
      autoStats.lastOutgoing = decision.matchedEffort;
      const singleNote = ladder.length === 1 ? ' [单档无选择]' : '';
      ctx.logger?.info?.(
        `auto-reasoning[${via}]: ${resolved.model} -> ${decision.matchedEffort}${singleNote} ` +
          `(score ${decision.score}/10, ${decision.reason}, src=${decision.source}, ladder=${ladder.join('/')})`,
      );
      return { ...resolved, reasoningEffort: decision.matchedEffort };
    } catch (error) {
      return skip(SKIP_ERROR, String(error));
    }
  }, { global: true, prepend: true });

  // ── 发射台账：数「本轮实际发射了几路」──────────────────────────────────
  // 挂 `tools/post-execute`（dsh-tools/lib/index.js:3504 的 waterfall）而不是
  // `tools/execute`：前者拿得到**最终结果**，能把台账追加到模型真正读到的那段文本上。
  // ⚠ 该 waterfall 跑在 execute 的 try/catch 里 —— 监听器抛错会让**这次工具调用变成失败**
  //   （dsh-tools 注释原文：a throwing listener → isError）。台账是旁路信息，
  //   绝不能拖垮工具本身 ⇒ 全程 try/catch，失败即原样放行。
  if (emissionLedgerOn) {
    ctx.on('tools/post-execute', async (exec, result, next) => {
      const decision = await next();
      try {
        const toolName = String(exec?.name ?? '');
        if (!DELEGATION_TOOLS.has(toolName)) return decision;
        const key = emissionKey(exec?.agent);
        const state = noteEmission(key, toolName);
        ctx.logger?.info?.(
          `jev-emission: ${key} ${toolName} -> 本轮第 ${state.count} 路(预算 ${emissionBudget})`,
        );
        // 基线取「下游已改写过的 content」，没有才退回原始 result.content。
        // ⚠ 不能只看 decision.content：无人改写时 next() 给的是 `{ kind: 'accept' }`，
        //   压根没有 content 字段 —— 那时模型读到的仍是 result.content。
        const base = typeof decision?.content === 'string' ? decision.content : result?.content;
        if (typeof base !== 'string') return decision;
        return { ...decision, content: `${base}\n\n${ledgerLine(state)}` };
      } catch (error) {
        ctx.logger?.warn?.(`jev-emission: 台账追加失败(已忽略，不影响工具结果): ${String(error)}`);
        return decision;
      }
    }, { global: true });
  }

  // 把档位决策与诊断计数暴露给客户端胶囊（走宿主共享 /api 通道，鉴权由宿主施加）。
  ctx.connection?.fetch?.register?.({
    path: '/api/auto-reasoning.effort',
    methods: ['GET'],
    requestBody: 'buffered',
    fetch: (request) => {
      const sessionId = new URL(request.url).searchParams.get('sessionId') ?? '';
      const decision = autoDecisions.get(sessionId) ?? (sessionId === '' ? [...autoDecisions.values()].pop() : undefined);
      return Promise.resolve(
        Response.json({
          enabled,
          ...autoStats,
          sessionId,
          forced: forcedSessions.has(sessionId),
          handpickedEffort: lastHandpickedEffort.get(sessionId) ?? null,
          decision: decision ?? null,
          emissionLedger: emissionLedgerOn,
          emissionBudget,
          emissions: emissionsOf(sessionId),
          sessions: [...autoDecisions.keys()],
          forcedSessions: [...forcedSessions],
        }),
      );
    },
  });

  // 「强制接管」开关的写入口。
  //
  // ⚠ 鉴权：宿主把鉴权放在**路由匹配之前**（统一 middleware），实测证据 ——
  //   无 cookie POST /api/auto-reasoning.force → 401；带 cookie 但路由不存在 → 404。
  //   也就是说写路由天然受宿主保护，本插件**不碰任何凭据**。
  //   若哪天宿主改成路由内鉴权，这里会裸奔 —— 改动前重跑上面那两条探测。
  ctx.connection?.fetch?.register?.({
    path: '/api/auto-reasoning.force',
    methods: ['POST'],
    requestBody: 'buffered',
    fetch: async (request) => {
      let body = {};
      try {
        body = await request.json();
      } catch {
        body = {};
      }
      const sessionId = String(body?.sessionId ?? '');
      if (sessionId === '') {
        return Response.json({ ok: false, error: 'sessionId is required' }, { status: 400 });
      }
      const forced = body?.forced === true;
      if (forced) rememberForced(sessionId);
      else forcedSessions.delete(sessionId);
      ctx.logger?.info?.(`auto-reasoning: ${sessionId} 强制接管${forced ? '开启' : '关闭'}`);
      return Response.json({ ok: true, sessionId, forced, forcedSessions: [...forcedSessions] });
    },
  });
}

export { decideReasoningEffort, decideReasoningEffortAsync } from './auto-reasoning.js';
export { queryJevReasoningEffort } from './jev-client.js';
