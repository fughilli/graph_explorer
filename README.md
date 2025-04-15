# Graph Explorer

Graph Explorer is a Python-based tool for programmatically creating and
manipulating node networks in TouchDesigner. It provides a bridge between Python
scripts and TouchDesigner's operator (node) system, allowing for algorithmic
generation and modification of node networks.

## Architecture

The system consists of three main components:

1. **TouchDesigner Script DAT** (`script_dat.py`)

   - Runs inside TouchDesigner
   - Exposes TouchDesigner's functionality via a Pyro5 RPC server
   - Manages I/O operators and network state
   - Handles callbacks for network changes

2. **Python Client** (`test.py`)

   - Connects to TouchDesigner via Pyro5
   - Provides high-level graph manipulation functions
   - Implements graph algorithms for node placement and connection

3. **Graph Utilities** (`graph_utils.py`)
   - Contains core graph manipulation algorithms
   - Handles node creation, connection, and layout
   - Implements topological sorting and other graph operations

## Key Features

- **Persistent I/O Configuration**: I/O operators (inputs/outputs) persist
  between script restarts
- **Component System**: Loads components from JSON descriptors and .tox files
- **Automatic Layout**: Implements automatic node positioning and connection
  routing
- **Graph Algorithms**: Supports operations like bridging between input and
  output nodes
- **Live Updates**: Supports real-time updates through callback system

## Setup

1. Install dependencies:

```bash
pip install Pyro5 ipython
```

2. Configure TouchDesigner:

   - Create a new project
   - Add a Script DAT and paste the contents of `script_dat.py`
   - Set up the I/O configuration in `config/io_config.json`

3. Run the Python client:

```bash
python test.py --port <port> --test-network
```

## Component System

Components are defined using JSON descriptors:

```json
{
  "tox_file": "component.tox", // or "td_component": "baseCHOP"
  "inputs": [{ "name": "in1", "type": "waveform" }],
  "outputs": [{ "name": "out1", "type": "tex" }],
  "description": "Component description"
}
```

## Usage Example

```python
# Connect to TouchDesigner
td_proxy = Pyro5.api.Proxy(f"PYRO:td@localhost:{port}")

# Get I/O configuration
io_config = td_proxy.get_io_handles()

# Create nodes and connections
created_nodes = bridge(td_proxy,
                      io_config['inputs'],
                      io_config['outputs'],
                      reuse_weight=1)

# Layout the network
layout_nodes(td_proxy, created_nodes)
```

## Development

- Components are stored in the `components/` directory
- I/O configuration is stored in `config/io_config.json`
- Use the `--test-network` flag for testing graph generation
- Monitor TouchDesigner's textport for debug information

## License

```
MIT License

Copyright (c) 2025 Kevin Balke

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
