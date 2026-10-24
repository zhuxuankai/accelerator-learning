# 评测集说明

- 根目录 `questions.jsonl` 是 v1 文件名级 smoke 数据，只用于确认命令能运行，不用于证明质量。
- `v2/demo-dev.jsonl` 和 `v2/demo-heldout.jsonl` 使用合成公开语料，适合 CI 和安装检查。
- `v2/local-*.template.jsonl` 是个人语料的人工标注模板。
- 正式本地评测必须复制模板为 `local-dev.jsonl` / `local-heldout.jsonl`，
  逐题填入精确 `rel_path`、`unit_label` 和答案支撑片段，并将 `approved` 改为 `true`。
- held-out 集在调参和选择模型时不可使用。
