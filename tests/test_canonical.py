from decimal import Decimal
import pytest
from app.canonical import canonical, fingerprint, equivalent, document_diff, _number_token

# --- 等价写法必须吸收（同一业务版本，重跑不重复生差异） ---

def test_field_order_is_equivalent():
    a = {"price": 12.5, "name": "货品", "tags": ["x", "y"]}
    b = {"tags": ["x", "y"], "name": "货品", "price": 12.5}
    assert equivalent(a, b) and fingerprint(a) == fingerprint(b)

def test_numeric_spellings_are_equivalent():
    assert equivalent({"v": 1}, {"v": 1.0})
    assert equivalent({"v": 100}, {"v": 1e2})
    assert equivalent({"v": Decimal("12.50")}, {"v": Decimal("12.5")})
    assert _number_token(Decimal("-0.00")) == "0"

def test_large_integer_exact_equivalence():
    big = 9007199254740993
    assert equivalent({"v": big}, {"v": Decimal(str(big))})
    assert not equivalent({"v": big}, {"v": big + 1})

def test_whitespace_equivalence_bounded():
    # 首尾空白、换行、制表符、连续空白属于等价写法
    assert equivalent({"t": "新品 上市"}, {"t": " 新品  上市 "})
    assert equivalent({"t": "a\nb"}, {"t": "a\tb"})
    # 词内单空格的增减是真实文本变化，不得抹平
    assert not equivalent({"t": "红 色"}, {"t": "红色"})

def test_fingerprint_deterministic_on_rerun():
    a = {"b": [1, {"x": " 12.50 "}], "a": {"k": 2}}
    b = {"a": {"k": 2}, "b": [1, {"x": "12.50"}]}
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a) == fingerprint(a)

def test_nested_equivalence_recurses():
    a = {"o": {"items": [{"id": 1, "v": 2.0}]}}
    b = {"o": {"items": [{"v": 2, "id": 1.0}]}}
    assert equivalent(a, b)

# --- 真实变化一个都不能漏（禁止过度抹平） ---

def test_text_id_not_equivalent_to_number():
    diffs = document_diff({"sku": "00123"}, {"sku": 123})
    assert not equivalent({"sku": "00123"}, {"sku": 123})
    assert diffs[0]["kind"] == "TYPE_CHANGED" and diffs[0]["path"] == "$.sku"
    # 证据保留两侧原值
    assert diffs[0]["left"] == "00123" and diffs[0]["right"] == 123

def test_missing_field_not_equivalent_to_null():
    assert not equivalent({"a": 1, "b": None}, {"a": 1})
    diffs = document_diff({"a": 1, "b": None}, {"a": 1})
    assert diffs[0]["kind"] == "FIELD_MISSING" and diffs[0]["path"] == "$.b"

def test_bool_not_equivalent_to_number():
    assert not equivalent({"f": True}, {"f": 1})
    assert document_diff({"f": True}, {"f": 1})[0]["kind"] == "TYPE_CHANGED"

def test_value_change_is_reported_with_path():
    diffs = document_diff({"price": Decimal("12.50")}, {"price": Decimal("12.60")})
    assert diffs == [{"path": "$.price", "kind": "VALUE_CHANGED",
                      "left": Decimal("12.50"), "right": Decimal("12.60")}]

def test_document_type_change_is_reported():
    diffs = document_diff({"d": {"x": 1}}, {"d": "{}"})
    assert diffs[0]["kind"] == "TYPE_CHANGED" and diffs[0]["path"] == "$.d"

def test_array_length_and_order_are_significant():
    assert not equivalent({"t": [1, 2]}, {"t": [1, 2, 3]})
    assert not equivalent({"t": [1, 2]}, {"t": [2, 1]})
    assert document_diff({"t": [1, 2]}, {"t": [1, 2, 3]})[0]["kind"] == "LENGTH_MISMATCH"

def test_null_distinct_from_empty_string():
    assert not equivalent(None, "")
    assert document_diff(None, "")[0]["kind"] == "TYPE_CHANGED"

def test_equivalent_inputs_produce_no_diff():
    assert document_diff({"a": 1, "b": "x y"}, {"b": " x  y ", "a": 1.0}) == []

def test_original_document_not_mutated():
    original = {"z": [1, 2], "a": " x "}
    canonical(original); fingerprint(original); document_diff(original, dict(original))
    assert original == {"z": [1, 2], "a": " x "}

def test_depth_guard():
    deep = {"k": 1}
    for _ in range(40):
        deep = {"k": deep}
    with pytest.raises(ValueError):
        canonical(deep)
