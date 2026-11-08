# 进度与阅读状态

## 查看

```powershell
pwsh tools/run.ps1 status
pwsh tools/run.ps1 progress list
pwsh tools/run.ps1 reading list
```

`progress.csv` 管理课程、仿真和写作；`reading.csv` 管理论文。两者都是个人数据，不进入 Git。

## 旧进度迁移

只有用户明确要求迁移旧 `进度追踪.csv` 时运行：

```powershell
pwsh tools/run.ps1 progress import-legacy -DryRun
pwsh tools/run.ps1 progress import-legacy -Accept
```

即使旧行写着“已完成”，导入后也要保留原来源；来源为“推断”的行不得自动改成“已确认”。

## 确认完成

```powershell
pwsh tools/run.ps1 progress confirm <id> --evidence "作业、代码、笔记或用户明确确认"
pwsh tools/run.ps1 reading confirm <paper-id> --evidence "读书笔记、汇报或用户明确确认"
```

缺少证据时拒绝修改。不得因为文件存在、论文被推荐、计划中出现或筛选过就标记完成。
`last_planned` 只表示安排日期。
