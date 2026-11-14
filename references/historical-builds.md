# 历史 Next 构建的现状核验与精确清理

build_artifact_guard.py 是独立政策。针对 .tmp、task-runs、candidates 等隔离候选中的普通 .next，核实当前已停用后，清理限定的独立编译代码和 webpack 缓存。它不清理正式发布、回退、依赖、数据库、唯一媒体或任意 build/dist 目录。

## 历史日志缺失时

不伪造任务结束记录。current-state-reconstruction 依据现存真实源码和构建身份、当前运行、保留应用以及启动/配置引用复核。Agent 仍须判断该候选是否可停用、源码和结果是否齐全、是否承担回退，以及旧版本需重建的影响。年龄和名字都不是证明。

执行器要求相邻 package.json 的真实 Next 依赖和受支持的 next build 语句；只读观察，不执行。至少保留一份独立源码/结果证据、实际当前启动/配置文件和一个当前/回退应用根，全部绑定身份及哈希。BUILD_ID 保留，不接受没有构建身份的未知失败目录。

## 选择和保护粒度

- 选择 .next/server、.next/static 中限定扩展名的编译代码、样式与 source map，以及已识别 webpack pack。
- 多硬链接、未知身份、只读/特殊属性、无法确认权限的文件逐个保留。同单元的其他独立生成文件继续核验。
- 原始/预渲染页面、RSC/未知内容、图片字体、媒体、JSON数据、数据库、来源标记附加流、构建身份及清单保持原位。
- 文件、目录、保留证据和卷变化立即停止。执行只删除冻结清单中的文件，不清空目录、不递归删除、不移动源码和状态。

## 原生运行绑定

Windows 用系统进程清单，macOS 用 ps 和 lsof，不读取进程私有内存或浏览器身份。未知的活动运行时不能用 idle=true 覆盖。

正在运行的 Next 预览必须映射到实际 app、PID 创建标识和 BUILD_ID。工具对原生命令中的 loopback 端口请求准确的 /_next/static/BUILD_ID/_buildManifest.js，与磁盘文件逐字节匹配。HTTP 不接受代理、跳转、外部主机或用户提供的任意URL。不请求业务API。

所选构建与任何活动 BUILD_ID 相同，包括副本/别名，一律保留。未映射服务、当前 app 引用和文件占用均阻断；不自动结束任何服务。

## 评估与调用

~~~json
{
  "schema": "inactive-next-build-review-v1",
  "source": ".tmp/historical-run/source/apps/web/.next",
  "lifecycle_mode": "current-state-reconstruction",
  "review": {
    "reviewer": "actual reviewing agent",
    "origin": "real producer and output relation",
    "inactive_reason": "current facts establishing this candidate is not selected",
    "retained_source_and_results": "where source and valuable results remain",
    "not_rollback_or_deployment": "reviewed current and rollback roles",
    "reference_scope": "actual launch/config scopes checked and remaining limits",
    "rebuild_impact": "old candidate needs a rebuild before serving again"
  },
  "producer": {"path": ".tmp/historical-run/source/apps/web/package.json", "sha256": "REAL_SHA256"},
  "retained_evidence": [{"path": ".tmp/historical-run/source/apps/web/app/page.tsx", "sha256": "REAL_SHA256"}],
  "reference_files": [{"path": "tools/start-current.py", "sha256": "REAL_SHA256"}],
  "retained_app_roots": ["apps/current"],
  "runtime_bindings": []
}
~~~

runtime_bindings 无活动 Next 服务时才可为空；有服务时每项为 pid、原生 process_stamp 和普通绝对 app 路径。由 Agent 调查产生，不让用户填 PID/哈希。输入必须是真实检查结果，示例不是可照填的声明。

~~~text
python ABS_SKILL/scripts/build_artifact_guard.py plan --project ABS_PROJECT --source REL_NEXT_ROOT --assessment ABS_REVIEW.json --output ABS_NEW_PLAN.json --confirm-idle
python ABS_SKILL/scripts/build_artifact_guard.py apply --plan ABS_PLAN.json --authorize-plan INTERNAL_SHA256 --receipt ABS_NEW_RECEIPT.json --confirm-idle
~~~

同一构建身份有持久的单次执行 claim；失败后核对原回执，不换计划或删除 claim 盲重试。日志在任何删除前持久化；未完成、拒绝和不确定结果分别记录。计划、当前占用、已删除逻辑量、已知分配量和实测卷空闲差值分别报告。

该工具不证明全世界没有引用，也不能排除未来启动。macOS锁为协作锁，须持续确认静止。APFS共享块/快照等会影响真实回收量。Windows/macOS实际验证状态看当前提交检查；CI合成场景通过不等于已对真实项目执行清理。

机制依据：[Next.js构建缓存文档](https://nextjs.org/docs/app/guides/ci-build-caching)。框架目录名称只用于路由，具体清理资格由上述来源、保留、运行和文件核验共同决定。
