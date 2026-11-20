"""业务版本同一性裁决（M3 版本冲突 / M4 可见性 / M7 归档凭据共用）。

目标：
- 吸收等价写法造成的虚假差异：JSON 字段顺序、数字的等价写法（1 与 1.00、
  超大整数、科学计数法）、字符串与键中的空白/换行差异。
- 绝不抹平真实变化：文本编号不与数字等价、字段缺失不与显式 null 等价、
  布尔不与数字等价、正文类型（对象/数组/标量）改变必须报差异。
- 不修改原始 document：原始 JSON 原文经各阶段原样保留，本模块只产出
  规范指纹与结构化差异，供页面裁决与归档证据同时引用。
"""
import hashlib
import json
from decimal import Decimal, InvalidOperation

# 防御异常深度输入；4MB 上限下正常正文远低于此值。
_MAX_DEPTH = 32


def _collapse_whitespace(text):
    # 等价的空白仅限：换行/制表符与空格互转、连续空白折叠、首尾空白去除。
    # 词内单空格是正文内容（"红 色" 与 "红色" 是不同文本），故折叠为单空格而非删除。
    return " ".join(str(text).split())


def canonical(value, depth=0):
    """返回带类型标签的规范结构：只做等价归一，绝不跨 JSON 类型判等。

    - dict：递归规范后按键排序（吸收字段顺序差异）。
    - list：递归规范，顺序保留（数组位置是有业务含义的）。
    - 数字（int/float/Decimal）：按 Decimal 精确归一为统一写法，避免浮点与
      超大整数精度损失；bool 是 int 子类，必须先行拦截。
    - 字符串：仅做空白归一，保留文本身份（"1" 不会变成数字 1）。
    - None/bool：原样保留类型。
    每个标量带显式类型标签，保证文本编号、显式 null、布尔等不被数字抹平原。
    """
    if depth > _MAX_DEPTH:
        raise ValueError("DOCUMENT_TOO_DEEP")
    if value is None:
        return {"__t__": "null", "v": None}
    if isinstance(value, bool):
        return {"__t__": "bool", "v": value}
    if isinstance(value, (int, float, Decimal)):
        return {"__t__": "number", "v": _number_token(value)}
    if isinstance(value, str):
        return {"__t__": "string", "v": _collapse_whitespace(value)}
    if isinstance(value, dict):
        return {_collapse_whitespace(k): canonical(v, depth + 1) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [canonical(v, depth + 1) for v in value]
    # 非 JSON 原生类型不静默吞掉，按字符串形态保留并标记，避免误判等价。
    return {"__t__": "unknown:" + type(value).__name__, "v": _collapse_whitespace(str(value))}


def _number_token(value):
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        # 无法作为数字精确解析时，退回字符串归一，不冒充数字。
        return _collapse_whitespace(str(value))
    if not decimal.is_finite():
        return _collapse_whitespace(str(value))
    # 去除尾随零与指数写法，1、1.0、1.00 归一到同一 token。
    normalized = decimal.normalize()
    token = format(normalized, "f")
    if "." in token:
        token = token.rstrip("0").rstrip(".")
    if token in ("", "-0"):
        token = "0"
    return token


def fingerprint(document):
    """业务正文指纹：等价正文（含 op 无关的 document 部分）得到同一稳定指纹。

    原始 document 不被修改；指纹仅用于同一性裁决与归档对照。
    """
    canonical_json = json.dumps(canonical(document), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def equivalent(left, right):
    """两份正文是否属于同一业务版本（规范结构相等，类型不被抹平）。"""
    return canonical(left) == canonical(right)


def _type_name(value):
    """原始值的 JSON 类型名（bool 先于 int，Decimal 归入 number）。"""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float, Decimal)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    return "unknown:" + type(value).__name__


def document_diff(left, right, path="$"):
    """结构化差异：仅报告真实变化，等价写法不产生条目。

    每个条目含 path / kind / left / right（原值，可回溯）：
    - VALUE_CHANGED   同路径同类型但值真实不同（数字按精确值比较，空白忽略）
    - TYPE_CHANGED    同路径 JSON 类型不同（含 文本编号 vs 数字、布尔 vs 数字）
    - FIELD_MISSING   一侧缺字段（缺失不与显式 null 混同）
    - LENGTH_MISMATCH 数组长度不同
    - ITEM_CHANGED    数组同位置元素不同
    空白归一与数字等价由 canonical 吸收，故纯空白/等价数字写法不会出现在结果里。
    输出中的 left/right 一律取自原始 document，不做任何改写。
    """
    changes = []
    left_type = _type_name(left)
    right_type = _type_name(right)

    if left_type != right_type:
        changes.append({"path": path, "kind": "TYPE_CHANGED", "left": left, "right": right})
        return changes

    if left_type == "object":
        for key in sorted(set(left) | set(right), key=str):
            child_path = f"{path}.{key}"
            if key not in left:
                changes.append({"path": child_path, "kind": "FIELD_MISSING", "left": None, "right": right[key]})
            elif key not in right:
                changes.append({"path": child_path, "kind": "FIELD_MISSING", "left": left[key], "right": None})
            else:
                changes.extend(document_diff(left[key], right[key], child_path))
        return changes

    if left_type == "array":
        if len(left) != len(right):
            changes.append({"path": path, "kind": "LENGTH_MISMATCH", "left": left, "right": right})
            return changes
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            child_path = f"{path}[{index}]"
            if not equivalent(left_item, right_item):
                if _type_name(left_item) != _type_name(right_item):
                    changes.append({"path": child_path, "kind": "TYPE_CHANGED", "left": left_item, "right": right_item})
                elif _type_name(left_item) in {"object", "array"}:
                    changes.extend(document_diff(left_item, right_item, child_path))
                else:
                    changes.append({"path": child_path, "kind": "ITEM_CHANGED", "left": left_item, "right": right_item})
        return changes

    if not equivalent(left, right):
        changes.append({"path": path, "kind": "VALUE_CHANGED", "left": left, "right": right})
    return changes
