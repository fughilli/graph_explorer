import Pyro5.api
import dataclasses
import Pyro5.server
from Pyro5.api import expose, config
import json
import os
import td
import select

# Set the Pyro server type to "multiplex" so that calls are handled synchronously.
config.SERVERTYPE = "multiplex"

NETWORK_COMPONENT_PATH = "/project1/network"

# -----------------------------------
# TouchDesigner Op and Proxy Classes
# -----------------------------------


class AnnotatedOp:

    def __init__(self, op, descriptor, reserved=False):
        self.op = op
        self.descriptor = descriptor
        self.reserved = reserved

    @classmethod
    def load(cls, name, components_path, reserved=False):
        json_path = os.path.join(components_path, f"{name}.json")
        print(f"[DEBUG] Loading JSON from: {json_path}")
        descriptor = json.load(open(json_path))
        descriptor["name"] = name

        # Handle either tox_file or td_component
        if "tox_file" in descriptor:
            # Load from specified tox file, relative to JSON location
            json_dir = os.path.dirname(json_path)
            tox_path = os.path.join(json_dir, descriptor["tox_file"])
            print(f"[DEBUG] Loading Tox from: {tox_path}")
            op = td.op('/project1/network').loadTox(tox_path)
        elif "td_component" in descriptor:
            # Create built-in TD component
            print(
                f"[DEBUG] Creating TD component: {descriptor['td_component']}")
            op = td.op('/project1/network').create(descriptor['td_component'])
        else:
            raise ValueError(
                f"Component descriptor must specify either 'tox_file' or 'td_component'"
            )

        return cls(op, descriptor, reserved)


