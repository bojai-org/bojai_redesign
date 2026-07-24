from prompt import PromptComposite, PromptLeaf


def test_leaf_render_returns_text():
    assert PromptLeaf(text="hello world").render() == "hello world"


def test_leaf_auto_generates_id():
    leaf = PromptLeaf(text="x")
    assert isinstance(leaf.id, str) and leaf.id


def test_leaf_explicit_id():
    assert PromptLeaf(text="x", id="my-id").id == "my-id"


def test_composite_render_joins_children_with_blank_line():
    composite = PromptComposite(components=[PromptLeaf(text="a"), PromptLeaf(text="b")])
    assert composite.render() == "a\n\nb"


def test_composite_empty_render_is_empty_string():
    assert PromptComposite().render() == ""


def test_composite_add_appends_and_indexes():
    composite = PromptComposite()
    leaf = PromptLeaf(text="x", id="leaf-1")
    composite.add(leaf)
    assert composite.find("leaf-1") is leaf
    assert composite.render() == "x"


def test_composite_remove():
    leaf = PromptLeaf(text="x", id="leaf-1")
    composite = PromptComposite(components=[leaf])
    composite.remove(leaf)
    assert composite.find("leaf-1") is None
    assert composite.render() == ""


def test_composite_find_missing_returns_none():
    assert PromptComposite().find("nope") is None


def test_composite_find_self_by_id():
    composite = PromptComposite(id="root")
    assert composite.find("root") is composite


def test_nested_composite_index_includes_descendants():
    inner_leaf = PromptLeaf(text="inner", id="inner-leaf")
    inner = PromptComposite(components=[inner_leaf], id="inner")
    outer = PromptComposite(components=[inner], id="outer")
    assert outer.find("inner-leaf") is inner_leaf
    assert outer.find("inner") is inner


def test_nested_composite_render():
    inner = PromptComposite(components=[PromptLeaf(text="b")])
    outer = PromptComposite(components=[PromptLeaf(text="a"), inner])
    assert outer.render() == "a\n\nb"
