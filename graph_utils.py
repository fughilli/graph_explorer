import json
import os
import random
from typing import Dict, List, Set, Tuple


def load_components(components_dir: str) -> Dict[str, dict]:
    """Load all component descriptors from the components directory."""
    components = {}

    # Load types.json first
    with open(os.path.join(components_dir, "types.json")) as f:
        types = json.load(f)
        print(f"[DEBUG] Loaded types: {types}")

    # Recursively walk through all directories
    for root, dirs, files in os.walk(components_dir):
        for filename in files:
            if filename.endswith('.json') and filename != 'types.json':
                json_path = os.path.join(root, filename)
                with open(json_path) as f:
                    # Get name without .json, but keep subdirectory structure
                    rel_path = os.path.relpath(json_path, components_dir)
                    name = rel_path[:-5]  # Remove .json
                    descriptor = json.load(f)
                    components[name] = descriptor
                    print(f"[DEBUG] Loaded component {name}: {descriptor}")

    return components


def find_components_producing_type(type_name: str,
                                   components: Dict[str, dict]) -> List[str]:
    """Find all components that have an output of the given type."""
    matching_components = []
    for name, descriptor in components.items():
        for output in descriptor.get("outputs", []):
            if output["type"] == type_name:
                matching_components.append(name)
                break
    print(f"[DEBUG] Components producing {type_name}: {matching_components}")
    return matching_components


def bridge(td_proxy, input_nodes: List[Tuple[int, str]],
           output_nodes: List[Tuple[int, str]]):
    """
    Stochastically generate a network connecting input_nodes to output_nodes.
    Each tuple in input_nodes and output_nodes is (handle, type).
    """
    print("[DEBUG] Starting bridge operation")
    print(f"[DEBUG] Input nodes: {input_nodes}")
    print(f"[DEBUG] Output nodes: {output_nodes}")

    # Load all component descriptors
    components = load_components(
        "/Users/kevin/Projects/graph_explorer/components")

    # Keep track of unsatisfied outputs we need to connect
    # Each entry is (handle, connector_index, required_type)
    outputs_to_satisfy = [(handle, 0, type_name)
                          for handle, type_name in output_nodes]

    # Keep track of available inputs we can connect to
    # Each entry is (handle, connector_index, type_name)
    available_inputs = [(handle, 0, type_name)
                        for handle, type_name in input_nodes]

    # Keep track of all nodes we create
    created_nodes = []

    while outputs_to_satisfy:
        output_handle, output_index, required_type = outputs_to_satisfy.pop(0)
        print(
            f"[DEBUG] Trying to satisfy output {output_handle}:{output_index} requiring type {required_type}"
        )

        # Find components that can produce this type
        producer_components = find_components_producing_type(
            required_type, components)
        if not producer_components:
            raise ValueError(
                f"No components found that can produce type {required_type}")

        # Randomly choose a component
        chosen_component = random.choice(producer_components)
        print(
            f"[DEBUG] Chose component {chosen_component} to produce {required_type}"
        )

        # Create the component
        new_handle = td_proxy.load(chosen_component)
        created_nodes.append(new_handle)
        print(f"[DEBUG] Created component with handle {new_handle}")

        # Connect its output to our target
        td_proxy.connect(new_handle, 0, output_handle, output_index)
        print(
            f"[DEBUG] Connected {new_handle}:0 -> {output_handle}:{output_index}"
        )

        # Add its inputs to our list of outputs we need to satisfy
        component_desc = components[chosen_component]
        for i, input_desc in enumerate(component_desc.get("inputs", [])):
            # First check if we have an available input of matching type
            matching_input_idx = None
            for j, (in_handle, in_index,
                    in_type) in enumerate(available_inputs):
                if in_type == input_desc["type"]:
                    matching_input_idx = j
                    break

            if matching_input_idx is not None:
                # Use this available input
                in_handle, in_index, _ = available_inputs.pop(
                    matching_input_idx)
                td_proxy.connect(in_handle, in_index, new_handle, i)
                print(
                    f"[DEBUG] Connected available input {in_handle}:{in_index} -> {new_handle}:{i}"
                )
            else:
                # Add to outputs we need to satisfy
                outputs_to_satisfy.append((new_handle, i, input_desc["type"]))
                print(
                    f"[DEBUG] Added new output to satisfy: {new_handle}:{i} type {input_desc['type']}"
                )

    if available_inputs:
        print(f"[WARNING] Some inputs were not used: {available_inputs}")

    # Return all nodes involved in the bridge
    return created_nodes