@Pyro5.api.expose
class TDProxy:

    def __init__(self):
        self.td = td
        self.ops_by_handle = {}
        self.current_handle = 0
        self.io_config = None

        self.input_handles = []
        self.output_handles = []

        self.io_config_path = None

        self.io_callback_ = None

        self.maybe_create_network_op()

    def maybe_create_network_op(self):
        if not td.op('/project1/network'):
            self.network_op = td.op('/project1').create('baseCOMP')
            self.network_op.name = 'network'

            # Network op was just created, there's no way we have any ops registered.
            # Clear all ops and the input/output handles.
            self.current_handle = 0
            self.ops_by_handle = {}
            self.input_handles = []
            self.output_handles = []
            self.io_config_path = None
        else:
            self.network_op = td.op('/project1/network')

        # Create a default op for project1
        if self.get_handle_for_native_op(self.network_op) is None:
            # Network op is not registered. First, clear all ops.
            self.clear()

            # Then, register the network op.
            self.insert_op(
                AnnotatedOp(self.network_op, {"name": "network"},
                            reserved=True))

    def load_io_config(self, io_config_path):
        if self.io_config_path != io_config_path:
            print(f"[DEBUG] Loading IO config from: {io_config_path}")
            self.set_io_config(json.load(open(io_config_path)))
            self.io_config_path = io_config_path

    def set_io_config(self, io_config):
        self.io_config = io_config

        # Delete old ops
        for handle in self.input_handles:
            self.delete_op(handle)
        for handle in self.output_handles:
            self.delete_op(handle)

        self.input_handles = []
        self.output_handles = []

        inputs = io_config["inputs"]
        for input in inputs:
            self.input_handles.append(self.load(input, reserved=True))

        outputs = io_config["outputs"]
        for output in outputs:
            self.output_handles.append(self.load(output, reserved=True))

    def insert_op(self, op):
        self.ops_by_handle[self.current_handle] = op
        self.current_handle += 1
        print(f"[DEBUG] Inserted op with handle {self.current_handle - 1}")
        return self.current_handle - 1

    def get_handle_for_native_op(self, native_op):
        return native_op.fetch("handle", None)

    def get_op(self, handle):
        print(f"[DEBUG] Retrieving op with handle {handle}")
        return self.ops_by_handle.get(handle)

    def io_callback(self, io_args):
        if self.io_callback_ is not None:
            try:
                # Call the specific method on the proxy
                self.io_callback_.notify(io_args)
            except Exception as e:
                print(f"Error calling IO callback: {e}")

    @expose
    def register_io_callback(self, callback_uri):
        # Store the URI and create a proxy to the callback object
        print(f"[DEBUG] Registering callback with URI: {callback_uri}")
        self.io_callback_ = Pyro5.api.Proxy(callback_uri)

    @expose
    def get_io_handles(self):
        return {
            "inputs": self.input_handles,
            "outputs": self.output_handles,
        }

    @expose
    def create_op(self, name):
        print(f"[DEBUG] Creating op: {name}")
        native_op = td.op('/project1/network').create(name)
        handle = self.insert_op(AnnotatedOp(native_op, {"name": name}))
        native_op.store("handle", handle)
        op.op.store("descriptor", op.descriptor)
        print(f"[DEBUG] Created op with handle {handle}")
        return handle

    @expose
    def list_ops(self):
        print("[DEBUG] Listing ops")
        return [(handle, op.descriptor)
                for handle, op in self.ops_by_handle.items()]

    @expose
    def load(self, name, reserved=False):
        print(f"[DEBUG] Loading component: {name}")
        op = AnnotatedOp.load(
            name, "/Users/kevin/Projects/graph_explorer/components", reserved)
        handle = self.insert_op(op)
        op.op.store("handle", handle)
        op.op.store("descriptor", op.descriptor)
        print(f"[DEBUG] Tox loaded with handle {handle}")
        return handle

    @expose
    def eval_to_str(self, expression):
        return str(eval(expression))

    @expose
    def get_op_node_geometry(self, handle):
        native_op = self.get_op(handle).op
        return (
            native_op.nodeX,
            native_op.nodeY,
            native_op.nodeWidth,
            native_op.nodeHeight,
        )

    @expose
    def get_op_descriptor(self, handle):
        return self.get_op(handle).descriptor

    @expose
    def get_op_attribute(self, handle, attribute, dir_output=False):
        print(
            f"[DEBUG] Getting attribute '{attribute}' from op with handle {handle}"
        )
        if op := self.get_op(handle):
            x = op.op
            for attr in attribute.split("."):
                if attr == '':
                    continue
                x = getattr(x, attr)
            print(f"[DEBUG] Retrieved attribute value: {x}")
            if dir_output:
                return str(dir(x))
            return str(x)
        print("[DEBUG] No op found for given handle.")
        return None

    @expose
    def set_op_attribute(self, handle, attribute, value):
        print(
            f"[DEBUG] Setting attribute '{attribute}' on op with handle {handle} to {value}"
        )
        if op := self.get_op(handle):
            x = op.op
            attrs = attribute.split(".")
            for attr in attrs[:-1]:
                x = getattr(x, attr)
            setattr(x, attrs[-1], value)
            print("[DEBUG] Attribute set.")
            return True
        print("[DEBUG] No op found for given handle.")
        return False

    @expose
    def get_op_connectors(self, handle) -> tuple[list, list]:
        print(f"[DEBUG] Getting connectors for op with handle {handle}")
        if op := self.get_op(handle):
            in_connectors = []
            out_connectors = []

            for connector in op.op.inputConnectors:
                print(f"[DEBUG] Input connector: {connector}")
                index = connector.index
                owner_handle = self.get_handle_for_native_op(connector.owner)
                target_handles_and_indices = [
                    (self.get_handle_for_native_op(target.owner), target.index)
                    for target in connector.connections
                ]

                in_connector = {
                    "owner": (owner_handle, index),
                    "targets": target_handles_and_indices,
                }
                print(f"[DEBUG] Converted connector: {in_connector}")
                in_connectors.append(in_connector)

            for connector in op.op.outputConnectors:
                print(f"[DEBUG] Output connector: {connector}")
                index = connector.index
                owner_handle = self.get_handle_for_native_op(connector.owner)
                target_handles_and_indices = [
                    (self.get_handle_for_native_op(target.owner), target.index)
                    for target in connector.connections
                ]

                out_connector = {
                    "owner": (owner_handle, index),
                    "targets": target_handles_and_indices,
                }
                print(f"[DEBUG] Converted connector: {out_connector}")
                out_connectors.append(out_connector)

            result = {"in": in_connectors, "out": out_connectors}
            print(f"[DEBUG] Retrieved connectors: {result}")
            return result
        raise ValueError("No op found for given handle.")

    @expose
    def connect(self, output_handle, output_index, input_handle, input_index):
        print(
            f"[DEBUG] Connecting output {output_index} of op {output_handle} to input {input_index} of op {input_handle}"
        )
        try:
            if output_op := self.get_op(output_handle):
                if input_op := self.get_op(input_handle):
                    output_op.op.outputConnectors[output_index].connect(
                        input_op.op.inputConnectors[input_index])
                    print("[DEBUG] Connection successful.")
                    return True
        except Exception as e:
            print(f"[DEBUG] Connection failed: {e}")
        return False

    @expose
    def disconnect(self, handle, in_indices, out_indices):
        print(
            f"[DEBUG] Disconnecting inputs {in_indices} and outputs {out_indices} from op with handle {handle}"
        )
        try:
            if op := self.get_op(handle):
                for in_index in in_indices:
                    op.op.inputConnectors[in_index].disconnect()
                for out_index in out_indices:
                    op.op.outputConnectors[out_index].disconnect()
                print("[DEBUG] Disconnection successful.")
                return True
        except Exception as e:
            print(f"[DEBUG] Disconnection failed: {e}")
        return False

    @expose
    def delete_op(self, handle):
        print(f"[DEBUG] Deleting op with handle {handle}")
        if op := self.get_op(handle):
            op.op.destroy()
            self.ops_by_handle.pop(handle)
            return True
        return False

    @expose
    def clear(self):
        print("[DEBUG] Clearing all ops")
        try:
            handles_to_remove = []
            for handle, op in self.ops_by_handle.items():
                if op.reserved:
                    # Skip the default project1 op, otherwise we crash.
                    continue
                try:
                    op.op.destroy()
                    handles_to_remove.append(handle)
                except Exception as e:
                    print(
                        f"[DEBUG] Error destroying op with handle {handle}: {str(e)}"
                    )
                    # Continue with other ops even if one fails
                    continue

            for handle in handles_to_remove:
                self.ops_by_handle.pop(handle)

            self.current_handle = len(self.ops_by_handle)
            return True
        except Exception as e:
            # Convert any TD errors to a standard Python error message
            print(f"[DEBUG] Error during clear operation: {str(e)}")
            raise RuntimeError(f"Failed to clear operators: {str(e)}")


