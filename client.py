import Pyro5.api
import argparse
from graph_utils import bridge, topo_sort_handles, layout_nodes
import logging
import threading

td_proxy_container = [None]

rebuild_lock = threading.Lock()


@Pyro5.api.expose  # Expose this class to be accessible over Pyro
class IOCallback:

    def __init__(self, td_proxy):
        self.td_proxy = td_proxy  # Store the original proxy

    @Pyro5.api.expose  # Make sure to expose the method
    def notify(self, args):  # Changed from __call__ to a named method
        print(f"Callback received: {args}")
        rebuild_lock.release()


def rebuild_graph(td_proxy):
    td_proxy.clear()
    # Create a test network by bridging to the output handles from the I/O config.
    created_nodes = bridge(td_proxy,
                           input_handles=[],
                           output_handles=[],
                           exclude_components=[
                               "io/*",
                           ],
                           include_io_config=True)

    # Sort and layout the created nodes
    io_handles = td_proxy.get_io_handles()
    all_nodes = created_nodes + io_handles["inputs"] + io_handles["outputs"]
    print(f"All nodes: {all_nodes}")
    sorted_handles = topo_sort_handles(td_proxy, all_nodes)
    layout_nodes(td_proxy, sorted_handles)


def main():
    global rebuild_flag
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

    uri = f"PYRO:td@localhost:{args.port}"
    td_proxy = Pyro5.api.Proxy(uri)
    print("Connected to TouchDesigner!")

    # Create a Pyro daemon for the callback object
    daemon = Pyro5.api.Daemon()
    callback = IOCallback(td_proxy)  # Pass the original proxy
    uri = daemon.register(callback)

    # Register the callback's URI instead of the function
    td_proxy.register_io_callback(uri)

    if args.test_network:
        rebuild_graph(td_proxy)

    # Start the daemon loop in a separate thread
    thread = threading.Thread(target=daemon.requestLoop, daemon=True)
    thread.start()

    rebuild_lock.acquire()

    while True:
        rebuild_lock.acquire()
        try:
            rebuild_graph(td_proxy)
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
