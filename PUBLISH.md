# 发布到 gitee / github

本 skill 已本地提交（见 `git log`）。发布只需把当前仓库推到两个远端。
**前置条件**：在两个平台各建一个**空仓库**，仓库名建议统一为 `db-novel-writer`，所有者 `hubert_woo`：

- gitee：https://gitee.com/hubert_woo/db-novel-writer （新建时**不要**勾选 README / LICENSE / .gitignore，保持空仓库）
- github：https://github.com/hubert_woo/db-novel-writer （新建时空仓库）

建好后，在本目录执行：

```bash
# 添加远端
git remote add gitee git@gitee.com:hubert_woo/db-novel-writer.git
git remote add github git@github.com:hubert_woo/db-novel-writer.git

# 推送（当前分支为 master）
git push -u gitee master
git push -u github master
```

若 github 用 HTTPS 或已配置别的 SSH key，把 `github` 那行的 URL 换成对应地址即可。

## 可选：打 tag

```bash
git tag -a v0.1.0 -m "db-novel-writer v0.1.0: 数据库中心小说创作 skill（SQLite 状态库 + 一致性审计）"
git push gitee v0.1.0
git push github v0.1.0
```

## 说明

- 仓库不含 `*.db`（已被 `.gitignore` 忽略），读者 clone 后用 `scripts/init_db.py --seed references/seed-honglou.json` 即可重建。
- `references/seed-honglou.json` 为《红楼：硬件鬼才林黛玉》脱敏示例种子，演示真实用法；换自己的小说只需替换种子 JSON。
