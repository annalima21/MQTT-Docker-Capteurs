from django import forms

from .models import Capteur


class CapteurForm(forms.ModelForm):
    """Formulaire simple pour créer ou modifier un capteur."""

    class Meta:
        model = Capteur
        fields = [
            "site",
            "type_capteur",
            "identifiant",
            "nom",
            "actif",
            "firmware_version",
            "date_installation",
            "config_json",
        ]
        widgets = {
            "date_installation": forms.DateInput(attrs={"type": "date"}),
            "config_json": forms.Textarea(attrs={"rows": 4}),
        }
