import unittest
from parameterized import parameterized
from graph_utils import bridge, topo_sort_handles, load_components
from unittest.mock import MagicMock, patch


class MockTDProxy:

    def __init__(self):
        self.next_handle = 100
        self.connections = {
        }  # (source_handle, source_idx) -> [(target_handle, target_idx)]
        self.loaded_components = {}  # handle -> component_name
        self.node_geometry = {}  # handle -> (x, y, w, h)
        self.attributes = {}  # (handle, attr) -> value

    def load(self, component_name):
        handle = self.next_handle
        self.next_handle += 1
        self.loaded_components[handle] = component_name
        self.node_geometry[handle] = (0, 0, 100, 100)  # Default geometry
        return handle

    def connect(self, source_handle, source_idx, target_handle, target_idx):
        key = (source_handle, source_idx)
        if key not in self.connections:
            self.connections[key] = []
        self.connections[key].append((target_handle, target_idx))

    def get_op_connectors(self, handle):
        # Build connector info based on connections
        in_conns = []
        out_conns = []

        # Find inputs to this handle
        for (src_h, src_idx), targets in self.connections.items():
            for tgt_h, tgt_idx in targets:
                if tgt_h == handle:
                    in_conns.append({
                        "owner": (handle, tgt_idx),
                        "targets": [(src_h, src_idx)]
                    })

        # Find outputs from this handle
        for (src_h, src_idx), targets in self.connections.items():
            if src_h == handle:
                out_conns.append({
                    "owner": (handle, src_idx),
                    "targets": targets
                })

        return {"in": in_conns, "out": out_conns}

    def get_op_node_geometry(self, handle):
        return self.node_geometry.get(handle, (0, 0, 100, 100))

    def set_op_attribute(self, handle, attr, value):
        self.attributes[(handle, attr)] = value


class TestGraphUtils(unittest.TestCase):

    def setUp(self):
        self.td_proxy = MockTDProxy()

        # Mock the components directory
        self.components_patcher = patch('graph_utils.load_components')
        self.mock_load_components = self.components_patcher.start()
        self.mock_load_components.return_value = {
            'rgb_to_tex': {
                'inputs': [{
                    'type': 'rgb'
                }],
                'outputs': [{
                    'type': 'tex'
                }]
            },
            'audio_to_band': {
                'inputs': [{
                    'type': 'waveform'
                }],
                'outputs': [{
                    'type': 'unitary'
                }, {
                    'type': 'unitary'
                }, {
                    'type': 'unitary'
                }]
            },
            'wrapped/unitary_to_rgb': {
                'inputs': [{
                    'type': 'unitary'
                }, {
                    'type': 'unitary'
                }, {
                    'type': 'unitary'
                }],
                'outputs': [{
                    'type': 'rgb'
                }]
            },
            # Add component that produces waveform
            'audio_in': {
                'inputs': [],
                'outputs': [{
                    'type': 'waveform'
                }]
            }
        }

    def tearDown(self):
        self.components_patcher.stop()

    @parameterized.expand([
        (
            "simple_chain",
            [(1, 'waveform')],  # input_nodes
            [(2, 'tex')],  # output_nodes
            3
        ),  # expected_node_count: audio_to_band -> unitary_to_rgb -> rgb_to_tex
        ("reuse_outputs", [(1, 'waveform')], [(2, 'tex'), (3, 'tex')],
         5),  # One extra rgb_to_tex for the second output
    ])
    def test_bridge(self, name, input_nodes, output_nodes,
                    expected_node_count):
        created_nodes = bridge(self.td_proxy,
                               input_nodes,
                               output_nodes,
                               reuse_weight=1)
        self.assertEqual(len(created_nodes), expected_node_count)

        # Verify no cycles
        # Include input and output nodes in the topological sort
        all_nodes = ([handle for handle, _ in input_nodes] + created_nodes +
                     [handle for handle, _ in output_nodes])
        sorted_handles = topo_sort_handles(self.td_proxy, all_nodes)
        self.assertEqual(len(sorted_handles), len(all_nodes))

        # Verify input nodes come before created nodes
        for in_handle, _ in input_nodes:
            for created_handle in created_nodes:
                self.assertLess(sorted_handles.index(in_handle),
                                sorted_handles.index(created_handle))

        # Verify created nodes come before output nodes
        for created_handle in created_nodes:
            for out_handle, _ in output_nodes:
                self.assertLess(sorted_handles.index(created_handle),
                                sorted_handles.index(out_handle))

    @parameterized.expand([
        ("linear_chain", {
            (1, 0): [(2, 0)],
            (2, 0): [(3, 0)]
        }, [1, 2, 3], [[1, 2, 3]]),
        (
            "diamond",
            {
                (1, 0): [(2, 0), (3, 0)],
                (2, 0): [(4, 1)],
                (3, 0): [(4, 0)]
            },
            [1, 2, 3, 4],
            # 2 and 3 are equal rank, so we can return either order
            [[1, 2, 3, 4], [1, 3, 2, 4]]),
    ])
    def test_topo_sort(self, name, connections, handles, expected_orders):
        # Set up the connections in the mock proxy
        for (src_h, src_idx), targets in connections.items():
            for tgt_h, tgt_idx in targets:
                self.td_proxy.connect(src_h, src_idx, tgt_h, tgt_idx)

        sorted_handles = topo_sort_handles(self.td_proxy, handles)
        self.assertIn(sorted_handles, expected_orders)


if __name__ == '__main__':
    unittest.main()
