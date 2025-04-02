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

# -------------------------------------------------
# Cleanup any previous instance stored in this DAT
# -------------------------------------------------
# "me.fetch" will return None if nothing has been stored yet.
old_manager = me.fetch('server_manager', None)
if old_manager is not None:
    try:
        print("[DEBUG] Shutting down previously stored Pyro server manager.")
        old_manager.stop_server()
    except Exception as e:
        print("[DEBUG] Error stopping previous Pyro server manager:", e)

# Create and store a new instance of the server manager.
new_manager = None  # Initialize variable
try:
    new_manager = None
    new_manager = Pyro5.api.Daemon(
    )  # We'll wrap this in our PyroServerManager below.
except Exception as e:
    print("[DEBUG] Error creating Pyro daemon:", e)

# -----------------------------------
# TouchDesigner Op and Proxy Classes
# -----------------------------------


class AnnotatedOp:

    def __init__(self, op, descriptor):
        self.op = op
        self.descriptor = descriptor

    @classmethod
    def load(cls, name, components_path):
        tox_path = os.path.join(components_path, f"{name}.tox")
        json_path = os.path.join(components_path, f"{name}.json")
        print(
            f"[DEBUG] Loading Tox from: {tox_path} and JSON from: {json_path}")
        return cls(
            td.op('/project1').loadTox(tox_path), json.load(open(json_path)))


class TdProxy:

    def __init__(self):
        self.td = td
        self.ops_by_handle = {}
        self.current_handle = 0

        self.insert_op(AnnotatedOp(td.op('/project1'), {"name": "project1"}))

    def insert_op(self, op):
        self.ops_by_handle[self.current_handle] = op
        self.current_handle += 1
        print(f"[DEBUG] Inserted op with handle {self.current_handle - 1}")
        return self.current_handle - 1

    def get_handle_for_native_op(self, native_op):
        for handle, op in self.ops_by_handle.items():
            if op.op == native_op:
                return handle
        return

    def get_op(self, handle):
        print(f"[DEBUG] Retrieving op with handle {handle}")
        return self.ops_by_handle.get(handle)

    @expose
    def create_op(self, name):
        print(f"[DEBUG] Creating op: {name}")
        native_op = td.op('/project1').create(name)
        handle = self.insert_op(AnnotatedOp(native_op, {"name": name}))
        print(f"[DEBUG] Created op with handle {handle}")
        return handle

    @expose
    def list_ops(self):
        print("[DEBUG] Listing ops")
        return [(handle, op.descriptor)
                for handle, op in self.ops_by_handle.items()]

    @expose
    def load_tox(self, name):
        print(f"[DEBUG] Loading tox: {name}")
        op = AnnotatedOp.load(
            name, "/Users/kevin/Projects/graph_explorer/components")
        handle = self.insert_op(op)
        op.op.tags.add(f"handle={handle}")
        print(f"[DEBUG] Tox loaded with handle {handle}")
        return handle

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
    def get_op_connectors(self, handle) -> tuple[list, list]:
        print(f"[DEBUG] Getting connectors for op with handle {handle}")
        if op := self.get_op(handle):
            in_connectors = []
            out_connectors = []

            for connector in op.op.inputConnectors:
                print(f"[DEBUG] Input connector: {connector}")
                owner_handle = self.get_handle_for_native_op(connector.owner)
                target_handles = [
                    self.get_handle_for_native_op(target)
                    for target in connector.connections
                ]

                in_connector = {
                    "owner_handle": owner_handle,
                    "target_handles": target_handles
                }
                print(f"[DEBUG] Converted connector: {in_connector}")
                in_connectors.append(in_connector)

            for connector in op.op.outputConnectors:
                print(f"[DEBUG] Output connector: {connector}")
                owner_handle = self.get_handle_for_native_op(connector.owner)
                target_handles = [
                    self.get_handle_for_native_op(target)
                    for target in connector.connections
                ]

                out_connector = {
                    "owner_handle": owner_handle,
                    "target_handles": target_handles
                }
                print(f"[DEBUG] Converted connector: {out_connector}")
                out_connectors.append(out_connector)

            result = in_connectors, out_connectors

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


td_proxy = TdProxy()

# -------------------------------------------------
# Pyro Server Manager with Synchronous Event Loop
# -------------------------------------------------


class PyroServerManager:

    def __init__(self):
        self.server = None
        self.running = False

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
            uri = self.server.register(td_proxy, objectId="td", force=True)
            print(f"[DEBUG] Pyro server running at {uri}")
        except Exception as e:
            print(f"[DEBUG] Error registering td_proxy: {e}")
            self.server = None
            return

        self.running = True
        print("[DEBUG] Server started in synchronous mode (multiplex).")

    def poll_events(self):
        if self.server and self.running:
            sockets = self.server.sockets
            # Process events as long as sockets report readiness.
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
        else:
            print("[DEBUG] No server to shut down.")


# Create a new PyroServerManager instance and store it in the DAT's storage.
new_manager = PyroServerManager()
me.store('server_manager', new_manager)

# -------------------------------------------------
# TouchDesigner Callback Functions
# -------------------------------------------------


def onSetupParameters(scriptOp):
    page = scriptOp.appendCustomPage('Custom')
    page.appendPulse('Startserver', label='Start Server')
    page.appendPulse('Stopserver', label='Stop Server')
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


def onCook(scriptOp):
    # Fetch the stored server manager.
    server_manager = me.fetch('server_manager', None)
    scriptOp.clear()
    # Poll Pyro events synchronously on each cook cycle.
    if server_manager and server_manager.running:
        server_manager.poll_events()

    scriptOp.appendRow(["Server running."])
