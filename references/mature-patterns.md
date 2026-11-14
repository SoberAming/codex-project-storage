# 成熟方案的借鉴与本技能的边界

核对日期：2026-11-14。仅借鉴设计机制，未复制第三方实现，未安装或运行第三方清理器。官方仓库/文档可以更新，实际命令以本机版本帮助和当前官方资料为准。

## uv：尊重工具拥有的缓存与锁

[官方仓库的缓存说明](https://github.com/astral-sh/uv/blob/main/docs/concepts/cache.md)和[发布文档](https://docs.astral.sh/uv/concepts/cache/)要求通过 uv 自己的接口管理缓存，不能手工改内部文件。原生命令具有锁行为，clean/prune 作用也不同；缓存通常可能跨项目共享。

本技能的实际采用：将依赖、虚拟环境、标准受管理缓存及带 pyvenv.cfg/CACHEDIR.TAG 边界的缓存从逐文件执行候选中排除，仍报告占用。native-cache 只读分析后单列建议，不直接运行 uv cache prune，不使用 --force 绕锁。CACHEDIR.TAG 在这里是保守排除信号，不能单独证明由 uv 管理。

本版已加入独立的窄范围pip原生适配，核实受支持版本、实际位置、真实独占生产证据和运行状态；不通过generic file-delete执行，也不宣称原生命令具有固定逐文件清单。uv仍为建议模式，尤其需要核实symlink依赖与prune的环境影响。详见[原生缓存](native-cache.md)。

## Czkawka：重复证据不等于删除理由

[核心说明](https://github.com/qarmin/czkawka/blob/master/instructions/Instruction_Core.md)采用逐级缩小内容校验范围；[CLI 说明](https://github.com/qarmin/czkawka/blob/master/instructions/Instruction_CLI.md)提供参考目录和硬链接处理。

本技能的实际采用：按身份去重，源码、素材、交付与恢复资料作为保留基准；相同大小、名称或时间不构成重复证明，更不构成删除理由。需要重复分析时先元数据筛选，再在限定范围做预哈希与全量内容校验，磁盘错误立即停止。内容相同后仍必须核对引用和保留用途。

当前增加了针对明确停用产物和指定保留副本的精确迁移/冗余释放；仍没有通用整盘重复文件扫描器。重复文件的内容核验需作为另一个有范围、读取预算和保留基准的只读任务处理，不能把本参考误当作现成命令能力。

## BleachBit：选择、预览与执行保持一致

[官方仓库](https://github.com/bleachbit/bleachbit/blob/master/README.md)及[CLI 文档](https://docs.bleachbit.org/doc/command-line-interface/)将预览和执行分开，并提供排除机制。

本技能的实际采用：scan → plan → apply；计划固定逐文件证据，执行重新验证。面向用户只展示推荐方案的收益、影响和保留范围，清单与指纹由 agent 维护。用户选择业务结果，agent 负责技术判断和落地验收。

不直接接入整盘清理类别或导入第三方规则包。各工具针对整机的规则，不自动满足当前项目的边界与历史保护要求。同卷回收站/隔离不算释放空间。

## 方案卡与内部证据

默认向用户展示一个推荐方案，必要时最多两个取舍：

| 方案 | 预期收益 | 使用影响 | 保留范围 |
| --- | --- | --- | --- |
| 删除：可再生缓存或已有完整保留副本的冗余产物 | 只计算当前模式已通过的条目；分配未知则说明 | 首次重建，或从指定保留副本取回 | 会话/索引、源码、素材、数据库、发布与恢复数据 |
| 迁移：已核实停用但需要保存的产物 | 单列复制和释放两个阶段 | 按所选新位置取回；断连影响由实际目标决定 | 原件先保留到校验与用途验收完成 |

没有已核实可执行项时，明确说“本轮先保留，已找到主要占用和后续核验方向”，不要为了凑释放量把未知数据交给用户猜。

内部报告每项至少记录 `producer / purpose / project_relation / references / recreation_method / evidence / action_support / uncertainty / retain_reference`。这里的字段是 agent 的分析要求，不是允许执行的权限声明；改字段不能绕过工具规则。
