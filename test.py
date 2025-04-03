import Pyro5.api
import IPython
import argparse


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
        nullTOP_index = td_proxy.create_op('nullTOP')
        unitary_to_rgb_index = td_proxy.load('wrapped/unitary_to_rgb')
        rgb_to_tex_index = td_proxy.load('rgb_to_tex')

        td_proxy.connect(audio_in_index, 0, audio_to_band_index, 0)
        td_proxy.connect(audio_to_band_index, 0, unitary_to_rgb_index, 0)
        td_proxy.connect(audio_to_band_index, 1, unitary_to_rgb_index, 1)
        td_proxy.connect(audio_to_band_index, 2, unitary_to_rgb_index, 2)
        td_proxy.connect(unitary_to_rgb_index, 0, rgb_to_tex_index, 0)
        td_proxy.connect(rgb_to_tex_index, 0, nullTOP_index, 0)

        td_proxy.set_op_attribute(nullTOP_index, "display", True)

    IPython.embed()


if __name__ == "__main__":
    main()
