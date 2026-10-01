# -*- coding: utf-8 -*-
"""
A8:补派失控 —— persona 的发射上限自相矛盾,导致 36.7% 的采样超出 3 路。

缺陷实锤(2026-10-01 实测 `_runs-assert-c3f-30.jsonl`):

    subagents 分布: {3: 19, 4: 10, 5: 1}
    总记录: 30   超过 3 路的: 11 (36.7%)

即 persona 宣称的「3 路隔离采样」有超过三分之一**根本不是 3 路**。

根因不是 agent 不听话,而是 **persona 自己写了一个自相矛盾的约束**:

    「每路角色最多补派 1 次(总发射上限 2 次)」

「每路 1 次」× 3 路 = **最多 4 次**;而括号里写「总发射上限 2 次」——
2 < 3,字面读来**三路根本发不齐**。agent 面对矛盾只能自行解释,
实测解释成了「按路各补 1 次」→ 4 路,再补一次 → 5 路。

而 persona 的裁决段又写死「3/3 独立收敛」「2/3 多数共识」,
**分母被改写成 4 或 5,而裁决措辞仍说 3** —— 这不是采样浪费,是**统计口径被污染**。

判据(预注册,R9):
  T1 persona 的发射上限必须**自洽**:给出一个单一的、不自相矛盾的总数上限
  T2 上限必须与裁决措辞的分母一致(3)
  T3 明确写出「补派计入总数上限」—— 否则 agent 会把补派当额外配额
  T4 persona 必须要求**记录实际发射数**,使超限可被事后审计
  T5 persona 不得出现「上限 2 次」这类与 N=3 矛盾的数字
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "benchmarks", "accuracy"))


def personaPrefix():
    """按 YAML 块标量缩进边界截取 persona(不能 slice 到 EOF —— 见 A9 教训)。"""
    lines = open(os.path.join(PLUGIN_ROOT, "cordis.patch.yml"), encoding="utf-8").read().split("\n")
    s = next((i for i, l in enumerate(lines) if re.match(r"^\s*prefix: \|-\s*$", l)), -1)
    assert s >= 0, "cordis.patch.yml 里找不到 `prefix: |-` 行"
    indent = re.search(r"\S", lines[s]).start()
    out = []
    for line in lines[s + 1:]:
        if line.strip() == "":
            out.append(line)
            continue
        if re.search(r"\S", line).start() < indent:
            break
        out.append(line)
    return "\n".join(out)


class TestEmissionCapConsistency(unittest.TestCase):

    def setUp(self):
        self.persona = personaPrefix()

    # 声明里的「含补派」是**语义**,不是子串:「不含补派」恰恰是 A8 缺陷原样。
    # 红队 ba16b403 变体 V12 实测:把它改成「(不含补派)」后 6 条判据全绿。
    CAP_DECL = re.compile(r"^\s*-\s*\*{0,2}总发射上限\s*(\d+)\s*次(\s*\((含补派)\))?", re.M)

    def test_T1_cap_is_self_consistent(self):
        """发射上限必须给出**单一**自洽的数字,且必须**含补派**。"""
        found = list(self.CAP_DECL.finditer(self.persona))
        caps = [m.group(1) for m in found]
        self.assertGreaterEqual(len(caps), 1, "persona 未声明总发射上限 —— 补派将不受任何约束")
        self.assertEqual(len(caps), 1,
            f"persona 声明了多个互相矛盾的总发射上限: {caps} —— agent 只能自行解释,"
            f"实测解释成 4~5 路(A8)")
        # 唯一那条声明必须写明「含补派」—— 不含就等于给补派开了额外配额(A8 直接成因)
        self.assertIsNotNone(
            found[0].group(2),
            "总发射上限未写明「含补派」—— 补派会被当成额外配额,"
            "实测 11/30(36.7%)的采样因此超出 3 路(红队变体 V12 把「含」改「不含」曾全绿)")
        # 并确保不是「不含补派」这种反向语义(子串包含关系会误判,故显式排除)
        self.assertNotIn("不含补派", found[0].group(0),
            "声明写的是「不含补派」—— 那等于把 A8 缺陷原样装回")

    def test_T2_cap_consistent_with_verdict_denominator(self):
        """上限必须 = 裁决分母,且 ≥ 3(字面上三路要发得齐)。"""
        cap = int(self.CAP_DECL.findall(self.persona)[0][0])
        # 裁决措辞的中英两形都要认:`2/3 Majority Consensus` / `2 路→2/3 多数`
        dens = re.findall(r"(\d)\s*/\s*(\d)\s*(?:Majority|多数)", self.persona)
        self.assertTrue(dens, "persona 未出现「N/M 多数共识」措辞,判据需重估")
        for num, den in dens:
            with self.subTest(裁决=f"{num}/{den}"):
                self.assertEqual(cap, int(den),
                    f"总发射上限 {cap} 与裁决分母 {den} 不一致 —— "
                    f"补派会让「{num}/{den} 共识」的分母被改写")
        self.assertGreaterEqual(cap, 3,
            f"总发射上限 {cap} < 3,字面上三路根本发不齐(persona 自相矛盾)")

    def test_T3_supplements_count_toward_cap(self):
        """必须明写补派**计入**总数上限,否则 agent 会把补派当额外配额(A8 的直接成因)。

        判据修正(红队 ba16b403 变体 V3 实证空壳):初版正则
        `上限[^。\\n]{0,20}含补派` 会命中 T1 那行声明里的「(含补派)」三个字,
        于是**把「补派计入总额」整条删掉仍然全绿**。现在锚定「补派计入/算入」这个
        **动作词**,并要求它出现在同一条 bullet 内。
        """
        self.assertRegex(
            self.persona, r"补派[^。\n]{0,10}(?:计入|算入)[^。\n]{0,20}总额|补派[^。\n]{0,20}计入[^。\n]{0,20}(?:总发射|这 3 次)",
            "persona 未写明「补派计入总额」—— agent 会把补派当额外配额,"
            "实测 11/30(36.7%)的采样因此超出 3 路")

    def test_T4_records_actual_emission_count(self):
        """必须要求记录实际发射数,使超限可被**事后审计**(B6:纯 prompt 无拦截 → 至少要可观测)。

        判据修正(红队 ba16b403 变体 V4 实证空壳):初版只搜「记录…发射数」,
        而 T6 那句「标识里的路数必须等于实际发射数」也含这四个字 → 删掉本条仍全绿。
        现在锚定**记录这个动作**本身(「记录」+「发射」),而不是「发射数」这个词。
        """
        self.assertRegex(
            self.persona, r"记录[^。\n]{0,25}发射|记下[^。\n]{0,25}发射|发射[^。\n]{0,10}(?:数|次数)[^。\n]{0,20}记",
            "persona 未要求记录实际发射数 —— 超出 3 路的采样无法事后审计,"
            "只能靠人翻 jsonl(实测正是这样发现的)")
        # 且必须说明**记在哪** —— 不落点的记录要求等于没要求
        self.assertRegex(
            self.persona, r"记(?:录|下)[^。\n]{0,40}(?:随结论|附在|写进|字段|行末|随裁决|结论中)",
            "persona 只说「记录」却没说记在哪 —— §一 要求首行是 `[JEV: X]`,"
            "把数字塞进首行会污染 extract_route 的取址(它取首个匹配)")

    def test_T5_no_contradictory_cap_numbers(self):
        """**声明**里不得残留与 N=3 矛盾的「上限 2 次」类数字。

        同样排除正文引述 —— persona 记录缺陷由来时会引用旧数字,那是历史,不是现行约束。
        """
        for m in self.CAP_DECL.finditer(self.persona):
            n = int(m.group(1))
            self.assertGreaterEqual(
                n, 3,
                f"persona 声明「总发射上限 {n} 次」,与 3 路采样矛盾"
                f"(截取:…{self.persona[max(0, m.start() - 30):m.end() + 20]}…)")


    def test_T6_route_number_must_match_actual_emission(self):
        """自查发现:若超限到 4 路,`3/3` 标识仍写「3」,而判分器 `is_three_path`
        **只按前缀判多路、不校验数字** —— 标识无法表达真实路数,机器不会拦。

        因此 persona 必须显式要求「标识里的路数 = 实际发射数」,
        否则就是 persona 承诺(可审计)与判分器能力(不校验)之间的又一处「验证剧场」。
        """
        self.assertRegex(
            self.persona, r"标识(?:里|中|中的)?[^。\n]{0,10}路数[^。\n]{0,20}(?:等于|必须)",
            "persona 未要求「标识里的路数 = 实际发射数」—— 判分器只判是否多路、不校验数字,"
            "用 3/3 标注 4 路结果不会被机器拦下")
        self.assertRegex(
            self.persona, r"不校验数字|不会(?:被)?机器拦下|机器不会拦",
            "persona 未说明判分器不校验标识里的数字 —— 后来的维护者会以为机器能兜住")


if __name__ == "__main__":
    unittest.main(verbosity=2)
