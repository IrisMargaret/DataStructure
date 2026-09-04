# -*- coding: utf-8 -*-
"""复杂布尔查询解析器（递归下降法）。

支持 AND / OR / NOT 与括号分组，例如：
    graph AND (neural OR network) NOT survey
    (transformer OR "large language model") NOT survey

文法（BNF）:
    or_expr  := and_expr (OR and_expr)*
    and_expr := not_expr (AND not_expr | 隐式 AND not_expr)*
    not_expr := NOT not_expr | atom
    atom     := '(' or_expr ')' | TERM

AST 节点用元组表示：
    ("term", word)         词条
    ("and",  L, R)         逻辑与
    ("or",   L, R)         逻辑或
    ("not",  X)            逻辑非

求值时将 AST 转化为集合运算：
    AND -> 交集 & , OR -> 并集 | , NOT -> 全集中差集 -
"""

import re

# 运算符常量
AND = "AND"
OR = "OR"
NOT = "NOT"

# 词法：双引号短语 / 左右括号 / 其他非空白、非括号字符序列
_TOKEN_RE = re.compile(r'"[^"]+"|\(|\)|[^\s()]+')


class QuerySyntaxError(ValueError):
    """查询语法错误（非法括号、孤立运算符等）。"""


class QueryParser:
    """递归下降解析器：query string -> AST。"""

    def __init__(self, query):
        self.tokens = self._tokenize(query)
        self.pos = 0

    @staticmethod
    def _tokenize(query):
        """词法分析：切分为 token 列表，双引号短语视为一个整体词条。"""
        tokens = []
        for match in _TOKEN_RE.finditer(query or ""):
            raw = match.group(0)
            if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
                tokens.append(raw[1:-1].strip().lower())
            else:
                tokens.append(raw)
        return tokens

    def parse(self):
        """解析完整查询，返回 AST 根节点。"""
        if not self.tokens:
            raise QuerySyntaxError("查询内容为空")
        node = self._parse_or()
        if self.pos != len(self.tokens):
            raise QuerySyntaxError(f"存在无法解析的内容: {self.tokens[self.pos:]}")
        return node

    # ---------- 语法分析（递归下降） ----------

    def _peek(self):
        """查看当前 token（不消费）。"""
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _next(self):
        """消费并返回当前 token。"""
        token = self._peek()
        self.pos += 1
        return token

    def _parse_or(self):
        """or_expr := and_expr (OR and_expr)*"""
        left = self._parse_and()
        while self._peek_is(OR):
            self._next()
            right = self._parse_and()
            left = ("or", left, right)
        return left

    def _parse_and(self):
        """and_expr := not_expr ((AND | 隐式) not_expr)*

        相邻关键词之间未写 AND 时按 AND 处理，如 "graph neural"。
        """
        left = self._parse_not()
        while True:
            token = self._peek()
            if token is None:
                break
            upper = token.upper()
            if upper == OR or token == ")":
                break            # 属于外层 or_expr / 括号，停止
            if upper == AND:
                self._next()
                right = self._parse_not()
                left = ("and", left, right)
            else:
                # 隐式 AND：相邻关键词、左括号或 NOT 均视为逻辑与。
                # 注意不能预消费 token：NOT 前缀必须由 _parse_not 识别。
                right = self._parse_not()
                left = ("and", left, right)
        return left

    def _parse_not(self):
        """not_expr := NOT not_expr | atom"""
        if self._peek_is(NOT):
            self._next()
            return ("not", self._parse_not())
        return self._parse_atom()

    def _parse_atom(self):
        """atom := '(' or_expr ')' | TERM"""
        token = self._next()
        if token is None:
            raise QuerySyntaxError("表达式意外结束")
        if token == "(":
            node = self._parse_or()
            if self._next() != ")":
                raise QuerySyntaxError("缺少右括号 ')'")
            return node
        if token == ")":
            raise QuerySyntaxError("多余的右括号 ')'")
        if token.upper() in (AND, OR, NOT):
            raise QuerySyntaxError(f"运算符 {token} 的位置非法")
        return ("term", token.strip().lower())

    def _peek_is(self, op):
        """判断当前 token 是否为指定运算符（忽略大小写）。"""
        token = self._peek()
        return token is not None and token.upper() == op


# ---------- 求值：AST -> 集合运算 ----------

def evaluate_ast(node, term_set_fn, universe):
    """递归求值 AST，返回论文 ID 集合。

    参数:
        node:        解析器生成的 AST 节点。
        term_set_fn: 词条 -> 包含该词的论文 ID 集合 的函数。
        universe:    全部论文 ID 集合（用于 NOT 求差集）。
    """
    kind = node[0]
    if kind == "term":
        return term_set_fn(node[1])
    if kind == "not":
        return universe - evaluate_ast(node[1], term_set_fn, universe)
    if kind == "and":
        return (evaluate_ast(node[1], term_set_fn, universe)
                & evaluate_ast(node[2], term_set_fn, universe))
    if kind == "or":
        return (evaluate_ast(node[1], term_set_fn, universe)
                | evaluate_ast(node[2], term_set_fn, universe))
    raise QuerySyntaxError(f"未知 AST 节点类型: {kind}")


def collect_terms(node):
    """收集 AST 中出现的全部叶子词条（用于结果页展示匹配词与评分）。"""
    terms = []

    def walk(n):
        if n[0] == "term":
            terms.append(n[1])
        elif n[0] == "not":
            walk(n[1])
        else:
            walk(n[1])
            walk(n[2])

    walk(node)
    # 去重且保持顺序
    seen = set()
    result = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result
