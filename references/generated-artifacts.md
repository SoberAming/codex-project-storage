# 精确删除可重建的中间产物

用于已停止生成、无运行引用、输入和生产依据完整保留的确定性媒体中间件。不要求为了删中间件先存一份重复输出；需要保留的是可重建依据。它不是通用 build/dist 清理器，也不是任意后缀删除器。

## 可执行范围

- `decoded-frames`：已有原媒体和解码依据的帧。
- `render-preview`：普通可重建预览，不能是验收/视觉基准或唯一生成结果。
- `deterministic-transform`：本地、确定性转换的衍生媒体。

所有对象至少48小时，输入是项目内独立、非空普通文件且位于待删树外；生产依据真实存在，重建所需依赖可用，无外部付费/随机生成服务依赖。工具沿用迁移器受限的媒体/归档类型和保护边界。源中混有源码、数据库、原件、保护名、成片/交付/发布内容时整项拒绝；目录名也参与保护判断。

AI生成结果、训练成果、完成导出、失败测试证据、trace、视觉基准、验收/审计资料不因可再次运行就算可再生。重新调用模型可能无法复现，应保护或另行归档。

## agent 内部流程

1. 查真实生产脚本/任务证据、输入、依赖和引用，确认停止读写。不能仅填JSON勾选项代替分析。
2. 在项目外写 assessment，再生成计划。
3. 用户已授权这个具体范围时执行，不让用户手工填参数。
4. 检查回执、保留输入/依据和源卷空闲变化，不执行自动重建。

```text
python ABS_SKILL/scripts/generated_artifact_guard.py plan --project ABS_PROJECT --source REL_OUTPUT_DIR --assessment ABS_ASSESSMENT.json --output ABS_PLAN.json
python ABS_SKILL/scripts/generated_artifact_guard.py apply --plan ABS_PLAN.json --receipt ABS_RECEIPT.json --authorize-plan INTERNAL_SHA256
```

macOS须有真实静止证据再加`--confirm-idle`。`--codex-home`可传宿主实际状态根；`--max-files`默认1000、`--max-bytes`默认100GiB，是上限不是目标，不能绕过保护规则。

assessment 示例字段（替换为本项目真实结论，不能照填虚构证据）：

```json
{
  "source": "task-work/decoded-frames",
  "classification": "generated-artifacts",
  "artifact_family": "decoded-frames",
  "purpose": "原媒体的临时逐帧分析",
  "producer_evidence": {"description": "已核对生产脚本中的输入与输出路径", "paths": ["tools/decode.py"]},
  "references_checked": true,
  "no_live_references": true,
  "writers_idle": true,
  "original_assets": false,
  "recreation_method": "已核对的本地解码步骤及其依赖",
  "rebuild_inputs": ["assets/original.mp4"],
  "deterministic_rebuild": true,
  "rebuild_dependencies_available": true,
  "not_unique_ai_output": true,
  "requires_external_service": false
}
```

## 校验与限度

逐文件计划绑定候选内容哈希、文件/目录/卷身份、大小和时间，执行前全量预检再逐项重验，只删除精确文件，保留目录。输入及生产依据的保护句柄覆盖整个执行批次；成员、输入、依据或命名空间变化则停止，回执记录已完成和未尝试项。

大原始媒体仅检查元数据，不为了清理再完整读取它。生产依据需要读取和哈希；同一个小生产脚本同时充当输入时，回执如实记录其以证据角色读取的字节。不能一概声称所有输入正文均读取0字节。

重建条件是agent经分析记录的证据，不等于本工具已实际重建成功。不同系统锁保证不同，也不能防御所有恶意并发；输入被改但元数据被伪装等情形不在通用重建证明内。来源或静止不能核实时保留。候选哈希也有预算上限，CRC/EIO时停止，不继续扫大原件。
