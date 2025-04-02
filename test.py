import Pyro5.api
import IPython
import argparse



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=60883)

    args = parser.parse_args()

    try:
        # Connect to the Pyro5 server
        uri = f"PYRO:td@localhost:{args.port}"  # Adjust the port if necessary
        td_proxy = Pyro5.api.Proxy(uri)

        print("Connected to TouchDesigner!")
        IPython.embed()
       
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()

