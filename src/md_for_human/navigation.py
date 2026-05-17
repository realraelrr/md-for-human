from __future__ import annotations

from pathlib import PurePosixPath

from md_for_human.models import NavNode, RenderedPage, SiteManifest


def build_navigation(
    manifest: SiteManifest,
    rendered_pages: dict[PurePosixPath, RenderedPage],
) -> tuple[list[NavNode], list[RenderedPage]]:
    top_level_nodes: list[NavNode] = []
    directory_nodes: dict[PurePosixPath, NavNode] = {}

    for document in manifest.documents:
        parent_children = top_level_nodes
        current_parts: list[str] = []

        for directory_name in document.relative_source_path.parts[:-1]:
            current_parts.append(directory_name)
            directory_path = PurePosixPath(*current_parts)
            directory_node = directory_nodes.get(directory_path)
            if directory_node is None:
                directory_node = NavNode(
                    name=directory_name,
                    relative_path=directory_path,
                    is_dir=True,
                )
                directory_nodes[directory_path] = directory_node
                parent_children.append(directory_node)
            parent_children = directory_node.children

        rendered_page = rendered_pages[document.output_path]
        parent_children.append(
            NavNode(
                name=rendered_page.title,
                relative_path=document.output_path,
                is_dir=False,
                document=document,
            )
        )

    ordered_pages = [rendered_pages[document.output_path] for document in manifest.documents]
    for index, page in enumerate(ordered_pages):
        page.previous_document = ordered_pages[index - 1].document if index > 0 else None
        page.next_document = (
            ordered_pages[index + 1].document if index + 1 < len(ordered_pages) else None
        )

    manifest.nav_tree = top_level_nodes
    return top_level_nodes, ordered_pages
