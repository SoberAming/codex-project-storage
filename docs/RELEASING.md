# 维护与版本发布

发布版本来自`references/verification.json`中的`bundle_version`。核心组件可以有不同版本和冻结SHA，不能为了文档看起来整齐而改写运行代码版本或历史测试结论。

## 本地校验

在独立开发环境安装`requirements-dev.txt`，不要往用户项目的生产环境装开发依赖。开发与CI使用PyYAML；核心使用不需要它。

```text
python -I -B tools/validate_repository.py --repo ABS_REPOSITORY --require-yaml
```

可加`--output ABS_OUTSIDE_REPORT.json`将报告放在仓库外的新位置。校验包括结构、语法、相对链接、工作流/模板、许可证文本和高置信隐私检查；不能证明所有秘密已被发现或作者权利已确认。

原始核心6套测试的源文件位于`tests`，每套用`--work-root ABS_ISOLATED_TEST_PARENT`运行，只创建虚构样本。发布工具、Mac ACL、测试退役和npm适配器各有独立测试，当前完整套数见CI的显式列表。精确命令见[贡献指南](../CONTRIBUTING.md)。不要对真实用户目录跑fixture测试或真实缓存清理；npm真实集成也只使用新建专用缓存。

`tests/test_cross_volume_optional.py`属于另行明确安排的实际跨卷测试，先读`--help`，不混入默认CI或把同卷模拟当实测。

## 制作安装包

```text
python -I -B tools/build_release.py --repo ABS_REPOSITORY --output-dir ABS_OUTSIDE_NEW_DIRECTORY
```

可显式传`--version 1.5.0`，必须与当前记录一致。输出目录在仓库外，工具拒绝覆盖已有结果。产物为：

- `codex-project-storage-1.5.0.zip`：顶层为`codex-project-storage`，含运行资源、许可证及公共文档。
- `codex-project-storage-1.5.0.manifest.json`：逐文件SHA、体积及构建信息。
- `SHA256SUMS`：安装ZIP和清单的校验值。

采用显式白名单，排除`.git`、`.github`、测试、开发工具、原始报告、缓存、私有配置和安装回执。文档中提到开发命令，需从源码包取得开发文件。包校验通过不代替用途与平台验收。

维护者可另制完整源码资料包，保留`.github`、测试和开发工具。源码资料包也应明确排除本机记录、产物、Git私有配置和缓存；GitHub创建tag后会提供对应源码下载。两种包用途不同，不要同名覆盖。

## 更新验证记录

记录实际代码SHA、测试系统/Python/文件系统、通过/失败/跳过、测试模式与范围。原始维护者的116项核心结果保持历史事实；远端CI、新工具和新平台结果另列实际日期及commit链接。未运行的Mac矩阵不能写成Mac已通过。

若改核心执行规则，补相应故障和竞态测试、独立样本试用及必要真实平台验证；文档/打包更新不应趁机扩大删除范围。

## 发布到GitHub

1. 确认版权署名、LICENSE和第三方说明。许可证有效文本检查不代表作者已经确认。
2. 核对仓库差异，确保没有会话、索引、数据库、凭据、完整用户扫描报告或真实fixture。
3. 推送代码，查看远端Actions实际结果；失败时先修复，保留失败记录。
4. 选定实际受测commit，创建对应版本标签和Release草稿，使用[当前升级说明](RELEASE_NOTES_v1.5.0.md)，更新其实际CI与发布状态。
5. 将三个安装包产物放入同一Release，确认下载和校验正常。首次公开可标记Pre-release；这不代表Mac能力已验收。
6. 由维护者最后发布，检查安装路径、相对文档、仓库安全入口和反馈表单。

本仓库CI使用只读内容权限，不自动创建Release或公开资料。草稿、tag、源码上传、Actions通过和正式发布是不同状态。网页操作依据见[GitHub Release文档](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)。
