# Dev Instructions

Change 

```python
    params["model"] = "code-davinci-002"
```

to

```python
    params["model"] = "ada"
```

Add your OPENAI_API_KEY to the list of keys in 'data.json'

```json
{"api_keys": [{"api_key": "<your key>", "name": "test"}], "usage": []}
```
