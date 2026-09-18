# MTG 中文卡牌向量数据库

面向指挥官(EDH)组牌辅助的本地卡牌语义检索库。数据为中英双语,支持中文或英文自然语言查询,并按颜色、法术力值、类型、赛制合法度等条件过滤。

## 数据源

| 源 | 用途 |
|---|---|
| [mtgch.com API](https://mtgch.com/api/v1/docs) | 全量中文卡名/类别/规则叙述/风味文本(社区翻译 + 官方中文),覆盖 1050 个系列 |
| Scryfall Bulk `oracle_cards` | 英文 Oracle 基准文本、合法赛制、edhrec 排名、价格 |
| Scryfall Bulk `all_cards` | 官方简体中文(zhs)印张,补充双面卡各面中文 |
| Scryfall Tagger `oracle_tags` | 社区功能标签(去除 cycle-* 归属类噪声)-> `sf_tags` |

## 产物

```
data/
  cards.jsonl            # 统一卡牌库,38,864 张(oracle 级别去重),每行一个 JSON
  slang.txt              # 语义搜索黑话词典(黑话=展开描述),页面可编辑,热生效
  tags.jsonl             # LLM 打标结果(ai_tags/ai_synergy/ai_desc),只读源头
  vectordb/cards.lance   # LanceDB 向量表(38,864 行,384 维向量 + FTS 全文索引)
  raw/                   # 原始抓取数据(可删除后按脚本重抓)
scripts/
  update_data.sh         # 一键更新数据快照并重建(自动备份、保留 AI 标签)
  fetch_scryfall.py      # 下载 Scryfall bulk(自动发现最新地址,流式转 jsonl)
  fetch_mtgch.py         # 抓取 mtgch 全部系列卡牌(断点续传)
  fetch_details.py       # 抓取双面卡/特殊牌详情(断点续传,限速友好)
  extract_zhs.py         # 从 all_cards 提取中文印张索引
  build_cards.py         # 三源合并 -> cards.jsonl(含拼音首字母 name_py、中文卡图优先)
  merge_tags.py          # Scryfall Tagger 标签 -> sf_tags
  tag_cards.py           # LLM 批量打标(GLM-4-Flash/DeepSeek),增量写入 tags.jsonl
  merge_ai_tags.py       # AI 标签去重合并进 cards.jsonl
  prefer_zhs_images.py   # 卡图就地换中文版本(同步向量库,不重新嵌入)
  build_vector_db.py     # 嵌入 + 建 LanceDB(断点续传,MTG_DB_DIR 可指定输出目录)
  query_db.py            # 语义查询 CLI
```

## 查询用法

```bash
python3 scripts/query_db.py "每当有生物死去时抓牌" -n 8 --commander
python3 scripts/query_db.py "ramp extra lands" --colors G --cmc-max 4
python3 scripts/query_db.py "保护指挥官的武具" --type 神器
python3 scripts/query_db.py "draw cards" --keyword "Drawing" --json
```

过滤参数:`--colors BR`(颜色认同包含)、`--cmc-max/--cmc-min`、`--type`(类型行关键词,中英均可)、
`--commander`(仅指挥官合法)、`--no-dfc`、`--keyword`(Scryfall 关键词)、`-n` 结果数、`--json` 输出完整卡数据。

## cards.jsonl 字段(每行)

- `oracle_id / name_en / name_zh / name_py` — 标识、中英卡名、中文名拼音首字母(如 罗堰妖精 -> lyyj)
- `type_line_en / type_line_zh / oracle_text_en / oracle_text_zh / flavor_text_zh` — 双语文本
- `mana_cost / cmc / colors / color_identity / keywords / power / toughness / loyalty / defense / produced_mana`
- `legalities`(全赛制)/ `edhrec_rank` / `prices`
- `rarity / set_code / collector_number / released_at / image_url / art_crop / all_sets`(中文卡图优先)
- `sf_tags` — Scryfall Tagger 社区功能标签
- `ai_tags / ai_synergy / ai_desc` — LLM 打标:功能标签 / 配合思路 / 一句话功能定位
- `is_dfc / layout` — 双面卡 `faces` 列表含每面双语( name/type/text 各中英一对 )

## 搜索能力(Web)

搜索栏一个框,四种能力自动路由(接口 `GET /api/search`):

| 输入 | 走的通道 | 例子 |
|---|---|---|
| 中文卡名 | 卡名精确/子串 | `阳光` → 阳光戒、阳光饰符 |
| 拼音首字母 | 首字母索引(精确>前缀>包含) | `lyyj` → 罗堰妖精 |
| 英文卡名 | 子串 + 分词前缀 + difflib 模糊纠错 | `llan sen`、`soll ring` → Sol Ring |
| 自然语言描述 | 向量 + FTS + 黑话扩展三路 RRF 融合 | `消灭所有生物` → 神之愤怒 |

- 语义路的嵌入文本 = 名称 + 类型 + **AI 功能定位** + 功能标签 + 双语规则,黑话(如 `轮子`、`加速`、`扫场`)
  在嵌入前自动展开成卡牌文本里的真实描述;词典在 `data/slang.txt`,
  页面搜索栏"词典"按钮可直接查看/编辑,保存即生效(也可 `GET/PUT /api/slang`)
- 卡名模式(fts)下:首字母 > 子串 > 模糊 > (全无命中时)FTS 兜底
- 所有通道都支持颜色/法术力值/类型/稀有度/指挥官合法等过滤条件
- 详情页:AI 标签云 + 功能定位、EDHREC 主将使用率(悬停显示主将卡图与使用率)、
  规则叙述默认中文(点击展开英文)、版本号点击跳 Scryfall 该印张

## 查询页面(Web)

```bash
cd web && npm run dev     # 一键启动:前端(7100) + 后端 API(8000) + 打开 LanceDB
```

浏览器打开 http://localhost:7100 。数据库(LanceDB)为嵌入式,随后端自动打开,无需单独启动;
Ctrl+C 停止时后端随之关闭。详见 `web/` 目录。

## 重建流程

一键更新(推荐,自动备份并保留 AI 标签):

```bash
bash scripts/update_data.sh
```

等价的手动步骤:

```bash
python3 scripts/fetch_scryfall.py         # 下载 Scryfall bulk(自动发现最新地址)
python3 scripts/fetch_mtgch.py 200        # 重复运行直到 exit=0
python3 scripts/fetch_details.py 500      # 可选:补双面卡详情
python3 scripts/extract_zhs.py            # 需先下载 all-cards.jsonl.gz 到 data/raw/
python3 scripts/build_cards.py
python3 scripts/merge_tags.py             # Scryfall Tagger 标签 -> sf_tags
python3 scripts/merge_ai_tags.py          # AI 标签 -> ai_tags/ai_synergy/ai_desc
python3 scripts/build_vector_db.py        # 中断后重跑自动续传
```

数据安全说明:

- `update_data.sh` 第 0 步会把 `cards.jsonl` / `tags.jsonl` 备份到 `data/backup/<时间戳>/`
- AI 标签源头 `data/tags.jsonl` 全程只读;重建 `cards.jsonl` 后由 `merge_ai_tags.py` 按 oracle_id 合并回去
- 向量库 `data/vectordb` 是从 `cards.jsonl` 全量再生的,删旧重建不丢任何数据
- 打标签任务(`tag_cards.py`)运行期间不要执行更新,等它写完再跑

嵌入模型:`paraphrase-multilingual-MiniLM-L12-v2`(本地 ONNX,384 维,中英双语)。

## AI 标签管线

1. `python3 scripts/tag_cards.py <批数>` — LLM(默认 GLM-4-Flash,免费)批量打标,断点续传,增量写 `data/tags.jsonl`
2. 定时任务"AI 标签完成后自动合并进卡片库"检测到打标进程结束且 tags.jsonl 有更新时,自动执行 `merge_ai_tags.py`
3. 定时任务"AI 标签合并完成后自动重建向量库"检测到合并完成后,自动以含 ai_desc 的新嵌入文本重建向量库(构建到 `vectordb_new` 后原子替换,不影响查询),完成发通知
4. 两个任务都在 `tags.jsonl` 再次更新时自动跟进;日常更新数据跑 `update_data.sh` 即可,管线自动衔接

## 已知限制

- 约 294 个 oracle(主要为衍生物/特殊版式)无中文名;指挥官合法卡的中文规则文本覆盖率 100%
- 部分炼金术(Alchemy)数字卡的双面详情未完全抓取(`fetch_details.py` 可随时续跑)
- `prices` 为 Scryfall 美元价;人民币价格可走 mtgch 接口按需补
