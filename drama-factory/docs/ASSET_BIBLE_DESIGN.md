# 资产圣经设计文档

## 1. 一句话命题
多镜头生成时角色和场景老是走样，因为每个镜头都重新画。资产圣经把角色三视图、场景空镜、道具白底图先固定下来，后面所有镜头只引用这些固定图，不重画。

## 2. 实体设计

### 2.1 AssetBible
项目级实体，一个项目可以有多条记录，每条对应一个冻结版本。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Long | 主键 |
| projectId | Long | 项目 id |
| version | Integer | 版本号，每次冻结 +1 |
| frozenAt | LocalDateTime | 冻结时间，未冻结为空 |
| frozenBy | String | 冻结人 |
| createdAt | LocalDateTime | 创建时间 |
| updatedAt | LocalDateTime | 更新时间 |

### 2.2 AssetBibleItem
资产圣经条目，记录某个锚点资产在圣经里的位置。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Long | 主键 |
| bibleId | Long | 关联 AssetBible.id |
| kind | String | 类型：character_view / scene_plate / prop_white |
| assetId | Long | 引用 assets.id，不复制文件 |
| label | String | 展示名，如"主角-林小满" |
| sortOrder | Integer | 排序，小的在前 |
| createdAt | LocalDateTime | 创建时间 |
| updatedAt | LocalDateTime | 更新时间 |

### 2.3 建表 SQL（SQLite）

```sql
CREATE TABLE asset_bible (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    frozen_at TEXT,
    frozen_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE asset_bible_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bible_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    asset_id INTEGER NOT NULL,
    label TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (bible_id) REFERENCES asset_bible(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);
```

### 2.4 Java 实体字段

**AssetBible.java**

```java
@Entity
@Table(name = "asset_bible")
public class AssetBible {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "project_id", nullable = false)
    private Long projectId;

    @Column(name = "version", nullable = false)
    private Integer version;

    @Column(name = "frozen_at")
    private LocalDateTime frozenAt;

    @Column(name = "frozen_by", length = 100)
    private String frozenBy;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;
}
```

**AssetBibleItem.java**

```java
@Entity
@Table(name = "asset_bible_item")
public class AssetBibleItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "bible_id", nullable = false)
    private Long bibleId;

    @Column(name = "kind", length = 32, nullable = false)
    private String kind;

    @Column(name = "asset_id", nullable = false)
    private Long assetId;

    @Column(name = "label", length = 255)
    private String label;

    @Column(name = "sort_order", nullable = false)
    private Integer sortOrder;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;
}
```

## 3. 流程

### 3.1 冻结
1. 项目达到可冻结条件：角色、场景、道具的锚点资产都已生成并上传到 assets 表。
2. 一键冻结：把当前所有锚点资产打包成 AssetBibleItem，写入一条 AssetBible 记录。version 取当前项目最大版本 +1，记录 frozenAt 和 frozenBy。
3. 冻结后 bible 记录和 item 记录都不再修改。

### 3.2 引用
1. 分镜或视频提交时，自动带上对应锚点的 assetId。
2. 下游生成任务只读 assetId 对应的 assets 记录，不复制文件，不重新生成。

### 3.3 解冻修订
1. 如果锚点图需要换，先解冻当前 bible（把 frozenAt 置空）。
2. 修改对应的 AssetBibleItem，或新增、删除 item。
3. 再次冻结时 version+1，生成新版本。
4. 旧版本保留，方便回溯。

## 4. 与现有 Asset 表的关系
AssetBibleItem.asset_id 直接引用 assets.id，不复制文件。assets 表里的锚点资产就是普通资产，type 是图片，source 是生成或上传。资产圣经只存引用关系和排序，不存文件路径。

## 5. API 草案

### 5.1 POST /api/projects/{id}/asset-bible/freeze
冻结当前项目的资产圣经。请求体可空，或包含 frozenBy。服务端检查项目下是否已有未冻结的 bible，有则基于它冻结；没有则新建。version 取当前项目最大 version +1。返回新 bible 的 id 和 version。

### 5.2 GET /api/projects/{id}/asset-bible
返回该项目当前生效的 bible（frozenAt 非空且 version 最大），包含 items 列表，每个 item 带 assetId、kind、label、sortOrder。如果项目从未冻结过，返回 404。

## 6. 里程碑拆分

### 里程碑 1：建表和实体
- 建 asset_bible 和 asset_bible_item 两张表。
- 写 AssetBible 和 AssetBibleItem 两个 JPA 实体。
- 写对应的 Repository。
- 交付：能通过 SQL 建表，实体能映射。

### 里程碑 2：冻结和查询接口
- 实现 POST /api/projects/{id}/asset-bible/freeze。
- 实现 GET /api/projects/{id}/asset-bible。
- 冻结时校验项目下锚点资产是否齐全。
- 交付：能冻结出一个版本，能查到当前版本和 items。

### 里程碑 3：引用和解冻
- 分镜/视频提交时自动带上锚点 assetId。
- 实现解冻修订：解冻当前版本，修改 items，再冻结出新版本。
- 交付：下游任务能拿到锚点引用，能换锚点图并出新版本。
