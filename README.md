# ☀️ Horizon Brief

**一个开源的、agenda 感知的每日新闻筛选引擎。** 每天早上从 ~14 个精选源（宏观/市场/前沿科技/crypto/国内）抓取最近 36 小时的新闻，用一次 Claude 调用按「这会不会改变*你的*仓位或研究议程」排序，推送一份双区简报到 Telegram / 飞书：

- **🎯 与你直接相关** — 与你的仓位、研究议程、关注催化剂挂钩的 3-5 条
- **🔭 视野扫描** — 全市场与前沿科技的结构性信号 3-5 条，刻意避开你的回音室

通用简报满大街都是；这个工具的全部价值在于排序函数里注入了**你自己的状态**——而那份状态（`AGENDA` secret）永远不进仓库。

## 它不是什么

- 不是实时告警（每天一次，GitHub Actions cron）
- 不是多用户 SaaS——**fork 即订阅**：fork 本仓库，填上自己的 secrets，就得到自己的个性化筛选器
- （暂时）不是量化因子。但 `data/` 目录从第一天起就以点态（point-in-time）格式记录每条候选新闻的发布/抓取时间戳、主题标签和通用重要性分——如果未来想检验「新闻信号对期权波动率有没有预测力」，无 look-ahead 偏差的原料已经在了

## 架构

```
GitHub Actions (每天 21:30 UTC = 布里斯班 07:30)
  └─ src/fetch.py   拉 RSS → 36h 窗口 + 去重 + 每源上限 → out/candidates.json
  └─ src/brief.py   单次 claude -p 调用（注入 AGENDA secret）→ out/brief.json
  │                 同时把通用元数据+评分写入 data/YYYY-MM-DD.jsonl（公开数据集）
  └─ src/push.py    推送 Telegram / 飞书（配了哪个推哪个）
  └─ commit data/ + state/ 回仓库
```

个性化的部分（`out/`，含「为什么与你相关」）被 gitignore；入库的只有通用元数据。

## 部署（fork 后 5 分钟）

1. **Fork 本仓库**（public fork 即可，Actions 免费不限分钟）
2. 在 repo Settings → Secrets and variables → Actions 添加：

   | Secret | 必需 | 怎么拿 |
   |---|---|---|
   | `CLAUDE_CODE_OAUTH_TOKEN` | ✅ | 本机装 Claude Code 后运行 `claude setup-token`（用 Pro/Max 订阅额度，零边际成本） |
   | `AGENDA` | ✅ | 照 [agenda.example.md](agenda.example.md) 写你自己的，整个文件内容贴进去 |
   | `TELEGRAM_BOT_TOKEN` | 二选一 | 找 [@BotFather](https://t.me/BotFather) 建 bot |
   | `TELEGRAM_CHAT_ID` | 二选一 | 给 bot 发条消息后访问 `api.telegram.org/bot<token>/getUpdates` 取 chat id |
   | `FEISHU_WEBHOOK_URL` | 二选一 | 飞书群 → 设置 → 群机器人 → 添加自定义机器人，复制 webhook |
   | `FEISHU_KEYWORD` | 可选 | 若机器人开了「自定义关键词」安全策略，填那个关键词（以 #话题 形式附在正文末尾；注意校验只看正文不看标题） |

3. Actions 页签手动跑一次 `daily-brief` 验证，之后每天自动

任何一步失败（token 过期、源全挂、推送被限流）都会向已配置的渠道推一条**失败告警**带运行日志链接——简报工具最危险的死法是静默死亡，这里把它焊死了。简报末尾还会自动带"⚠️ 源异常"脚注，源腐烂时你会在第一时间看到。

## 保持 agenda 新鲜（重要）

排序质量 = agenda 新鲜度。研究议程变了就在本地改 `agenda.md`（已 gitignore），然后一条命令同步：

```powershell
gh secret set AGENDA -b (Get-Content agenda.md -Raw)
```

> ⚠️ Windows 用户设置所有 secret 都请用 `-b` 参数传值。PowerShell 管道（`"..." | gh secret set`）会给值偷偷加上 U+FEFF（BOM），导致运行时 `InvalidSchema: No connection adapters` 这类诡异错误；`<` 重定向则在 PowerShell 里直接不可用。代码层已对凭证做了 BOM 清洗兜底，但源头干净更好。

把这步做进你"策略书变更"的工作流里——议程变更本来就要写文档，顺手同步一份。未来如果想自动注入实时仓位，可以让交易仓库的本地定时任务定期跑同一条命令。

## 本地调试

```powershell
pip install -r requirements.txt
python src/fetch.py
$env:AGENDA = Get-Content agenda.md -Raw   # 你的私有 agenda（已 gitignore）
python src/brief.py                         # 需要本机已登录 claude CLI
$env:TELEGRAM_BOT_TOKEN = "..."; $env:TELEGRAM_CHAT_ID = "..."
python src/push.py
```

## 调整口味

- 换源/加源：编辑 [config/sources.yaml](config/sources.yaml)（死源只会告警不会让运行失败）
- 改排序哲学：prompt 在 [src/brief.py](src/brief.py) 顶部
- 改推送时间：[.github/workflows/daily.yml](.github/workflows/daily.yml) 的 cron

## License

MIT
