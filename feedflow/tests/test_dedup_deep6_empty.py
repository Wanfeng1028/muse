import unittest


def get_text_for(item):
    title = item.get("title", "")
    content = item.get("content_text", "")
    return (title + " ") * 2 + content


class TestDedupDeep6Empty(unittest.TestCase):
    def test_get_text_for_all_empty(self):
        self.assertEqual(get_text_for({"title": "", "content_text": ""}), "  ")

    def test_get_text_for_title_only(self):
        self.assertEqual(get_text_for({"title": "hello", "content_text": ""}), "hello hello ")

    def test_get_text_for_content_only(self):
        self.assertEqual(get_text_for({"title": "", "content_text": "body"}), "  body")

    def test_get_text_for_both(self):
        self.assertEqual(get_text_for({"title": "t", "content_text": "c"}), "t t c")


if __name__ == "__main__":
    unittest.main()