def topo_sort_handles(td_proxy, handles):
    print("[DEBUG] Starting topological sort")
    # Get the connection information for each handle
    connection_info = {}
    for handle in handles:
        print(f"[DEBUG] Getting connectors for handle {handle}")
        connectors = td_proxy.get_op_connectors(handle)
        print(f"[DEBUG] Raw connector info: {connectors}")

        # Look at the actual connections in the input connectors
        in_connections = []
        for in_conn in connectors["in"]:
            if in_conn[
                    "targets"]:  # Only count connectors that have actual connections
                in_connections.append(in_conn)

        out_connections = []
        for out_conn in connectors["out"]:
            if out_conn[
                    "targets"]:  # Only count connectors that have actual connections
                out_connections.append(out_conn)

        connection_info[handle] = {
            "in_connectors": in_connections,
            "out_connectors": out_connections
        }
        print(
            f"[DEBUG] Handle {handle} has {len(in_connections)} active inputs and {len(out_connections)} active outputs"
        )

    # Find a node with no incoming connections
    print("[DEBUG] Finding start node (node with no inputs)")
    start_node = None
    for handle, info in connection_info.items():
        if not info["in_connectors"]:
            start_node = handle
            print(f"[DEBUG] Found start node: {handle}")
            break

    if start_node is None:
        raise ValueError("No start node found - graph may have cycles")

    sorted_handles = []
    visited = set()

    def visit(handle):
        print(f"[DEBUG] Visiting node {handle}")
        if handle is None:  # Skip None handles
            print(f"[DEBUG] Skipping None handle")
            return
        if handle in visited:
            print(f"[DEBUG] Node {handle} already visited, skipping")
            return
        visited.add(handle)
        print(f"[DEBUG] Processing outputs of node {handle}")
        for out_connector in connection_info[handle]["out_connectors"]:
            for target_handle, _ in out_connector["targets"]:
                if target_handle is not None:  # Only follow non-None handles
                    print(
                        f"[DEBUG] Following connection to node {target_handle}"
                    )
                    visit(target_handle)
                else:
                    print(f"[DEBUG] Skipping None target handle")
        print(f"[DEBUG] Adding node {handle} to sorted list")
        sorted_handles.append(handle)

    visit(start_node)
    print(f"[DEBUG] Topological sort complete. Order: {sorted_handles}")
    return sorted_handles


def layout_nodes(td_proxy, sorted_handles):
    print("[DEBUG] Starting node layout")
    # Reverse the order to get left-to-right layout
    sorted_handles = list(reversed(sorted_handles))

    # Add the output node (handle 1) to our layout
    sorted_handles.append(1)  # The output node always has handle 1

    # Get the geometry for each handle
    geometry = {}
    total_width = 0
    max_height = 0
    MARGIN = 20  # Units between nodes

    print("[DEBUG] Collecting geometry information")
    for handle in sorted_handles:
        print(f"[DEBUG] Getting geometry for handle {handle}")
        x, y, w, h = td_proxy.get_op_node_geometry(handle)
        geometry[handle] = (x, y, w, h)
        total_width += w
        max_height = max(max_height, h)
        print(f"[DEBUG] Node {handle} geometry: x={x}, y={y}, w={w}, h={h}")

    # Calculate total width including margins
    total_width += MARGIN * (len(sorted_handles) - 1)

    # Calculate starting x position to center around 0
    start_x = -total_width / 2

    # Set all of the node X coordinates according to the sorted order
    current_x = start_x
    print("[DEBUG] Positioning nodes")
    for handle in sorted_handles:
        x, y, w, h = geometry[handle]
        # Center vertically at y=0
        center_y = -h / 2

        print(
            f"[DEBUG] Setting position for handle {handle} to x={current_x}, y={center_y}"
        )
        td_proxy.set_op_attribute(handle, "nodeX", current_x)
        td_proxy.set_op_attribute(handle, "nodeY", center_y)

        # Move to next position including margin
        current_x += w + MARGIN
