import json
import os
import random
import logging
from typing import Dict, List, Set, Tuple
from pathlib import Path

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default to INFO level

# Create console handler if none exists
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)


def load_components(components_dir: str) -> Dict[str, dict]:
    """Load all component descriptors from the components directory."""
    components = {}
    components_path = Path(components_dir)

    # Load types.json first
    with open(os.path.join(components_dir, "types.json")) as f:
        types = json.load(f)
        logger.debug(f"[DEBUG] Loaded types: {types}")

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
                    logger.debug(
                        f"[DEBUG] Loaded component {name}: {descriptor}")

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
    logger.debug(
        f"[DEBUG] Components producing {type_name}: {matching_components}")
    return matching_components


def bridge(td_proxy,
           input_handles: List[int],
           output_handles: List[int],
           reuse_weight: float = 0.7,
           include_io_config: bool = True):
    """
    Stochastically generate a network connecting input nodes to output nodes.
    Each handle represents a node in the TouchDesigner network.
    Types are determined from component descriptors.

    The handles from the I/O config are automatically added to the input and output lists when `include_io_config` is True.

    Args:
        td_proxy: The TouchDesigner proxy object.
        input_handles: A list of input handles.
        output_handles: A list of output handles.
        reuse_weight: The weight of the reuse operation.
    """
    logger.debug("Starting bridge operation")
    logger.debug("Input handles: %s", input_handles)
    logger.debug("Output handles: %s", output_handles)

    # Load all component descriptors
    components = load_components(
        "/Users/kevin/Projects/graph_explorer/components")

    if include_io_config:
        io_config = td_proxy.get_io_handles()
        input_handles.extend(io_config["inputs"])
        output_handles.extend(io_config["outputs"])

        # Deduplicate the input and output handles
        input_handles = list(set(input_handles))
        output_handles = list(set(output_handles))

    # Get types for input and output nodes from their descriptors
    # Each entry is (handle, index, type)
    input_nodes = []
    for handle in input_handles:
        descriptor = td_proxy.get_op_descriptor(handle)
        if descriptor and "outputs" in descriptor:
            for idx, output in enumerate(descriptor["outputs"]):
                output_type = output["type"]
                input_nodes.append((handle, idx, output_type))
                logger.debug("Input node %d output[%d] provides type %s",
                             handle, idx, output_type)
        else:
            raise ValueError(f"No descriptor found for input handle {handle}")

    # Keep track of unsatisfied outputs we need to connect
    outputs_to_satisfy = []
    for handle in output_handles:
        descriptor = td_proxy.get_op_descriptor(handle)
        if descriptor and "inputs" in descriptor:
            for idx, input_desc in enumerate(descriptor["inputs"]):
                input_type = input_desc["type"]
                outputs_to_satisfy.append((handle, idx, input_type))
                logger.debug("Output node %d input[%d] requires type %s",
                             handle, idx, input_type)
        else:
            raise ValueError(f"No descriptor found for output handle {handle}")

    # Keep track of available inputs we can connect to
    available_inputs = [(handle, idx, type_name)
                        for handle, idx, type_name in input_nodes]

    # Keep track of all nodes we create
    created_nodes = []

    # Keep track of available outputs by type
    available_outputs = {}  # type -> List[(handle, index)]

    # Keep track of node ordering to prevent cycles
    node_order = {}
    current_order = 0

    # Initialize output nodes with highest order
    for handle in output_handles:
        node_order[handle] = current_order
        current_order += 1

    def can_connect_without_cycle(source_handle: int,
                                  target_handle: int) -> bool:
        """Check if connecting source to target would create a cycle."""
        nonlocal current_order

        # If target isn't in ordering yet, assign it current_order
        if target_handle not in node_order:
            node_order[target_handle] = current_order
            current_order += 1

        # If source isn't in ordering yet, assign it an order before target
        if source_handle not in node_order:
            node_order[source_handle] = node_order[target_handle] - 1

        result = node_order[source_handle] < node_order[target_handle]
        logger.debug(
            f"[DEBUG] Cycle check: source={source_handle}(order={node_order.get(source_handle, 'None')}), "
            f"target={target_handle}(order={node_order.get(target_handle, 'None')}), result={result}"
        )
        return result

    while outputs_to_satisfy:
        output_handle, output_index, required_type = outputs_to_satisfy.pop(0)
        logger.debug(
            f"[DEBUG] Trying to satisfy output {output_handle}:{output_index} requiring type {required_type}"
        )

        # Try to find an existing output of the required type
        logger.debug(f"[DEBUG] Available outputs by type: {available_outputs}")
        valid_existing_outputs = [
            (h, idx) for h, idx in available_outputs.get(required_type, [])
            if can_connect_without_cycle(h, output_handle)
        ]
        logger.debug(
            f"[DEBUG] Valid existing outputs for {required_type}: {valid_existing_outputs}"
        )

        rand_val = random.random()
        use_existing = valid_existing_outputs and rand_val < reuse_weight
        logger.debug(
            f"[DEBUG] Random value: {rand_val}, REUSE_WEIGHT: {reuse_weight}, use_existing: {use_existing}"
        )

        if use_existing:
            # Use an existing output
            source_handle, source_index = random.choice(valid_existing_outputs)
            logger.debug(
                f"[DEBUG] Reusing existing output {source_handle}:{source_index} of type {required_type}"
            )
            td_proxy.connect(source_handle, source_index, output_handle,
                             output_index)
            logger.debug(
                f"[DEBUG] Connected {source_handle}:{source_index} -> {output_handle}:{output_index}"
            )

        else:
            # Create a new component
            producer_components = find_components_producing_type(
                required_type, components)
            logger.debug(
                f"[DEBUG] Found producer components for {required_type}: {producer_components}"
            )
            if not producer_components:
                raise ValueError(
                    f"No components found that can produce type {required_type}"
                )

            chosen_component = random.choice(producer_components)
            logger.debug(
                f"[DEBUG] Chose component {chosen_component} to produce {required_type}"
            )

            new_handle = td_proxy.load(chosen_component)
            created_nodes.append(new_handle)
            logger.debug(f"[DEBUG] Created component with handle {new_handle}")

            # Connect its output to our target
            td_proxy.connect(new_handle, 0, output_handle, output_index)
            logger.debug(
                f"[DEBUG] Connected {new_handle}:0 -> {output_handle}:{output_index}"
            )

            # Register all outputs as available
            component_desc = components[chosen_component]
            for i, output_desc in enumerate(component_desc.get("outputs", [])):
                if i != 0:  # Skip the output we just used
                    output_type = output_desc["type"]
                    if output_type not in available_outputs:
                        available_outputs[output_type] = []
                    available_outputs[output_type].append((new_handle, i))
                    logger.debug(
                        f"[DEBUG] Registered available output {new_handle}:{i} of type {output_type}"
                    )

            # Add its inputs to our list of outputs we need to satisfy
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
                    logger.debug(
                        f"[DEBUG] Connected available input {in_handle}:{in_index} -> {new_handle}:{i}"
                    )
                else:
                    # Add to outputs we need to satisfy
                    outputs_to_satisfy.append(
                        (new_handle, i, input_desc["type"]))
                    logger.debug(
                        f"[DEBUG] Added new output to satisfy: {new_handle}:{i} type {input_desc['type']}"
                    )

    if available_inputs:
        logger.warning(
            f"[WARNING] Some inputs were not used: {available_inputs}")

    # Return all nodes involved in the bridge
    return created_nodes


