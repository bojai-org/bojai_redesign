import pytest
from build.prompt import PromptLeaf, PromptComposite


class TestPromptLeaf:
    def test_render_returns_text(self):
        assert PromptLeaf(text="hello", id="l").render() == "hello"

    def test_render_empty_string(self):
        assert PromptLeaf(text="", id="l").render() == ""

    def test_uses_provided_id(self):
        assert PromptLeaf(text="t", id="my_id").id == "my_id"

    def test_auto_generates_id_when_none(self):
        leaf = PromptLeaf(text="t")
        assert leaf.id is not None
        assert len(leaf.id) > 0

    def test_two_leaves_without_id_get_unique_ids(self):
        a = PromptLeaf(text="a")
        b = PromptLeaf(text="b")
        assert a.id != b.id


class TestPromptComposite:
    def test_render_single_child(self):
        comp = PromptComposite(id="root", components=[PromptLeaf(text="only", id="a")])
        assert comp.render() == "only"

    def test_render_joins_children_with_double_newline(self):
        comp = PromptComposite(id="root", components=[
            PromptLeaf(text="first", id="a"),
            PromptLeaf(text="second", id="b"),
        ])
        assert comp.render() == "first\n\nsecond"

    def test_render_empty_composite(self):
        assert PromptComposite(id="root").render() == ""

    def test_find_self_by_id(self):
        comp = PromptComposite(id="root")
        assert comp.find("root") is comp

    def test_find_direct_child(self):
        leaf = PromptLeaf(text="hi", id="leaf1")
        comp = PromptComposite(id="root", components=[leaf])
        assert comp.find("leaf1") is leaf

    def test_find_nested_leaf(self):
        deep = PromptLeaf(text="deep", id="deep_leaf")
        inner = PromptComposite(id="inner", components=[deep])
        root = PromptComposite(id="root", components=[inner])
        assert root.find("deep_leaf") is deep

    def test_find_nested_composite(self):
        inner = PromptComposite(id="inner")
        root = PromptComposite(id="root", components=[inner])
        assert root.find("inner") is inner

    def test_find_returns_none_for_unknown_id(self):
        assert PromptComposite(id="root").find("ghost") is None

    def test_add_appends_component(self):
        comp = PromptComposite(id="root")
        leaf = PromptLeaf(text="new", id="new")
        comp.add(leaf)
        assert leaf in comp.components

    def test_add_makes_component_findable(self):
        comp = PromptComposite(id="root")
        leaf = PromptLeaf(text="new", id="new")
        comp.add(leaf)
        assert comp.find("new") is leaf

    def test_add_composite_indexes_its_children(self):
        deep = PromptLeaf(text="d", id="deep")
        inner = PromptComposite(id="inner", components=[deep])
        root = PromptComposite(id="root")
        root.add(inner)
        assert root.find("deep") is deep

    def test_remove_removes_component(self):
        leaf = PromptLeaf(text="bye", id="bye")
        comp = PromptComposite(id="root", components=[leaf])
        comp.remove(leaf)
        assert leaf not in comp.components

    def test_remove_makes_component_unfindable(self):
        leaf = PromptLeaf(text="bye", id="bye")
        comp = PromptComposite(id="root", components=[leaf])
        comp.remove(leaf)
        assert comp.find("bye") is None

    def test_render_nested_composite(self):
        inner = PromptComposite(id="inner", components=[
            PromptLeaf(text="x", id="x"),
            PromptLeaf(text="y", id="y"),
        ])
        root = PromptComposite(id="root", components=[
            PromptLeaf(text="start", id="s"),
            inner,
        ])
        assert root.render() == "start\n\nx\n\ny"
