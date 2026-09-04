# -*- coding: utf-8 -*-
"""agent 包：基于大模型 API 的论文拆解 Agent（可选增强）。

配置全部来自 .env（LLM_API_BASE / LLM_API_KEY / LLM_MODEL 等），
代码内不出现任何密钥或供应商地址；未配置时系统自动降级为规则拆解。
"""

__all__ = ["llm", "prompts", "paper_agent"]
