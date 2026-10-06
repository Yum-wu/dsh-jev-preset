#!/usr/bin/env node
// G5 规避审计 + 审计日志自动提交。
//
// 为什么「审计后 commit」是**功能必需**,不是卫生习惯:
//   tools/evasion_audit.py 的防篡改基线读的是 `git show HEAD:docs/evasion-audit.log`
//   (见该脚本 L477-492)。不提交 = HEAD 里的日志停在旧值,基线随之停滞,
//   回退检测的灵敏度逐轮衰减。所以每次审计后必须把追加的部分提交掉。
//
// 语义:
//   1. 跑审计, stdout/stderr 原样透传(不吞输出), 命令行参数原样转发。
//   2. **无论审计退出码是什么**, 只要 docs/evasion-audit.log 相对 HEAD 有变化就提交它。
//      ⚠ 用 `git commit --only <path>`: 只提交这一个路径,
//      工作区里其它已暂存 / 未暂存的改动一律不受影响。
//      (不能写成 `git add <path> && git commit` —— 那会把别人已暂存的东西一起卷进来。)
//   3. 退出码 = 审计的退出码。提交失败只告警, 不改判定 ——
//      审计的 exit 1/3/4 是有业务含义的判定, 不能被 git 的失败覆盖掉。
//
// 用法:
//   npm run audit:evasion          # 等价于 python tools/evasion_audit.py + 自动提交
//   node tools/audit-evasion.mjs --json
//
// ⚠ 直接跑 `python tools/evasion_audit.py` 仍然可用, 但**不会**自动提交。
//   需要提交的场合一律走本包装器。

import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const LOG = 'docs/evasion-audit.log';

const audit = spawnSync('python', ['tools/evasion_audit.py', ...process.argv.slice(2)], {
  cwd: ROOT,
  stdio: 'inherit',
});

const code = audit.status ?? 1;

// 相对 HEAD 有没有变化? git diff --quiet: exit 1 = 有变化, 0 = 无, 其它 = 查不了
const diff = spawnSync('git', ['diff', '--quiet', 'HEAD', '--', LOG], { cwd: ROOT });

if (diff.status === 1) {
  const commit = spawnSync(
    'git',
    ['commit', '--only', LOG, '-m', `chore(jev): G5 规避审计日志追加 (审计 exit ${code})`],
    { cwd: ROOT, stdio: 'inherit' },
  );
  if (commit.status !== 0) {
    process.stderr.write(
      '\n[audit-evasion] ⚠ 日志已更新但提交失败(不影响本次审计判定)。\n' +
      '  常见原因: 未配置 git user.name/user.email, 或该文件被 .gitignore 排除。\n' +
      '  ⚠ 基线不会前进, 下次审计前请手工提交 docs/evasion-audit.log。\n',
    );
  }
} else if (diff.status !== 0) {
  process.stderr.write(
    `\n[audit-evasion] ⚠ 无法比对 ${LOG} 与 HEAD(无 git / 不在仓库内), 跳过提交。\n`,
  );
}

process.exit(code);
