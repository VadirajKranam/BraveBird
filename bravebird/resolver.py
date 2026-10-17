from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from .types import ResolverAttempt, ResolvedTarget
from .utils import normalize_text


CONTROL_TAGS = {"input", "textarea", "select", "button"}


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    parent: _Node | None = None
    children: list[_Node] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    def text(self) -> str:
        parts = [*self.text_parts]
        for child in self.children:
            parts.append(child.text())
        return normalize_text(" ".join(parts))


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node(tag="#document", attrs={})
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag=tag.lower(), attrs={key.lower(): (value or "") for key, value in attrs}, parent=self.current)
        self.current.children.append(node)
        if tag.lower() not in {"br", "img", "input", "meta", "link", "hr", "source"}:
            self.current = node

    def handle_endtag(self, tag: str) -> None:
        node = self.current
        while node.parent is not None and node.tag != tag.lower():
            node = node.parent
        if node.parent is not None:
            self.current = node.parent

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.current.text_parts.append(data)


@dataclass
class FieldSpec:
    key: str
    label: str
    kind: str
    aliases: list[str] = field(default_factory=list)


def _build_attempt(strategy: str, detail: str, success: bool) -> ResolverAttempt:
    return ResolverAttempt(strategy=strategy, detail=detail, success=success)


def _matches_text(value: str, expected: str, aliases: list[str]) -> bool:
    target = normalize_text(value)
    options = [expected, *aliases]
    normalized = [normalize_text(option) for option in options if option]
    return any(option in target or target in option for option in normalized)


def _find_all(node: _Node, tag_names: set[str]) -> list[_Node]:
    results: list[_Node] = []
    for child in node.children:
        if child.tag in tag_names:
            results.append(child)
        results.extend(_find_all(child, tag_names))
    return results


def _find_by_id(node: _Node, target_id: str) -> _Node | None:
    for child in _find_all(node, {"*"}):
        if child.attrs.get("id") == target_id:
            return child
    return None


def _iter_descendants(node: _Node) -> list[_Node]:
    return [desc for child in node.children for desc in [child, *_iter_descendants(child)]]


def _controls(node: _Node) -> list[_Node]:
    return [child for child in _iter_descendants(node) if child.tag in CONTROL_TAGS]


def _labels(node: _Node) -> list[_Node]:
    return [child for child in _iter_descendants(node) if child.tag == "label"]


def _iframe_nodes(node: _Node) -> list[_Node]:
    return [child for child in _iter_descendants(node) if child.tag == "iframe" and child.attrs.get("srcdoc")]


def _accessible_name(control: _Node, root: _Node) -> str:
    for attr in ("aria-label", "title", "placeholder"):
        if control.attrs.get(attr):
            return control.attrs[attr]
    control_id = control.attrs.get("id")
    if control_id:
        for label in _labels(root):
            if label.attrs.get("for") == control_id:
                return label.text()
    labelled_by = control.attrs.get("aria-labelledby", "")
    if labelled_by:
        parts: list[str] = []
        for token in labelled_by.split():
            ref = _find_by_id(root, token)
            if ref:
                parts.append(ref.text())
        if parts:
            return normalize_text(" ".join(parts))
    ancestor = control.parent
    while ancestor is not None:
        if ancestor.tag == "label":
            return ancestor.text()
        ancestor = ancestor.parent
    return ""


def _selector_for(control: _Node) -> str:
    if control.attrs.get("id"):
        return f"#{control.attrs['id']}"
    if control.attrs.get("name"):
        return f"{control.tag}[name=\"{control.attrs['name']}\"]"
    classes = control.attrs.get("class", "").split()
    if classes:
        return f"{control.tag}." + ".".join(classes)
    return control.tag


