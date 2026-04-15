import pandas as pd
from typing import Tuple

from pathlib import Path

from projectcard import ProjectCard
from projectcard import write_card


def add_cards_to_registry(
    card_file_list: list, input_df: pd.DataFrame, config: dict, write_to_disk: bool
) -> pd.DataFrame:
    """
    Returns an updated registry dataframe.

    Args:
        card_file_list: a list of project cards and their filenames
        input_df: input registry DataFrame. See the format in `registry.csv`.
        config: input configuration
        write_to_disk: a boolean indicating whether project card updates should be written
            to disk. If True, the input project cards will be overwritten.

    Returns:
        Registry DataFrame updated

    """

    nodes_in_use = _make_available("nodes", config)
    links_in_use = _make_available("links", config)
    out_df = input_df

    # Track ID changes across the entire batch
    global_id_map = {"nodes": {}, "links": {}}

    for card, filename in card_file_list:
        card_modified = False
        
        # 1. APPLY PREVIOUS REASSIGNMENTS
        # Update any IDs in this card that were changed by a prerequisite project
        card, was_updated = _apply_global_id_map(card, global_id_map)
        card_modified = card_modified or was_updated

        # 2. PROCESS CHANGES (All categories, not just roadway_addition )
        if card.project not in input_df["project_added"].values:
            for change_index, change_dict in enumerate(card.changes):
                # Process additions and capture new reassignments
                for cat in ["roadway_addition"]:
                    if cat in change_dict:
                        out_df, id_updates, card = _process_addition(
                            cat, change_index, out_df, card, nodes_in_use, links_in_use, global_id_map
                        )
                        card_modified = card_modified or id_updates

                # Validate and sync IDs for modifications/deletions 
                for cat in ["roadway_property_change", "roadway_deletion"]:
                    if cat in change_dict:
                        card, was_synced = _sync_modification_ids(change_dict[cat], global_id_map)
                        card_modified = card_modified or was_synced

        if card_modified and write_to_disk:
            # Clean up metadata before writing
            for key in ["file", "valid"]:
                card.__dict__.pop(key, None)
            write_card(card, filename=Path(filename))

    return out_df


def _process_addition(category, change_index, out_df, card, nodes_in_use, links_in_use, global_id_map):
    card_modified = False
    
    # Process Nodes
    if "nodes" in card.changes[change_index][category]:
        # Pass global_id_map as the 6th argument
        node_df, node_update, card = _update_registry(
            category, "nodes", out_df, card, change_index, nodes_in_use, global_id_map
        )
        if node_df is not None:
            out_df = pd.concat([out_df, node_df], ignore_index=True)
            card_modified = card_modified or node_update
    
    # Process Links
    # Pass global_id_map as the 6th argument
    link_df, link_update, card = _update_registry(
        category, "links", out_df, card, change_index, links_in_use, global_id_map
    )
    if link_df is not None:
        out_df = pd.concat([out_df, link_df], ignore_index=True).drop_duplicates().reset_index(drop=True)
        card_modified = card_modified or link_update

    return out_df, card_modified, card


def _sync_modification_ids(change_content, global_id_map):
    """
    Updates IDs within modification or deletion dictionaries based on global reassignments.
    """
    was_synced = False
    
    # Sync Link IDs in modifications/deletions
    if "links" in change_content:
        # Check if it's a list (Add New Roadway style) or dict (Roadway Deletion style)
        links = change_content["links"]
        link_list = links if isinstance(links, list) else [links]
        
        for link in link_list:
            if "model_link_id" in link:
                # Handle single ID or list of IDs (common in deletions)
                ids = link["model_link_id"]
                if isinstance(ids, list):
                    for i, lid in enumerate(ids):
                        if lid in global_id_map["links"]:
                            ids[i] = global_id_map["links"][lid]
                            was_synced = True
                elif ids in global_id_map["links"]:
                    link["model_link_id"] = global_id_map["links"][ids]
                    was_synced = True

    # Sync Node IDs similarly
    if "nodes" in change_content:
        nodes = change_content["nodes"]
        node_list = nodes if isinstance(nodes, list) else [nodes]
        for node in node_list:
            if "model_node_id" in node:
                nid = node["model_node_id"]
                if nid in global_id_map["nodes"]:
                    node["model_node_id"] = global_id_map["nodes"][nid]
                    was_synced = True

    return was_synced