# -------------------------------------------------
# Pyro Server Manager with Synchronous Event Loop
# -------------------------------------------------


class PyroServerManager:

    def __init__(self):
        self.server = None
        self.running = False
        self.uri = None  # And the full URI
        self.io_args = None
        self.td_proxy = TDProxy()

    def load_io_config(self, io_config_path):
        self.td_proxy.load_io_config(io_config_path)

    def set_io_args(self, io_args):
        self.io_args = json.loads(io_args)

    def io_callback(self):
        self.td_proxy.io_callback(self.io_args)

    def start_server(self):
        if self.server is not None:
            print("[DEBUG] Server is already running.")
            return

        # Create the Pyro daemon.
        self.server = Pyro5.api.Daemon()
        print("[DEBUG] Pyro daemon created.")
        try:
            # Unregister any previous registration for "td"
            self.server.unregister("td")
            print("[DEBUG] Previous 'td' registration unregistered.")
        except Exception as ex:
            print(f"[DEBUG] Failed to unregister previous object: {ex}")
        try:
            # Register our proxy. Save the URI.
            uri = self.server.register(self.td_proxy,
                                       objectId="td",
                                       force=True)
            self.uri = str(uri)
            print(f"[DEBUG] Pyro server running at {self.uri}")
        except Exception as e:
            print(f"[DEBUG] Error registering td_proxy: {e}")
            self.server = None
            return

        self.running = True
        print("[DEBUG] Server started in synchronous mode (multiplex).")

        # Create the network op if it doesn't exist.
        self.td_proxy.maybe_create_network_op()

    def poll_events(self):
        if self.server and self.running:
            sockets = self.server.sockets
            while True:
                try:
                    ready, _, _ = select.select(sockets, [], [], 0.01)
                    if ready:
                        for sock in ready:
                            print(
                                f"[DEBUG] Processing socket with fileno: {sock.fileno()}"
                            )
                        self.server.events(ready)
                    else:
                        break
                except Exception as e:
                    print(f"[DEBUG] Exception in poll_events: {e}")
                    break
        else:
            print("[DEBUG] Server not running; poll_events skipped.")

    def stop_server(self):
        if self.server:
            try:
                self.server.shutdown()
                print("[DEBUG] Server shut down successfully.")
            except Exception as e:
                print(f"[DEBUG] Error during server shutdown: {e}")
            self.running = False
            self.server = None
            self.uri = None
        else:
            print("[DEBUG] No server to shut down.")


