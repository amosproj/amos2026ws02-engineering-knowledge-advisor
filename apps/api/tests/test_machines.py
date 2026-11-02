import base64
import json

import pytest

from model.machine import STEP_FILE_MAX_SIZE
from storage.s3 import create_upload_form


def test_upload_form_pins_key_and_exact_size():
    url, fields = create_upload_form("machines/abc/source.step", 1234)

    policy = json.loads(base64.b64decode(fields["policy"]))
    assert url == "/storage/test"
    assert fields["key"] == "machines/abc/source.step"
    assert ["content-length-range", 1234, 1234] in policy["conditions"]
    assert {"bucket": "test"} in policy["conditions"]
    assert {"key": "machines/abc/source.step"} in policy["conditions"]


@pytest.mark.parametrize(
    "override",
    [
        {"name": "   "},
        {"filename": "machine.stl"},
        {"size": 0},
        {"size": STEP_FILE_MAX_SIZE + 1},
    ],
)
def test_create_machine_rejects_invalid_request(client, override):
    body = {"name": "Press", "filename": "press.STEP", "size": 10} | override

    response = client.post("/api/v1/machines", json=body)

    assert response.status_code == 422
