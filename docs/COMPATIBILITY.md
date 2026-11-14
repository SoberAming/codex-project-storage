# 兼容性与验证状态

## 1.5.0 当前验证规则

1.5代码和新增隔离测试必须在Windows/macOS各Python3.10与3.13四个托管组合通过。每次以[对应提交的CI](https://github.com/SoberAming/codex-project-storage/actions/workflows/ci.yml)为准，发布附件记录精确commit、run、各suite结果及平台跳过；旧版计数不证明新版通过。核心运行代码指纹见[verification.json](../references/verification.json)。

新增任务残留、画像及状态保护测试会核验真实精确清理和源码/会话/索引等保留样本。Windows强制共享拒绝与macOS协作锁语义分别验证，后者仍需确认静止。原有原生npm10.9.2缓存集成保持执行，不按新增功能跳过旧路线。

Codex、Claude Code、Kimi Code、WorkBuddy等是任务产物来源及潜在调用宿主；本次操作系统测试不构成每个宿主的端到端验收。个人Mac、外盘、全量APFS共享/快照、真实业务项目未因此取得验收。不会拿用户的真实会话或数据库做删除试验。

---

以下1.4记录为历史，不能用于证明1.5新组件或修订通过。

# 1.4 历史兼容性记录

当前版本：1.4.0。验证记录日期：2026-11-14。[修复后四格CI](https://github.com/SoberAming/codex-project-storage/actions/runs/43557649569)已在修订`b75a54ccd85f8cb55561bc84c6db1eba89877f15`完成，四格均成功。下列结果只绑定该修订；最终发布tag仍须对应其精确修订通过的[发布检查](https://github.com/SoberAming/codex-project-storage/actions/workflows/ci.yml)，不能由这次运行代替后续文档提交的最终检查。

## 1.4托管验证

四格均使用Node22.14.0/npm10.9.2，执行仓库校验、10套隔离测试和仓库外安装包构建。npm原生集成已显式启用，没有按缺少工具参数跳过。

| 托管环境 | Python | 总数 | 通过 | 平台跳过 |
| --- | --- | --- | --- | --- |
| Windows X64，`win25-vs2026` | 3.10.11 | 258 | 256 | 2 |
| Windows X64，`win25-vs2026` | 3.13.17 | 258 | 256 | 2 |
| macOS ARM64，`macos26` | 3.10.11 | 258 | 254 | 4 |
| macOS ARM64，`macos26` | 3.13.17 | 258 | 254 | 4 |

Windows镜像版本为`20261103.298.1`，macOS为`20261102.0473.1`。Windows跳过两项Apple原生ACL检查：`test_native_new_file_and_directory_metadata`、`test_native_nonempty_acl_is_captured`。macOS跳过四项Windows专用检查：`test_actual_psmodulepath_injection_is_not_loaded`、`test_cim_stale_row_ignored_only_after_os_confirmed_exit`、`test_live_project_process_and_inaccessible_runtime_refused`、`test_evidence_is_write_protected_until_native_returns`。这些跳过不计入通过；本次链接能力检查没有跳过。

64项npm套件在Windows全部通过，在macOS为63通过、1项上述Windows共享拒绝测试跳过。每格均真实执行离线新包的专用缓存创建和固定npm原生清理，删除2个缓存文件，逻辑字节Windows为878、macOS为894；原包、生产记录及原日志保留，未处理真实用户或共享缓存。40项PG退役套件在Windows全部通过，macOS为37通过、3项上述Windows活动检查跳过。每格的真实CLI与系统活动查询均成功处理6个虚构布局文件，共29,461,707逻辑字节，未启动或连接PostgreSQL，未执行项目代码。

这证明相应托管环境的隔离样本行为。个人Mac设备、外盘、完整APFS克隆/快照或业务工作流、真实PG服务器及业务数据库没有因此获得验收。逻辑删除量与卷空闲变化分别记录；其他磁盘活动可能使后者为负。macOS协作锁仍不能阻止非协作写入。

## 历史本机与其他范围

| 环境/功能 | 状态 |
| --- | --- |
| Windows / Python 3.13.13，历史1.4本机记录 | 兼容修复前10套共246项：237通过，9项平台/链接能力跳过；另32组独立目标复核通过。保留为历史，不代表当前组件或托管结果 |
| Windows / Python 3.13.13，历史1.3 | 核心6套共116项：114通过，2跳过 |
| 原始样本文件系统 | E样本卷缺少原生符号链接/硬链接创建能力，因此2项明确跳过；身份别名边界另有模拟 |
| Windows专用pip26.1.1 | 全新隔离缓存真实download一次、purge一次；6缓存文件共87,982逻辑字节，保留文件哈希不变，无install |
| pip25.0.1 | 实现已纳入受支持版本及模拟合同测试，未在此记录中完成该版本的真实purge |
| 中间件独立试用 | 冻结6脚本与相关说明前后不变，虚构项目删2预览共136字节，11保留文件及状态索引不变 |
| macOS / APFS | 当前托管结果见上表；个人Mac设备/外盘/完整APFS语义/业务工作流尚未验收 |
| Python3.10 | 原始维护者本机仅做语法检查；当前修订已在Windows X64及macOS ARM64以3.10.11真实运行，见上表 |
| Linux | 未作正式支持和运行承诺；POSIX分支不等于Linux已验收 |
| 跨卷NTFS→exFAT | v1.2有小样本真实验证，迁移脚本与共用guard后来有变更；历史不等于1.4跨卷或所有平台重新验收 |
| 网络盘、云占位、复杂元数据 | 不作为普通本地目标默认执行；不支持情形保留并另立方案 |
| 其他Agent宿主 | Skill结构可参考，权限和工具管理机制需单独验证；没有WorkBuddy等宿主实测承诺 |

## 自动测试配置

源码包含Windows/macOS、Python3.10/3.13矩阵，以及仓库检查、隔离测试与安装包构建。当前1.4的[首次失败运行](https://github.com/SoberAming/codex-project-storage/actions/runs/43556855654)保留了官方Node分发缺少内置`npm/npmrc`时的拒绝。修正只允许普通、身份稳定的安装目录中该叶文件明确缺失；存在时完整哈希绑定，缺父目录、链接、权限/I/O错误、出现或漂移仍拒绝，其他实现文件仍为必需。探测前后及原生清理前均复核，未创建或修复npm安装配置。[修复后运行](https://github.com/SoberAming/codex-project-storage/actions/runs/43557649569)的四格结果见上表。

1.3首次公开的[原始运行](https://github.com/SoberAming/codex-project-storage/actions/runs/43534331248)保留了Windows两格通过与Mac空ACL分支失败，后者增加了窄修复和15项回归，未跳过迁移检查。这段历史不为1.4新增执行器背书；新增测试与原始116项分列，不把模拟或跳过描述为原生成功。

该兼容修复依据Apple原始实现：[ACL查询路径](https://raw.githubusercontent.com/apple-oss-distributions/Libc/main/posix1e/acl_file.c)在对象查询成功后继续读取ACL属性，[ACL属性未设置](https://raw.githubusercontent.com/apple-oss-distributions/Libc/main/gen/filesec.c)也可能返回ENOENT。执行器只在对象前后普通类型和身份/元数据稳定时确认无扩展ACL；实际缺失、漂移或权限/I/O错误仍拒绝。

原始核心证据摘要保留在[verification.json](../references/verification.json)。原始本机路径、安装回执和完整QA样本不随开源包公开。新增发布工具的检查单独记录，不能改写核心测试计数。

## 已知功能范围

项目类型线索覆盖广于自动执行能力。通用清理执行器不删除依赖、业务或状态数据库、Git对象、共享模型或未知构建目录。独立退役器只处理正向证明可丢弃的合成PG测试data；当前支持的布局和证据条件见[规则](../references/retired-runtime.md)。原生缓存限分别合格的专用pip与npm10.9.2；uv、其他版本、共享/默认缓存为建议。需要原路径兼容、改应用配置或活动状态迁移的对象不进入通用迁移器。
