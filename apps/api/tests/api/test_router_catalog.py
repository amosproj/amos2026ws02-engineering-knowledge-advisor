from services.catalog.service import get_machine_status


def test_the_machine_status_is_the_most_urgent_file_status():
    assert get_machine_status([]) == "empty"
    assert get_machine_status(["ready", "ready"]) == "ready"
    assert get_machine_status(["ready", "failed"]) == "failed"
    assert get_machine_status(["failed", "processing", "ready"]) == "processing"
    assert get_machine_status(["processing", "uploading"]) == "uploading"
