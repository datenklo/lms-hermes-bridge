from lms_hermes_bridge.tray import Tray


def test_menu_item_has_blue_update_icon_only_when_update_exists():
    available = {"yes": False}
    tray = Tray(lambda: None, [
        (lambda: "Check updates", lambda: None,
         lambda: "update-available" if available["yes"] else None),
    ])
    props = tray._item(1).unpack()[1]
    assert props["label"] == "Check updates" and "icon-name" not in props
    available["yes"] = True
    props = tray._item(1).unpack()[1]
    assert props["icon-name"] == "update-available"
