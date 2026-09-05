# -*- coding: utf-8 -*-
"""Porter 词干提取算法（手写实现）。

参考 Martin Porter (1980) 的经典算法：按“辅元音结构计数 m”分段规则
依次剥离常见词缀（Step 1a/1b/1c/2/3/4/5a/5b）。

约定：
- 仅处理拉丁字母词；长度 < 4 或含数字/连字符的词不词干
  （保护 ai、cnn、3d、state-of-the-art 这类短词/专名不被误伤）；
- 中文词不经由此模块（由 Preprocessor 分流）。
"""


class PorterStemmer:
    """手写 Porter 词干提取器（无第三方依赖）。"""

    def __init__(self):
        self._b = []  # 词干缓冲区（字符数组）
        self._k = 0   # 当前词干末尾下标
        self._j = 0   # 一般偏移（记录后缀起始位置）

    # ---------------- 内部判定原语 ----------------

    def _cons(self, i):
        """b[i] 是否为辅音（含规则：y 视前一字符而定）。"""
        ch = self._b[i]
        if ch in "aeiou":
            return False
        if ch == "y":
            return True if i == 0 else not self._cons(i - 1)
        return True

    def _m(self):
        """度量 m：词干 0..j 区间内 VC（元辅音交替）序列数。

        例如 tree -> 0，troubles -> 1，troublesome -> 2，o -> 0。
        """
        n = 0
        i = 0
        while True:
            if i > self._j:
                return n
            if not self._cons(i):
                break
            i += 1
        i += 1
        while True:
            while True:
                if i > self._j:
                    return n
                if self._cons(i):
                    break
                i += 1
            i += 1
            n += 1
            while True:
                if i > self._j:
                    return n
                if not self._cons(i):
                    break
                i += 1
            i += 1

    def _vowel_in_stem(self):
        """词干 0..j 中是否含元音（条件 *v*）。"""
        return any(not self._cons(i) for i in range(self._j + 1))

    def _doublec(self, j):
        """b[j-1] 与 b[j] 是否为相同的双辅音（条件 *d）。"""
        return (j >= 1 and self._b[j] == self._b[j - 1]
                and self._cons(j))

    def _cvc(self, i):
        """b[i-2..i] 形如 辅-元-辅 且末辅音非 w/x/y（条件 *o）。"""
        if i < 2 or not self._cons(i) or self._cons(i - 1) \
                or not self._cons(i - 2):
            return False
        return self._b[i] not in "wxy"

    def _ends(self, s):
        """若词干 0..k 以 s 结尾，置 j = k - len(s) 并返回 True。"""
        length = len(s)
        if length > self._k + 1:
            return False
        if "".join(self._b[self._k - length + 1:self._k + 1]) != s:
            return False
        self._j = self._k - length
        return True

    def _setto(self, s):
        """把 b[j+1..k] 替换为 s。"""
        self._b = self._b[:self._j + 1] + list(s)
        self._k = len(self._b) - 1

    def _r(self, s):
        """若 m > 0 则替换为 s（Step 2/3 的通用动作）。"""
        if self._m() > 0:
            self._setto(s)

    # ---------------- 词干主流程 ----------------

    def stem(self, word):
        """返回 word 的词干；非词干化对象（短词/含符号）原样返回。"""
        word = (word or "").strip().lower()
        if len(word) < 4 or not word.isalpha():
            return word
        self._b = list(word)
        self._k = len(self._b) - 1

        self._step1a()
        self._step1b()
        self._step1c()
        self._step2()
        self._step3()
        self._step4()
        self._step5()
        return "".join(self._b[:self._k + 1])

    def _step1a(self):
        """复数/第三人称处理：sses->ss, ies->i, ss 保留, s 删除。"""
        if self._b[self._k] != "s":
            return
        if self._ends("sses"):
            self._k -= 2
        elif self._ends("ies"):
            self._setto("i")
        elif self._b[self._k - 1] != "s":
            self._k -= 1

    def _step1b(self):
        """ed/ing 还原，并按 eed/元音规则补充处理。"""
        if self._ends("eed"):
            if self._m() > 0:
                self._k -= 1
            return
        if not (self._ends("ed") or self._ends("ing")):
            return
        if not self._vowel_in_stem():
            return
        self._k = self._j  # 去掉 ed/ing 后缀
        if self._ends("at"):
            self._setto("ate")
        elif self._ends("bl"):
            self._setto("ble")
        elif self._ends("iz"):
            self._setto("ize")
        elif self._doublec(self._k):
            self._k -= 1  # 去重辅音
            if self._b[self._k] in "lsz":
                self._k += 1  # l/s/z 不去重（full->ful 例外保护）
        elif self._m() == 1 and self._cvc(self._k):
            self._setto("e")

    def _step1c(self):
        """y -> i（条件 *v*）。"""
        if self._ends("y") and self._vowel_in_stem():
            self._b[self._k] = "i"

    def _step2(self):
        """名词/形容词词尾（-ation/-iveness 等）按映射表还原。"""
        rules = [
            ("ational", "ate"), ("tional", "tion"), ("enci", "ence"),
            ("anci", "ance"), ("izer", "ize"), ("abli", "able"),
            ("alli", "al"), ("entli", "ent"), ("eli", "e"),
            ("ousli", "ous"), ("ization", "ize"), ("ation", "ate"),
            ("ator", "ate"), ("alism", "al"), ("iveness", "ive"),
            ("fulness", "ful"), ("ousness", "ous"), ("aliti", "al"),
            ("iviti", "ive"), ("biliti", "ble"), ("logi", "log"),
        ]
        for suffix, repl in rules:
            if self._ends(suffix):
                self._r(repl)
                return

    def _step3(self):
        """-icate/-ative/-ize 等进一步简化。"""
        rules = [
            ("icate", "ic"), ("ative", ""), ("alize", "al"),
            ("iciti", "ic"), ("ical", "ic"), ("ful", ""), ("ness", ""),
        ]
        for suffix, repl in rules:
            if self._ends(suffix):
                self._r(repl)
                return

    def _step4(self):
        """删除 -ance/-ence/-er/-ment 等后缀（条件 m > 1）。"""
        if self._ends("al") or self._ends("ance") or self._ends("ence") \
                or self._ends("er") or self._ends("ic") \
                or self._ends("able") or self._ends("ible") \
                or self._ends("ant") or self._ends("ement") \
                or self._ends("ment") or self._ends("ent"):
            pass
        elif self._ends("ion") and self._j >= 0 \
                and self._b[self._j] in "st":
            pass
        elif self._ends("ou") or self._ends("ism") or self._ends("ate") \
                or self._ends("iti") or self._ends("ous") \
                or self._ends("ive") or self._ends("ize"):
            pass
        else:
            return
        if self._m() > 1:
            self._k = self._j

    def _step5(self):
        """尾部 e 与双写 l 的收尾规则。"""
        self._j = self._k
        if self._b[self._k] == "e":
            m = self._m()
            if m > 1 or (m == 1 and not self._cvc(self._k - 1)):
                self._k -= 1
        if self._b[self._k] == "l" and self._doublec(self._k) \
                and self._m() > 1:
            self._k -= 1
