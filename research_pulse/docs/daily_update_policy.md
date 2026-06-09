# Research Pulse 每日更新规则

## arXiv Daily

- 只导入真实 arXiv API 中的新论文。
- 周六、周日或 arXiv 没有新结果时，不创建占位条目，不新增空历史日期。
- 今日页会沿用每个模块的最新一批内容，所以 arXiv 没更新时仍显示上一批最新 arXiv。

## 每日固定模块

以下模块每天由定时 Agent 尝试更新：

- 近两年高影响力 paper
- 论文考古：经典理论与科学思维
- AI for Science / AI for 民生
- 学术人物关系网

## 去重规则

- 优先按 paper / PDF / project / code / profile 链接去重。
- 没有链接时，按规范化后的标题和作者生成去重键。
- 已经导入过的条目不会再次写入数据库。
- 没有非重复新条目时，不发送飞书更新提醒。
- 近两年高影响力、论文考古、AI for Science、学术人物关系网默认避免 90 天内重复主题或重复人物。
- arXiv 导入会在 DeepSeek 分析和 PDF 截图前先按 arXiv ID、paper/PDF 链接、标题作者全局去重。

## 质量门槛

- 不导入 demo、示例、占位、无来源链接的条目。
- 论文类条目必须有可打开的 paper/PDF/project/code/GitHub/DOI/source 链接之一。
- 人物类条目必须有 profile/homepage/source 链接之一。
- arXiv、近两年高影响力和 AI for Science 条目必须有英文摘要和忠实中文摘要。
- 标签必须是主题/方法/任务标签，不能是 arXiv、daily、context、agent generated、科学推理、高影响力这类空标签。
- 核心贡献和主要框架不能只有标题，每条必须解释具体做了什么。

## 收藏夹整理

收藏夹不按来源模块硬分，而按研究系列聚合。当前默认系列包括：

- 世界模型 / VLA / Agent
- 视频生成与可控编辑
- AI for Science / 民生
- 经典理论与科学思维
- 学术人物关系网
- 其他收藏
