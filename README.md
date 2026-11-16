# Claude 智能体输出治理 · Output Governance

让 AI 智能体（Claude Code 等）产生的文件「**人能看懂、可控、可回溯**」——不只是命名，是**整套输出治理**。

## 解决什么问题

AI 智能体工作时会乱吐文件：`output_20261116_a1b2c3.md`、一堆 `final_v2` 副本、散落的临时文件、内容重复的文件……本仓库用「**规范 + 引擎**」双向治理：

- **规范层**（skills）：告诉 Claude 该怎么命名、怎么组织
- **引擎层**（govern.py）：真正能执行的工具，扫描 / 重命名 / 归档 / 清理 / 去重

## 全生命周期模型

```
生成(命名) ──▶ 组织(分类) ──▶ 活跃(使用) ──▶ 归档(回溯) ──▶ 清理(删除)
```

## 引擎：govern.py

```bash
python govern.py scan [目录]       # 体检报告（只读）
python govern.py rename [目录]     # 重命名乱命名文件
python govern.py organize [目录]   # 按分类整理根目录文件
python govern.py archive [目录]    # 归档长期未动的文件
python govern.py cleanup [目录]    # 清理临时/垃圾文件
python govern.py dedup [目录]      # 按内容哈希删除重复文件
```

- 默认 **dry-run**（只预览，不修改），加 `--apply` 才真正执行
- 归档阈值用 `--days N`（默认 30 天）

**用法示例**：

```bash
python govern.py scan ~/project          # 先看体检报告
python govern.py rename ~/project --apply # 确认后动手
```

## 安装

1. skills 放进 Claude Code 全局目录：

```bash
git clone https://github.com/resapomr6-cell/claude-smart-naming.git
cp -r claude-smart-naming/skills/smart-naming ~/.claude/skills/
cp -r claude-smart-naming/skills/output-governance ~/.claude/skills/
```

2. 引擎 `govern.py` 是独立脚本，放哪都行，用时：

```bash
python govern.py <command> <目标目录>
```

## 命名规则（smart-naming）

文件名主体用 **2~8 字内容摘要**，禁止 `output` / `result` / 随机串；一次性任务不加日期，持续演进任务（论文/项目/日志）加 `_YYYYMMDD` 或 `_v2`。

## 分类目录

`报告/` `笔记/` `工具/` `数据/` `图片/` `文档/` `归档/`

## License

MIT
