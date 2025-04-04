import Pyro5.api
import IPython
import argparse
from graph_utils import bridge, topo_sort_handles, layout_nodes


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
        # Create a test network by bridging from audio_in to tex_out
        created_nodes = bridge(td_proxy,
                               input_nodes=[(td_proxy.load('audio_in'),
                                             "waveform")],
                               output_nodes=[
                                   (1, "tex")
                               ])  # Handle 1 is always the output node

        # Sort and layout the created nodes
        sorted_handles = topo_sort_handles(td_proxy, created_nodes)
        layout_nodes(td_proxy, sorted_handles)

    IPython.embed()


if __name__ == "__main__":
    main()
