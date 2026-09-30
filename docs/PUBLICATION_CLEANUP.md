# 公开历史与发布产物清理

## 整合基线

当前源码基线整合桌面与 CLI 的共享业务、扫码登录、任务巡检、账号异常保护与凭证安全。许可证、上游作者归属和来源说明保留；个人实测过程与本机账号设置不属于公开文档。

公开 Git 历史从单个整合提交开始，作者使用 GitHub noreply 地址。旧开发提交、版本标签、Release 二进制包、Actions 构建产物及旧运行日志不再作为本仓库发布内容。新 EXE 须单独检查和验收后发布。

本机已安装程序、凭证、暂停状态和任务预算不因远端清理而改变。第二阶段策略仍等待调研。

## 已有克隆

推荐重新克隆。若有未提交工作，先在本机保存需要的文件，再复制到新克隆中审核。

不要把旧分支合并进整合后的 main，也不要 mirror-push 本机旧备份，否则可能恢复已经清理的历史和标签。历史备份仅在本机受限目录保存，不上传 GitHub。

## 清理的边界

删除远端引用、发布包和构建记录不能收回他人的下载、克隆、缓存或 fork。旧提交按 SHA 或从 fork 网络仍可能访问；脱离 fork 网络和清理当前引用也不等于服务器历史对象已彻底擦除。GitHub Support 对敏感数据缓存和不可写引用有专门处理流程，但不受理一般非敏感开发历史的完全擦除。

如果发现真实凭证曾公开，先在平台撤销相关会话/更新凭证，再申请必要的服务器清理。不得把真实凭证附在公开 Issue 中。

参考：[GitHub 敏感数据清理说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)、[脱离 fork 网络](https://docs.github.com/en/pull-requests/how-tos/work-with-forks/detaching-a-fork)。
