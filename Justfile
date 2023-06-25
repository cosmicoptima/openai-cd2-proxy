install:
  sudo apt-get install python3-flask-cors
  poetry install
  echo You may need the next line to get gunicorn to work?
  poetry run pip install --force-reinstall -U setuptools

run:
  poetry run gunicorn main:app --reload

test:
  curl -X POST http://localhost:8000/v1/completions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -d '{ \
      "model": "text-davinci-003", \
      "prompt": "Say this is a test", \
      "max_tokens": 7, \
      "temperature": 0 \
    }'
