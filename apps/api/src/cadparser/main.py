import cadquery as cq
import os

original_add = cq.Assembly.add

def safe_add(self, child, name=None, loc=None, color=None, material=None):
    if name is not None:
        base_name = name
        counter = 1
        existing_names = {c.name for c in self.children}
        while name in existing_names:
            name = f"{base_name}_{counter}"
            counter += 1
    return original_add(self, child, name=name, loc=loc, color=color, material=material)


cq.Assembly.add = safe_add

def parse_step_with_cq(file_path):
    print(f"Lade STEP-Datei mit CadQuery Assembly: {file_path} ...")

    assy = cq.Assembly.importStep(file_path)

    def print_node(node, depth=0):
        indent = "  " * depth
        name = getattr(node, "name", "Unbenannt")
        print(f"{indent}- Bauteil/Baugruppe: {name}")

        for child in node.children:
            print_node(child, depth + 1)

    print("\nErfolgreich geladen! Baugruppen-Struktur:")
    print("=" * 50)
    print_node(assy)
    print("=" * 50)


def main():
    step_file_path = r"C:\Users\chris\Downloads\Pack&Go Inventor\TEF1006U001-G00_802.stp"

    if not os.path.exists(step_file_path):
        print(f"Fehler: Datei '{step_file_path}' nicht gefunden.")
        return

    try:
        parse_step_with_cq(step_file_path)
    except Exception as e:
        print(f"Fehler beim Parsen: {e}")


if __name__ == "__main__":
    main()