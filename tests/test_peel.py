"""render-depth-peel 评测：15 个测试覆盖 10 个缺陷与 5 条基础契约。

所有测试在初始状态下都调用 ``deeppeel.peel`` 中的桩，因此必定失败。
"""

import math

from deeppeel.peel import (
    combine,
    depth_epsilon,
    layer_stats,
    peel,
    reference,
    resolve_layer,
    sort_layers,
    validate_layers,
)

TOL = 1e-9


def premultiplied(rgb, alpha):
    """把直通 RGB 与 alpha 转成预乘 RGBA。"""
    r, g, b = rgb
    return (r * alpha, g * alpha, b * alpha, alpha)


def fragment(depth, rgb=(0.0, 0.0, 1.0), alpha=1.0):
    """构造一个契约规定的片元 dict（depth 0..1，alpha 0..1）。"""
    return {"depth": float(depth), "rgba": premultiplied(rgb, float(alpha))}


def assert_rgba(actual, expected, tol=TOL):
    """断言预乘 RGBA 四元组按绝对容差相等。"""
    assert isinstance(actual, tuple), f"expected tuple, got {type(actual)!r}"
    assert len(actual) == 4, f"expected 4 components, got {actual!r}"
    for got, want in zip(actual, expected):
        assert math.isclose(got, want, rel_tol=0.0, abs_tol=tol), (
            f"RGBA mismatch: got {actual!r}, expected {expected!r}"
        )


# 缺陷 5：sort_layers 对同深度片元不稳定，参考解对比会随机失败。
def test_sort_layers_orders_by_depth_and_preserves_ties():
    first_half = fragment(0.5, (0.2, 0.3, 0.4), 1.0)
    middle_a = fragment(0.2, (0.2, 0.0, 0.0), 1.0)
    second_half = fragment(0.5, (0.4, 0.3, 0.2), 1.0)
    nearest = fragment(0.05, (0.1, 0.1, 0.1), 1.0)
    middle_b = fragment(0.2, (0.0, 0.2, 0.0), 1.0)
    fragments = [first_half, middle_a, second_half, nearest, middle_b]

    ordered = sort_layers(fragments)

    assert [id(item) for item in ordered] == [
        id(nearest),
        id(middle_a),
        id(middle_b),
        id(first_half),
        id(second_half),
    ]
    assert [id(item) for item in fragments] == [
        id(first_half),
        id(middle_a),
        id(second_half),
        id(nearest),
        id(middle_b),
    ]


# 缺陷 1：peel 每层处理完不移除片元，第一层被重复剥离 N 次。
def test_peel_removes_consumed_fragments():
    a = fragment(0.3, (1.0, 0.0, 0.0), 1.0)
    b = fragment(0.1, (0.0, 1.0, 0.0), 1.0)
    c = fragment(0.2, (0.0, 0.0, 1.0), 1.0)
    fragments = [a, b, c]

    layers = peel(fragments, 3)

    assert len(layers) == 3
    assert all(len(layer) == 1 for layer in layers)
    assert [id(layer[0]) for layer in layers] == [id(b), id(c), id(a)]
    assert sum(len(layer) for layer in layers) == 3
    assert [id(item) for item in fragments] == [id(a), id(b), id(c)]


# 缺陷 2：resolve_layer 写成 dst = src*a + dst，漏乘 (1-a)，背景不透、整体偏亮。
def test_resolve_layer_source_over_premultiplied():
    layer = [fragment(0.5, (1.0, 0.0, 0.0), 0.5)]

    result = resolve_layer(layer, (0.0, 0.0, 1.0, 1.0))

    assert_rgba(result, (0.5, 0.0, 0.5, 1.0))


# 缺陷 3：combine 从前到后合成，顺序反了。
def test_combine_composites_back_to_front():
    front = [fragment(0.1, (1.0, 0.0, 0.0), 0.5)]
    back = [fragment(0.9, (0.0, 0.0, 1.0), 0.5)]

    result = combine([front, back], (0.0, 0.0, 0.0, 1.0))

    assert_rgba(result, (0.5, 0.0, 0.25, 1.0))


# 缺陷 4：combine 每层把层 alpha 与背景 alpha 两次相乘，双重 alpha，边缘发暗。
def test_combine_applies_alpha_once():
    layer = [fragment(0.4, (1.0, 0.0, 0.0), 0.5)]

    result = combine([layer], (1.0, 1.0, 1.0, 1.0))

    assert_rgba(result, (1.0, 0.5, 0.5, 1.0))


# 缺陷 6：peel 用严格 < 比较深度，同深度的一叠透明面只剥一个就跳层。
def test_peel_consumes_equal_depth_stack_layer_by_layer():
    a = fragment(0.6, (1.0, 0.0, 0.0), 1.0)
    b = fragment(0.2, (0.0, 1.0, 0.0), 0.4)
    c = fragment(0.2, (0.0, 0.0, 1.0), 0.4)
    d = fragment(0.2, (1.0, 1.0, 0.0), 0.4)
    e = fragment(0.9, (1.0, 0.0, 1.0), 0.4)

    layers = peel([a, b, c, d, e], 8)

    assert [len(layer) for layer in layers] == [1, 1, 1, 1, 1]
    assert [id(layer[0]) for layer in layers] == [id(b), id(c), id(d), id(a), id(e)]
    assert [layer[0]["depth"] for layer in layers] == [0.2, 0.2, 0.2, 0.6, 0.9]