def _apply_global_id_map(card, id_map):
    """Updates all IDs in a card based on previous reassignments."""
    updated = False
    for change in card.changes:
        for cat, content in change.items():
            if not isinstance(content, dict):
                continue
            
            for node_type in ["nodes", "links"]:
                if node_type not in content:
                    continue
                
                id_key = "model_node_id" if node_type == "nodes" else "model_link_id"
                items = content[node_type]
                
                # Case 1: List of objects (e.g., roadway_addition)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            old_id = item.get(id_key)
                            if old_id in id_map[node_type]:
                                item[id_key] = id_map[node_type][old_id]
                                updated = True
                
                # Case 2: Dict of lists (e.g., roadway_deletion)
                elif isinstance(items, dict):
                    if id_key in items and isinstance(items[id_key], list):
                        ids_to_check = items[id_key]
                        for i, old_id in enumerate(ids_to_check):
                            if old_id in id_map[node_type]:
                                ids_to_check[i] = id_map[node_type][old_id]
                                updated = True
    return card, updated


def _make_available(nodes_or_links: str, config: dict) -> list:
    """
    Converts dictionary of available nodes and links to list of available nodes
    Args:
        nodes_or_links: string, either 'nodes' or 'links'
        config: input configuration
    Returns:
        list of available nodes
    """
    if nodes_or_links == "nodes":
        key_word = "nodes_used_by_geography"
        min_id = config.get("minimum_allowable_node_id")
        max_id = config.get("maximum_allowable_node_id")
    else:
        key_word = "links_used_by_geography"
        min_id = config.get("minimum_allowable_link_id")
        max_id = config.get("maximum_allowable_link_id")

    subject_dict = config.get(key_word)

    ids_in_use = {n: False for n in range(min_id, max_id + 1)}
    for entry in subject_dict:
        temp_start = entry.get("start")
        temp_end = entry.get("end")
        for id in range(temp_start, temp_end + 1):
            ids_in_use[id] = True

    return ids_in_use


def _is_id_in_allowable_range(
    nodes_or_links: str,
    project_name: str,
    subject_id: int,
    range_in_use: dict,
):
    """
    Checks if the new node or link id is in the allowable range defined in the config file

    Args:
        nodes_or_links (str): "node" or "link", which is used in error message
        project_name (str): project name, which is used in error message
        subject_id (int): the proposed new node or link id number
        range_in_use (dict): a dictionary defining the id range with a bool indicating if the id number is used in the base network

    Raises:
        ValueError: informs the user of the disconnect between config file and the Project Card
    """
    if subject_id not in range_in_use:
        msg = (
            "New {} id ({}) in project '{}' is not in the base networks allowable range"
            "({} to {}) as defined in the configuration file.".format(
                nodes_or_links,
                project_name,
                min(range_in_use.keys()),
                max(range_in_use.keys()),
            )
        )
        raise ValueError(msg)


def _is_id_used_in_base_network(
    nodes_or_links: str,
    project_name: str,
    subject_id: int,
    range_in_use: dict,
):
    """
    Checks if new node or link id is used in the base network as defined in the config file

    Args:
        nodes_or_links (str): "node" or "link", which is used in error message
        project_name (str): project name, which is used in error message
        subject_id (int): the proposed new node or link id number
        range_in_use (dict): a dictionary defining the id range with a bool indicating if the id number is used in the base network

    Raises:
        ValueError: informs the user of the disconnect between the config file and the Project Card
    """
    if subject_id in range_in_use:
        if range_in_use[subject_id] == True:
            msg = (
                "New {} id ({}) in project '{}' is in use in the base network. "
                "Please check that the base network {}s are defined correctly in "
                "the config file.".format(
                    nodes_or_links,
                    subject_id,
                    project_name,
                    nodes_or_links,
                )
            )
            raise ValueError(msg)


