import Pyro5.api
import IPython
import argparse
from graph_utils import bridge, topo_sort_handles, layout_nodes
import logging


def main():
    # Add at the top of the file, before any other imports
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(name)s - %(levelname)s - %(message)s',
        force=True  # This ensures we override any existing configuration
    )

    # Set up root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

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
        # Create a test network by bridging to the output handles from the I/O config.
        # Add an audio_in input into the network.
        created_nodes = bridge(td_proxy,
                               input_handles=[],
                               output_handles=[],
                               exclude_components=[
                                   "wrapped/tex_out",
                                   "wrapped/unitary_in",
                                   "wrapped/waveform_in",
                                   "rgb_to_tex",
                                   "audio_in",
                                   ], include_io_config=True)

        # Sort and layout the created nodes
        io_handles = td_proxy.get_io_handles()
        all_nodes = created_nodes + io_handles["inputs"] + io_handles["outputs"]
        print(f"All nodes: {all_nodes}")
        sorted_handles = topo_sort_handles(td_proxy, all_nodes)
        layout_nodes(td_proxy, sorted_handles)

    IPython.embed()


if __name__ == "__main__":
    main()
