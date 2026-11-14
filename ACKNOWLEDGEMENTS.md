# 来源与致谢

本项目围绕项目存储归属、用户决策、精确计划和执行验收实现工具。下列资料帮助核对机制与设计取舍；链接不代表依赖、合作或官方背书。

| 来源 | 参考内容 |
| --- | --- |
| [OpenAI Skills](https://learn.chatgpt.com/docs/build-skills) | Skill结构、发现位置与调用 |
| [OpenAI环境变量](https://learn.chatgpt.com/docs/config-file/environment-variables)、[工作树](https://learn.chatgpt.com/docs/environments/git-worktrees) | 状态根与工作树关系，不将聊天和索引当项目缓存 |
| [pip cache](https://pip.pypa.io/en/stable/cli/pip_cache/)、[pip配置](https://pip.pypa.io/en/stable/topics/configuration/) | 由所属工具管理缓存，核实隔离参数和真实配置 |
| [uv缓存](https://docs.astral.sh/uv/concepts/cache/) | 缓存锁、共享和链接依赖的影响 |
| [Czkawka](https://github.com/qarmin/czkawka) | 分阶段重复证据、参考目录与硬链接度量 |
| [BleachBit](https://github.com/bleachbit/bleachbit) | 预览与执行范围保持一致、排除规则 |
| [Python文件操作文档](https://docs.python.org/3/library/shutil.html) | 内容校验与平台元数据保真是不同条件 |
| [GitHub Docs](https://docs.github.com/en/communities) | 社区资料、问题模板与安全报告机制 |

更具体的采用方式见[设计参考](references/mature-patterns.md)。本次发布准备未引入这些清理器的实现或规则包，也未捆绑它们的可执行程序。新增外部代码时，贡献者需明确来源、许可及保留通知，不能将设计参考误写为代码授权。
