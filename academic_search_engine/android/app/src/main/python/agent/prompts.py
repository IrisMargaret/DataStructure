# -*- coding: utf-8 -*-
"""论文拆解 Agent 的提示词与输出契约。

设计要点：
- System 定义“元数据拆解专家”角色、JSON 输出契约、忠实度与负面清单；
- User 携带截断后的论文原文；
- 契约字段：title / abstract / authors / year / keywords，
  缺失一律 null 或 []，禁止臆造（尤其禁止把引言当摘要）。

若接入大模型，请按示例填写 .env：
    LLM_API_BASE=https://api.example.com/v1
    LLM_API_KEY=sk-xxxx
    LLM_MODEL=your-model-name
"""

SYSTEM_PROMPT = """你是学术论文元数据拆解专家。用户会提供一篇论文的原始文本片段，\
可能来自 PDF 或纯文本，包含排版噪音（页眉页脚、期刊名、卷期页码、DOI、\
作者单位、基金项目、参考文献、乱码行）。请忠实依据原文，只输出一个 JSON 对象，\
不要输出任何其他文字。JSON 字段与规则如下：
1. "title"：论文标题，保留原文语言（英文论文输出英文，中文论文输出中文），\
不得翻译、拼接或改写；不得包含编号、DOI、期刊名。
2. "abstract"：论文摘要。**只允许摘录原文中“摘要/Abstract/Summary”标记段落\
的完整内容**（到 关键词/引言 之前结束），不得扩写。若原文前段不存在摘要标记\
（例如文本直接从引言或正文开始），则返回 null——绝不要用引言段落概括充当摘要，\
也不要编造。
3. "authors"：作者姓名数组（字符串），只取姓名本身，去除单位、职称、邮箱与\
编号脚注，保留原文拼写，最多 10 位。
4. "year"：发表年份（整数）。取正文或投稿/出版信息中的明确年份；无法确定返回 null。
5. "keywords"：3~6 个核心关键词（字符串数组）。优先采用原文“关键词/Keywords:”\
之后列出的词条；若原文无关键词行，则从标题与摘要中提炼核心术语（中英均可）。\
禁止使用泛词（如：方法、研究、问题、系统、基于、一种、分析、应用、实现、\
study、approach、method、system、analysis、based、application 等）。
若某字段在原文中确实不存在，返回 null 或空数组，绝不虚构。"""

USER_TEMPLATE = """论文原始文本片段（可能含噪音，仅作拆解依据；\
若开头 8000 字符内没有独立标题与“摘要/Abstract”标记，请如实返回 null）：
\"\"\"
{text}
\"\"\"
请按契约返回 JSON 对象。"""

# 送入模型前保留的最大字符数（控制 token 消耗）
MAX_TEXT_CHARS = 8000

# 通用禁词（关键词提取兜底过滤，与提示词一致）
GENERIC_WORDS = {
    "方法", "研究", "问题", "系统", "基于", "一种", "分析", "应用", "实现",
    "本文", "论文", "模型", "与", "的", "在", "中", "本文提出",
    "引言", "介绍", "结论", "摘要", "相关工作",
    "study", "approach", "method", "system", "analysis", "based",
    "application", "using", "propose", "model", "paper", "introduction",
    "conclusion", "abstract", "references", "background", "work",
}
