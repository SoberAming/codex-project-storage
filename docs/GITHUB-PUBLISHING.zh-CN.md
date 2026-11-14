# 首次发布到GitHub

这份指南用于本项目及其后续版本的GitHub发布。所有者已于2026-11-14确认MIT许可证、仓库名和直接公开发布。仓库、远端测试、安全功能和Release的完成状态仍以GitHub实际结果为准。

| 项目 | 已确认的发布配置 |
| --- | --- |
| GitHub账号 | `SoberAming` |
| 仓库名 | `codex-project-storage` |
| 仓库地址 | `https://github.com/SoberAming/codex-project-storage` |
| 版本tag | `v1.3.0` |
| 中文名称 | 项目磁盘管家 |
| 许可证 | MIT；署名为`Copyright (c) 2026 SoberAming` |
| 首次发布状态建议 | 先发布带明确限制的Pre-release，Mac尚未真机验收 |

## 一、发布身份与许可证

1. 本项目使用上述个人账号和仓库名。后续若经所有者决定改为组织或其他名字，同步替换文档中的仓库URL及安全入口；不要改Skill目录名来凑URL。
2. 本项目采用MIT，版权署名见根目录LICENSE。MIT允许使用、修改、分发和商用，要求保留版权及许可说明，正文含免责条款；见[标准MIT说明](https://choosealicense.com/licenses/mit/)。若维护者另行决定变更分发许可，应核对权利与既有许可条件，更新相关说明并重新构建包。

本次首次发布已获得所有者授权；后续发布仍以维护者当前明确决定为准。授权、源码推送、CI通过和Release发布是不同事实，不能互相替代。

## 二、创建空仓库

在GitHub右上角选择`New repository`，Owner选`SoberAming`，名称填`codex-project-storage`。可先Private审阅，准备公开时再切Public；选择Public并上传即对外可见。

复制以下英文简介到Description：

```text
Project-scoped storage optimization for Codex. Understand disk usage, protect critical data, and choose evidence-based cleanup or migration on Windows and macOS.
```

本地已包含README、.gitignore和LICENSE。创建空仓库时不要再勾选自动添加这三项，避免初始历史冲突。依据见[GitHub创建仓库文档](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)。

## 三、上传完整源码

推荐用GitHub Desktop：登录自己的账号，使用`Clone repository`克隆刚创建的空仓库到新目录；将本地源码资料包解压后的**根目录内容**复制到该克隆目录。保留克隆时生成的`.git`，不要用来源不明的`.git`覆盖它。

检查根目录应直接看到`SKILL.md`、README、LICENSE、`scripts`、`references`、`tests`、`tools`、`docs`、`agents`和`.github`。`.github`必须存在，里面包含工作流和反馈模板。不要只上传ZIP或仅上传SKILL.md；也不要把仓库内容再套一层同名目录。

GitHub Desktop的Changes中审阅文件，确认没有会话/数据库/认证、本机安装回执、完整磁盘报告、真实业务素材、测试输出、下载包或缓存。提交摘要可用：

```text
Prepare v1.3.0 open-source release
```

确认Git作者邮箱设置，可使用GitHub提供的noreply地址。然后Commit，再Push。此时实际仓库是否公开取决于你选择的可见性。

### 熟悉Git时的替代方式

在**解压的源码根目录**运行。先自行确认当前目录正确且没有其他仓库；命令仅作手动发布指引，本工具不会替你执行远端操作。

```text
git init -b main
git status --short
git add .
git diff --cached --stat
git commit -m "Prepare v1.3.0 open-source release"
git remote add origin https://github.com/SoberAming/codex-project-storage.git
git push -u origin main
```

若目录已有Git历史、remote或远端不是空仓库，先核对状态，不使用force push绕过。认证交给GitHub客户端正常登录，不把Token写进URL、脚本、聊天或公开历史。

## 四、运行测试并设置仓库

推送后打开Actions，检查Windows/macOS、Python3.10/3.13矩阵的实际结果。工作流只对新建隔离样本操作，内容权限只读，不自动发Release。某格失败先看日志并修复，不能只看其他格通过就声称全部支持。

设置建议：

- 默认分支设为`main`，打开Issues。
- About里加入主题：`codex`、`codex-skill`、`agent-skills`、`disk-space`、`storage-management`、`windows`、`macos`、`python`。
- 当前没有已发布网站，Website可以留空，不虚构演示地址。
- 启用Private vulnerability reporting。GitHub当前入口为Settings → Security and quality → Advanced Security → Private vulnerability reporting；实际界面以当前版本为准。见[官方说明](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)。
- 核对Security页出现`Report a vulnerability`，问题模板和PR模板能正常显示。
- 可按团队条件给main设置PR审阅和状态检查；先确认实际检查名称再要求它，不猜名字。
- CI或安全开关未启用前，不加入虚假的绿灯徽章或已启用声明。

## 五、创建Release草稿

先按[发布工具说明](RELEASING.md)校验并生成三个产物。在GitHub Releases选择`Draft a new release`，新建tag`v1.3.0`，Target选择实际通过检查的commit。Release title可复制：

```text
v1.3.0 · 项目磁盘管家 / Codex Project Storage
```

正文使用[已写好的Release说明](RELEASE_NOTES_v1.3.0.md)。上传：

1. `codex-project-storage-1.3.0.zip`
2. `codex-project-storage-1.3.0.manifest.json`
3. `SHA256SUMS`

GitHub会另提供该tag对应源码下载；本地完整源码资料ZIP用于上传准备，不必当普通用户安装包。首次建议勾选Pre-release，检查完再发布。保存草稿、创建tag、正式发布是不同动作；公开仓库中推送代码本身已对外可见。

Release管理依据见[GitHub官方文档](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)。

## 六、公开后验收

- 未登录访问仓库，确认可见性与预期一致，README和许可正常。
- 从Release下载安装ZIP，核对SHA256SUMS，解压后直接有`codex-project-storage/SKILL.md`。
- 新的隔离项目中先只读调用，确认发现和报告正常；不要拿真实数据试误删。
- 检查Issue模板有隐私提示，安全报告渠道可用。
- 记录实际Release URL、tag、commit、Actions结果和已知限制。

不要把上传成功、CI通过或文档完备称作所有真实项目都已安全验收。

## 可复制的简短介绍

```text
我整理了一个 Codex 项目磁盘管理 Skill。它先查清项目占用、数据用途和引用，再给出删除、迁移或组合方案，用户决定采用的结果。支持多种代码和媒体项目的分析，保护源码、素材、会话、索引和恢复资料。Windows有隔离样本验证；Mac尚未完成真机验收，自动执行仅限已验证规则。仓库和下载地址请使用实际发布后的链接。
```
