"""OPML 导入导出模块：支持 FeedFlow 订阅的分组结构与源清单交换。"""

import xml.etree.ElementTree as ET

from . import store


def export_opml(db_path) -> str:
    """导出所有分组与订阅为 OPML 2.0 字符串。"""
    folders = store.list_folders(db_path)
    feeds = store.list_feeds(db_path)

    # 按分组归类源，folder_id 为 None 的为未分组
    grouped = {}
    ungrouped = []
    for feed in feeds:
        fid = feed.get("folder_id")
        if fid is None:
            ungrouped.append(feed)
        else:
            grouped.setdefault(fid, []).append(feed)

    opml = ET.Element("opml", {"version": "2.0"})
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = "FeedFlow 订阅导出"
    body = ET.SubElement(opml, "body")

    # 先输出有分组的源
    for folder in folders:
        folder_outline = ET.SubElement(
            body, "outline", {"text": folder["name"], "title": folder["name"]}
        )
        for feed in grouped.get(folder["id"], []):
            ET.SubElement(
                folder_outline,
                "outline",
                {
                    "text": feed["title"],
                    "title": feed["title"],
                    "type": "rss",
                    "xmlUrl": feed["feed_url"],
                    "htmlUrl": feed["site_url"],
                },
            )

    # 未分组源直接挂 body
    for feed in ungrouped:
        ET.SubElement(
            body,
            "outline",
            {
                "text": feed["title"],
                "title": feed["title"],
                "type": "rss",
                "xmlUrl": feed["feed_url"],
                "htmlUrl": feed["site_url"],
            },
        )

    xml_bytes = ET.tostring(opml, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")


def import_opml(db_path, xml_text) -> dict:
    """解析 OPML 文本，递归提取所有 outline 的 xmlUrl 并创建源。

    返回 {"imported": 成功数量, "skipped": 跳过数量}。
    同名分组只创建一次；已存在的源（feed_url 唯一冲突）计入 skipped。
    """
    imported = 0
    skipped = 0

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {"imported": 0, "skipped": 0}

    # 已建分组名称 -> id 缓存
    folder_cache = {}

    def get_or_create_folder(name):
        """按名称获取或创建分组，返回 folder_id。"""
        if not name:
            return None
        if name in folder_cache:
            return folder_cache[name]
        for f in store.list_folders(db_path):
            if f["name"] == name:
                folder_cache[name] = f["id"]
                return f["id"]
        new_id = store.create_folder(db_path, name)
        folder_cache[name] = new_id
        return new_id

    def walk(node, parent_folder_id):
        """递归遍历 outline 节点。"""
        nonlocal imported, skipped
        for outline in node.findall("outline"):
            xml_url = outline.get("xmlUrl")
            if xml_url:
                # 这是一个源
                title = outline.get("text") or outline.get("title") or ""
                try:
                    feed_id = store.create_feed(db_path, xml_url, parent_folder_id, 0)
                    if title:
                        store.update_feed(db_path, feed_id, title=title)
                    imported += 1
                except Exception:  # noqa: BLE001
                    # 重复源记为 skipped，故意宽捕获
                    skipped += 1
            else:
                # 这是一个分组（或嵌套容器）
                folder_name = outline.get("text") or outline.get("title") or ""
                folder_id = get_or_create_folder(folder_name)
                walk(outline, folder_id)

    body = root.find("body")
    if body is not None:
        walk(body, None)

    return {"imported": imported, "skipped": skipped}
