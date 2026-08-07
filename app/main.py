import random
import string

from flask import Flask, jsonify, redirect, request
from google.cloud import firestore

app = Flask(__name__)

GCP_PROJECT_ID = "karthi-url-shortener-2026"

db = firestore.Client(project=GCP_PROJECT_ID)
urls_collection = db.collection("urls")

CODE_LENGTH = 6
CODE_CHARS = string.ascii_letters + string.digits


def generate_short_code():
    while True:
        code = "".join(random.choices(CODE_CHARS, k=CODE_LENGTH))
        if not urls_collection.document(code).get().exists:
            return code


def is_valid_url(url):
    return isinstance(url, str) and (url.startswith("http://") or url.startswith("https://"))


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify(status="ok"), 200


@app.route("/shorten", methods=["POST"])
def shorten_url():
    data = request.get_json(silent=True) or {}  # silent=True avoids a 400 crash on a bad/missing JSON body
    original_url = data.get("url")

    if not is_valid_url(original_url):
        return jsonify(error="Provide a valid URL"), 400

    short_code = generate_short_code()
    urls_collection.document(short_code).set({"original_url": original_url})

    return jsonify(
        short_code=short_code,
        short_url=request.host_url + short_code,
        original_url=original_url,
    ), 201


@app.route("/urls", methods=["GET"])
def url_list():
    return jsonify(
        [
            {"short_code": doc.id, "original_url": doc.to_dict()["original_url"]}
            for doc in urls_collection.stream()
        ]
    ), 200


@app.route("/<short_code>", methods=["GET"])
def redirect_to_url(short_code):
    doc = urls_collection.document(short_code).get()
    if not doc.exists:
        return jsonify(error="Short code not found"), 404
    return redirect(doc.to_dict()["original_url"], code=302)


@app.route("/<short_code>", methods=["DELETE"])
def delete_url(short_code):
    doc_ref = urls_collection.document(short_code)
    if not doc_ref.get().exists:
        return jsonify(error="Please enter a valid short_code"), 404
    doc_ref.delete()
    return jsonify(message=f"{short_code} deleted"), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
