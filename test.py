import Pyro5.api
import IPython
import argparse


def topo_sort_handles(td_proxy, handles):
    print("[DEBUG] Starting topological sort")
    # Get the connection information for each handle
    connection_info = {}
    for handle in handles:
        print(f"[DEBUG] Getting connectors for handle {handle}")
        in_connectors, out_connectors = td_proxy.get_op_connectors(handle)
        connection_info[handle] = {
            "in_connectors": in_connectors,
            "out_connectors": out_connectors
        }
        print(f"[DEBUG] Handle {handle} has {len(in_connectors)} inputs and {len(out_connectors)} outputs")
    
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
        if handle in visited:
            print(f"[DEBUG] Node {handle} already visited, skipping")
            return
        visited.add(handle)
        print(f"[DEBUG] Processing outputs of node {handle}")
        for out_connector in connection_info[handle]["out_connectors"]:
            next_handle = out_connector[0]
            print(f"[DEBUG] Following connection to node {next_handle}")
            visit(next_handle)
        print(f"[DEBUG] Adding node {handle} to sorted list")
        sorted_handles.append(handle)

    visit(start_node)
    print(f"[DEBUG] Topological sort complete. Order: {sorted_handles}")
    return sorted_handles

def layout_nodes(td_proxy, sorted_handles):
    print("[DEBUG] Starting node layout")
    # Get the geometry for each handle
    geometry = {}
    for handle in sorted_handles:
        print(f"[DEBUG] Getting geometry for handle {handle}")
        x, y, w, h = td_proxy.get_op_node_geometry(handle)
        geometry[handle] = (x, y, w, h)
        print(f"[DEBUG] Node {handle} geometry: x={x}, y={y}, w={w}, h={h}")
    
    # Set all of the node X coordinates according to the sorted order and cumulative width
    cum_width = 0
    cum_height = 0
    for handle in sorted_handles:
        x, y, w, h = geometry[handle]
        print(f"[DEBUG] Setting position for handle {handle} to x={cum_width}, y={cum_height}")
        td_proxy.set_op_attribute(handle, "nodeX", cum_width)
        td_proxy.set_op_attribute(handle, "nodeY", cum_height)
        cum_width += w
        cum_height += h




def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=60883)
    parser.add_argument("--test-network", action="store_true")

    args = parser.parse_args()

    try:
        # Connect to the Pyro5 server
        uri = f"PYRO:td@localhost:{args.port}"  # Adjust the port if necessary
        td_proxy = Pyro5.api.Proxy(uri)
        print("Connected to TouchDesigner!")
    except Exception as e:
        print(f"Error: {e}")

    if args.test_network:
        audio_to_band_index = td_proxy.load('audio_to_band')
        audio_in_index = td_proxy.load('audio_in')
        unitary_to_rgb_index = td_proxy.load('wrapped/unitary_to_rgb')
        rgb_to_tex_index = td_proxy.load('rgb_to_tex')

        td_proxy.connect(audio_in_index, 0, audio_to_band_index, 0)
        td_proxy.connect(audio_to_band_index, 0, unitary_to_rgb_index, 0)
        td_proxy.connect(audio_to_band_index, 1, unitary_to_rgb_index, 1)
        td_proxy.connect(audio_to_band_index, 2, unitary_to_rgb_index, 2)
        td_proxy.connect(unitary_to_rgb_index, 0, rgb_to_tex_index, 0)
        td_proxy.connect(rgb_to_tex_index, 0, 1, 0)

        # Perform topological sorting to lay out the nodes. The geometry can be
        # fetched as follows:
        #
        # x,y,w,h = td_proxy.get_op_node_geometry(audio_in_index)
        #
        # Connections can also be fetched:
        #
        # in_connectors, out_connectors = td_proxy.get_op_connectors(audio_in_index)
        sorted_handles = topo_sort_handles(td_proxy, [audio_in_index, audio_to_band_index, unitary_to_rgb_index, rgb_to_tex_index])
        layout_nodes(td_proxy, sorted_handles)


    IPython.embed()


if __name__ == "__main__":
    main()
