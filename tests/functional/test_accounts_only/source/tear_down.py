"""Stop HTTP mock started by set_up.py."""


def run(test_context):
    if hasattr(test_context, "_http_patcher"):
        test_context._http_patcher.stop()
