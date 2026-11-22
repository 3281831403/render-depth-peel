# render-depth-peel

## 题面

换成深度剥离做透明后，叠三层以上就开始发亮、层数一多还丢背景：剥离时每层处理完不把该片元从列表中移除，第一层被重复剥离 N 次；单层 over 合成写成 dst = src*a + dst，漏乘 (1-a)，背景不透、整体偏亮；combine 从前到后合成，顺序反了，结果与参考解不符；combine 在每层把层 alpha 与背景 alpha 两次相乘，双重 alpha，边缘发暗；sort_layers 用了不稳定的排序，深度相等的片元顺序不定，参考解对比随机失败；peel 用严格 < 比较深度，同一深度的一叠透明面只剥离最前一个然后跳层；depth_epsilon 与相机 near/far 精度无关（固定 1e-6），远距离精度不够、层被错误合并；layer_stats 的覆盖率把重叠片元重复计数，覆盖率可以 > 1；validate_layers 只检查层数、不检查层深度递增，错误剥离顺序未被发现；combine 丢弃最后一层之后的背景 alpha 贡献，背景没有参与最终合成。关键是与参考解对齐：顺序、alpha 只乘一次、同深度要逐层消耗。deeppeel/peel.py 是核心，tests/test_peel.py 15个红。要修的是：让剥离即移除、over 补回 (1-a)、combine 后到前且 alpha 只乘一次、同深度按输入顺序逐层消耗、depth_epsilon 随相机精度缩放、覆盖率按并集去重、validate_layers 校验深度递增、背景 alpha 参与合成，直到 15 个测试全绿。

## 运行方式

在仓库根目录执行：

```bash
python -m pytest tests -q
```

初始状态下 8 个函数全部是 `raise NotImplementedError` 桩，预期输出恰好是：

```text
15 failed
```

要求没有 collection / import / syntax error；15 个失败都由测试调用桩触发（`NotImplementedError`），而不是测试文件本身出错。实现 `deeppeel/peel.py` 后预期变为 `15 passed`。

## 数据约定

- 片元：`{"depth": float, "rgba": (r, g, b, a)}`。
- `depth` 取值 0..1：0 为最近层，1 为最远层。
- `rgba` 为预乘 alpha 颜色：`r, g, b` 已乘以 `a`，四个分量均为 0..1 且 `r, g, b <= a`。
- 层是片元的 `list`，列表顺序为从前往后；`combine` 必须从后往前合成。
- 除 `depth_epsilon` 自身外，浮点比较容差一律为 `1e-9`。
- 只使用标准库 `math` 和 pytest，离线、无随机。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 游戏、图形与多媒体 |
| 子方向 | 图形渲染 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

## tests 不可修改

`tests/test_peel.py` 是评测基准：其中 10 个测试分别对应上面 10 个缺陷，另 5 个测试覆盖基础契约（不透明单层、0.5/0.5 解析值、剥离层深度非递减、与参考解 8 层内对齐、层数耗尽后的剩余片元）。**不允许修改 tests**，只能实现 `deeppeel/peel.py`。
