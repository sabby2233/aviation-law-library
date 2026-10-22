# 航空法律资料库

一个**可检索的航空法律资料库**。只做事实层与检索：收录法规、案例与标准，每条记录可直达官方原文。

> 本站整理自公开来源，不提供法律意见，事实以官方原文为准。

---

## 定位

| 是什么 | 不是什么 |
|---|---|
| 公开的法律资料检索工具 | 不是学术出版项目 |
| 事实层：原文链接、一手材料、可核对 | **不含署名观点与学理评注** |
| 机器可读：REST / JSON / 供大模型调用 | 不是每日资讯推送站 |

观点与课程输出由微信公众号「律风助手」承担，署名观点与可引用的学术成果由论文承担。
**本站在三者中只负责"查得到、查得准、能核对"。**

---

## 五个信源

| 源 | 接口 | 内容 | 条数 | 抓取方式 |
|---|---|---|---|---|
| **eCFR** | `ecfr.gov/api/versioner` | 14 CFR 现行条文（含末次修订日） | 3191 | 官方 API，免 key |
| **Federal Register** | `federalregister.gov/api/v1` | 航空法规变更事件（文号、生效日） | 570 | 官方 API，免 key |
| **中国民航局** | `caac.gov.cn/was5/web/search` | CCAR 规章与规范性文件（含部号、有效性） | 292 | TRS 搜索接口 |
| **司法部法通网** | `lexcom.12348.gov.cn/api` | 我国涉外法律法规 + 域外法律中文译本 | 78 + 18 | 官方 API，免 key |
| **ICAO 附件** | 用户提供的官方 booklet | 18 条（Annex 1–18，中英标准名 + 分卷结构） | 标准名已核验，正文不入库 |
| **EUR-Lex / Cellar** | `publications.europa.eu/resource/celex` | EASA 基础条例、无人机与 U-space 规则包、GDPR（含条文标题） | 7（425 条条文标题） | 官方 API，免 key |
| **执法案例** | 用户早前自建仓库 | 各国 DPA 处罚与法院判决 | 49 | 快照导入（待核验） |

**合计 4224 条 / 41 个法域 / 17257 条断言。**

### 分工与不重复

- eCFR 与 Federal Register 是**同一法域的纵向补齐**：前者是"现在要求什么"（现行条文），
  后者是"刚改了什么"（变更事件）。此前只有后者，答不了实务者最常问的问题。
- 民航局 TRS 与法通网是**上下位关系**：前者是部门规章（CCAR 部级），
  后者是法律与行政法规（《民用航空法》《无人驾驶航空器飞行管理暂行条例》等上位法）。
- **ICAO 已接入 18 条附件**（Annex 1–18），来源是用户提供的 ICAO 官方
  《Annexes 1 to 18》booklet（224 页，六语种含中文）。**中英文标准名全部从 booklet
  原文抽取并与目录页逐条校验一致（18/18）**，非模型记忆。
  五种写法均可精确检索：`Annex 8` / `Annex8` / `附件 8` / `附件8` / `附件第 8 条`。
  **仅存元数据与引注，不存条文正文**（SARPs 保留版权、不得印刷分发）。
  - booklet 的边界：不含 **Annex 19**（2006 年才制定）、不含任何 **PANS 文件号**、
    只出现 `Doc 9760` 一个 Doc 号、每章仅 2–4 页概要而无条文。
  - 程序文件（`icao:doc` / `icao:pans` 命名空间）规则已就绪但数据未接入，
    查询会明确返回「本站未收录」。
- 法通网的**域外法律中文译本实测 974 条中以航空法为规范对象的为 0 条**
  （该库是"走出去"导向的投资贸易法库）。本库只收录其中与航空数据治理交叉的
  数据与网络安全类 18 条，并在 `agent.md` 中如实写明这一覆盖事实。

### 信源可达性实测记录

| 源 | 结论 |
|---|---|
| Federal Register API | 可用，免 key，含文号/生效日/CFR 引用 |
| eCFR API | 可用，免 key；`{date}` 须为**已生效版本日**（取自 `titles.json` 的 `up_to_date_as_of`），`full` 端点必须带 `Accept-Encoding` |
| 民航局 TRS | 可用；`channelid=269689` 为规章栏目，返回结构化表格（部号 + 有效性 + 发文日期 + 办文单位） |
| 法通网 | 可用；Vue SPA，接口基址在 bundle 里（`axios.create({baseURL:"/api"})`）；分页参数是 `current`/`size`（`size` 上限 100）；`/query` 是详情接口而非检索 |
| 北大法宝 MCP | 可用，但**每次仅返回 20 条**（`Total` 字段给出总量），适合核验与精查，不适合批量采集 |
| 威科先行 MCP | 接口同类，本次会话配额用尽 |

