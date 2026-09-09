from package.services.json_utils import clean_json_response


def test_removes_json_code_fence():
    content = """```json
{
  "value": 1
}
```"""

    result = clean_json_response(content)

    assert result == '{\n  "value": 1\n}'


def test_removes_generic_code_fence():
    content = """```
{
  "value": 1
}
```"""

    result = clean_json_response(content)

    assert result == '{\n  "value": 1\n}'


def test_plain_json_is_unchanged():
    content = """
    {
      "value": 1
    }
    """

    result = clean_json_response(content)

    assert result == '{\n      "value": 1\n    }'