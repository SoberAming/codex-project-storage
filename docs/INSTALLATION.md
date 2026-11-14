# 安装与升级

需要可运行 Python 3.10+ 的环境，以及支持本地Skill并允许执行本地脚本的Agent宿主。核心工具仅用标准库；普通使用无需安装PyYAML。pip原生路线另要求已有、可信且版本受支持的pip，不能为清理而自动安装工具。

官方Skill目录与结构依据见[OpenAI文档](https://learn.chatgpt.com/docs/build-skills)。当前宿主的实际发现位置优先，不修改CODEX_HOME来安装。

## 选择一个位置

| 用途 | 通用位置 |
| --- | --- |
| Windows用户级 | `%USERPROFILE%\.agents\skills\codex-project-storage` |
| macOS用户级 | `~/.agents/skills/codex-project-storage` |
| 只在某个项目使用 | `<项目>/.agents/skills/codex-project-storage` |
| 宿主明确列出旧位置 | 沿用其`~/.codex/skills/codex-project-storage` |

选择一个发现位置即可。同名多处安装可能造成版本混淆；不要覆盖当前目录而不核对。

## 方式一：下载已发布安装包

1. 仓库公开且Release创建后，在该版本Release下载专门的`codex-project-storage-1.5.0.zip`，不要把GitHub自动生成的整个源码压缩包直接当安装目录。
2. 同时取得`SHA256SUMS`，核对文件完整性。来源可信性还取决于你是否从维护者的正确仓库下载。
3. 解压，将其中的`codex-project-storage`整个文件夹放到上表所选位置。
4. 确认安装后的结构是`codex-project-storage/SKILL.md`，旁边有`agents`、`scripts`和`references`；不能多套一层同名目录。
5. 在目标项目中显式调用`$codex-project-storage`。若宿主仍显示旧列表，按宿主支持方式刷新或在新聊天中重试。

Windows核对ZIP哈希：

```powershell
Get-FileHash -LiteralPath '.\codex-project-storage-1.5.0.zip' -Algorithm SHA256
```

macOS核对ZIP哈希：

```sh
shasum -a 256 ./codex-project-storage-1.5.0.zip
```

## 方式二：Git检出

本项目源码地址为`https://github.com/SoberAming/codex-project-storage`。下面的固定版本检出命令在对应tag实际发布后可用；源码推送到main不等于该tag已存在。目录已存在时先检查，不能对已有安装强制覆盖。

Windows PowerShell用户级示例：

```powershell
$skillParent = Join-Path $env:USERPROFILE '.agents\skills'
$skillTarget = Join-Path $skillParent 'codex-project-storage'
if (Test-Path -LiteralPath $skillTarget) { throw '目标已存在，请先检查或升级现有安装。' }
New-Item -ItemType Directory -Path $skillParent -Force | Out-Null
git clone --depth 1 --branch v1.5.0 https://github.com/SoberAming/codex-project-storage.git $skillTarget
```

macOS用户级示例：

```sh
mkdir -p "$HOME/.agents/skills"
git clone --depth 1 --branch v1.5.0 https://github.com/SoberAming/codex-project-storage.git "$HOME/.agents/skills/codex-project-storage"
```

标准`git clone`在目标非空时会拒绝。不要接着手工删现有目录绕过拒绝。

## 升级或移除

先核实安装目录是否只有本Skill，记录当前版本与自定义改动，备份旧版到Skill发现根之外，再安装新版本并核对。不要备份到同一个Skill根下造成重复发现。升级不会要求迁移会话、修改索引或清空历史。

移除仅移除已核实的Skill安装目录，不影响项目、报告或Codex状态。移除前仍需核对自定义文件；本指南不提供一键递归删除命令。

## 其他Agent与兼容范围

其他支持Skill的Agent可以参考本目录结构，但发现位置、权限、工具调用和宿主工作树管理可能不同。未在WorkBuddy或其他宿主完成独立兼容验收，不能直接宣称通用即插即用；先使用只读分析并核对其权限行为。


Claude Code、Kimi Code 和 WorkBuddy 官方均提供技能机制，但目录、入口和权限各异。分别参阅 [Claude Code](https://code.claude.com/docs/en/skills)、[Kimi Code](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html)、[WorkBuddy](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Practice-Cases/Practice-Eight)。这不等于本工具已在上述每种宿主中完成端到端实测。只读验证加载与权限后，再使用具体执行路线。
