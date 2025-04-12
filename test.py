import Pyro5.api
import IPython
import argparse
from graph_utils import bridge, topo_sort_handles, layout_nodes
import logging
import threading

td_proxy_container = [None]

@Pyro5.api.expose    # Expose this class to be accessible over Pyro
class IOCallback:
    @Pyro5.api.expose    # Make sure to expose the method
    def notify(self, args):    # Changed from __call__ to a named method
        print(f"Callback received: {args}")
        print(f"TD proxy container: {td_proxy_container}")
        if td_proxy_container[0] is not None:
            print(f"Rebuilding graph")
            rebuild_graph(td_proxy_container[0])

def rebuild_graph(td_proxy):
    td_proxy.clear()
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
        uri = f"PYRO:td@localhost:{args.port}"
        td_proxy = Pyro5.api.Proxy(uri)
        print("Connected to TouchDesigner!")
        
        # Create a Pyro daemon for the callback object
        daemon = Pyro5.api.Daemon()
        callback = IOCallback()
        uri = daemon.register(callback)
        
        # Register the callback's URI instead of the function
        td_proxy.register_io_callback(uri)

        td_proxy_container[0] = td_proxy
        
        if args.test_network:
            rebuild_graph(td_proxy)
            
        # Start the daemon loop in a separate thread
        #thread = threading.Thread(target=daemon.requestLoop, daemon=True)
        #thread.start()

        daemon.requestLoop()
            
    except Exception as e:
        print(f"Error: {e}")

    IPython.embed()


if __name__ == "__main__":
    main()