---

## 架构

静态站 + Git 版本控制。**无数据库、无后端、无构建步骤。**

```
data/
  schema.json              数据结构规范（JSON Schema）
  identifiers.json         标识符规范化规则表（数据，非代码，可独立扩展）
  record_id.py             永久标识与状态词表的单一真源
  manifest.json            完整语料（构建产物，15.5 MB）
  browse.json              首屏精简索引（构建产物，7.0 MB）
  details/<桶>/<id>.json   单条完整记录，按需加载（4199 个文件）
  records/*.json           分来源的记录文件
  snapshots/               源数据快照（便于离线重建与留痕）
  sources/registry.json    来源登记表：url、机构、证据等级、检索式、检索日期
  entities/                主体主数据（航司/机场/GDS/DPA）—— 待建
scripts/
  collect_federal_register.py   美国联邦公报
  collect_ecfr.py               eCFR 现行条文
  collect_caac.py               中国民航局规章栏目
  collect_lexcom.py             司法部法通网
  collect_eurlex.py            欧盟 EUR-Lex / Cellar（分批执行 + 增量合并）
  collect_aviation_data_cases.py 执法案例导入
  build_sources.py         由记录反推来源登记表（等级从断言派生）
  build_manifest.py        汇总生成 manifest.json
  build_browse.py          生成首屏精简索引与详情文件
  build_api.js             生成 /api/v1/ 出口
  validate.py              质量断言（唯一反幻觉机制）
site/
  index.html               检索界面
  js/{search,glossary,app}.js
  test_search.js           检索层回归测试（45 项断言）
  test_browse_parity.js    精简索引与全量索引的召回一致性（8 项）
  api/v1/                  manifest / latest / keys/ / facets/ / agent.md
```

**为什么不用数据库**：全库数据在浏览器内加载，检索完全本地完成。
Git 还额外提供数据库给不了的东西：`git blame` 的逐断言审计链、
commit SHA 的引用锚点、`/tree/<sha>` 的历史版本站。

### 首屏分层加载

完整语料 15.5 MB（gzip 1.31 MB）全量加载，对境内访问是硬伤。做法：

| 文件 | 体积 | 何时加载 |
|---|---|---|
| `data/browse.json` | 7.0 MB（gzip 1.10 MB） | 首屏。含列表渲染字段 + **预抽的检索词 terms** + 规范键原料 refValues |
| `data/details/<桶>/<id>.json` | 平均 2.3 KB | 点「展开详情」时按需拉取 |
| `data/manifest.json` | 15.5 MB | 完整语料，供下载与全量消费 |

**`site/test_browse_parity.js` 把「精简索引召回 = 全量索引召回」钉死**（30 组查询逐条比对）。
这不是可有可无的检查——开发中曾两次踩坑：Python 端切词缺"数字段单独抽出"规则，
以及为压缩体积按词长裁剪 terms（导致 `787` 从 25 条掉到 0 条）。**召回一致性优先于体积。**

---

## 检索层：三层索引与一条铁律

```
① 规范键索引  key(ns:value) → Set<recordIndex>   标识符精确查，唯一真值来源
② 字段倒排    field:token  → Set<recordIndex>     分字段，精确率 100%
③ 全文倒排    token       → Set<recordIndex>     主题发现，容错
```

**铁律：标识符查询只走 ①，绝不回落 ②③。**

理由是法律检索的语义要求"命中即证据"，未命中必须是可表达的合法答案（"库中没有"）。
假阳性比零命中危险得多——`39 CFR 39` 曾返回 275 条 `14 CFR 39` 的内容，
用户和 AI 都无法从结果外观察出退化。

修复前后（实测）：

| 查询 | 修复前 | 修复后 |
|---|---|---|
| `14 CFR 108` | 568（全库） | **0** + "未收录"告警 |
| `39 CFR 39` | 275（法域错，无迹象） | **0** |
| `14 CFR 91` | 356（精确率 15.7%） | **318（100%）** |
| `管制空域` | 141（全是 airspace） | **10** |
| `适航指令` | 332（含 57 条污染） | **276** |
| `737` / `787` / `A350` | 2 / 0 / 0 | **15 / 22 / 25** |

### 标识符规范键

规则写在 `data/identifiers.json`（数据不是代码，加一条 DPA 文号规则只需加一段 JSON）：