def _find_available_id(
    nodes_or_links: str,
    project_name: str,
    subject_id: str,
    range_in_use: dict,
    subject_df: pd.DataFrame,
) -> int:
    """
    If the node or link id is already in the registry and we need to find a new number, this method iterates up from
    the proposed node number to find the next available id, which it returns.

    Args:
        nodes_or_links (str): "node" or "link", which is used in error message
        project_name (str): project name, which is used in error message
        subject_id (int): the proposed new node or link id number
        range_in_use (dict): a dictionary defining the id range with a bool indicating if the id number is used in the base network
        subject_df (pd.DataFrame): node or link registry dataframe

    Returns:
        int: available node or link id
    """

    number = subject_id
    for i in range(subject_id, max(range_in_use.keys())):
        if i not in subject_df["id"].values:
            if range_in_use[i] == False:
                number = i
                break

    if number == subject_id:
        msg = "Software failed to find an available number for {} id ({}) in project '{}'. " "Please check that the base network {}s are defined correctly in the config file.".format(
            nodes_or_links,
            subject_id,
            project_name,
            nodes_or_links,
        )

    return number


def _update_registry(
    category: str,
    nodes_or_links: str,
    input_df: pd.DataFrame,
    card: ProjectCard,
    change_index: int,
    range_in_use: dict,
    global_id_map: dict
) -> Tuple[pd.DataFrame, bool, dict]:
    """
    Updates node or link entries in the registry database

    Args:
        nodes_or_links: input string, 'nodes' or 'links'
        input_df: input registry DataFrame
        card: ProjectCard with new entry
        change_index: The index of the ProjectCard changes list being assessed
        start: largest node number in the existing network

    Returns:
        An updated registry database with new node entries
        A flag as to whether the card needs to be modified
        An updated dictionary of the card entries
    """
    write_updated_card = False

    if nodes_or_links == "nodes":
        subject_word = "node"
        subject_id_word = "model_node_id"
    else:
        subject_word = "link"
        subject_id_word = "model_link_id"

    subject_df = input_df[input_df["type"] == subject_word]

    for subject_index, subject in enumerate(card.changes[change_index][category][nodes_or_links]):
        new_id = subject[subject_id_word]

        _is_id_in_allowable_range(subject_word, card.project, new_id, range_in_use)
        _is_id_used_in_base_network(subject_word, card.project, new_id, range_in_use)

        if new_id not in subject_df["id"].values:
            updates_df = pd.DataFrame(
                {
                    "type": subject_word,
                    "id": [new_id],
                    "project_added": [card.project],
                }
            )
            subject_df = pd.concat([subject_df, updates_df])
        else:
            number = _find_available_id(
                subject_word,
                card.project,
                new_id,
                range_in_use,
                subject_df,
            )
            
            # Record the reassignment for other cards
            global_id_map[nodes_or_links][new_id] = number 
            
            # Update current card
            card.changes[change_index][category][nodes_or_links][subject_index][subject_id_word] = number
            
            if nodes_or_links == "nodes":
                for i in range(0, len(card.changes[change_index][category]["links"])):
                    if card.changes[change_index][category]["links"][i]["A"] == new_id:
                        card.changes[change_index][category]["links"][i]["A"] = number
                    if card.changes[change_index][category]["links"][i]["B"] == new_id:
                        card.changes[change_index][category]["links"][i]["B"] = number
            updates_df = pd.DataFrame(
                {
                    "type": subject_word,
                    "id": [number],
                    "project_added": [card.project],
                }
            )
            subject_df = pd.concat([subject_df, updates_df])
            write_updated_card = True

    return subject_df, write_updated_card, card
