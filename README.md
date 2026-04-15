# Project Card Registry Template 
A template repository for managing and automating [Network Wrangler](https://github.com/network-wrangler/network_wrangler) Project Card registries.

[Network Wrangler](https://github.com/network-wrangler/network_wrangler) is a Python library for managing travel model network scenarios. Network Wrangler uses `Project Cards` to define network edits. The purpose of this repository is to automate the reconciliation of conflicting Project Cards. 

Consider, for example, an existing base year network that includes nodes A, B, and C. Project Card X extends Main Street, adding Node 1 at Location Alpha. Project Card Y extends Broad Street, adding a different node at Location Beta, but also labeling the new node Node 1. In the current Network Wrangler framework, users must manually manage the conflicting `Node 1` definitions. The purpose of this repository is to automate the node (and link) numbering process via a registry.

## 🚀 Getting Started

1. **Use as a Template**: This repository is a `template`, designed to be used to create repositories that have the same functionality.
2. **Configure ID Ranges**: Open `registry_config.yml` to define the allowable range of the `model_node_id` and `model_link_id` fields. 
    * This range should include all possible values of nodes and links used in your travel model. 
    * The software will fail if a Project Card uses an ID outside these allowable ranges.
3. **Define Base Network**: Also in `registry_config.yml`, define the node and link identifiers already used in the base network. 
    * These can be generic to the entire region or specific to geographies, such as counties.
    * For each geography, define the `start` and `end` nodes and links used in the base year network.
    * The software will fail if a Project Card introduces an ID already used by the base network.

## 🤖 How Does this Work?
When a Project Card is added to the `projects/` directory and a Pull Request is opened, the Gatekeeper automation (`validate-pr.yml`) runs the following procedures:

1. **Topological Sorting**: The system uses `TopologicalSorter` to ensure projects are processed based on their `prerequisites`. "Creator" projects (those adding nodes/links) are always processed before "Modifier" or "Deletion" projects.
2. **Conflict Identification**: The system parses every card to detect potential ID violations before they reach the registry This includes
3. **Registry Reconciliation**:
    * If a card adds an ID already in the `registry.csv` database, the system automatically finds the next available ID
    * The Project Cards are updated accordingly to reflect these new IDs
4. **Global ID Syncing**: If "Project A" has its IDs re-numbered due to a conflict, any subsequent Modification or Deletion cards in the same batch (e.g., "Project B") targeting those original IDs are **automatically updated** to match the new IDs assigned to Project A.
5. **Impact Reporting**: Every Pull Request receives a detailed report showing exactly which projects are being **Added** or **Removed** from the state network.

## 🛠️ Managing Project Cards
All changes to the registry are managed by modifying files in the `projects/` directory of a secondary branch. The automation executes the necessary syncing and validation once a Pull Request is opened.

### Adding a Project Card
* Place the new YAML file in the `projects/` directory.
* Document any project requirements in the `dependencies` field (e.g., `prerequisites: ['Project-A']`) to ensure the creator card is processed before modifiers.

### Removing a Project Card
* Delete the YAML file for the unwanted project from the `projects/` directory.
* **Automated Cleanup**: The registry automatically prunes IDs and project entries from `registry.csv` if the corresponding card file no longer exists in the directory.

### Editing a Project Card
* Modify the content of an existing Project Card YAML directly within the `projects/` folder.
* The system will re-evaluate the updated IDs and topological dependencies against the registry and base network during the validation run.

## 🛡️ Safety & Maintenance

* **PR Gatekeeper (`validate-pr.yml`)**: Prevents invalid or conflicting IDs from reaching the `main` branch.
* **Final Guardian (`check-registry.yml`)**: Runs on every push to `main` to verify that the `registry.csv` and project files remain 100% consistent.
* **Circular Dependency Protection**: The system blocks any submission that contains cyclical project requirements (e.g., Project A needs B, and B needs A).