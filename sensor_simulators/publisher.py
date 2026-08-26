import json
import paho.mqtt.client as mqtt


class MqttPublisher:
    def __init__(self, host="localhost", port=1883):
        self.client = mqtt.Client()
        self.host = host
        self.port = port

    def connect(self):
        self.client.connect(self.host, self.port, 60)

    def publish(self, topic, payload):
        self.client.publish(
            topic,
            json.dumps(payload)
        )
        print("Publié :", topic)
        print(payload)

    def disconnect(self):
        self.client.disconnect()