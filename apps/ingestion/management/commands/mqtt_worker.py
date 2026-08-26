from django.core.management.base import BaseCommand
from django.db import close_old_connections, connections

from apps.ingestion.mqtt_client import MqttIngestionClient


class Command(BaseCommand):
    help = "Lance le worker MQTT"

    def handle(self, *args, **kwargs):
        self.stdout.write(
            self.style.SUCCESS("MQTT worker démarré")
        )

        # Ferme les anciennes connexions avant de démarrer le worker.
        close_old_connections()

        client = MqttIngestionClient()

        try:
            client.start()

        finally:
            # Si le worker s'arrête, on ferme toutes les connexions restantes.
            connections.close_all()