def topo_sort_handles(td_proxy, handles):
    logger.debug("Starting topological sort")
    # Get the connection information for each handle
    connection_info = {}

    # First pass: collect all handles including referenced inputs
    all_handles = set(handles)
    for handle in handles:
        logger.debug(f"[DEBUG] Getting connectors for handle {handle}")
        connectors = td_proxy.get_op_connectors(handle)
        logger.debug(f"[DEBUG] Raw connector info: {connectors}")

        # Look at the actual connections in the input connectors
        for in_conn in connectors["in"]:
            if in_conn[
                    "targets"]:  # Only look at connectors that have actual connections
                for target_handle, _ in in_conn["targets"]:
                    if target_handle is not None:
                        all_handles.add(target_handle)

    # Second pass: get connection info for all handles
    for handle in all_handles:
        connectors = td_proxy.get_op_connectors(handle)

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
        logger.debug(
            f"[DEBUG] Handle {handle} has {len(in_connections)} active inputs and {len(out_connections)} active outputs"
        )

    # Kahn's algorithm for topological sort
    # Count incoming edges for each node
    in_degree = {
        handle: len(connection_info[handle]["in_connectors"])
        for handle in all_handles
    }

    # Find all nodes with no incoming edges
    queue = [handle for handle in all_handles if in_degree[handle] == 0]
    logger.debug(f"[DEBUG] Starting nodes with no incoming edges: {queue}")

    sorted_handles = []
    while queue:
        current = queue.pop(0)  # Get next node with no incoming edges
        sorted_handles.append(current)
        logger.debug(f"[DEBUG] Adding node {current} to sorted list")

        # Remove edges from current node to its targets
        for out_conn in connection_info[current]["out_connectors"]:
            for target_handle, _ in out_conn["targets"]:
                if target_handle in in_degree:  # Only process nodes we're tracking
                    in_degree[target_handle] -= 1
                    logger.debug(
                        f"[DEBUG] Reduced in-degree of {target_handle} to {in_degree[target_handle]}"
                    )
                    if in_degree[target_handle] == 0:
                        queue.append(target_handle)
                        logger.debug(
                            f"[DEBUG] Node {target_handle} has no more incoming edges, adding to queue"
                        )

    if len(sorted_handles) != len(all_handles):
        raise ValueError("Graph has cycles")

    logger.debug(f"[DEBUG] Topological sort complete. Order: {sorted_handles}")
    return sorted_handles


def layout_nodes(td_proxy, sorted_handles):
    logger.debug("Starting node layout")
    # Add the output node (handle 1) to our layout
    sorted_handles.append(1)  # The output node always has handle 1

    # Get the geometry for each handle
    geometry = {}
    total_width = 0
    max_height = 0
    MARGIN = 20  # Units between nodes

    logger.debug("[DEBUG] Collecting geometry information")
    for handle in sorted_handles:
        logger.debug(f"[DEBUG] Getting geometry for handle {handle}")
        x, y, w, h = td_proxy.get_op_node_geometry(handle)
        geometry[handle] = (x, y, w, h)
        total_width += w
        max_height = max(max_height, h)
        logger.debug(
            f"[DEBUG] Node {handle} geometry: x={x}, y={y}, w={w}, h={h}")

    # Calculate total width including margins
    total_width += MARGIN * (len(sorted_handles) - 1)

    # Calculate starting x position to center around 0
    start_x = -total_width / 2

    # Set all of the node X coordinates according to the sorted order
    current_x = start_x
    logger.debug("[DEBUG] Positioning nodes")
    for handle in sorted_handles:
        x, y, w, h = geometry[handle]
        # Center vertically at y=0
        center_y = -h / 2

        logger.debug(
            f"[DEBUG] Setting position for handle {handle} to x={current_x}, y={center_y}"
        )
        td_proxy.set_op_attribute(handle, "nodeX", current_x)
        td_proxy.set_op_attribute(handle, "nodeY", center_y)

        # Move to next position including margin
        current_x += w + MARGIN