| 命名空间 | 示例 | 说明 |
|---|---|---|
| `cfr` | `cfr:14:39`、`cfr:14:89.305` | 吸收 `14 CFR 39` / `14 CFR Part 39` / `§39.13`；part 级与 section 级并存 |
| `fr` | `fr:91:66283` | 联邦公报文号 |
| `frdoc` | `frdoc:2026-21422` | 联邦公报文号（另一形态） |
| `ad` | `ad:2026-20-14` | FAA 适航指令号 |
| `docket` | `docket:FAA-2026-8845` | 行政案卷号 |
| `icao` | `icao:annex:13`、`icao:doc:9944` | ICAO 附件与文件号 |
| `ccar` | `ccar:91`、`ccar:290-R4` | 中国民航规章部（部号与带版次的精确式） |
| `gb` | `gb:35273:2019` | 中国国家标准 |
| `dpunr` | `dpunr:es:ps-00300-2019` | 各国 DPA 决定编号 |
| `celex` | `celex:679` | 欧盟 CELEX（自动吃掉前导零，`…0679` 与 `679` 同键） |
| `eureg` | `eureg:2019:947` | 欧盟人读编号（`(EU) 2019/947` / `Regulation (EU) 2019/947` 同键） |
| `euarticle` | `euarticle:132` | 欧盟条文号（Article 132 = EASA 条例的个人数据处理条款） |

站内可直接用 `cfr:14:39` 语法精确查，也支持前缀（`ad:2026-`）。

### 中英检索

数据源多为英文原文，而读者是中文。`site/js/glossary.js` 维护中英术语对照
（适航、无人机、远程识别、民航规章、涉外法规、数据保护等），
中文查询自动展开为英文候选（组间 OR）。**采用最长匹配**——查「适航指令」只展开「适航指令」，
不再连带展开「适航」（此前子串污染使「管制空域」返回全部 airspace 记录）。

对照表随数据一起版本化，并带 `selfCheck()` 自检（键唯一性、值非空）。

---

## 核心机制：质量断言代替提示词

`scripts/validate.py` 是本库唯一的反幻觉机制，**不调用大模型，全部为确定性检查**。
方法论纪律写进代码，而不是留在文档里等人遵守。

| 规则 | 内容 |
|---|---|
| `SRC-01` | 断言引用的 sourceId 必须存在于来源登记表 |
| `SRC-03` | L4/L5 级来源不得入库，须退入待核实线索队列 |
| `SRC-06` | 来源登记等级必须与该来源下断言的等级一致（取最严） |
| `SRC-07` | 人工录入的来源不得标为 L0（除非声明已核验） |
| `EVD-01` | 一手来源占比（断言级加权）≥ 80% |
| `EVD-02` | **核心事实字段**一手支撑率 ≥ 80%（只看决定日/金额/裁判结论，无法灌水） |
| `DAT-01` | 时间不等式：决定日 ≤ 公布日 ≤ 获知日；公布日 ≤ 生效日 |
| `DAT-02` | 案件缺决定日须标注"决定日未知"，不得用报道日顶替 |
| `PEN-02` | 最终罚款额不得高于拟议额 |
| `PEN-03` | 有金额必须有 `amountBasisText`（官方原文摘录） |
| `PEN-04` | 多币种时禁止跨币种合计 |
| `STA-01` | 状态机非法转换拦截（撤销后不可复活） |
| `STA-02` | 废止/失效/被取代的记录须保留可追溯的终结说明 |
| `CIT-02` | 文献引用须有检索凭证（检索库/检索式/日期/命中位置） |
| `CIT-03` | 程序性处置案件不得用作实体规则先例 |
| `CIT-04` | 裁判结论字段须 L0/L1 级证据（回原文核对） |
| `CIT-05` | 脚注编号单一真源，禁止手写编号 |
| `ENT-01` | 主体字段必须是 entityId 外键，禁止内嵌主体文本 |
| `DEAD-01` | 全库取单一默认值的字段判失败（死字段检测） |
| `LOC-01` | locator 必须是原文定位，不得指向本站自身标识 |
| `MAN-03` | meta 声明的各类计数须与实际一致（字段名与内容相符） |
| `ARC-01` | 无快照的来源须显式声明 `archiveStatus` |
| `R-01`~ | 检索层断言由 `site/test_search.js` 承担（45 项） |
| `PARITY` | 精简索引召回一致性由 `site/test_browse_parity.js` 承担（8 项） |

**开发过程中这些断言实际抓出并修掉的真问题**（说明断言有牙齿，不是摆设）：
SRC-01 未登记 sourceId · ID-01 recordId 格式 · ID-02 跨年撞号 · 罚款口径三态不一 ·
日期口径混用（把新闻发布日记为决定日）· 术语表子串污染 · API 与客户端语义分叉 ·
`meta.caseCount` 命名错误 · locator 指向自己旧仓库 · 状态词表在采集器与断言表之间漂移 ·
来源渠道判定只认 federalregister 导致 CAAC 被误判为人工录入。

### 单一真源：ID 规则与状态词表

