# Claude Smart Naming · 智能文件命名 Skill

让 AI 生成的文件名「人能看懂」，杜绝 `output_20261116_a1b2c3.md` 这类天书命名。

## 解决什么问题

AI 智能体（Claude Code 等）生成文件时，经常偷懒用 `output + 日期 + 随机串` 当文件名，人看不懂、也没法归档管理。这个 skill 强制它用「内容摘要」起名。

## 命名规则

| 维度 | 规则 |
|---|---|
| 文件名主体 | 2~8 字内容摘要，中文内容用中文、技术类用英文 kebab-case |
| 禁用词 | `output` / `result` / `temp` / `未命名` / 随机串（hash/UUID/时间戳） |
| 日期 / 版本 | 一次性任务不加日期；持续演进任务（论文/项目/日志）加 `_YYYYMMDD` 或 `_v2` |
| 分类目录 | `报告/` `笔记/` `工具/` `临时/` `论文/` `项目/` |

判断口诀：**这文件未来会不会有第二版？** 会 → 带版本/日期；不会 → 纯名。

## 安装

把 skill 目录放进 Claude Code 的全局 skills 目录：

```bash
git clone https://github.com/resapomr6-cell/claude-smart-naming.git
cp -r claude-smart-naming/skills/smart-naming ~/.claude/skills/
```

或软链：

```bash
ln -s "$(pwd)/skills/smart-naming" ~/.claude/skills/smart-naming
```

## 建议配合常驻规则

skill 是「按需触发」的，命名这种「每次都要遵守」的规则，建议再加到 `~/.claude/CLAUDE.md` 里常驻：

```markdown
# 文件命名规范（常驻）
生成任何文件时用「智能命名」规则（详见 skill `smart-naming`）：
文件名主体用 2~8 字内容摘要，禁止 output/result/随机串；
一次性任务不加日期，持续演进任务加 _YYYYMMDD 或 _v2。
```

## License

MIT
