"""深度剥离透明合成（depth peeling）的离线参考实现。

数据约定
--------
- 片元：``{"depth": float, "rgba": tuple[float, float, float, float]}``。
- ``depth`` 取值 0..1：0 是最近层，1 是最远层。
- ``rgba`` 为**预乘 alpha** 颜色：``r, g, b`` 已经乘过 ``a``，四个分量均在
  0..1；因此 ``r, g, b`` 不会大于 ``a``。
- 层：片元的 ``list``，列表顺序为从前往后（front-to-back）；合成时从
  后往前（back-to-front）遍历。
- 除 ``depth_epsilon`` 外，所有浮点比较的绝对容差均为 ``1e-9``。

实现约束
--------
- 只使用标准库 ``math``；不要修改输入 list 或片元 dict。
"""

TOL = 1e-9


def _over(src, dst):
    """预乘 alpha 的 over 合成：src over dst，alpha 只乘一次。"""
    sr, sg, sb, sa = src
    dr, dg, db, da = dst
    one_minus_a = 1.0 - sa
    return (
        sr + dr * one_minus_a,
        sg + dg * one_minus_a,
        sb + db * one_minus_a,
        sa + da * one_minus_a,
    )


def sort_layers(fragments):
    """按 depth 升序稳定排序片元。

    参数
    ----
    fragments : list[dict]
        待排序片元；不得原地修改。

    返回
    ----
    list[dict]
        新列表，按 ``depth`` 升序；深度相等（``abs(d1 - d2) <= 1e-9``）
        的片元保持输入中的相对顺序（稳定排序）。

    容差
    ----
    1e-9。
    """
    # 按输入顺序把容差内相等的深度归入同一组，组内保持输入顺序，
    # 再按各组首个片元的深度排序，从而实现带容差的稳定排序。
    groups = []  # [(anchor_depth, [fragment, ...]), ...]
    for fragment in fragments:
        depth = fragment["depth"]
        for anchor, members in groups:
            if abs(depth - anchor) <= TOL:
                members.append(fragment)
                break
        else:
            groups.append((depth, [fragment]))

    groups.sort(key=lambda group: group[0])

    ordered = []
    for _, members in groups:
        ordered.extend(members)
    return ordered


def peel(fragments, layers):
    """深度剥离：最多产出 ``layers`` 层，每层一个片元。

    契约
    ----
    - 每轮在剩余片元中取 ``depth`` 最小者；并列时取输入顺序中最早者。
    - 被选中的片元单独组成一层（``[fragment]``），并立即从剩余集合中
      移除，后续层不得重复出现。
    - 返回 ``list[list[dict]]``，外层按剥离顺序排列，层深度非递减。
    - ``layers <= 0`` 返回 ``[]``；剩余片元不足 ``layers`` 时不产生空层。
    - 不修改 ``fragments``；未剥离数量可由
      ``len(fragments) - sum(len(layer) for layer in result)`` 计算。
    - 深度相等按 1e-9 容差判定。
    """
    if layers <= 0:
        return []

    # 用下标列表表示“剩余集合”，每轮弹出被选中的下标——剥离即移除，
    # 同深度片元因此会一轮一个、按输入顺序逐层消耗。
    remaining = list(range(len(fragments)))
    result = []

    for _ in range(layers):
        if not remaining:
            break

        best_pos = 0
        best_depth = fragments[remaining[0]]["depth"]
        for pos in range(1, len(remaining)):
            depth = fragments[remaining[pos]]["depth"]
            # 仅当严格更小（超出容差）才替换；容差内相等保留更早的片元。
            if depth < best_depth - TOL:
                best_pos = pos
                best_depth = depth

        index = remaining.pop(best_pos)
        result.append([fragments[index]])

    return result


def resolve_layer(layer, background):
    """把同一层内的片元按预乘 alpha 的 over 合成到背景上。

    参数
    ----
    layer : list[dict]
        层内片元，列表顺序为从前往后。
    background : tuple[float, float, float, float]
        预乘 RGBA 背景，分量 0..1。

    返回
    ----
    tuple[float, float, float, float]
        预乘 RGBA。合成从后往前：对层内片元逆序遍历，逐个执行
        ``out = src + dst * (1 - src.a)``（逐分量，alpha 同理）。
        空层返回背景。

    容差
    ----
    1e-9。
    """
    out = tuple(background)
    for fragment in reversed(layer):
        out = _over(fragment["rgba"], out)
    return out


