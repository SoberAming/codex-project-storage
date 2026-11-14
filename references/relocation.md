# 停用产物迁移与冗余副本释放

## 适用条件

执行器只接受当前项目内精确的非根产物目录：已核实由项目生成或已经完成的普通导出，已查明用途与来源，当前没有运行引用/写入。来源证据与完整成员固化到计划。它不能证明全世界没有引用，agent 必须说明实际检查范围；其他项目或应用是否仍依赖无法核实时保留。

会话/索引、数据库及sidecar、Git、认证凭据、源码配置文档、原始素材、依赖与工具管理缓存、发布/验收/恢复数据仍有硬保护。媒体扩展名白名单不等于任意媒体可迁移，目录名或assessment的分类字段也不能解除保护。

本版不建旧路径兼容链接、不改引用和应用设置。对象需要原路径或仍在活跃工作流中时，单独制定迁移方案，不能在本执行器中假称无引用。

## agent 准备用途核实记录

assessment 存在项目产物目录与目标目录之外，包含：

```json
{
  "source": "exports/completed-run",
  "classification": "completed-exports",
  "purpose": "已经结束的任务导出，归档保留",
  "producer_evidence": {
    "description": "已检查生产脚本及相关输出设置",
    "paths": ["render.py"]
  },
  "references_checked": true,
  "no_live_references": true,
  "writers_idle": true,
  "original_assets": false
}
```

这只是格式示例，不能原样填 true 当作已经做过检查。agent 必须实际核实证据，再生成内部计划。证据文件须是项目内普通文件，不能用会话、凭据等内容充当来源证据；文件身份/哈希还会在后续阶段复查。

## 按用户选择生成精确计划

```text
python ABS_SKILL/scripts/relocation_guard.py plan --project ABS_PROJECT --source REL_ARTIFACT_DIR --target ABS_TARGET_DIR --action migrate --assessment ABS_ASSESSMENT.json --output ABS_PLAN.json
```

`--action migrate` 使用全新目标目录，拒绝覆盖，并要求实际不同卷；`--action deduplicate` 使用已经存在的独立保留副本，可以位于同卷，但不能是同一对象或硬链接。源/目标不能父子重叠或位于本次释放集合中。

计划有明确文件数、读取预算和目标保留余量。默认先元数据检查完整性/保护边界，之后才读选中文件。所有目录（含空目录）和文件成员完整冻结；不完整、越界或超预算不能成为执行计划。

权限保真默认采用 preserve。对于普通非敏感导出，可提出 `--metadata-policy portable-export`，但用户方案必须说明目标采用目标位置的权限、跨文件系统的时间精度影响；此模式不等于完整元数据备份。ADS、扩展属性、资源叉、加密/离线占位、链接等仍不因选择portable而放行。默认不能静默降低权限保真要求。

## 迁移：先复制、验收，再释放

```text
python ABS_SKILL/scripts/relocation_guard.py copy --plan ABS_PLAN.json --receipt ABS_COPY.json --authorize-plan INTERNAL_PLAN_SHA
python ABS_SKILL/scripts/relocation_guard.py accept --plan ABS_PLAN.json --copy-receipt ABS_COPY.json --output ABS_ACCEPT.json --authorize-plan INTERNAL_PLAN_SHA --confirm-accepted
python ABS_SKILL/scripts/relocation_guard.py release --plan ABS_PLAN.json --accept ABS_ACCEPT.json --receipt ABS_RELEASE.json --authorize-plan INTERNAL_PLAN_SHA
```

copy 创建全新目标，流式复制并落盘，再对完整副本与源核验。此时源必须仍在，复制或哈希通过不代表已经释放。

accept 记录用户所选保存结果已经满足用途，绑定精确计划、复制回执、权限模式和核验结果。用户先前已选择“迁移并在校验与用途验收后释放”时，agent 完成验收后直接记录，不重复问；若必须应用/界面验收而尚未完成，就保留源。

release 前完整复查两端、来源证据和目录成员；之后逐文件同时持有源与保留副本守护句柄，核验后仅删计划中的源文件，不递归删除目录。首次变化/错误停止后续，回执区分完成、失败、不确定与未尝试。

## 删除已有副本的冗余产物

使用 `--action deduplicate` 建计划，目标是 agent 已确认的保留目录，不需要 copy。accept 阶段核验已存在的保留副本及用途，命令不传 `--copy-receipt`；之后 release 同样完整预核、逐文件释放。它不是整盘重复文件扫描器，不能只按同名/大小/新旧时间判定重复。

用户选择“删除冗余副本”后，方案应明确唯一保留的位置和取回方式；未核实副本、用途或稳定性时不释放原件。

## 目标位置和成果

路径由运行时发现和用户业务选择决定；不固定为任何盘符、移动盘名称或挂载点。目标卷必须在各阶段仍为已记录的卷，设备断连/替换即停止。外盘未来可被拔走，释放源代表用户接纳该保留位置；无法保证未来所有时间都在线。

源卷空闲量前后差、删除逻辑字节、已知物理分配分别记录。源未释放时迁移只完成复制；同卷迁移不作为源卷腾盘方案。删除同卷独立冗余副本可能有收益，硬链接/APFS克隆/快照等要按实际分配和实测空闲说明。

## 平台和元数据依据

[Python 文件复制文档](https://docs.python.org/3/library/shutil.html)说明普通copy/copy2不能保真全部平台元数据，所以本工具不能把字节校验包装成ACL、ADS或资源叉备份。Windows使用底层独占句柄；POSIX为协作锁，macOS需确认静止且真实验证状态单列。

[Windows 卷身份接口](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getvolumenameforvolumemountpointw)支持按挂载点取得实际卷身份，不能只凭盘符或路径字符串判断不同卷。
