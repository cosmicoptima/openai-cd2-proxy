from dotenv import load_dotenv
load_dotenv()

import hashlib
import json
import time

from os import getenv
from sys import argv
from threading import Event, Lock, Thread
from uuid import uuid4

from flask import Flask, jsonify, request
from flask_cors import CORS

import openai
import tiktoken

app = Flask(__name__)
CORS(app)
openai.api_key = getenv("OCP_OPENAI_API_KEY")
openai.organization = getenv("OCP_OPENAI_ORG")

pending_requests = {}
lock = Lock()

def load_data():
    global data
    try:
        with open("data.json") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"api_keys": [], "usage": []}

load_data()

encoding = tiktoken.encoding_for_model("code-davinci-002")


@app.route("/v1/completions", methods=["POST"])
def handle_request():
    params = request.get_json()

    load_data()
    api_key_full = request.headers.get("Authorization")
    if api_key_full.startswith("Bearer "):
        api_key = api_key_full[7:]
    else:
        return jsonify({"error": "Invalid API key"}), 401

    if "prompt" not in params:
        return jsonify({"error": "prompt is required"}), 400

    matching_keys = [key for key in data["api_keys"] if key["api_key"] == api_key]
    if len(matching_keys) == 0:
        return jsonify({"error": "Invalid API key"}), 401
    data["usage"].append({"name": matching_keys[0]["name"], "time": time.time()})

    with open("data.json", "w") as f:
        json.dump(data, f)
    
    params["model"] = "code-davinci-002"

    prompt = params["prompt"]
    shared_params = {k: v for k, v in params.items() if k != "prompt"}

    event = Event()

    sha256 = hashlib.sha256()
    sha256.update(json.dumps(tuple(sorted(params.items()))).encode("utf-8"))
    key = sha256.digest()
    value = {"prompt": prompt, "event": event}

    with lock:
        if key not in pending_requests:
            pending_requests[key] = {"shared_params": shared_params, "values": [value]}
        else:
            pending_requests[key]["values"].append(value)

    event.wait()

    with lock:
        for value in pending_requests[key]["values"]:
            if value["prompt"] == prompt:
                return jsonify(value["response"])
        

def handle_pending_requests():
    while True:
        with lock:
            if not pending_requests:
                continue

            key = next(iter(pending_requests))
            shared_params = pending_requests[key]["shared_params"]
            values = pending_requests[key]["values"]

            prompts = [value["prompt"] for value in values]

            response = openai.Completion.create(
                prompt=prompts,
                **shared_params
            )

            if "n" in shared_params:
                n = shared_params["n"]
            else:
                n = 1
            choices = response["choices"]
            grouped_choices = [choices[i:i + n] for i in range(0, len(choices), n)]

            for value, choices in zip(values, grouped_choices):
                value["response"] = {
                    "choices": choices,
                    "usage": create_usage_dict(values, choices)
                }
                value["event"].set()

            key_to_delete = key

        time.sleep(3)

        with lock:
            del pending_requests[key_to_delete]


def create_usage_dict(value, choices):
    usage_dict = {
        "prompt_tokens": len(encoding.encode(value["prompt"])),
        "completion_tokens": sum([len(encoding.encode(choice["text"])) for choice in choices])
    }
    usage_dict["total_tokens"] = usage_dict["prompt_tokens"] + usage_dict["response_tokens"]
    if usage_dict["completion_tokens"] == 0:
        usage_dict["completion_tokens"] = None
    return usage_dict


try:
    if __name__ == "__main__":
        if len(argv) > 1 and argv[1] == "add-key":
            if len(argv) != 3:
                print("Usage: main.py add-key [name]")
                exit(1)
        
            name = argv[2]
            api_key = str(uuid4())
       
            data["api_keys"].append({"name": name, "api_key": api_key})
            print(f"Added key {api_key} for {name}")
        elif len(argv) > 1 and argv[1] == "delete-key":
            if len(argv) != 3:
                print("Usage: main.py delete-key [name]")
                exit(1)
        
            name = argv[2]
        
            data["api_keys"] = [key for key in data["api_keys"] if key["name"] != name]
            print(f"Deleted key for {name}")
        elif len(argv) > 1 and argv[1] == "list-keys":
            if len(argv) != 2:
                print("Usage: main.py list-keys")
                exit(1)
        
            for key in data["api_keys"]:
                print(f"{key['name']}: {key['api_key']}")
        elif len(argv) > 1:
            print("Usage: main.py [add-key|delete-key|list-keys]")
            exit(1)
        else:
            Thread(target=handle_pending_requests, daemon=True).start()
            app.run()
    
    else:
        Thread(target=handle_pending_requests, daemon=True).start()
finally:
    with open("data.json", "w") as f:
        json.dump(data, f)
