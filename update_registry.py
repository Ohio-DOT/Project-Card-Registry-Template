import os
import yaml
import pandas as pd

from methods_io import read_project_cards
from methods_add_cards import add_cards_to_registry

CARD_DIR = os.path.join(".", "projects")
REGISTRY_FILE = "registry.csv"
CONFIG_FILE = "registry_config.yml"

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

    # Sort cards by project name to ensure deterministic ID assignment
    card_file_list.sort(key=lambda x: x[0].project.lower())
    
    # Identify active projects and prune deleted ones
    active_project_names = [card.project for card, _ in card_file_list]
    
    # Keep only rows in the registry where the project still exists in the folder
    pruned_reg_df = input_reg_df[input_reg_df['project_added'].isin(active_project_names)]

    # Add any new cards or update IDs
    df = add_cards_to_registry(
        card_file_list, pruned_reg_df, config_dict, write_card_updates
    )
    
    # Save the updated registry
    df.to_csv(output_reg_file, index=False)

if __name__ == "__main__":
    update_registry()