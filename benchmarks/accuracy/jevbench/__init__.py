# -*- coding: utf-8 -*-
"""JEV 准确率基准:参数化出题器 + 参考解 + 程序化判分器。

- solve    参考解(Decimal 精确运算,题面口径的唯一正典)
- cases    参数化出题器(同 seed 逐字节确定)
- extract  从模型输出中抽取最终 JSON / JEV 路由标识
- grading  判分、配置间配对比较、难度筛选、门控评分、判分器自检
- stats    Wilson 置信区间、McNemar 精确检验
"""
SUITE_VERSION = 1