def combine(layers, background):
    """从后到前合成所有层，并保留背景 alpha 贡献。

    参数
    ----
    layers : list[list[dict]]
        层列表，``layers[0]`` 为最前层；层内列表同样从前往后。
    background : tuple[float, float, float, float]
        预乘 RGBA 背景，分量 0..1。

    返回
    ----
    tuple[float, float, float, float]
        预乘 RGBA。先逆序遍历层（最后层最先合成），层内再逆序遍历片元，
        每个片元执行一次 over：``out = src + dst * (1 - src.a)``。
        背景作为初始 dst 参与合成，其 alpha 不得丢弃；层 alpha 只乘一次。
        空 ``layers`` 返回背景。

    容差
    ----
    1e-9。
    """
    out = tuple(background)
    for layer in reversed(layers):
        for fragment in reversed(layer):
            out = _over(fragment["rgba"], out)
    return out


def reference(fragments, background):
    """暴力参考解：稳定排序后从后到前逐片元 over 合成。

    - 先按 ``depth`` 升序稳定排序（同深度保持输入顺序），再从后往前合成。
    - 与 ``combine(peel(fragments, len(fragments)), background)`` 在所有
      片元都被剥离时应一致。
    - 返回预乘 RGBA ``tuple``；容差 1e-9。
    """
    out = tuple(background)
    for fragment in reversed(sort_layers(fragments)):
        out = _over(fragment["rgba"], out)
    return out


def depth_epsilon(scale):
    """返回与相机深度精度尺度相关的“深度相等”阈值。

    ``scale`` 是相机深度精度尺度（世界空间深度量级，例如由 near/far
    决定的距离），要求 ``scale >= 0``。阈值按 24 位深度缓冲的量化步长
    随尺度缩放：

        max(1e-9, abs(scale) * 2**-24)

    因此 ``scale`` 为 0 时退化为 1e-9 下限，远距离时阈值线性增大，
    不会用一个固定常量把远近不同的层错误合并。
    """
    return max(TOL, abs(scale) * 2.0 ** -24)


def layer_stats(layers):
    """统计每层片元数与总覆盖。

    返回 dict
    ---------
    - ``layer_count``：层数。
    - ``counts``：每层片元数组成的 list。
    - ``fragment_count``：片元总数。
    - ``coverage``：所有片元 alpha 的并集覆盖率
      ``1 - prod(1 - a_i)``，截断到 [0, 1]；无片元时为 ``0.0``。
      重叠片元只计一次，覆盖率不会超过 1。

    容差
    ----
    1e-9。
    """
    counts = [len(layer) for layer in layers]
    fragment_count = sum(counts)

    if fragment_count == 0:
        coverage = 0.0
    else:
        unseen = 1.0
        for layer in layers:
            for fragment in layer:
                unseen *= 1.0 - fragment["rgba"][3]
        coverage = 1.0 - unseen
        coverage = min(1.0, max(0.0, coverage))

    return {
        "layer_count": len(layers),
        "counts": counts,
        "fragment_count": fragment_count,
        "coverage": coverage,
    }


def validate_layers(layers, max_layers):
    """检查剥离层是否合法，返回错误码列表（合法时为空 list）。

    检查项
    ------
    - ``len(layers) > max_layers``：追加 ``"layer_count_exceeded"``。
    - 空层：追加 ``"empty_layer:{i}"``。
    - 层深度非递增：层深度取该层第一个片元的 ``depth``；若
      ``depth[i] < depth[i-1] - 1e-9``，追加 ``"depth_order:{i}"``
      （比较时跳过空层）。
    - 错误码按“层数 → 空层（下标升序）→ 深度顺序（下标升序）”排列，
      每项只报告一次。

    容差
    ----
    1e-9。
    """
    errors = []

    if len(layers) > max_layers:
        errors.append("layer_count_exceeded")

    for index, layer in enumerate(layers):
        if len(layer) == 0:
            errors.append("empty_layer:{0}".format(index))

    previous_depth = None
    for index, layer in enumerate(layers):
        if len(layer) == 0:
            # 空层不参与深度递增比较。
            continue
        depth = layer[0]["depth"]
        if previous_depth is not None and depth < previous_depth - TOL:
            errors.append("depth_order:{0}".format(index))
        previous_depth = depth

    return errors
