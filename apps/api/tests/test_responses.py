from app.core.responses import error_response, success_response


def test_success_response_shape():
    res = success_response({"ok": True})
    assert res.success is True
    assert res.data == {"ok": True}
    assert res.meta.request_id
    assert res.meta.timestamp


def test_error_response_shape():
    res = error_response(code="VALIDATION_ERROR", message="bad field", field="email")
    assert res.success is False
    assert res.error.code == "VALIDATION_ERROR"
    assert res.error.field == "email"
