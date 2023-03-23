from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request
import openai
from os import getenv
from threading import Event, Lock, Thread
import time

app = Flask(__name__)
openai.api_key = getenv("OPENAI_API_KEY")

pending_requests = {}
lock = Lock()


@app.route("/v1/completions", methods=["POST"])
def handle_request():
    params = request.get_json()
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
            key = dict(next(iter(pending_requests), None))
            values = pending_requests[key]

            prompts = [value["prompt"] for value in values]

            response = openai.Completion.create(
                prompt=prompts,
                **key
            )

            choices = response["choices"]
            grouped_choices = [choices[i:i + key["n"]] for i in range(0, len(choices), key["n"])]

            for value, choices in zip(values, grouped_choices):
                value["response"] = {"choices": choices}
                value["event"].set()

            key_to_delete = tuple(sorted(key.items()))

        time.sleep(3)

        with lock:
            del pending_requests[key_to_delete]


if __name__ == "__main__":
    Thread(target=handle_pending_requests, daemon=True).start()
    app.run()
