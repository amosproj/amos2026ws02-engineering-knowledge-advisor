from dataclasses import dataclass

from services.cad.assembly_tree_node import AssemblyTreeNode


@dataclass
class CadFile:
    identifier: str
    root_node: AssemblyTreeNode

    def print_tree(self) -> None:
        self.root_node.print_sub_tree(0)
