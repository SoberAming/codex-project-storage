# 第三方说明

## 运行时

六个核心脚本使用 Python 标准库与本包模块。仓库和安装包不分发 Python 解释器、pip/uv/npm 实现、浏览器、模型、数据集或第三方清理器。运行环境中的这些组件遵循其各自许可。

pip是已有可信环境中的受限外部调用对象，不是本仓库包含的库；未满足支持条件时不给执行资格。标准库可用不表示所有平台已完成实测。

## 开发和持续集成

- PyYAML只用于开发/发布校验，安装依赖时适用[PyYAML自身许可](https://github.com/yaml/pyyaml/blob/main/LICENSE)。不把其源码打进Skill安装包。
- GitHub Actions工作流引用`actions/checkout`、`actions/setup-python`及工作流中列出的官方动作。它们由GitHub执行，遵循各自仓库许可，不打包到安装包。
- MIT文本使用标准[MIT许可](https://opensource.org/license/mit)；本仓库的具体版权声明见[LICENSE](LICENSE)。

## 参考资料

文档中链接的项目与资料见[致谢](ACKNOWLEDGEMENTS.md)。本仓库许可不重新授予链接目标的代码、商标或内容权利。后续引入外部实现、图标、字体、素材或规则包时须在本文件补来源、许可和必要通知。
