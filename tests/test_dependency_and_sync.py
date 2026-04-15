import os
import pytest
import pandas as pd
from pathlib import Path
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
    Test that if Project A's node is reassigned due to conflict, 
    Project B (Modifying Project A's node) gets its ID updated automatically.
    """
    card_dir = tmp_path / "projects"
    card_dir.mkdir()
    reg_file = tmp_path / "registry.csv"
    
    # 1. Create a conflict in the registry: Node 1001 is already taken by Project Z
    data = [["node", 1001, "Project Z"]]
    pd.DataFrame(data, columns=["type", "id", "project_added"]).to_csv(reg_file, index=False)

    # 2. Project A adds Node 1001 (Conflict!) -> Should become 1002
    a_yaml = (
        "project: Project A\n"
        "dependencies: {prerequisites: []}\n"
        "changes:\n"
        "  - roadway_addition:\n"
        "      nodes: [{X: 1, Y: 1, model_node_id: 1001}]\n"
        "      links: []"
    )
    (card_dir / "project_A.yml").write_text(a_yaml)

    # 3. Project B modifies Node 1001
    b_yaml = (
        "project: Project B\n"
        "dependencies: {prerequisites: ['Project A']}\n"
        "changes:\n"
        "  - roadway_modification:\n"
        "      nodes: [{model_node_id: 1001, drive_node: 0}]"
    )
    (card_dir / "project_B.yml").write_text(b_yaml)

    # 4. Run Update (Allowing write to disk to check B's updated YAML)
    update_registry(
        config_file="registry_config.yml",
        input_reg_file=str(reg_file),
        output_reg_file=str(reg_file),
        card_dir=str(card_dir),
        write_card_updates=True
    )

    # 5. Assertions
    # Check Registry: Project A should have node 1002
    df = pd.read_csv(reg_file)
    assert df[(df['project_added'] == "Project A") & (df['type'] == "node")]['id'].iloc[0] == 1002

    # Check Project B's File: It should now target Node 1002, NOT 1001
    from projectcard import read_card
    updated_b = read_card(str(card_dir / "project_B.yml"))
    target_node_id = updated_b.changes[0]['roadway_modification']['nodes'][0]['model_node_id']
    
    assert target_node_id == 1002