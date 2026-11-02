from dataclasses import dataclass, field


@dataclass
class AssemblyTreeNode:
    identifier: str
    kind: str
    dimensions: tuple[float, float, float] | None
    children: list["AssemblyTreeNode"] = field(default_factory=list)

    def print_sub_tree(self, depth: int = 0) -> None:
        indent = "  " * depth
        print(f"{indent}- {self.identifier} ({self.kind})")
        if self.dimensions:
            print(f"{indent}  Dimensions: {self.dimensions}")
        for child in self.children:
            child.print_sub_tree(depth + 1)
