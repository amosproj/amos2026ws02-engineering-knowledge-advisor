from dataclasses import dataclass

from cad.assembly_tree_node import AssemblyTreeNode


@dataclass
class CadFile:
    identifier: str
    root_nodes: list[AssemblyTreeNode]

    def print_tree(self) -> None:
        for node in self.root_nodes:
            node.print_sub_tree(0)
