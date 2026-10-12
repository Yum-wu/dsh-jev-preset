// 自动思考深度客户端实时胶囊
//
// 挂到 DSH Web 的 conversation.composer.dock 插槽（输入框底栏，与影子盘状态条同级）。
// 档位由宿主侧 agent/request 瀑布决策，客户端只轮询只读路由 /api/auto-reasoning.effort。
//
// 会话隔离：决策在宿主侧按 sessionId 归档，这里把当前会话 id 作为查询参数带上，
// 否则多会话会共享同一条「最近一次」记录。
// 会话 id 取自对话根节点的 data-conversation-session 属性 —— 该属性由
// @deepseek-ai/dsh-client-ui-conversation 渲染，是客户端唯一可见的会话身份来源。
window.__ModuleLoader__.load({
  id: "dsh-auto-reasoning",
  factory: (require) => {
    const module = { exports: {} };
    const exports = module.exports;
    const React = require("react");

    const T = {
      ink2: 'var(--dsw-alias-label-secondary)',
      green: 'var(--dsw-alias-state-success-primary)',
      amber: 'var(--dsw-alias-state-warn-primary)',
      red: 'var(--dsw-alias-state-error-primary)',
      purple: '#a855f7',
      blue: '#3b82f6',
    };

    const EFFORT_COLORS = [
      [/^(max|xhigh)$/, T.purple],
      [/^high$/, T.red],
      [/^medium$/, T.amber],
      [/^(low|minimal)$/, T.green],
    ];

    const colorFor = (level) => {
      const l = String(level || '').toLowerCase();
      for (const [re, c] of EFFORT_COLORS) if (re.test(l)) return c;
      return T.blue;
    };

    /** 当前会话 id；DOM 上没有（hero 态 / 加载中）时返回空串。 */
    const currentSessionId = () => {
      try {
        const el = document.querySelector('[data-conversation-session]');
        return el ? el.getAttribute('data-conversation-session') || '' : '';
      } catch {
        return '';
      }
    };

    const VIA_LABEL = {
      sentinel: '会话首次',
      echo: '每轮重评',
      orphan: '子代理接管',
      forced: '强制接管',
      handpicked: '用户手选',
    };

    const SKIP_LABEL = {
      'no-ladder': '模型无档位 · 回落默认',
      error: '决策异常 · 回落默认',
      'no-prompt': '取不到提示词 · 按 routine 评分',
    };

    const AutoEffortPill = () => {
      const [level, setLevel] = React.useState(null);
      const [score, setScore] = React.useState(null);
      const [detail, setDetail] = React.useState('');
      const [forced, setForced] = React.useState(false);
      const [singleTier, setSingleTier] = React.useState(false);
      const [handpicked, setHandpicked] = React.useState(null);
      const [busy, setBusy] = React.useState(false);
      const [hint, setHint] = React.useState('');

      // 胶囊三态（2026-10-05 默认语义反转后）：
      //   auto      = 默认接管。遇用户手选则让位（这是用户的显式选择，不该被覆盖）
      //   forced    = 点击后。无条件接管，连手选也压过 —— 手选期间回到 auto 的唯一出口
      //   让位中    = 刚检测到手选档位，暂不接管
      const toggleForced = async () => {
        const sid = currentSessionId();
        if (sid === '') { setHint('没有可用的会话 id，点不动'); return; }
        setBusy(true);
        try {
          const res = await fetch('/api/auto-reasoning.force', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionId: sid, forced: !forced }),
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok || data.ok !== true) {
            setHint(`切换失败 HTTP ${res.status}`);
            return;
          }
          setForced(data.forced === true);
          setHint(data.forced
            ? '已强制接管：即使你手选档位也由插件决定'
            : '已回到默认：手选档位时自动让位');
        } catch (e) {
          setHint('切换失败：' + String(e).slice(0, 60));
        } finally {
          setBusy(false);
        }
      };

      React.useEffect(() => {
        let cancelled = false;

        const poll = async () => {
          try {
            const sid = currentSessionId();
            const url = '/api/auto-reasoning.effort' + (sid ? '?sessionId=' + encodeURIComponent(sid) : '');
            const res = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
            if (!res.ok) return;
            const data = await res.json();
            if (cancelled || !data) return;
            if (typeof data.forced === 'boolean') setForced(data.forced);
            if (typeof data.handpickedEffort === 'string') setHandpicked(data.handpickedEffort);
            else if (!forced) setHandpicked(null);

            const d = data.decision;
            if (d) {
              setLevel(d.effort);
              setScore(d.score);
              const isSingle = Boolean(d.singleTier || (Array.isArray(d.ladder) && d.ladder.length === 1));
              setSingleTier(isSingle);
              const via = VIA_LABEL[d.via] ? ` · ${VIA_LABEL[d.via]}` : '';
              if (d.skipped && !d.effort) {
                // 插件接管了，但没能产出档位：显式说出来，别让它看起来像「插件没挂」
                setDetail(`${d.model} · ${SKIP_LABEL[d.skipped] || d.skipped} · ${d.skippedDetail || ''}${via}`);
                return;
              }
              const singleNote = isSingle ? ' · ⚠ 单档无选择' : '';
              setDetail(
                `${d.model} · ${d.reason} · src=${d.source || '?'} · 阶梯 ${Array.isArray(d.ladder) ? d.ladder.join('/') : '-'}${singleNote}${via} · 会话 ${d.sessionId}` +
                  (d.skipped ? ` · ⚠ ${SKIP_LABEL[d.skipped] || d.skipped}` : '')
              );
              return;
            }
            setSingleTier(false);
            setLevel(null);
            setScore(null);
            setDetail(
              data.enabled
                ? `已见 agent/request ${data.seen} 次 · 接管 ${data.takenOver || 0} 次 · 本会话尚无决策`
                : '插件未启用',
            );
          } catch {}
        };

        poll();
        const timer = setInterval(poll, 3000);
        return () => { cancelled = true; clearInterval(timer); };
      }, []);

      const color = forced ? T.purple : handpicked ? T.ink2 : colorFor(level);
      const label = forced
        ? `⚡强制接管 (${level ?? '待定'}${singleTier ? '·单档' : ''})`
        : handpicked
          ? `让位给手选 ${handpicked}`
          : level
            ? singleTier
              ? `Auto (${level}) · 单档`
              : `Auto (${level})`
            : 'auto · 待接管';
      const text = label + (score == null || singleTier ? '' : ` · ${score}/10`);
      const title =
        (forced
          ? `【强制接管中】本会话所有请求的档位都由插件决定，你手选的档位也会被压过。${singleTier ? '（该模型为单档模型，无法调档）' : ''}点击 = 回到默认。`
          : handpicked
            ? `【已让位】检测到你手选了「${handpicked}」，插件不接管。点击 = 强制接管，压过手选。`
            : singleTier
              ? `【单档模型·无选择空间】该模型网关仅提供单一思考档位 (${level})，无法按任务复杂度动态升降档。`
              : '【默认自动接管】档位由插件按任务复杂度逐轮决定。你手选档位时插件会自动让位。') +
        (hint ? '\n' + hint : '') + (detail ? '\n' + detail : '');

      return React.createElement(
        'div',
        {
          title,
          role: 'button',
          onClick: toggleForced,
          style: {
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '2px 8px',
            borderRadius: 999,
            border: `${forced ? '2px' : '1px'} solid ${color}${forced ? 'cc' : '44'}`,
            background: forced
              ? `color-mix(in srgb, ${color} 22%, transparent)`
              : `color-mix(in srgb, ${color} 10%, transparent)`,
            marginRight: 8,
            maxWidth: 260,
            cursor: busy ? 'progress' : 'pointer',
            opacity: busy ? 0.6 : 1,
            userSelect: 'none',
          },
        },
        [
          React.createElement('span', {
            key: 'dot',
            style: {
              width: 6,
              height: 6,
              borderRadius: 999,
              background: color,
              flexShrink: 0,
              boxShadow: `0 0 6px ${color}`,
            },
          }),
          React.createElement(
            'span',
            {
              key: 'label',
              style: {
                fontSize: 11,
                fontWeight: 700,
                color,
                fontFamily: 'monospace',
                letterSpacing: '0.02em',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              },
            },
            text
          ),
        ]
      );
    };

    function apply(ctx) {
      const slots = ctx.get("slots");
      if (!slots) return;

      slots.inject('conversation.composer.dock', () =>
        slots.register(
          { name: 'conversation.composer.dock', id: 'auto-reasoning-pill', order: 5 },
          () => React.createElement(AutoEffortPill, null)
        )
      );
    }

    exports.apply = apply;
    exports.inject = ["slots"];
    return module.exports;
  },
});
