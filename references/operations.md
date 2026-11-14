# 项目所在磁盘优化：调用与内部操作

## 日常调用

打开目标项目后输入：

```text
$codex-project-storage 优化这个项目所在磁盘。你查清数据用途、引用和可用存储位置，给我删除、迁移或组合方案，说明收益和影响，我只决定采用哪种方案。
```

已有明确执行授权时 agent 直接在该范围内推进；只要建议时仅做只读分析。用户不需要复制命令、挑文件 ID、判断索引用途或输入哈希。

## 发现实际源卷与目标

```text
python ABS_SKILL/scripts/volume_advisor.py inspect --project ABS_PROJECT --output ABS_REPORT.json
```

可重复传入 `--target ABS_TARGET` 检查用户指定位置；用户给出容量目标时传入 `--goal-free-gib NUMBER`。输出项目外的新 JSON 和同名 Markdown，不覆盖既有报告。没有明确容量目标时不要假造一个用户承诺。

报告提供实际源卷、容量、空闲量、目标卷身份及限制。所有路径运行时确定，不默认任何盘符、挂载名、目录名或目标类型。Windows 挂载卷与 macOS 挂载目录按实际身份识别；不能把名字叫 Archive 的文件夹当成移动硬盘。同卷目录不算释放源卷空间的迁移目标。

可用容量只是第一道筛选，精确迁移对象、目标余量、稳定性和兼容性仍由后续计划核实。未连接、只读、网络、云占位或能力不明位置不直接执行迁移。内部盘、移动盘、网盘的取用与断连影响应当在方案里分别说明。

## 全面画像与精确缓存清理

```text
python ABS_SKILL/scripts/project_profiler.py inspect --project ABS_PROJECT --output ABS_PROFILE.json
```

默认用全面画像解释项目大小，含Git、依赖、环境、构建和未知数据；不执行项目命令。重复`--related-root ABS_RELATED`只测明确授权的外部关联目录，分开计量，不表示授权删除；共享候选默认不递归测量。`--scan-json ABS_SCAN.json`只复用仍匹配的逐文件分配量，不能叠加旧汇总。更多见[项目类型](project-types.md)。

`coverage.complete=false`反映全局归属/语义尚未全部审计；另看项目元数据遍历完整标记。具体候选子树必须经对应执行器完整核验，不能把全局语义缺口说成所有子树都无法处理。画像覆盖与以下缓存专用scan不同，二者总量不能直接比较增长。

```text
python ABS_SKILL/scripts/storage_guard.py scan --project ABS_PROJECT --output ABS_SCAN_DIR
python ABS_SKILL/scripts/storage_guard.py plan --scan ABS_SCAN_DIR/scan.json --ids INTERNAL_IDS --output ABS_PLAN.json
python ABS_SKILL/scripts/storage_guard.py apply --plan ABS_PLAN.json --receipt ABS_RECEIPT.json --authorize-plan INTERNAL_SHA256
```

这些参数由 agent 管理。报告目录放项目外健康位置。扫描不读业务正文；计划只哈希明确选中的缓存，执行前重验。

当前缓存删除规则仍为：当前工具 Python 运行时的 CPython 缓存、对应源码存在、默认至少 48 小时、单文件不超过 64 MiB、通过头部初验与身份/哈希核对。头部初验不是完整字节码语义或重编译等价证明。

依赖、虚拟环境、标准受管理缓存和 pyvenv.cfg/CACHEDIR.TAG 边界保持保护；缓存专用扫描刻意跳过这些目录，由全面画像解释其大小。不能把依赖包内子目录重新命名为项目入口绕过保护。webpack、pytest 和未支持类别先分析用途再给建议。

## 确定性中间产物与原生缓存

仅在对应规则核实后执行，参数仍由agent管理。

