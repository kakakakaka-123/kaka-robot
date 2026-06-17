from kaka_core import notifications
from kaka_core.notifications import unified_service


def test_notification_package_exports_unified_service_entrypoint() -> None:
    assert notifications.deliver_notification is unified_service.deliver_notification
    assert notifications.NotificationDeliveryError is unified_service.NotificationDeliveryError