# -------------------------------------------------
# TouchDesigner Callback Functions
# -------------------------------------------------

# Use storeStartupValue so the stored value isn't pickled with the project.
me.storeStartupValue('server_manager', None)

me.storeStartupValue('io_config_path', None)


def onSetupParameters(scriptOp):
    page = scriptOp.appendCustomPage('Graph Explorer')
    page.appendPulse('Startserver', label='Start Server')
    page.appendPulse('Stopserver', label='Stop Server')
    page.appendPulse('Iocallback', label='I/O Callback')
    page.appendStr('Ioargs', label='I/O Args')
    # Add a string parameter to show the server URI.
    page.appendStr('Serveruri', label='Server URI')
    page.appendFloat('Dummycook', label='Dummy Force Cook Parameter')

    p = page.appendStr('Ioconfig', label='I/O Config')[0]
    p.default = 'config/io_config.json'

    scriptOp.par.Dummycook.expr = "me.time.seconds"
    scriptOp.par.Dummycook.readOnly = True

    print("[DEBUG] onSetupParameters: Parameters set up.")


def onPulse(par):
    # Fetch the stored server manager.
    server_manager = me.fetch('server_manager', None)
    print(f"[DEBUG] onPulse triggered: {par.name}")
    if server_manager is None:
        print("[DEBUG] No server manager found!")
        return
    if par.name == 'Startserver':
        server_manager.start_server()
    elif par.name == 'Stopserver':
        server_manager.stop_server()
        me.store('server_manager', None)
    elif par.name == 'Iocallback':
        server_manager.io_callback()


SHOULD_STOP = True


def onCook(scriptOp):
    global SHOULD_STOP

    # Fetch the stored server manager.
    server_manager = me.fetch('server_manager', None)
    if server_manager is None:
        server_manager = PyroServerManager()
        me.store('server_manager', server_manager)
    else:
        if SHOULD_STOP:
            server_manager.stop_server()
            SHOULD_STOP = False

    scriptOp.clear()
    # Poll Pyro events synchronously on each cook cycle.
    if server_manager and server_manager.running:
        input_path = scriptOp.par.Ioconfig.eval()
        server_manager.load_io_config(input_path)
        server_manager.poll_events()
        uri_str = str(server_manager.uri) if server_manager.uri else "Unknown"
        scriptOp.appendRow(["Server running on port: " + uri_str])
        # Update the custom parameter on the DAT (if it exists)
        try:
            # Update the parameter value. Adjust the syntax if needed.
            scriptOp.par.Serveruri = uri_str
        except Exception as e:
            print(f"[DEBUG] Error updating Serveruri parameter: {e}")

        io_args = scriptOp.par.Ioargs.eval()
        try:
            server_manager.set_io_args(io_args)
        except Exception as e:
            print(f"[DEBUG] Error setting io args: {e}")
    else:
        scriptOp.appendRow(["Server not running."])
        try:
            scriptOp.par.Serveruri = ""
        except Exception as e:
            print(f"[DEBUG] Error updating Serveruri parameter: {e}")
