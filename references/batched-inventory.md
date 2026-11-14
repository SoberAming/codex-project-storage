# 大项目的可续扫元数据清单

project_batches.py 将任务发现、分批扫描和汇总分开。全程不执行项目命令、不读取项目文件正文、不清理文件。输出放项目外健康位置，不预设盘符。

## 调用

~~~text
python ABS_SKILL/scripts/project_batches.py discover --project ABS_PROJECT --output ABS_NEW_LEDGER --focus builds
python ABS_SKILL/scripts/project_batches.py scan --ledger ABS_LEDGER --max-files 5000 --max-seconds 25
python ABS_SKILL/scripts/project_batches.py report --ledger ABS_LEDGER --output ABS_NEW_REPORT.json
~~~

重复 scan 继续队列。discover --unit RELATIVE_UNIT 可重复传入，选择明确、互不重叠的子单元；scan --unit EXACT_DISCOVERED_UNIT 可优先完成其中某个任务。默认发现一级目录和 .tmp、.runtime、task-runs、outputs、releases 中的直接任务；发现本身有数量预算。具体任务上限不等于无效判断。

--focus metadata 观察允许范围内的普通文件元数据；--focus builds 跳过依赖、媒体、数据等保留子树，保留其排除原因和大小未知状态，只计 .next 中的文件。构建聚焦结果不能冒充全项目总量。

## 续扫和完整性

- SQLite 清单是本工具在新目录创建的私有报告，身份绑定到专用清单；绝不打开 Agent 的会话或索引数据库。
- 目录一次枚举为持久队列；每批提交检查点，恢复后不重新遍历已完成目录。一个目录有独立条目上限，超过则标错误，不假称完成。
- 目录身份或成员在批次之间发生变化，该单元停止并保留；其他独立单元仍可调查。要刷新该单元，建立新清单，不盲目覆盖旧证据。
- 路径和文件身份保存在清单中，没有4096节点后的匿名合并。报告列出准确构建根，以及每个观察单元的 complete/pending/scanning/error 状态。
- 多硬链接按身份归并观察量，每个多链接路径单独保护；独立文件仍列入审查。未知身份不合并到同一个零ID，不计为可执行收益。
- 不跟随符号链接、联接、私密状态根或 Git 内部目录。排除范围大小未知，不能记录成空目录。

independent_review_bytes 是元数据审查优先级，不是可清理量。报告完成表示所列元数据范围完成，不证明已停用、没有全球引用或具备删除授权。清理仍需独立执行器重新核验精确成员和当前使用情况。

清单含项目文件名，留在本机；开源时只发布匿名样例和合成测试。--max-seconds 在当前目录快照结束后检查，不承诺抢占正在进行的系统调用。崩溃残留 command-lock 时先核对原进程和证据，不自动删除或抢锁。
