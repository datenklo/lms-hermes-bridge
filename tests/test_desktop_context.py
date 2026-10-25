from lms_hermes_bridge.desktop_context import ContextError, image_data


def test_image_data_encodes_supported_mime():
    image = image_data(b"png-bytes", "image/png", "shot.png")
    assert image["mime"] == "image/png" and image["name"] == "shot.png"
    assert image["data"] == "cG5nLWJ5dGVz"


def test_image_data_rejects_non_image_and_oversized():
    try:
        image_data(b"x", "text/plain")
    except ContextError:
        pass
    else:
        raise AssertionError("non-image content was accepted")
    try:
        image_data(b"x" * (16 * 1024 * 1024 + 1), "image/png")
    except ContextError:
        pass
    else:
        raise AssertionError("oversized image was accepted")
