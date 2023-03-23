from dotenv import load_dotenv
load_dotenv()

import dataset
from flask import Flask, jsonify, request
import openai
from os import getenv
from sys import argv
from threading import Event, Lock, Thread
import time
from uuid import uuid4

app = Flask(__name__)
openai.api_key = getenv("OCP_OPENAI_API_KEY")
openai.organization = getenv("OCP_OPENAI_ORG")

pending_requests = {}
lock = Lock()

db = dataset.connect("sqlite:///db.sqlite3")
api_keys = db["api_keys"]
usage = db["requests"]


@app.route("/v1/completions", methods=["POST"])
def handle_request():
    params = request.get_json()

    if "prompt" not in params:
        return jsonify({"error": "prompt is required"}), 400
    if "api_key" not in params:
        return jsonify({"error": "api_key is required"}), 400

    api_key = params["api_key"]
    if not api_keys.find_one(api_key=api_key):
        return jsonify({"error": "invalid api_key"}), 401
    usage.insert(dict(api_key=api_key, timestamp=time.time()))
    
    params["model"] = "code-davinci-002"

    prompt = params["prompt"]
    shared_params = {k: v for k, v in params.items() if k != "prompt"}

    event = Event()

    key = tuple(sorted(shared_params.items()))
    value = {"prompt": prompt, "event": event}

    with lock:
        if key not in pending_requests:
            pending_requests[key] = [value]
        else:
            pending_requests[key].append(value)

    event.wait()

    with lock:
        for value in pending_requests[key]:
            if value["prompt"] == prompt:
                return jsonify(value["response"])
        

def handle_pending_requests():
    while True:
        with lock:
            if not pending_requests:
                continue

            key = next(iter(pending_requests))
            values = pending_requests[key]

            prompts = [value["prompt"] for value in values]

            response = openai.Completion.create(
                prompt=prompts,
                **dict(key)
            )

            if "n" in dict(key):
                n = dict(key)["n"]
            else:
                n = 1
            choices = response["choices"]
            grouped_choices = [choices[i:i + n] for i in range(0, len(choices), n)]

            for value, choices in zip(values, grouped_choices):
                value["response"] = {"choices": choices}
                value["event"].set()

            key_to_delete = key

        time.sleep(3)

        with lock:
            del pending_requests[key_to_delete]


if __name__ == "__main__":
    if len(argv) > 1 and argv[1] == "add-key":
        if len(argv) != 4:
            print("Usage: main.py add-key [name] [api_key]")
            exit(1)
    
        name = argv[2]
        api_key = argv[3]
    
        api_keys.insert(dict(name=name, api_key=api_key))
        print(f"Added key {api_key} for {name}")
    elif len(argv) > 1 and argv[1] == "delete-key":
        if len(argv) != 3:
            print("Usage: main.py delete-key [name]")
            exit(1)
    
        name = argv[2]
    
        api_keys.delete(name=name)
        print(f"Deleted key for {name}")
    elif len(argv) > 1 and argv[1] == "list-keys":
        if len(argv) != 2:
            print("Usage: main.py list-keys")
            exit(1)
    
        for key in api_keys:
            print(f"{key['name']}: {key['api_key']}")
    elif len(argv) > 1:
        print("Usage: main.py [add-key|delete-key|list-keys]")
        exit(1)
    else:
        Thread(target=handle_pending_requests, daemon=True).start()
        app.run()

else:
    Thread(target=handle_pending_requests, daemon=True).start()