# 缺陷 7：depth_epsilon 与相机 near/far 精度无关（固定 1e-6），远距离层被合并。
def test_depth_epsilon_scales_with_camera_precision():
    huge = 1.0e6
    expected_huge = max(1e-9, abs(huge) * 2.0**-24)

    assert math.isclose(
        depth_epsilon(huge), expected_huge, rel_tol=1e-12, abs_tol=0.0
    )
    assert depth_epsilon(huge) > depth_epsilon(1.0e4) > depth_epsilon(1.0)
    assert math.isclose(depth_epsilon(0.0), 1e-9, rel_tol=0.0, abs_tol=0.0)
    assert math.isclose(depth_epsilon(1e-12), 1e-9, rel_tol=0.0, abs_tol=0.0)


# 缺陷 8：layer_stats 把重叠片元重复计入覆盖率，覆盖率可以 > 1。
def test_layer_stats_coverage_counts_overlap_once():
    stats = layer_stats(
        [
            [fragment(0.5, alpha=0.5)],
            [fragment(0.5, alpha=0.5), fragment(0.5, alpha=0.5)],
        ]
    )

    assert stats["layer_count"] == 2
    assert stats["counts"] == [1, 2]
    assert stats["fragment_count"] == 3
    assert math.isclose(stats["coverage"], 0.875, rel_tol=0.0, abs_tol=TOL)

    many = [[fragment(0.5, alpha=0.2) for _ in range(20)]]
    many_stats = layer_stats(many)
    assert math.isclose(
        many_stats["coverage"], 1.0 - 0.8**20, rel_tol=0.0, abs_tol=TOL
    )
    assert 0.0 <= many_stats["coverage"] <= 1.0


# 缺陷 9：validate_layers 只检查层数，不检查层深度递增。
def test_validate_layers_detects_depth_order():
    ordered = [[fragment(0.1)], [fragment(0.2)], [fragment(0.4)]]
    assert validate_layers(ordered, 5) == []

    decreasing = [[fragment(0.4)], [fragment(0.1)]]
    errors = validate_layers(decreasing, 5)
    assert "depth_order:1" in errors

    too_many = [[fragment(0.1)], [fragment(0.2)], [fragment(0.3)]]
    assert "layer_count_exceeded" in validate_layers(too_many, 2)

    with_empty = [[], [fragment(0.5)]]
    assert "empty_layer:0" in validate_layers(with_empty, 5)


# 缺陷 10：combine 丢弃最后一层之后的背景 alpha 贡献，背景未参与最终合成。
def test_combine_keeps_background_alpha():
    layer = [fragment(0.2, (1.0, 0.0, 0.0), 0.5)]

    result = combine([layer], (0.05, 0.10, 0.15, 0.25))

    assert_rgba(result, (0.525, 0.05, 0.075, 0.625))


# 基础契约：单层不透明片元结果等于该片元颜色。
def test_single_opaque_fragment_returns_its_color():
    opaque = fragment(0.3, (0.2, 0.4, 0.6), 1.0)

    result = combine([[opaque]], (0.9, 0.1, 0.5, 0.4))

    assert_rgba(result, (0.2, 0.4, 0.6, 1.0))


# 基础契约：两层半透明（0.5/0.5）合成结果与解析值一致。
def test_two_half_alpha_layers_analytic():
    front = [fragment(0.2, (1.0, 0.0, 0.0), 0.5)]
    back = [fragment(0.8, (0.0, 1.0, 0.0), 0.5)]

    result = combine([front, back], (0.0, 0.0, 0.0, 0.0))

    assert_rgba(result, (0.5, 0.25, 0.0, 0.75))


# 基础契约：peel 后的层深度非递减。
def test_peel_layer_depths_are_non_decreasing():
    fragments = [fragment(depth) for depth in (0.8, 0.2, 0.5, 0.2, 0.9, 0.5)]

    layers = peel(fragments, 8)

    assert len(layers) == 6
    assert sum(len(layer) for layer in layers) == 6
    layer_depths = [layer[0]["depth"] for layer in layers]
    assert layer_depths == sorted(layer_depths)
    assert all(a <= b for a, b in zip(layer_depths, layer_depths[1:]))


# 基础契约：参考解与剥离解在 8 层内误差 < 1e-9。
def test_peel_matches_reference_with_eight_layers():
    specs = [
        (0.05, (1.0, 0.0, 0.0), 0.6),
        (0.15, (0.0, 1.0, 0.0), 0.5),
        (0.25, (0.0, 0.0, 1.0), 0.4),
        (0.35, (1.0, 1.0, 0.0), 0.3),
        (0.45, (1.0, 0.0, 1.0), 0.2),
        (0.55, (0.0, 1.0, 1.0), 0.5),
        (0.65, (0.5, 0.5, 0.5), 0.9),
        (0.75, (1.0, 0.5, 0.0), 0.1),
    ]
    fragments = [fragment(depth, rgb, alpha) for depth, rgb, alpha in specs]
    background = (0.10, 0.20, 0.30, 0.45)

    layers = peel(fragments, 8)
    assert sum(len(layer) for layer in layers) == 8

    assert_rgba(combine(layers, background), reference(fragments, background))


# 基础契约：层数耗尽（片元数 > layers）时被剥离的片元可检测。
def test_peel_detects_leftover_fragments_when_layers_exhausted():
    fragments = [fragment(depth) for depth in (0.6, 0.1, 0.5, 0.2, 0.4, 0.3)]

    layers = peel(fragments, 4)

    assert len(layers) == 4
    peeled = [layer[0] for layer in layers]
    assert sum(len(layer) for layer in layers) == 4
    remaining = len(fragments) - sum(len(layer) for layer in layers)
    assert remaining == 2
    assert [id(item) for item in peeled] == [
        id(fragments[1]),
        id(fragments[3]),
        id(fragments[5]),
        id(fragments[4]),
    ]
    assert [item["depth"] for item in peeled] == [0.1, 0.2, 0.3, 0.4]
