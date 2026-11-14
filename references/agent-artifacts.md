# 已结束 Agent 任务的可丢弃产物

1.5.0 新增 `scripts/agent_artifact_guard.py`。这条路线按真实任务和产物判断，与发起任务的是 Codex、WorkBuddy、Claude Code、Kimi Code 或其他宿主无关；不同宿主的安装与端到端兼容验证须分别声明。脚本不依赖、解析或改写它们的会话和索引格式。

## 能处理什么

三个窄类别：

- `browser-captures`：已经完成的临时截图、浏览器录屏与追踪产物。仅 `.png/.jpg/.jpeg/.webp/.webm/.mp4/.trace/.zip/.har`。
- `download-fragments`：已终止下载留下的片段。仅 `.part/.partial/.crdownload/.download`，不包括完整安装包或下载的原始业务素材。
- `tool-scratch`：明确可丢弃、并已保留有用结果的工具暂存/调试输出。仅 `.tmp/.part/.partial/.log/.trace/.zip`。

选择普通项目内某次运行的准确子单元，末级名为 `scratch/captures/traces/previews/download-fragments/tmp/temp`。示例 `task-runs/capture-20261114-01/captures` 只是布局示例，不是固定宿主目录。父级必须是可识别运行名，不接受整个项目、整个 `outputs` 或整个 `.runtime`。其他布局先分析，不能改名或移动现有文件来绕过保护。

源码、原始素材、唯一 AI 生成结果、正式交付/验收/基准、数据库、会话、索引、凭据及恢复资料不走这条路线。任何一个不支持或受保护成员使整个单元保留。文件夹名、大小、年龄、UUID、Git 忽略状态和“以前删除过”都不是无效证明。归档可能还有独立价值，不能为了空间目标笼统删除。

## 为什么最近完成的任务也可以处理

这条新路线没有 48 小时等待。它要求真实、独立的运行结束记录，同时绑定此次运行、准确源路径和真实生产脚本，并记录任务终态及写入方退出；有用结果或输入必须独立保留。完整成员/身份/内容快照在静止观察前后保持一致，当前可见进程、打开文件、引用检查均通过，调用方明确确认该任务写入方持续停止后才可执行。若产物修改时间晚于终止记录，拒绝并重新审查。

旧媒体、字节码和 PG 测试数据执行器的年龄门槛没有被放宽。不能为缺少历史证据的旧目录临时补造一份“已结束”声明，也不能把新机制的记录回填成旧运行事实。检查器无法自动证明任意代码的业务含义，生产者和保留价值仍由 Agent 核实。

## 调用

```text
python ABS_SKILL/scripts/agent_artifact_guard.py plan --project ABS_PROJECT --source REL_TASK_UNIT --assessment ABS_ASSESSMENT.json --output ABS_PLAN.json --confirm-idle
python ABS_SKILL/scripts/agent_artifact_guard.py apply --plan ABS_PLAN.json --authorize-plan PLAN_SHA256 --receipt ABS_RECEIPT.json --confirm-idle
```

可选 `--codex-home ABS_STATE_ROOT`、`--max-files 10000`、`--max-bytes 1073741824`、`--idle-seconds 1`。所有平台都需要 `--confirm-idle`，它不能替代当前原生检查。计划、评估和回执均在项目外，输出必须是新文件；需要空闲健康位置。Agent 将已授权方案转换为准确计划并执行，用户无需手工输入文件 ID 或哈希。

## 评估格式

下列值必须来自真实保留证据。示例只是字段形状，不是生成假历史记录的模板。`sha256` 绑定对应真实文件，引用必须逐字出现在原文件中。

```json
{
  "schema": "completed-agent-task-assessment-v1",
  "source": "task-runs/capture-20261114-01/captures",
  "run_id": "capture-20261114-01",
  "family": "browser-captures",
  "agent": "the actual initiating Agent, if known",
  "review": {
    "reviewer": "actual reviewing agent",
    "origin_reason": "explain actual producer/run relationships",
    "discardability_reason": "explain why these exact files have no continuing use",
    "no_unique_value_reason": "explain exclusion of unique outputs and acceptance evidence",
    "reference_scope_reason": "explain reviewed consumers, exclusions and remaining limits",
    "retained_results_reason": "identify the useful result/input that remains"
  },
  "producer": {
    "path": "tools/capture.mjs",
    "sha256": "the real 64-character lowercase SHA256",
    "output_quote": "a real source excerpt showing the supported output operation using capturePath",
    "output_path_quote": "a real source excerpt assigning capturePath under task-runs and captures",
    "path_symbol": "capturePath"
  },
  "completion": {
    "path": "task-runs/capture-20261114-01/run.log",
    "sha256": "the real 64-character lowercase SHA256",
    "source_quote": "a real excerpt containing the exact project-relative source and run ID",
    "producer_quote": "a real command/run excerpt containing tools/capture.mjs",
    "terminal_quote": "a real completed/finished/failed/cancelled terminal status",
    "writer_stop_quote": "a real stopped/closed/exited/terminated writer record"
  },
  "retained_results": [
    {"path": "results/report.md", "sha256": "the real 64-character lowercase SHA256"}
  ]
}
```

生产者必须为保留的可执行源码，不能用新写的声明代替。路径定义与实际输出操作须使用同一 `path_symbol`，或操作中包含准确源路径；路径定义按完整组件绑定项目内产物根和单元，不能仅引用一个 `write` 关键字。终止记录使用完整路径 token 绑定源和生产者，不能以 `captures-old`、`capture.mjs.disabled` 冒充选中的 `captures`、`capture.mjs`。终止记录必须独立于生产者源码。有用结果/输入至少一份，与生产者和终止记录不同，不得位于删除单元内。读取它们仅用于哈希绑定，不输出正文。评估正文读取前限制为 1 MiB。有限的安全配置可以用 `reference_files` 显式声明 `path/sha256/reason`，但不能借此读取 `.env`、凭据或客户文档。会话和状态存储不能用作证据输入。

## 停止和回执

执行重新检查全部成员、身份、内容、源卷、保留证据和当前引用，锁定保留文件，每个待删文件再次校验并通过原生句柄/描述符精确删除。仅在最后移除已确认的空目录，永不递归删除新出现的成员。

先独占创建并锚定事件目录，独占创建日志并持久写入初始化记录，成功后才创建源单元的持久 claim。已有目录、重解析路径或日志初始化错误会在 claim 前以结构化初始化拒绝结果返回，不删除旧日志、不消耗该源单元授权。已存在的旧 claim 永不删除或覆盖。

持久 claim 防止更换计划或回执后盲目重试。每批最多 64 个成员在删除前写入持久事件记录；中断可能发生于删除成功但确认未落盘之间，须按原 claim 和待核对批次审查。回执区分 `refused_before_delete`、`partial_or_uncertain` 和 `completed`，分别记录实际确认删除量与源卷空闲差值。

Windows 独占当前文件句柄；macOS 使用可见进程、`lsof` 和协作锁，无法排除其他用户/非协作写入或未来新写入。已知 Agent、shell 或运行时若无法读取命令行，且操作系统未确认进程已经退出，则拒绝；当前执行工具链的祖先仍例外。检查不足或任务仍在运行就保留，绝不自动杀进程、提权、解锁、改配置或重试。扫描与释放保持线性阶段遍历，不逐文件重扫整棵树。