```text
python ABS_SKILL/scripts/generated_artifact_guard.py plan --project ABS_PROJECT --source REL_DIR --assessment ABS_ASSESSMENT.json --output ABS_PLAN.json
python ABS_SKILL/scripts/generated_artifact_guard.py apply --plan ABS_PLAN.json --receipt ABS_RECEIPT.json --authorize-plan INTERNAL_SHA256
python -I -B ABS_SKILL/scripts/native_cache_guard.py plan --project ABS_PROJECT --tool pip --cache REL_CACHE --output ABS_NATIVE_PLAN.json
python -I -B ABS_SKILL/scripts/native_cache_guard.py apply --plan ABS_NATIVE_PLAN.json --receipt ABS_NATIVE_RECEIPT.json --authorize-plan INTERNAL_SHA256 --confirm-idle
```

生成产物适用范围、assessment和真实重建依据见[生成产物](generated-artifacts.md)。它不要求保留重复输出，但原件、输入、生产依据和唯一结果都保留。原生路线见[原生缓存](native-cache.md)，仅极窄项目专用pip可执行；全平台需要实际静止确认，不能补造既有缓存历史，uv/npm为建议模式。两条路线都不运行项目脚本。

Codex状态、会话、数据库与宿主工作树管理见[状态与工作树](codex-state.md)。工具可支持的归档与原始文件删除不同，必要ignored文件须单独保存。

## 迁移与删除冗余副本

运行前阅读 [产物迁移与冗余释放](relocation.md)。两者均须先明确源用途、来源证据、引用检查和保留结果，不能靠目录旧/大/cache 名称判断。

- 迁移：保留有价值的停用产物，目标是另一个实际卷；复制和完整核验期间源保持，完成用途验收后才释放源。
- 删除冗余：目标是已经存在的独立保留副本；核实对应文件、内容、身份、可用性和用途后释放源副本。同卷独立重复文件的删除也可能腾出空间，硬链接不能按两份内容计收益。

需要兼容旧路径或改应用配置的对象，本版只给独立方案。不会自动建链接、切换会话根、搬活动工作树、数据库或原始素材。

## 容量与成果口径

分别给出：源卷空闲目标/当前缺口、已核实候选的逻辑量和已知分配估计、目标复制所需容量和保留余量、完成后实测源卷空闲变化。压缩/稀疏/硬链接/APFS共享块/快照和其他进程写入都可能影响差值。

复制保留源、同卷挪目录、计划生成和移动到同卷废纸篓不算已释放源卷空间。未实现/未核实项不计入推荐方案承诺。若只能安全释放一小部分就报告仍有缺口，不把项目所在卷扩大为整卷任意清理。

## 运行条件与故障

Python 3.10+，本包工具仅用标准库；原生pip执行另要求可信解释器中已经安装受支持版本，不自动安装依赖。macOS 已实现流程但真机状态以交付验证记录为准；写操作使用协作锁，agent 只在已有静止证据时加 `--confirm-idle`。没有锁文件不代表没有读写。

文件、来源证据、卷身份或目录成员变化，出现锁冲突、CRC/EIO 或断连时立即停止，保留已完成项和未尝试项。失败状态不自动重放，不改权限绕过、不强制关闭应用。外盘在验收后也可能被拔出；用户选择转移后需要从新位置取回，工具不能承诺永久可达。

## 避免再次增长

按生产脚本实际路径落实任务目录、容量预算、停止水位和产物保留期。将原始输入、编辑源、交付品、恢复点和可再生中间件区分清楚。检查本地依赖和打包范围，避免重复复制项目；共用下载缓存应走工具支持方式，不把登录配置或各项目运行环境盲目链接。用户未要求时不创建后台定时清理。

## 安装与分发

通用用户级目录是 Windows `%USERPROFILE%/.agents/skills` 或 macOS `~/.agents/skills`；只供项目使用时放 `<项目>/.agents/skills`。当前宿主若列出的根是 `~/.codex/skills`，按宿主位置安装。同名技能选择一个发现位置，保持目录下直接包含 SKILL.md，不更改 CODEX_HOME。

查看 references/verification.json 区分组件版本、历史验证、当前运行结果、真实平台和模拟检查；Windows 的通过不能代替 macOS、NTFS 特性或业务用途验收。
