# 工具管理缓存：窄范围原生清理

缓存内部结构交给所属工具管理，不把原生内部文件混进通用逐文件删除器。原生能力不等于无风险；共享缓存可能支撑其他环境，项目定义的clean还可能执行任意代码。

## 本版执行能力

仅支持 **pip 25.0.1 / 26.1.1**、已存在且真实证明为当前项目独占的缓存。其他版本、默认/共享/混合/项目外缓存、证据不足均只给建议。uv、npm目前明确为`advice_only`，不是未检测就可以手工删。

必须有真实使用历史：事先存在的CACHEDIR.TAG、专用配置、成功生产收据、最近7天的归属和引用审计。标记本身不是独占证明；pip不自动生成这个标记。**不得给既有缓存临时补标记、倒填生产收据或捏造审计来获得可执行状态。** 以后新建专用缓存可在真实使用前建立规范，但这不是清理现有缓存的捷径。

```text
python -I -B ABS_SKILL/scripts/native_cache_guard.py plan --project ABS_PROJECT --tool pip --cache REL_CACHE --output ABS_PLAN.json
python -I -B ABS_SKILL/scripts/native_cache_guard.py apply --plan ABS_PLAN.json --receipt ABS_RECEIPT.json --authorize-plan INTERNAL_SHA256 --confirm-idle
```

所有平台均须实际核实无读写，再由agent传`--confirm-idle`。计划绑定整个原生清理范围和内容快照，不是逐文件unlink清单。只有一次消费资格；失败/超时/结果待复核不能自动重放。

## 证据合同

项目内`.storage-cache/pip-binding.json`严格绑定以下结构；字段是机器校验合同，用户不用填写。真实生产配置/收据应在使用该专用缓存时自然记录，不用于伪造既有历史。

```json
{
  "schema": "project-native-cache-binding-v1",
  "project": "ABS_PROJECT",
  "tool": "pip",
  "cache": ".cache/pip",
  "ownership": "project-exclusive",
  "audit": {
    "reviewed_at": "TIMEZONE_AWARE_RECENT_TIMESTAMP",
    "reviewed_by": "ACTUAL_REVIEWER",
    "checked_project_roots": ["ABS_PROJECT"],
    "external_references": "none-found",
    "evidence": "实际检查过的范围、生产路径和无外部引用依据，不能填模板空话"
  },
  "producer_config": ".storage-cache/pip.ini",
  "producer_receipt": ".storage-cache/producer.json"
}
```

专用INI仅含`[global] cache-dir=ABS_CACHE`。生产收据`pip-cache-producer-v1`记录真实项目、cwd、可信解释器及SHA、配置及SHA、`config_loading=PIP_CONFIG_FILE`、实际cache、固定安全前缀后的`install|wheel|download -r REL_REQUIREMENTS`、真实返回码0；需求文件也纳入计划核验。准确要求以当前CLI和校验错误为准，不为凑合同重跑用户安装。

执行前检查可信解释器在项目外、pip实现/版本/帮助/cache-dir、受保护边界、文件内容和成员快照。子进程从可信位置启动，固定`-I -B -m pip --isolated ... --cache-dir ABS_CACHE cache purge`参数，清理注入环境，使用空配置覆盖，日志指向空设备；不执行项目模块、shell脚本或自动安装pip。工具通过绝对路径私有加载本包依赖，`-I`仍能运行。

输出最多64KiB，超时仅终止自己启动的子进程，不杀其他程序。有协作锁和祖先检查，操作后核对范围与外部保留数据；返回0仅代表`native_completed_verified_scope`，失败/超时/待复核返回3，预检拒绝返回2。原生工具调用仍有竞态限制，不能保证对抗其他写入者。

## 为什么其他缓存不直接通删

- [pip cache](https://pip.pypa.io/en/stable/cli/pip_cache/) 提供本工具实际调用的管理命令；[隔离参数](https://pip.pypa.io/en/stable/cli/pip/)与[配置加载](https://pip.pypa.io/en/stable/topics/configuration/)单独核实。受支持版本来自已审查实现，不据此保证未来版本。
- [uv cache](https://docs.astral.sh/uv/concepts/cache/)要求用uv管理，部分环境可能使用symlink链接；清掉仍依赖的cache可能破坏环境。prune亦有范围和环境影响，不能一律称作安全无副作用。
- [npm cache](https://docs.npmjs.com/cli/v11/commands/npm-cache/)通常是跨项目共享；其清空需要force语义，本版不替用户默认强制执行。
- [Cargo home](https://doc.rust-lang.org/cargo/guide/cargo-home.html)含凭据和安装记录，不能把整个根当下载缓存；[Go module cache](https://go.dev/ref/mod#module-cache)也是共享资料。

验证记录区分模拟、只读真实探测和一次全新隔离缓存的真实purge；后者只证明受测Windows/pip组合，不等于用户既有缓存可清理，也不代替macOS实机验收。
