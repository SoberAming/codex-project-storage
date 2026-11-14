# 兼容性与验证状态

当前升级版本：1.4.0。原始维护者验证日期：2026-11-14。下表保留1.3历史记录；新增运行资格、npm和画像测试以[1.4升级记录](RELEASE_NOTES_v1.4.0.md)及对应组件SHA为准，不沿用1.3托管CI来声称1.4已跨平台验收。

| 环境/功能 | 状态 |
| --- | --- |
| Windows / Python 3.13.13，1.4候选 | 10套共246项：237通过，9项平台/链接能力跳过；另32组独立目标复核通过；新Mac矩阵未运行 |
| Windows / Python 3.13.13，历史1.3 | 核心6套共116项：114通过，2跳过 |
| 原始样本文件系统 | E样本卷缺少原生符号链接/硬链接创建能力，因此2项明确跳过；身份别名边界另有模拟 |
| Windows专用pip26.1.1 | 全新隔离缓存真实download一次、purge一次；6缓存文件共87,982逻辑字节，保留文件哈希不变，无install |
| pip25.0.1 | 实现已纳入受支持版本及模拟合同测试，未在此记录中完成该版本的真实purge |
| 中间件独立试用 | 冻结6脚本与相关说明前后不变，虚构项目删2预览共136字节，11保留文件及状态索引不变 |
| macOS / APFS | 公开版使用GitHub macOS runner执行隔离样本，结果以实际发布commit为准；个人Mac设备/外盘/业务工作流尚未验收，协作锁不能阻止非协作写入 |
| Python3.10 | 原始维护者仅做语法检查；首次公开CI中Windows3.10已通过，当前发布revision仍以Actions实际结果为准 |
| Linux | 未作正式支持和运行承诺；POSIX分支不等于Linux已验收 |
| 跨卷NTFS→exFAT | v1.2有小样本真实验证；迁移脚本SHA未变，共用guard后来补强。历史不等于v1.3所有平台重新验收 |
| 网络盘、云占位、复杂元数据 | 不作为普通本地目标默认执行；不支持情形保留并另立方案 |
| 其他Agent宿主 | Skill结构可参考，权限和工具管理机制需单独验证；没有WorkBuddy等宿主实测承诺 |

## 自动测试配置

源码包含Windows/macOS、Python3.10/3.13矩阵，以及仓库检查、隔离测试与安装包构建。[实际CI记录](https://github.com/SoberAming/codex-project-storage/actions/workflows/ci.yml)应与发布commit对应。首次公开的[原始运行](https://github.com/SoberAming/codex-project-storage/actions/runs/43534331248)保留了Windows两格通过与Mac空ACL分支失败，后者已增加窄修复和15项回归，未跳过迁移检查。新增测试与原始116项分列，不把模拟或跳过描述为原生成功。

该兼容修复依据Apple原始实现：[ACL查询路径](https://raw.githubusercontent.com/apple-oss-distributions/Libc/main/posix1e/acl_file.c)在对象查询成功后继续读取ACL属性，[ACL属性未设置](https://raw.githubusercontent.com/apple-oss-distributions/Libc/main/gen/filesec.c)也可能返回ENOENT。执行器只在对象前后普通类型和身份/元数据稳定时确认无扩展ACL；实际缺失、漂移或权限/I/O错误仍拒绝。

原始核心证据摘要保留在[verification.json](../references/verification.json)。原始本机路径、安装回执和完整QA样本不随开源包公开。新增发布工具的检查单独记录，不能改写核心测试计数。

## 已知功能范围

项目类型线索覆盖广于自动执行能力。通用清理执行器不删除依赖、业务或状态数据库、Git对象、共享模型或未知构建目录。独立退役器只处理正向证明可丢弃的合成PG测试data；当前支持的布局和证据条件见[规则](../references/retired-runtime.md)。原生缓存限分别合格的专用pip与npm10.9.2；uv、其他版本、共享/默认缓存为建议。需要原路径兼容、改应用配置或活动状态迁移的对象不进入通用迁移器。