def _resolve_in_document(root: _Node, field: FieldSpec, frame_path: list[int]) -> ResolvedTarget | None:
    attempts: list[ResolverAttempt] = []
    role_name = {"button": "button", "combobox": "combobox"}.get(field.kind, "textbox")

    for control in _controls(root):
        name = _accessible_name(control, root)
        if name and _matches_text(name, field.label, field.aliases):
            attempts.append(_build_attempt("role/name", f"matched accessible name {name}", True))
            return ResolvedTarget(frame_path=frame_path, strategy="role/name", selector_kind="role", selector_value=f"{role_name}:{name}", attempts=attempts)
    attempts.append(_build_attempt("role/name", "no accessible-name match", False))

    for label in _labels(root):
        label_text = label.text()
        if not _matches_text(label_text, field.label, field.aliases):
            continue
        if label.attrs.get("for"):
            attempts.append(_build_attempt("label", f"label[for={label.attrs['for']}] matched {label_text}", True))
            return ResolvedTarget(frame_path=frame_path, strategy="label", selector_kind="label", selector_value=label_text, attempts=attempts)
        for child in _iter_descendants(label):
            if child.tag in CONTROL_TAGS:
                attempts.append(_build_attempt("label", f"label wrapper matched {label_text}", True))
                return ResolvedTarget(frame_path=frame_path, strategy="label", selector_kind="label", selector_value=label_text, attempts=attempts)
    attempts.append(_build_attempt("label", "no label association matched", False))

    for container in _iter_descendants(root):
        if container.tag not in {"form", "fieldset", "section", "div", "li", "tr"}:
            continue
        if _matches_text(container.text(), field.label, field.aliases):
            for child in container.children:
                if child.tag in CONTROL_TAGS:
                    selector = _selector_for(child)
                    attempts.append(_build_attempt("nearby text", f"matched container {selector}", True))
                    return ResolvedTarget(frame_path=frame_path, strategy="nearby text", selector_kind="css", selector_value=selector, attempts=attempts)
    attempts.append(_build_attempt("nearby text", "no nearby text match", False))

    for control in _controls(root):
        ancestor = control.parent
        while ancestor is not None:
            if ancestor.tag in {"div", "li", "tr", "fieldset", "section"} and _matches_text(ancestor.text(), field.label, field.aliases):
                selector = _selector_for(control)
                attempts.append(_build_attempt("structure", f"matched structured container {selector}", True))
                return ResolvedTarget(frame_path=frame_path, strategy="structure", selector_kind="css", selector_value=selector, attempts=attempts)
            ancestor = ancestor.parent
    attempts.append(_build_attempt("structure", "no structural match", False))

    tokens = [token for token in normalize_text(" ".join([field.key, field.label, *field.aliases])).split() if token]
    for control in _controls(root):
        haystack = normalize_text(" ".join([control.attrs.get("id", ""), control.attrs.get("name", ""), control.attrs.get("class", "")]))
        if any(token in haystack for token in tokens):
            selector = _selector_for(control)
            attempts.append(_build_attempt("id/class", f"matched {selector}", True))
            return ResolvedTarget(frame_path=frame_path, strategy="id/class", selector_kind="css", selector_value=selector, attempts=attempts)
    attempts.append(_build_attempt("id/class", "no id/class match", False))
    return None


def resolve_field_from_html(html: str, field: FieldSpec) -> ResolvedTarget | None:
    builder = _TreeBuilder()
    builder.feed(html)
    direct = _resolve_in_document(builder.root, field, [])
    if direct:
        return direct
    for index, iframe in enumerate(_iframe_nodes(builder.root)):
        srcdoc = iframe.attrs.get("srcdoc", "")
        nested = resolve_field_from_html(srcdoc, field)
        if nested:
            return ResolvedTarget(
                frame_path=[index, *nested.frame_path],
                strategy=nested.strategy,
                selector_kind=nested.selector_kind,
                selector_value=nested.selector_value,
                attempts=[_build_attempt("iframe", f"descended into iframe[{index}]", True), *nested.attempts],
            )
    return None
