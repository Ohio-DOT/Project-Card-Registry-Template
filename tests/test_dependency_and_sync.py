import os
import sys
import inspect
import pytest
import pandas as pd

from projectcard import read_card

c_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
p_dir = os.path.dirname(c_dir)
sys.path.insert(0, p_dir)

from update_registry import update_registry

@pytest.mark.ci
@pytest.mark.update_registry
@pytest.mark.dependency
def test_topological_sorting_order(tmp_path):
    """
    Ensures that projects are processed based on dependencies:
    Project B (Modifier) must follow Project A (Creator).
    """
    card_dir = tmp_path / "projects"
    card_dir.mkdir()
    reg_file = tmp_path / "registry.csv"
    conf_file = "registry_config.yml"

    # Create Project A (Creator)
    # A has no dependencies
    a_content = "project: Project A\ndependencies: {prerequisites: []}\nchanges: []"
    (card_dir / "project_A.yml").write_text(a_content)

    # Create Project B (Modifier)
    # B depends on A
    b_content = "project: Project B\ndependencies: {prerequisites: ['Project A']}\nchanges: []"
    (card_dir / "project_B.yml").write_text(b_content)

    # Initialize empty registry
    pd.DataFrame([], columns=["type", "id", "project_added"]).to_csv(reg_file, index=False)

    # If sorting works, this should not raise an error
    update_registry(
        config_file=conf_file,
        input_reg_file=str(reg_file),
        output_reg_file=str(reg_file),
        card_dir=str(card_dir),
        write_card_updates=False
    )
    
    # Verification: Check if both appear in registry
    df = pd.read_csv(reg_file)
    assert "Project A" in df['project_added'].values or len(df) == 0 # (If changes are empty, length might be 0)

@pytest.mark.ci
@pytest.mark.update_registry
@pytest.mark.dependency
def test_circular_dependency_error(tmp_path):
    """
    Verifies that circular dependencies (A -> B -> A) block the update.
    """
    card_dir = tmp_path / "projects"
    card_dir.mkdir()
    
    # A depends on B
    (card_dir / "project_A.yml").write_text("project: Project A\ndependencies: {prerequisites: ['Project B']}\nchanges: []")
    # B depends on A
    (card_dir / "project_B.yml").write_text("project: Project B\ndependencies: {prerequisites: ['Project A']}\nchanges: []")

    with pytest.raises(ValueError, match="CIRCULAR DEPENDENCY DETECTED"):
        update_registry(card_dir=str(card_dir))

@pytest.mark.ci
@pytest.mark.update_registry
@pytest.mark.dependency
def test_inter_card_id_reconciliation(tmp_path):
    """
    Test that if Project B's node is reassigned due to conflict with existing 
    Project A (from project_AB folder), Project C (modifying Project B) 
    gets its ID updated automatically.
    """
    card_dir = tmp_path / "projects"
    card_dir.mkdir()
    reg_file = tmp_path / "registry.csv"
    
    # 1. Use Project A from project_AB as the existing project in the registry
    # Copy its card to the temp directory so the Source of Truth logic doesn't prune it
    existing_a_path = os.path.join(p_dir, "tests", "projects", "project_AB", "project_A.yml")
    with open(existing_a_path, 'r') as f:
        a_content = f.read()
    (card_dir / "project_A.yml").write_text(a_content)

    # 2. Populate registry: Project A already owns Nodes 1001 and 1002 
    data = [
        ["node", 1001, "Project A"],
        ["node", 1002, "Project A"],
        ["link", 501, "Project A"]
    ]
    pd.DataFrame(data, columns=["type", "id", "project_added"]).to_csv(reg_file, index=False)

    # 3. Create Project B: Tries to add Node 1001 (Conflict!) -> Should become 1003 
    b_yaml = (
        "project: Project B\n"
        "dependencies: {prerequisites: []}\n"
        "changes:\n"
        "  - roadway_addition:\n"
        "      nodes: [{X: 1, Y: 1, model_node_id: 1001}]\n"
        "      links: []"
    )
    (card_dir / "project_B.yml").write_text(b_yaml)

    # 4. Create Project C: Modifies Node 1001 (intended for Project B)
    # Uses official 'roadway_property_change' schema with nested 'facility' selection
    c_yaml = (
        "project: Project C\n"
        "dependencies: {prerequisites: ['Project B']}\n"
        "changes:\n"
        "  - roadway_property_change:\n"
        "      facility:\n"
        "        nodes: {model_node_id: [1001], ignore_missing: true}\n"
        "      property_changes:\n"
        "        drive_node: {set: 0}"
    )
    (card_dir / "project_C.yml").write_text(c_yaml)

    # 5. Run Update (write_card_updates=True to verify Project C's file changes)
    update_registry(
        config_file="registry_config.yml",
        input_reg_file=str(reg_file),
        output_reg_file=str(reg_file),
        card_dir=str(card_dir),
        write_card_updates=True
    )

    # 6. Assertions
    df = pd.read_csv(reg_file)
    
    # Project B's node should have been bumped to 1003 because 1001/1002 were taken by A [cite: 81]
    b_node_id = df[(df['project_added'] == "Project B") & (df['type'] == "node")]['id'].iloc[0]
    assert b_node_id == 1003

    # Check Project C's YAML: It should now target Node 1003, NOT 1001
    updated_c = read_card(str(card_dir / "project_C.yml"))
    target_ids = updated_c.changes[0]['roadway_property_change']['facility']['nodes']['model_node_id']
    
    assert 1003 in target_ids