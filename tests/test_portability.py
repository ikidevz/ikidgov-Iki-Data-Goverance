import json


def test_all_modules_return_json_safe_output(all_modules):
    for module in all_modules:
        result = module.run()
        assert json.dumps(result)
