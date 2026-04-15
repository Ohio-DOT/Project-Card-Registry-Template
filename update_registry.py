import os
import yaml
import pandas as pd
from graphlib import TopologicalSorter
from methods_io import read_project_cards
from methods_add_cards import add_cards_to_registry

CARD_DIR = os.path.join(".", "projects")
REGISTRY_FILE = "registry.csv"
CONFIG_FILE = "registry_config.yml"

def sort_projects_by_dependency(card_file_list):
    """Sorts project cards based on dependencies and detects cycles."""
    # Sort alphabetically first to ensure deterministic tie-breaking
    card_file_list.sort(key=lambda x: x[0].project)

    project_map = {card.project: (card, filename) for card, filename in card_file_list}
    ts = TopologicalSorter()

    for card, _ in card_file_list:
        # Check prerequisites in the dependencies dictionary 
        prereqs = card.dependencies.get("prerequisites", [])
        if not isinstance(prereqs, list):
            prereqs = []
        
        # Add project and its dependencies to the sorter
        ts.add(card.project, *prereqs)

    try:
        sorted_names = list(ts.static_order())
        # Return only cards that were actually provided in this batch
        return [project_map[name] for name in sorted_names if name in project_map]
    except Exception as e:
        msg = f"❌ CIRCULAR DEPENDENCY DETECTED: The project cards have a cyclical relationship. {str(e)}"
        raise ValueError(msg)

def update_registry(
    config_file: str = CONFIG_FILE,
    input_reg_file: str = REGISTRY_FILE,
    output_reg_file: str = REGISTRY_FILE,
    card_dir: str = CARD_DIR,
    write_card_updates: bool = True,
):
    # Load existing registry
    input_reg_df = pd.read_csv(input_reg_file)
    with open(config_file, "r") as file:
        config_dict = yaml.safe_load(file)

    # Read current project cards from the directory
    card_file_list = read_project_cards(card_dir)

    # Sort cards by dependency
    card_file_list = sort_projects_by_dependency(card_file_list)

    # Calculate differences
    current_projects = {card.project for card, _ in card_file_list}
    registered_projects = set(input_reg_df['project_added'].unique())
    to_remove = registered_projects - current_projects
    to_add = current_projects - registered_projects
    
    # Print summary for the GitHub Action report
    print("--- PROJECT REGISTRY SUMMARY ---")
    print(f"➕ Projects to Add: {list(to_add) if to_add else 'None'}")
    print(f"🗑️ Projects to Remove: {list(to_remove) if to_remove else 'None'}")
    print("--------------------------------")
    
    # Prune registry of missing projects and add new ones
    pruned_df = input_reg_df[input_reg_df['project_added'].isin(current_projects)]
    df = add_cards_to_registry(card_file_list, pruned_df, config_dict, write_card_updates)
    
    # Save the updated registry
    df.to_csv(output_reg_file, index=False)

if __name__ == "__main__":
    update_registry()