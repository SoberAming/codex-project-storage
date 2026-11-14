# 项目磁盘管家 · Codex Project Storage

[English](README.en.md) · [安装](docs/INSTALLATION.md) · [使用示例](docs/QUICKSTART.md) · [安全边界](docs/SAFETY.md)

[![CI](https://github.com/SoberAming/codex-project-storage/actions/workflows/ci.yml/badge.svg)](https://github.com/SoberAming/codex-project-storage/actions/workflows/ci.yml)

项目越做越大，先弄清楚空间用在哪里，再决定删除或迁移。

这是一个面向 Codex 的项目存储优化 Skill。Agent 核实数据用途、项目归属、引用、重建条件和存储位置，给出推荐方案；用户决定采用的结果，无需逐个辨认缓存、索引和技术文件。

适合代码、网页、视频、设计、研究和数据项目，也能分析没有标准配置文件的目录。路径和盘符运行时发现，不预设系统盘、移动盘或迁移目的地。

```mermaid
flowchart LR
    A[确认项目和所在磁盘] --> B[解释占用与数据价值]
    B --> C[推荐删除、迁移或组合方案]
    C --> D[用户选择结果]
    D --> E[精确计划与执行前复核]
    E --> F[执行回执与空间复查]
```

## 可以做什么

| 能力 | 当前范围 |
| --- | --- |
| 项目占用画像 | 识别 Node、Python、Rust、Go、Java、.NET、C++、移动端等工具链，以及媒体、测试和数据线索；计量依赖、Git、构建、素材和未知目录 |
| 实际卷与目标分析 | 核实源卷、目标卷、可用容量和覆盖缺口，避免把同卷换目录当成腾盘 |
| 精确缓存删除 | 对应源码存在且满足身份、格式、年龄和保护规则的 CPython 缓存 |
| 中间产物删除 | 输入和生产依据保留、可在本地确定重建的部分媒体中间件，如临时解码帧和普通预览 |
| 原生缓存管理 | 极窄范围、真实证明为项目专用的 pip 25.0.1 / 26.1.1 缓存；uv/npm 当前只给建议 |
| 迁移与冗余释放 | 已核实停用的合格产物，完整校验及用途验收后释放源；也可核实已有独立保留副本后释放冗余 |
| 增长治理建议 | 根据真实写入路径提出任务目录、输出预算、保留期和结束后收纳方案 |

类型识别用于诊断。自动执行限定在上述工具明确支持、经核实和授权的范围。其他构建缓存、共享环境、模型数据或未知资料先保留，继续分析或提出工具专用方案。

## 快速开始

1. 安装 Python 3.10+，将本目录放入当前宿主支持的 Skill 根。通用位置为用户级 `~/.agents/skills/codex-project-storage`，也可放在项目内 `.agents/skills/codex-project-storage`；宿主明确使用 `~/.codex/skills` 时沿用该位置。不要为了安装修改 CODEX_HOME。详细步骤见[安装指南](docs/INSTALLATION.md)。
2. 在 Codex 打开需要优化的具体项目。
3. 先提出需求，让 Agent 完成分析并给出方案：

```text
$codex-project-storage 分析这个项目所在磁盘的主要占用、增长来源和数据价值，给我推荐的删除、迁移或组合方案。先只分析，不修改文件；保护源码、原始素材、会话、索引和恢复资料。
```

审阅方案后，可以选择明确范围：

```text
采用你刚才列出的组合方案，按清单清理已核实可重建的中间产物，并把已核实停用的导出迁移到我选定的位置。完成内容校验和用途验收后释放原位置；条件变化就停止，保留未处理项。
```

已有明确执行授权时不重复询问相同权限。报告、精确清单和校验参数由 Agent 管理。更多情景见[使用示例](docs/QUICKSTART.md)。

## 关键数据如何保护

- 会话、索引、SQLite、凭据、源代码、原始素材、依赖环境、恢复点、交付和验收资料、视觉基准及唯一 AI 结果默认保护。
- 大、旧、被 Git 忽略、目录叫 temp/cache 都不能独自构成删除理由。
- 计划绑定范围、成员、内容与身份；执行前复核，出现变化、锁冲突、断连或磁盘读写错误停止。
- 迁移保留源直到完整校验和用途验收完成；同卷挪位置、复制后留源不算已经释放空间。
- 不自动结束应用、提权、改配置、创建兼容链接、截断历史或设置后台清理。

本工具无法证明全球所有引用或消除并发风险。重建条件仍需要 Agent 依据真实项目核实。锁、文件系统和分配量有平台差异，见[安全设计](docs/SAFETY.md)与[兼容性](docs/COMPATIBILITY.md)。

## 验证状态

v1.3 核心版本在 Windows / Python 3.13.13 的隔离样本中运行了 **116 项测试：114 通过，2 项因样本文件系统缺少链接能力而跳过**；另有隔离 pip 缓存的真实清理和冻结组件的独立试用记录。摘要见[验证记录](references/verification.json)。

公开版在 GitHub 的 Windows/macOS、Python 3.10/3.13 环境运行隔离样本；请查看上方 CI 的实际结果及其对应 commit。首次 Mac 运行发现的空 ACL 兼容分支已修复并增加回归，失败记录保留。**尚未完成个人 Mac 设备、外部磁盘和实际业务工作流验收**；托管样本通过不能代替这些验收。新增发布工具和 Mac ACL 测试单独记录，不混入原始核心 116 项。

## 参与和反馈

- [贡献指南](CONTRIBUTING.md)：安全边界、测试和提交要求。
- [安全报告](SECURITY.md)：潜在误删、越界或凭据泄漏请使用私密渠道，避免公开真实数据。
- [支持说明](SUPPORT.md)和[行为规范](CODE_OF_CONDUCT.md)。
- [架构](docs/ARCHITECTURE.md)、[版本记录](CHANGELOG.md)与[后续方向](docs/ROADMAP.md)。
- [来源与致谢](ACKNOWLEDGEMENTS.md)、[第三方说明](THIRD_PARTY_NOTICES.md)。

## 维护与发布

运行工具只使用 Python 标准库；开发检查使用 PyYAML。维护脚本、GitHub Actions 和测试位于源代码包中，安装包只保留运行资源和公共说明。制作安装包与源码包的方法见[发布说明](docs/RELEASING.md)。

首次开源的仓库设置、上传、Release 和可复制发布文案见[GitHub 发布指南](docs/GITHUB-PUBLISHING.zh-CN.md)。

本项目独立维护，不是 OpenAI 官方产品。许可证为 [MIT](LICENSE)，第三方资料和工具遵循各自许可。
