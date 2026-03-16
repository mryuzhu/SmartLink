from __future__ import annotations

import threading
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover
    mqtt = None

try:
    import serial
except ImportError:  # pragma: no cover
    serial = None


class IntegrationManager:
    def __init__(self, config_manager, action_service, logger) -> None:
        self.config_manager = config_manager
        self.action_service = action_service
        self.logger = logger
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []
        self.status_info = {
            "mqtt": {"connected": False, "enabled": False, "last_error": ""},
            "card_reader": {"enabled": False, "alive": False, "last_error": "", "last_card_id": ""},
        }

    def start(self) -> None:
        self._start_card_reader()
        self._start_mqtt_listener()

    def stop(self) -> None:
        self.stop_event.set()

    def status(self) -> dict:
        return self.status_info

    def _start_card_reader(self) -> None:
        if serial is None:
            self.status_info["card_reader"]["last_error"] = "pyserial 未安装"
            return

        def worker() -> None:
            while not self.stop_event.is_set():
                settings = self.config_manager.get_settings()
                self.status_info["card_reader"]["enabled"] = settings.enable_card_reader
                if not settings.enable_card_reader:
                    time.sleep(1)
                    continue
                try:
                    with serial.Serial(settings.serial_port, 9600, timeout=1) as ser:
                        self.status_info["card_reader"]["alive"] = True
                        while not self.stop_event.is_set():
                            card_id = ser.readline().decode(errors="ignore").strip()
                            if not card_id:
                                time.sleep(0.2)
                                continue
                            self.status_info["card_reader"]["last_card_id"] = card_id
                            for action in self.action_service.list_actions():
                                if card_id in action.card_ids:
                                    self.logger.info(
                                        "card matched action=%s card_id=%s", action.name, card_id
                                    )
                                    self.action_service.run_action_async(action.name, source="card")
                                    break
                except Exception as exc:  # pragma: no cover
                    self.status_info["card_reader"]["alive"] = False
                    self.status_info["card_reader"]["last_error"] = str(exc)
                    self.logger.warning("card reader loop error: %s", exc)
                    time.sleep(3)

        thread = threading.Thread(target=worker, daemon=True, name="card-reader")
        thread.start()
        self.threads.append(thread)

    def _start_mqtt_listener(self) -> None:
        if mqtt is None:
            self.status_info["mqtt"]["last_error"] = "paho-mqtt 未安装"
            return

        def worker() -> None:
            while not self.stop_event.is_set():
                settings = self.config_manager.get_settings()
                topics = {
                    action.bafy_topic
                    for action in self.action_service.list_actions()
                    if action.bafy_topic
                }
                self.status_info["mqtt"]["enabled"] = bool(settings.bafy_uid and topics)
                if not settings.bafy_uid or not topics:
                    time.sleep(5)
                    continue
                client = mqtt.Client(client_id=settings.bafy_uid)

                def on_connect(
                    bound_client, _userdata, _flags, rc, _props=None, *, bound_topics=topics
                ):
                    self.status_info["mqtt"]["connected"] = rc == 0
                    for topic in bound_topics:
                        bound_client.subscribe(topic)

                def on_message(_client, _userdata, msg):
                    payload = msg.payload.decode(errors="ignore")
                    for action in self.action_service.list_actions():
                        if action.bafy_topic != msg.topic:
                            continue
                        brightness_value = None
                        if action.type == "brightness":
                            text = payload.removeprefix("on#")
                            if text.isdigit():
                                brightness_value = int(text)
                        self.action_service.run_action_async(
                            action.name,
                            brightness_value=brightness_value,
                            source="mqtt",
                        )
                        break

                client.on_connect = on_connect
                client.on_message = on_message
                try:
                    client.connect("bemfa.com", 9501, 60)
                    client.loop_forever()
                except Exception as exc:  # pragma: no cover
                    self.status_info["mqtt"]["connected"] = False
                    self.status_info["mqtt"]["last_error"] = str(exc)
                    self.logger.warning("mqtt loop error: %s", exc)
                    time.sleep(5)

        thread = threading.Thread(target=worker, daemon=True, name="mqtt-listener")
        thread.start()
        self.threads.append(thread)