`scripts/record_id.py` 是永久标识与状态机词表的唯一出处，采集器与断言都从它导入。
早期版本两者各写一份，导致 `in_force`（采集器）与 `effective`（断言表）不匹配，
151 条废止记录全被误判为非法状态转换。

**永久标识格式**：`AVA-<法域>-<类型>-<来源标识>`

| 示例 | 含义 |
|---|---|
| `AVA-US-CFR-89-89-305` | 美国 14 CFR 89.305 现行条文 |
| `AVA-US-FR-R-2026-214220` | 美国联邦公报 RULE |
| `AVA-CN-CCAR-290-R4` | 中国 CCAR-290 第 4 版 |
| `AVA-ES-ADP-A-009` | 西班牙航空数据保护案例 |
| `AVA-CN-LAW-100063964526000157` | 司法部法通网收录法规 |

---

## 数据模型要点

- **断言式结构**：每条记录是一个断言集合，每条断言挂自己的 `sourceId` 与 `locator`。
- **证据等级 L0–L5**：L0 官方一手文书 / L1 官方二手 / L2 国际组织文件 /
  L3 专业二手 / L4 一般媒体（仅可作线索）/ L5 模型生成（永不作为来源）。
  门槛作用在**写入与发布**，不是检索。
- **六个时间字段**：决定日 / 公布日 / 通报日 / 生效日 / 废止日 / 获知日，互不混用。
- **罚款拆表**：拟议额 / 最终额 / 减免依据分行，原币为准。
- **永久标识**：一经分配永不复用、永不重编。
- **状态机**：`draft / adopted / promulgated / effective / not_yet_effective /
  amended / superseded / repealed / invalidated / settled / under_appeal / final`。

---

## 对外出口

| 地址 | 内容 |
|---|---|
| `/api/v1/manifest.json` | 完整语料（含完整证据链 assertions） |
| `/api/v1/latest.json` | **按源分层取样**（非全库按日期——单一源会占满时间窗口） |
| `/api/v1/keys/{ns}.json` | 规范键 → recordId 表，AI 可自由组合查询 |
| `/api/v1/facets/index.json` | 分面统计（法域/类型/状态/主题/证据等级） |
| `/api/v1/facets/{类型}_{法域}.json` | 已排好序的切片 |
| `/api/v1/agent.md` | 给大模型的接入说明（含决策树、硬约束、信源覆盖实况） |
| `/data/details/<桶>/<id>.json` | 单条完整记录（查一条不要拉 16 MB） |

**API 与客户端在构造上不可能不一致**：`build_api.js` 不自己分词、不自己匹配，
只从 `site/js/search.js` 构建的索引里查表。

---

## 使用

```bash
# 采集
python scripts/collect_federal_register.py
python scripts/collect_ecfr.py            # 约 13 分钟（38 个 part）
python scripts/collect_caac.py
python scripts/collect_lexcom.py
python scripts/collect_aviation_data_cases.py --source-url data/snapshots/cases_source.json

# 汇总与登记
python scripts/build_sources.py
python scripts/build_manifest.py
python scripts/build_browse.py

# 质量门禁（CI 必跑）
python scripts/validate.py --data data/manifest.json
node site/test_search.js
node site/test_browse_parity.js

# API 出口
node scripts/build_api.js

# 本地预览
python -m http.server 8000
# 打开 http://localhost:8000/site/
```

> 直接双击 `index.html` 会被浏览器同源策略拦截 `fetch`，须用本地服务器打开。

---

## 许可

- 代码：MIT
- 数据内容：CC BY 4.0（署名），**仅及于本库自行编制的编排与事实性转述**
- 原始文本与图片：权利归各权利人，本站不转载，只提供元数据与链接

## 已知边界

- 4199 条为**本站收录范围**，不是航空法律领域的全集
- 案例类的决定日全部缺失（49 条），须回官方一手核验后才可作为引证依据
- 案例中 7 条为二手来源（律所简报、媒体）
- 中国民航规章的"失效/废止/历史版本"只表明官方栏目标注的状态，
  废止的确切日期与替代规章需回原文核实
- 主体主数据（entities/）为空，跨主体聚合分析尚不可用
- 证据均为活链接（无存档快照），官方站点改版即失去证据
- 域外航空法覆盖美国（eCFR）与欧盟（EUR-Lex）两个法域；**ICAO 未接入**（反爬 + 版权）
- 欧盟法源只存元数据与**条文标题**，不存条文正文（EU 决策文本再利用受官方声明约束）
- EUR-Lex 的法源收录采用「候选清单 + 逐条核验」，候选清单扩充需人工核验——
  实测凭记忆写的 27 条 CELEX 中仅 3 条为航空法、7 条编号不存在、17 条指向无关领域
